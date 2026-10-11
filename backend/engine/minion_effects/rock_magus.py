"""Rock Magus attack and Empower mechanics.

Ability coefficients and timing come from the current canonical SS13 skill data.
Growth stages and shared Spirit Magus pools use the helpers in minion_offense.
"""
from dataclasses import asdict, replace
from math import floor

from engine.models import SourceEntry

OWNER_ID = "summon_rock_magus"

_ROLE_TAGS = {"base skill": "Base", "enhanced skill": "Enhanced", "empower": "Empower", "ultimate": "Ultimate"}


def _whole_attack_speed_percent_steps(attack_speed_inc: float) -> int:
    # Whole percentage points only; compensate for binary representations such as 0.29 * 100.
    return floor(max(0.0, attack_speed_inc) * 100.0 + 1e-9)


def _role(ability: dict) -> str:
    tags = {str(tag).lower() for tag in (ability.get("skill_tags") or [])}
    return next((role for tag, role in _ROLE_TAGS.items() if tag in tags), "")


def handler(source, owner, base_stats, level, count, *, condition_state=None):
    from engine.minion_offense import (
        ability_label,
        calculate_minion_offense,
        combine_minion_forms,
        fold_spirit_magi_pools,
        growth_stage,
        nyi_offense,
        spirit_magi_growth,
    )
    from engine.skill_resolver import _parse_cast_time

    abilities = {_role(skill): skill for skill in owner.get("minion_skills") or []}
    conditions = (condition_state if condition_state is not None
                  else getattr(source, "condition_state", {})) or {}

    def enemy_weight() -> float:
        explicit = conditions.get("enemy_count_weight")
        if explicit is not None:
            return max(1.0, float(explicit))
        return 1.0  # owner default: normal enemy

    # The existing Enemy selector encodes Normal/Magic=1, Rare=2, Boss=5.
    is_boss = enemy_weight() >= 5.0
    growth = spirit_magi_growth(source)
    stage = growth_stage(growth)
    enhanced_chance = max(0.0, min(1.0, source.total("spirit_magi_enhanced_skill_chance")
                                 + (0.30 if stage >= 2 else 0.0)))
    # Owner's single unverified check at 18% Enhanced chance: roughly 120 in-game DPS vs 108
    # in the engine (baseline 90 in game vs 85 in the engine), suggesting fast-insert F ~= 0.17.
    # One point is not enough to fit Rock's cadence; leave that Thunder-calibrated mechanic out
    # until more measurements exist.

    buffed = replace(source, _entries=list(source._entries), source_log=list(source.source_log))
    fold_spirit_magi_pools(buffed, growth)

    def add(stat: str, amount: float, text: str) -> None:
        if amount:
            buffed.add_with_source(stat, amount, SourceEntry(
                stat=stat, amount=amount, source_type="minion", label="Rock Magus",
                source_name="Rock Magus", text=text,
            ))

    # Growth Stage 5 damage is shared by every Spirit Magus ability.
    if stage >= 5:
        add("minion_dmg_additional", 0.50, "Growth Stage 5: +50% additional damage")

    # Iris-selected skills do not run the Magus's normal Empower rotation, so per-cast
    # values use the persistent Spirit Magus stats before Gold Rush uptime is folded in.
    cast_source = replace(buffed, _entries=list(buffed._entries), source_log=list(buffed.source_log))

    empower = abilities.get("Empower")
    empower_uptime = 0.0
    cast_slot_factor = 1.0
    empower_display = None
    if empower:
        duration_base = float(empower.get("duration") or 0.0)
        cooldown_base = _parse_cast_time(empower.get("cooldown", "")) or 0.0
        cast_time = _parse_cast_time(empower.get("cast_speed", "")) or 0.0
        if conditions.get("_engine_harvest_time_linked"):
            cast_time = 0.0
        duration_inc = source.total("minion_skill_effect_duration_inc")
        cdr_inc = source.total("minion_cdr_speed_inc") + source.total("spirit_magi_cdr_speed_inc")
        duration = duration_base * (1.0 + duration_inc)
        cooldown = cooldown_base / (1.0 + cdr_inc) if cooldown_base else 0.0
        empower_uptime = min(1.0, duration / cooldown) if duration > 0 and cooldown > 0 else 0.0
        if conditions.get("_engine_iris_merged") and not conditions.get("_engine_iris_spam_empower", True):
            empower_uptime = 0.0
        # The existing boss condition is represented by the current target's enemy count weight.
        # In the absence of a boss target, the documented normal-enemy default is one.
        empower_effect = 1.0 + source.total("spirit_magi_empower_effect_additional")
        if stage >= 4 and is_boss:
            empower_effect += 1.20
        affected = min(10.0, enemy_weight())
        add("minion_dmg_additional", 0.06 * affected * empower_effect * empower_uptime,
            f"Gold Rush: +6% additional damage per affected enemy × {affected:g}, "
            f"{empower_uptime:.0%} uptime")
        add("minion_movement_speed_inc", 0.03 * affected * empower_effect * empower_uptime,
            f"Gold Rush: +3% Movement Speed per affected enemy × {affected:g}, "
            f"{empower_uptime:.0%} uptime")
        # Match Thunder Magus: Empower is cast as soon as ready and occupies part of the attack cycle.
        if cast_time > 0 and cooldown > 0:
            cast_slot_factor = max(0.0, 1.0 - 0.5 * cast_time / cooldown)
        empower_display = {
            "name": ability_label(empower), "empower_effect": empower_effect,
            "base_cooldown": cooldown_base, "cooldown": cooldown,
            "base_duration": duration_base, "duration": duration,
            "cdr_inc": cdr_inc, "duration_inc": duration_inc,
            "uptime": empower_uptime,
            "cast_slot_factor": cast_slot_factor,
            "buffs": [{"label": "Damage", "stat": "damage",
                       "base": 0.06 * affected * empower_effect,
                       "value": 0.06 * affected * empower_effect * empower_uptime,
                       "active": True}],
        }

    results = []
    skill_casts = {}
    skill_forms = {}

    def record_cast(role, skill, offense, *, source_for_cast=buffed, hits=None):
        if not skill:
            return
        from engine.minion_offense import _speed_add_product
        cast_time_base = _parse_cast_time(skill.get("cast_speed", "")) or 0.0
        cooldown_base = _parse_cast_time(skill.get("cooldown", "")) or 0.0
        tags = {str(tag).lower() for tag in (skill.get("skill_tags") or [])}
        speed_kind = "attack" if "attack" in tags else "cast"
        speed_inc_key = "minion_attack_speed_inc" if speed_kind == "attack" else "minion_cast_speed_inc"
        speed_add_key = "minion_attack_speed_additional" if speed_kind == "attack" else "minion_cast_speed_additional"
        speed_factor = (1.0 + source.total(speed_inc_key)) * _speed_add_product(source_for_cast, speed_add_key)
        cast_time = cast_time_base / speed_factor if cast_time_base and speed_factor > 0 else 0.0
        if role == "Empower" and conditions.get("_engine_harvest_time_linked"):
            cast_time = 0.0
        cdr_inc = source.total("minion_cdr_speed_inc") + source.total("spirit_magi_cdr_speed_inc")
        cooldown = cooldown_base / (1.0 + cdr_inc) if cooldown_base else 0.0
        rate = 1.0 / max(cast_time, cooldown) if max(cast_time, cooldown) > 0 else 0.0
        hit_form = offense.hit_forms[0] if offense and offense.hit_forms else None
        skill_casts[role.lower()] = {
            "name": ability_label(skill), "role": role,
            "damage_per_cast": hit_form.avg_hit_with_crit * (hits or hit_form.hits_per_fire) if hit_form else 0.0,
            "damage_per_cast_vs_target": (hit_form.dps_vs_target / hit_form.fires_per_sec)
                if hit_form and hit_form.fires_per_sec > 0 else 0.0,
            "hits_per_cast": hits or (hit_form.hits_per_fire if hit_form else 0),
            "base_cast_time": cast_time_base, "cast_time": cast_time,
            "base_cooldown": cooldown_base, "cooldown": cooldown,
            "casts_per_second": rate, "included_in_default_dps": False,
        }

    base = abilities.get("Base")
    enhanced = abilities.get("Enhanced")
    if base:
        base_cast_result = calculate_minion_offense(cast_source, base, base_stats, level, count)
        skill_forms["base skill"] = base_cast_result
        record_cast("Base", base, base_cast_result, source_for_cast=cast_source)
        results.append(calculate_minion_offense(
            buffed, base, base_stats, level,
            rate_multiplier=(1.0 - enhanced_chance) * cast_slot_factor,
        ))
    if enhanced:
        enhanced_source = replace(cast_source, _entries=list(cast_source._entries), source_log=list(cast_source.source_log))
        enhanced_rotation_source = replace(
            buffed, _entries=list(buffed._entries), source_log=list(buffed.source_log),
        )
        if stage >= 3:
            # Rock Blast's per-enemy damage uses the same weighted enemy count as Gold Rush.
            per_enemy = min(8.0, enemy_weight())
            enhanced_source.add_with_source("minion_dmg_additional", 0.035 * per_enemy, SourceEntry(
                stat="minion_dmg_additional", amount=0.035 * per_enemy,
                source_type="minion", label="Rock Blast", source_name="Rock Blast",
                text=f"Rock Blast: +3.5% additional damage per enemy within 8 m × {per_enemy:g}",
            ))
            enhanced_rotation_source.add_with_source("minion_dmg_additional", 0.035 * per_enemy, SourceEntry(
                stat="minion_dmg_additional", amount=0.035 * per_enemy,
                source_type="minion", label="Rock Blast", source_name="Rock Blast",
                text=f"Rock Blast: +3.5% additional damage per enemy within 8 m × {per_enemy:g}",
            ))
        enhanced_cast = calculate_minion_offense(enhanced_source, enhanced, base_stats, level,
                                                  shotgun_hits=3, shotgun_falloff=0.0)
        enhanced_merged_cast = calculate_minion_offense(
            enhanced_rotation_source, enhanced, base_stats, level, count,
            shotgun_hits=3, shotgun_falloff=0.0,
        )
        skill_forms["enhanced skill"] = enhanced_merged_cast
        record_cast("Enhanced", enhanced, enhanced_cast, source_for_cast=enhanced_source, hits=3)
        results.append(calculate_minion_offense(
            enhanced_rotation_source, enhanced, base_stats, level,
            rate_multiplier=enhanced_chance * cast_slot_factor,
            shotgun_hits=3, shotgun_falloff=0.0,
        ))

    if empower:
        record_cast("Empower", empower, None)
        buff_form = nyi_offense(empower, level)
        buff_form.nyi = [f"Gold Rush is an Empower buff folded into attacks at {empower_uptime:.0%} uptime."]
        results.append(buff_form)

    ultimate = abilities.get("Ultimate")
    ultimate_summary = None
    if ultimate:
        from engine.minion_offense import _speed_add_product

        ultimate_source = replace(cast_source, _entries=list(cast_source._entries), source_log=list(cast_source.source_log))
        ultimate_inc = source.total("spirit_magi_ultimate_dmg_inc")
        ultimate_add = source.total("spirit_magi_ultimate_dmg_additional")
        if ultimate_inc:
            ultimate_source.add_with_source("minion_dmg_inc", ultimate_inc, SourceEntry(
                stat="minion_dmg_inc", amount=ultimate_inc, source_type="minion",
                label="Ultimate Skill Damage", source_name="Ultimate Skill Damage",
                text="Spirit Magus Ultimate Damage Increased",
            ))
        if ultimate_add:
            ultimate_source.add_with_source("minion_dmg_additional", ultimate_add, SourceEntry(
                stat="minion_dmg_additional", amount=ultimate_add, source_type="minion",
                label="Ultimate Skill Damage", source_name="Ultimate Skill Damage",
                text="Spirit Magus Ultimate Damage Additional",
            ))
        attack_speed_inc = source.total("minion_attack_speed_inc")
        attack_speed_add = source.total("minion_attack_speed_additional")
        # Full Bloom transfers 50% of both Spirit Magus Attack Speed pools to Ultimate Attack Damage.
        ultimate_source.add_with_source("minion_dmg_additional", 0.5 * (attack_speed_inc + attack_speed_add),
                                        SourceEntry(
            stat="minion_dmg_additional", amount=0.5 * (attack_speed_inc + attack_speed_add),
            source_type="minion", label="Full Bloom", source_name="Full Bloom",
            text="Full Bloom: 50% of Attack Speed bonuses apply as additional Ultimate Attack Damage",
        ))
        # SS13: +0.2% Ultimate additional damage for each whole +1% increased Attack Speed.
        attack_speed_steps = _whole_attack_speed_percent_steps(attack_speed_inc)
        attack_speed_damage = attack_speed_steps * 0.002
        if attack_speed_damage:
            ultimate_source.add_with_source("minion_dmg_additional", attack_speed_damage, SourceEntry(
                stat="minion_dmg_additional", amount=attack_speed_damage,
                source_type="minion", label="Towering Mountains", source_name="Towering Mountains",
                text=f"Towering Mountains: +0.2% additional damage per whole 1% minion Attack Speed × {attack_speed_steps}",
            ))
        ultimate_count_bonus = min(8.0, enemy_weight())
        ultimate_source.add_with_source("minion_dmg_additional", 0.05 * ultimate_count_bonus, SourceEntry(
            stat="minion_dmg_additional", amount=0.05 * ultimate_count_bonus,
            source_type="minion", label="Towering Mountains", source_name="Towering Mountains",
            text=f"Towering Mountains: +5% additional damage per enemy × {ultimate_count_bonus:g}",
        ))
        ultimate_speed_add = source.total("minion_ultimate_attack_speed_additional")
        ultimate_time = _parse_cast_time(ultimate.get("cast_speed", "")) or 0.0
        ultimate_cooldown_base = _parse_cast_time(ultimate.get("cooldown", "")) or 0.0
        ultimate_speed_factor = ((1.0 + attack_speed_inc)
                                 * _speed_add_product(ultimate_source, "minion_attack_speed_additional")
                                 * (1.0 + ultimate_speed_add))
        effective_cast_time = ultimate_time / ultimate_speed_factor if ultimate_time and ultimate_speed_factor > 0 else 0.0
        ultimate_cdr = source.total("minion_cdr_speed_inc") + source.total("spirit_magi_cdr_speed_inc")
        effective_cooldown = (ultimate_cooldown_base / (1.0 + ultimate_cdr)
                              if ultimate_cooldown_base and 1.0 + ultimate_cdr > 0 else 0.0)
        if conditions.get("whirlwind_tango_merged"):
            effective_cooldown = 0.0
        ultimate_interval = max(effective_cast_time, effective_cooldown)
        ultimate_rate = 1.0 / ultimate_interval if ultimate_interval > 0 else 0.0
        ultimate_result = calculate_minion_offense(
            ultimate_source, ultimate, base_stats, level, 1, shotgun_hits=2, shotgun_falloff=0.0,
        )
        natural_rate = ultimate_result.skills_per_second
        rate_scale = ultimate_rate / natural_rate if natural_rate > 0 else 0.0
        ultimate_result.skills_per_second = ultimate_rate
        ultimate_result.total_dps *= rate_scale
        ultimate_result.total_dps_vs_target *= rate_scale
        ultimate_result.base_cast_time = ultimate_time
        for form in ultimate_result.hit_forms:
            form.fires_per_sec = ultimate_rate
            form.dps_contribution *= rate_scale
            form.dps_vs_target *= rate_scale
        for row in ultimate_result.damage_rows:
            row.dps_final *= rate_scale
            row.dps_vs_target_final *= rate_scale
            row.dps_by_type_vs_target = {
                dtype: value * rate_scale for dtype, value in row.dps_by_type_vs_target.items()
            }
            row.pct_of_total = 100.0 if ultimate_result.total_dps_vs_target > 0 else 0.0
        ultimate_result.multistrike_repeat_aps *= rate_scale
        if ultimate_result.hit_forms:
            per_cast = ultimate_result.hit_forms[0]
            ultimate_summary = {
                "name": ability_label(ultimate),
                "damage_per_cast": per_cast.avg_hit_with_crit * per_cast.hits_per_fire,
                "damage_per_cast_vs_target": per_cast.dps_vs_target / per_cast.fires_per_sec
                if per_cast.fires_per_sec > 0 else 0.0,
                "hits_per_cast": 2,
                "base_cast_time": ultimate_time,
                "cast_time": effective_cast_time,
                "base_cooldown": ultimate_cooldown_base,
                "cooldown": effective_cooldown,
                "casts_per_second": ultimate_rate,
                "included_in_default_dps": False,
            }
        # Keep the exposed form's rate and cooldown identical to the Ultimate summary,
        # including the zero-rate case and Whirlwind Tango's zero cooldown.
        if ultimate_summary is None:
            record_cast("Ultimate", ultimate, ultimate_result, source_for_cast=ultimate_source, hits=2)
        else:
            from engine.compute import _source_log_stat_map

            ultimate_result.minion_ultimate = ultimate_summary
            ultimate_breakdown = asdict(ultimate_result)
            ultimate_breakdown["stat_map"] = _source_log_stat_map(ultimate_source)
            skill_casts["ultimate"] = {
                **ultimate_summary,
                "role": "Ultimate",
                "hit_breakdown": ultimate_breakdown,
            }
        skill_forms["ultimate"] = ultimate_result
    combined = combine_minion_forms(owner.get("name") or "Rock Magus", results, count)
    combined.spirit_magi_growth = growth
    combined.spirit_magi_stage = stage
    combined.spirit_magi_enhanced_chance = enhanced_chance
    combined.spirit_magi_max = count
    combined.minion_empower = empower_display
    combined.minion_ultimate = ultimate_summary
    combined.minion_skill_casts = skill_casts
    combined.minion_skill_forms = skill_forms
    return combined
