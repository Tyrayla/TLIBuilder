"""Erosion Magus damage forms, based on the canonical Spirit Magus skill data."""
from dataclasses import replace

from engine.models import SourceEntry

OWNER_ID = "summon_erosion_magus"
_ROLE_TAGS = {"base skill": "Base", "enhanced skill": "Enhanced", "empower": "Empower", "ultimate": "Ultimate"}


def _role(ability: dict) -> str:
    tags = {str(tag).lower() for tag in (ability.get("skill_tags") or [])}
    return next((role for tag, role in _ROLE_TAGS.items() if tag in tags), "")


def handler(source, owner, base_stats, level, count, *, condition_state=None):
    from engine.minion_offense import (
        _speed_add_product, ability_label, calculate_minion_offense, combine_minion_forms, fold_spirit_magi_pools,
        growth_stage, nyi_offense, spirit_magi_growth, spirit_magi_physique_inc, spirit_magi_skill_area_inc,
    )
    from engine.skill_resolver import _parse_cast_time

    by_role = {}
    for ability in owner.get("minion_skills") or []:
        by_role.setdefault(_role(ability), ability)

    growth = spirit_magi_growth(source)
    stage = growth_stage(growth)
    chance = min(1.0, max(0.0, source.total("spirit_magi_enhanced_skill_chance") + (0.30 if stage >= 2 else 0.0)))
    working = replace(source, _entries=list(source._entries), source_log=list(source.source_log))
    fold_spirit_magi_pools(working, growth)

    def add(stat: str, amount: float, text: str, label: str = "Erosion Magus") -> None:
        if amount:
            working.add_with_source(stat, amount, SourceEntry(
                stat=stat, amount=amount, source_type="minion", label=label, source_name=label, text=text))

    if stage >= 5:
        add("minion_dmg_additional", 0.50, "Growth Stage 5: +50% additional damage", "Growth")

    empower = by_role.get("Empower")
    empower_uptime = 0.0
    empower_display = None
    empower_effect = 1.0
    ultimate_buff = 0.0
    if empower:
        duration = float(empower.get("duration") or 0.0) * (1.0 + source.total("minion_skill_effect_duration_inc"))
        base_cd = _parse_cast_time(empower.get("cooldown", "")) or 0.0
        empower_cdr = (source.total("minion_cdr_speed_inc")
                       + source.total("spirit_magi_cdr_speed_inc"))
        cooldown = base_cd / max(1.0 + empower_cdr, 1e-9) if base_cd > 0 else 0.0
        empower_uptime = min(1.0, duration / cooldown) if duration > 0 and cooldown > 0 else 0.0
        raw_enemy_weight = (condition_state or {}).get("enemy_count_weight")
        enemy_weight = float(1.0 if raw_enemy_weight is None else raw_enemy_weight)
        boss = enemy_weight == 5.0
        empower_effect = 1.0 + source.total("spirit_magi_empower_effect_additional") + (1.20 if boss and stage >= 4 else 0.0)
        erosion_buff = 0.20 * empower_effect * empower_uptime
        ultimate_buff = 0.50 * empower_effect * empower_uptime if stage >= 4 else 0.0
        # All Erosion Magus hits are Erosion after intrinsic conversion, so the generic minion
        # additional-damage pool is type-equivalent here and is already consumed by the engine.
        add("minion_dmg_additional", erosion_buff,
            f"Withering Payback: +20% additional Erosion Damage × {empower_effect:.3g} Empower Effect × {empower_uptime:.0%} uptime",
            "Withering Payback")
        empower_display = {
            "name": ability_label(empower), "empower_effect": empower_effect,
            "empower_effect_inc": empower_effect - 1.0, "base_cooldown": base_cd, "cooldown": cooldown,
            "base_duration": float(empower.get("duration") or 0.0), "duration": duration,
            "uptime": empower_uptime,
            "buffs": [{"label": "Erosion Damage", "stat": "erosion_damage", "base": 0.20,
                       "value": erosion_buff, "active": True},
                      {"label": "Ultimate Damage", "stat": "ultimate_damage", "base": 0.50,
                       "value": ultimate_buff, "active": stage >= 4,
                       "note": "Growth Stage 4+ while Empower lasts"}],
        }

    results = []
    empower_base_time = _parse_cast_time(empower.get("cast_speed", "")) if empower else 0.0
    harvest_time_linked = any(
        entry.source_type == "support"
        and any(str(value or "").strip().casefold() == "harvest time"
                for value in (entry.label, entry.source_name))
        for entry in source.source_log)
    empower_time = 0.0 if harvest_time_linked else empower_base_time
    base = by_role.get("Base")
    enhanced = by_role.get("Enhanced")
    if base:
        results.append(calculate_minion_offense(
            working, base, base_stats, level, count, rate_multiplier=(1.0 - chance),
            intrinsic_convert={"physical": {"erosion": 1.0}}, apply_cooldown_recovery_to_rate=True))
    if enhanced:
        extra_spike_selected = bool((condition_state or {}).get("erosion_stage4_extra_spike", False))
        spikes = 2 + (empower_uptime if stage >= 4 and extra_spike_selected else 0.0)
        results.append(calculate_minion_offense(
            working, enhanced, base_stats, level, count, rate_multiplier=chance,
            shotgun_hits=spikes, shotgun_falloff=0.0,
            intrinsic_convert={"physical": {"erosion": 1.0}}, apply_cooldown_recovery_to_rate=True))
    if empower:
        result = nyi_offense(empower, level)
        result.nyi = ["Withering Payback is modeled as a buff at its duration/cooldown uptime; its damage-triggered cast is intentionally ignored."]
        results.append(result)

    ultimate = by_role.get("Ultimate")
    if ultimate:
        ultimate_source = replace(working, _entries=list(working._entries), source_log=list(working.source_log))
        # These pools are read by the Ultimate's formula now; their generic engine consumption is a separate task.
        for stat, amount in (
            ("minion_dmg_inc", source.total("spirit_magi_ultimate_dmg_inc")),
            ("minion_dmg_additional", source.total("spirit_magi_ultimate_dmg_additional")),
        ):
            if amount:
                ultimate_source.add_with_source(stat, amount, SourceEntry(
                    stat=stat, amount=amount, source_type="minion", label="Spirit Magus Ultimate",
                    source_name="Spirit Magus Ultimate", text="Spirit Magus Ultimate damage pool"))
        if ultimate_buff:
            ultimate_source.add_with_source("minion_dmg_additional", ultimate_buff, SourceEntry(
                stat="minion_dmg_additional", amount=ultimate_buff, source_type="minion",
                label="Withering Payback", source_name="Withering Payback",
                text="Withering Payback: +50% additional Ultimate Damage at Growth Stage 4+"))
        result = calculate_minion_offense(
            ultimate_source, ultimate, base_stats, level, count, rate_multiplier=0.0,
            intrinsic_convert={"physical": {"erosion": 1.0}}, apply_cooldown_recovery_to_rate=True)
        if result.hit_forms:
            ultimate_form = result.hit_forms[0]
            cast_speed = ((1.0 + ultimate_source.total("minion_cast_speed_inc"))
                          * _speed_add_product(ultimate_source, "minion_cast_speed_additional")
                          * _speed_add_product(ultimate_source, "minion_ultimate_cast_speed_additional"))
            ultimate_form.effective_cast_time = ultimate_form.base_cast_time / max(cast_speed, 1e-9)
            cdr = (ultimate_source.total("minion_cdr_speed_inc")
                   + ultimate_source.total("spirit_magi_cdr_speed_inc"))
            ultimate_form.effective_cooldown = ultimate_form.base_cooldown / max(1.0 + cdr, 1e-9)
        result.nyi = [
            "Per-cast Ultimate form only. It is excluded from default DPS until a selecting Iris trait or trigger dispatcher consumes it.",
            "World of Thorns per-cast damage uses uptime-averaged Empower bonuses; it assumes casts sample the Empower window in proportion to its uptime (event phase is not simulated).",
        ]
        for ultimate_form in result.hit_forms:
            ultimate_form.nyi = list(result.nyi)
        results.append(result)

    combined = combine_minion_forms(owner.get("name") or "Erosion Magus", results, count)
    if empower:
        empower_form = next((form for form in combined.hit_forms if form.name == ability_label(empower)), None)
        if empower_form:
            empower_form.base_cast_time = empower_base_time
            empower_form.base_cooldown = base_cd
            empower_form.effective_cast_time = empower_time / max(
                (1.0 + working.total("minion_cast_speed_inc"))
                * _speed_add_product(working, "minion_cast_speed_additional"), 1e-9)
            empower_form.effective_cooldown = cooldown
    combined.spirit_magi_growth = growth
    combined.spirit_magi_stage = stage
    combined.spirit_magi_physique_inc = spirit_magi_physique_inc(source, growth)
    combined.skill_area_inc = spirit_magi_skill_area_inc(stage)
    combined.spirit_magi_enhanced_chance = chance
    combined.spirit_magi_max = count
    combined.minion_empower = empower_display
    if stage >= 4:
        combined.nyi.append("Stage 4 extra Bleak Grass spike is OWNER TO CONFIRM; enable erosion_stage4_extra_spike to model one full-damage recast during Withering Payback uptime, with no added cast time or damage penalty.")
    if stage >= 3:
        combined.nyi.append("Bleak Grass's Stage 3+ temporary Erosion Damage Taken stacks are not yet time-weighted against the target.")
    return combined
