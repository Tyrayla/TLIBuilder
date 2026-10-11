"""Iris (The Forsaken) — Vigilant Breeze trait mechanics.

Damage contributions and the user-set Breeze state are handled here. Reconjuring
cycle math and merged-skill dispatch live in small pure helpers so minion modules
can consume them without making Ultimate forms part of default DPS.
"""
from __future__ import annotations

TRAIT_ID = "vigilant_breeze"

_SLOT_BASE, _SLOT_45, _SLOT_60, _SLOT_75 = 0, 1, 2, 3
_BASE_DMG_ADD = (0.0, 0.05, 0.10, 0.15, 0.20)
_WHIRLWIND_LIFE_COST = (0.10, 0.09, 0.08, 0.07, 0.06)
_WHIRLWIND_BREEZE = (2, 3, 3, 4, 4)
_WHIRLWIND_SKILL_DMG = {"SS12": -0.40, "SS13": -0.60}
_WHISPER_HEAL = (0.025, 0.03, 0.035, 0.04, 0.05)
_WHISPER_INTERVAL = (0.9, 0.5, 0.2, 0.1, 0.03)
_WHISPER_MAX = (4, 5, 6, 7, 8)
_REUNION_DMG = (0.01, 0.02, 0.03, 0.04, 0.05)
_REUNION_DRAIN = (0.08, 0.07, 0.07, 0.06, 0.06)
_WARMEST_STEP = (0.05, 0.045, 0.041, 0.038, 0.035)
_WARMEST_CAP = (15, 17, 19, 21, 23)
_STREAM_ORIGIN = (0.001, 0.0015, 0.002, 0.0025, 0.003)
_NURTURE_DMG_TAKEN = (-0.20, -0.24, -0.28, -0.32, -0.36)
_NURTURE_REGEN_SHARE = (0.50, 0.60, 0.70, 0.80, 1.00)
_NURTURE_REGAIN_SHARE = (1.00, 1.20, 1.40, 1.60, 2.00)


def _enabled(slot_levels, idx):
    return idx < len(slot_levels) and int(slot_levels[idx]) > 0


def _tier(slot_levels, idx):
    level = abs(int(slot_levels[idx])) if idx < len(slot_levels) else 1
    return max(0, min(4, level - 1))


def _number(state, key, default=0.0, lo=0.0, hi=1000.0):
    try:
        value = float(state.get(key, default))
    except (TypeError, ValueError):
        value = float(default)
    return max(lo, min(hi, value))


def _pick(picks, slot_levels, name, idx):
    return _enabled(slot_levels, idx) and name in picks


def apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks, **_):
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    picks = set(advanced_picks or [])
    contributions = []
    vigilant_active = bool(condition_state.get("vigilant_breeze_active", True))
    set_conditions = {"vigilant_breeze_active": vigilant_active}

    def add(stat_key, amount, text, source="Vigilant Breeze"):
        if amount:
            contributions.append({"stat_key": stat_key, "amount": amount, "text": text, "source": source})

    if not _enabled(slot_levels, _SLOT_BASE):
        return {"contributions": [], "set_conditions": {"vigilant_breeze_active": False}}

    base_level = _tier(slot_levels, _SLOT_BASE)
    if base_level:
        add("minion_dmg_additional", _BASE_DMG_ADD[base_level],
            f"Vigilant Breeze: +{_BASE_DMG_ADD[base_level] * 100:g}% additional Minion Damage")

    count = 1.0 if vigilant_active else 0.0
    current_max = 10.0
    life_cost = 0.20
    tango_life_cost = 0.0
    tango_breeze_gain = 0
    damage_factor = 1.0

    if _pick(picks, slot_levels, "Whirlwind Tango", _SLOT_45):
        tier = _tier(slot_levels, _SLOT_45)
        season = getattr(build_input, "season", None) or "SS13"
        penalty = _WHIRLWIND_SKILL_DMG.get(season)
        if penalty is not None:
            add("spirit_magi_dmg_additional", penalty,
                f"Whirlwind Tango ({season}): {penalty * 100:g}% additional Spirit Magus Skill Damage")
        tango_life_cost = _WHIRLWIND_LIFE_COST[tier]
        tango_breeze_gain = _WHIRLWIND_BREEZE[tier]
        set_conditions["vigilant_breeze_whirlwind_tango"] = True
    else:
        set_conditions["vigilant_breeze_whirlwind_tango"] = False

    if _pick(picks, slot_levels, "Breeze's Whisper", _SLOT_45):
        tier = _tier(slot_levels, _SLOT_45)
        add("spirit_magi_enhanced_skill_chance", 0.30, "Breeze's Whisper: +30% chance for Spirit Magi to use an Enhanced Skill")
        set_conditions.update({
            "vigilant_breeze_whisper_active": True,
            "vigilant_breeze_whisper_heal_pct": _WHISPER_HEAL[tier],
            "vigilant_breeze_whisper_interval": _WHISPER_INTERVAL[tier],
        })
    else:
        set_conditions["vigilant_breeze_whisper_active"] = False

    if _pick(picks, slot_levels, "Happiest Reunion", _SLOT_60):
        tier = _tier(slot_levels, _SLOT_60)
        count = (_number(condition_state, "vigilant_breeze_total_magi", 1.0, 0.0, 5.0)
                 if vigilant_active else 0.0)
        p = _REUNION_DMG[tier]
        damage_factor = (1.0 + p) ** count
        if count > 0:
            add("spirit_magi_dmg_additional", damage_factor - 1.0,
                f"Happiest Reunion: per-Magus additional damage product (1 + {p * 100:g}%)^{count:g}")
        add("max_spirit_magi_flat", 1.0, "Happiest Reunion: +1 Max Spirit Magi in Map")
        life_cost += _REUNION_DRAIN[tier]
        set_conditions["vigilant_breeze_happiest_reunion"] = vigilant_active
        set_conditions["vigilant_breeze_merged_magi_effective"] = count
    else:
        set_conditions["vigilant_breeze_happiest_reunion"] = False
        set_conditions["vigilant_breeze_merged_magi_effective"] = count

    if _pick(picks, slot_levels, "Warmest Vigilance", _SLOT_60):
        tier = _tier(slot_levels, _SLOT_60)
        spent = _number(condition_state, "vigilant_breeze_life_consumed_pct", 0.0)
        defeated = _number(condition_state, "vigilant_breeze_enemies_defeated", 0.0)
        spent_bp = int(round(spent * 100.0))
        step_bp = int(round(_WARMEST_STEP[tier] * 10_000.0))
        bonus = min(_WARMEST_CAP[tier], spent_bp // step_bp)
        current_max += bonus
        set_conditions["vigilant_breeze_warmest_bonus_stacks"] = bonus
        set_conditions["vigilant_breeze_warmest_defeated_stacks"] = defeated
        set_conditions["vigilant_breeze_warmest_active"] = True
    else:
        set_conditions["vigilant_breeze_warmest_active"] = False

    if _pick(picks, slot_levels, "Merging Stream", _SLOT_75) and vigilant_active:
        tier = _tier(slot_levels, _SLOT_75)
        set_conditions["vigilant_breeze_merging_stream"] = True
        set_conditions["vigilant_breeze_origin_effect_per_2_growth"] = _STREAM_ORIGIN[tier]
    else:
        set_conditions["vigilant_breeze_merging_stream"] = False

    if _pick(picks, slot_levels, "Nurturing Breeze", _SLOT_75):
        tier = _tier(slot_levels, _SLOT_75)
        regen_share = _NURTURE_REGEN_SHARE[tier]
        regain_share = _NURTURE_REGAIN_SHARE[tier]
        for player_stat, minion_stat, share in (
            ("life_regen_speed_inc", "minion_life_regen_speed_inc", regen_share),
            ("life_regen_inc", "minion_life_regen_inc", regen_share),
            ("life_regen_flat", "minion_life_regen_flat", regen_share),
            ("life_regain_inc", "minion_life_regain_inc", regain_share),
            ("energy_shield_regain_inc", "minion_es_regain_inc", regain_share),
            ("life_regain_interval_additional", "minion_life_regain_interval_additional", regain_share),
            ("energy_shield_regain_interval_additional", "minion_es_regain_interval_additional", regain_share),
        ):
            amount = float(ls_state.get("iris_" + player_stat, 0.0)) * share
            add(minion_stat, amount,
                f"Nurturing Breeze: {share * 100:g}% of Iris {player_stat.replace('_', ' ')} bonus copied to Magi")
        add("dmg_taken_additional", _NURTURE_DMG_TAKEN[tier],
            f"Nurturing Breeze: {_NURTURE_DMG_TAKEN[tier] * 100:g}% additional damage taken")
        set_conditions["vigilant_breeze_nurturing_regen_share"] = regen_share
        set_conditions["vigilant_breeze_nurturing_regain_share"] = regain_share
    else:
        set_conditions["vigilant_breeze_nurturing_regen_share"] = 0.0
        set_conditions["vigilant_breeze_nurturing_regain_share"] = 0.0

    whisper_bonus = _number(condition_state, "vigilant_breeze_whisper_bonus_stacks", 0.0, 0.0, 8.0)
    if set_conditions.get("vigilant_breeze_whisper_active"):
        whisper_tier = _tier(slot_levels, _SLOT_45)
        current_max += min(whisper_bonus, _WHISPER_MAX[whisper_tier])
    set_conditions["vigilant_breeze_max_stacks"] = current_max
    set_conditions["vigilant_breeze_life_cost_pct_max_per_sec"] = life_cost
    set_conditions["vigilant_breeze_whirlwind_life_cost_pct_max_per_cast"] = tango_life_cost
    set_conditions["vigilant_breeze_whirlwind_breeze_gain"] = tango_breeze_gain

    current = _number(condition_state, "vigilant_breeze_stacks", 0.0, 0.0, 100.0)
    if condition_state.get("vigilant_breeze_use_max_stacks", True):
        current = current_max
    current += float(set_conditions.get("vigilant_breeze_warmest_defeated_stacks", 0.0) or 0.0)
    current = min(current, current_max)
    set_conditions["vigilant_breeze_current_stacks"] = current if vigilant_active else 0.0
    # The shared Spirit Magus layer applies +6 Growth per Breeze stack to each Magus.

    set_conditions["vigilant_breeze_damage_factor"] = damage_factor
    return {"contributions": contributions, "set_conditions": set_conditions}


def stash(*, source, ls_state, **_):
    """Capture Iris's converged regen/regain pools for the next trait pass."""
    for key in ("life_regen_speed_inc", "life_regen_inc", "life_regen_flat", "life_regain_inc",
                "energy_shield_regain_inc", "life_regain_interval_additional",
                "energy_shield_regain_interval_additional"):
        ls_state["iris_" + key] = source.total(key)


def normalize_selected_skill_role(selected_skill):
    raw = str(selected_skill or "").strip().lower()
    role = raw.rsplit("(", 1)[-1].rstrip(") ").strip()
    return {"base": "base skill", "base skill": "base skill",
            "ultimate": "ultimate", "ultimate skill": "ultimate"}.get(role, role)


def selected_skill_contract(*, selected_skill, minion_skills, source, growth=100.0, ultimate_cooldown_zero=False,
                            life_cost_pct_max_per_cast=0.0, breeze_per_cast=0):
    """Resolve one selected role to each Magus's matching ability and cast rate, without computing damage.

    Ultimate damage is intentionally not included in the default minion total. A later
    Magus module can call this contract and consume its own skill formula.
    """
    from engine.minion_offense import (
        _MINION_SPEED_INC, _MINION_SPEED_ADD, _parse_cast_time, _speed_add_product, growth_stage,
    )

    role = normalize_selected_skill_role(selected_skill)
    abilities = list(minion_skills or [])

    def find_skill(skill_role):
        return next((s for s in abilities
                     if skill_role in {str(t).lower() for t in (s.get("skill_tags") or [])}), None)

    if role not in {"base skill", "ultimate"}:
        return {"selected_skill": selected_skill, "role": role, "available": False,
                "damage_in_default_total": False, "reason": "selected skill role is unsupported"}
    resolved = find_skill(role)
    if not resolved:
        return {"selected_skill": selected_skill, "role": role, "available": False,
                "damage_in_default_total": False, "reason": f"{role} is unavailable for this Magus"}
    tags = {str(t).lower() for t in (resolved.get("skill_tags") or [])}
    is_spell = "spell" in tags
    which = "cast" if is_spell else "attack"
    base_time = _parse_cast_time(resolved.get("cast_speed", "")) or 0.0
    if base_time <= 0:
        return {"selected_skill": selected_skill, "skill_name": resolved.get("name"), "role": role,
                "available": False, "damage_in_default_total": False,
                "reason": "selected skill cast time is unavailable"}
    ultimate = role == "ultimate"
    ultimate_speed_key = f"minion_ultimate_{which}_speed_additional"
    rate = ((1.0 / base_time) * (1.0 + source.total(_MINION_SPEED_INC[which]))
            * _speed_add_product(source, _MINION_SPEED_ADD[which])
            * (_speed_add_product(source, ultimate_speed_key) if ultimate else 1.0))
    cooldown = _parse_cast_time(resolved.get("cooldown", "")) or 0.0
    if role == "ultimate" and ultimate_cooldown_zero:
        cooldown = 0.0
    elif cooldown > 0:
        cooldown /= max(1e-9, 1.0 + source.total("minion_cdr_speed_inc")
                        + (source.total("spirit_magi_cdr_speed_inc") if ultimate else 0.0))
    if cooldown > 0:
        rate = min(rate, 1.0 / cooldown) if rate > 0 else 1.0 / cooldown
    skill_forms = []
    enhanced_chance = 0.0
    if role == "base skill":
        enhanced = find_skill("enhanced skill")
        enhanced_chance = source.total("spirit_magi_enhanced_skill_chance")
        if growth_stage(float(growth)) >= 2:
            enhanced_chance += 0.30
        enhanced_chance = max(0.0, min(1.0, enhanced_chance))
        # Owner ruling: Enhanced REPLACES an individual Base cast, so its share uses the Base cadence;
        # Enhanced's own cast-time/cooldown schedule does not create a separate rotation.
        skill_forms = [
            {"role": "base skill", "skill_name": resolved.get("name"),
             "casts_per_second": rate * (1.0 - enhanced_chance)},
            {"role": "enhanced skill", "skill_name": enhanced.get("name") if enhanced else None,
             "casts_per_second": rate * enhanced_chance if enhanced else 0.0},
        ]
    else:
        skill_forms = [{"role": "ultimate", "skill_name": resolved.get("name"),
                        "casts_per_second": rate}]
    ultimate_damage_pools = ({
        "inc": source.total("spirit_magi_ultimate_dmg_inc"),
        "additional": source.total("spirit_magi_ultimate_dmg_additional"),
    } if ultimate else {})
    return {"selected_skill": selected_skill, "skill_name": resolved.get("name"), "role": role,
            "available": True, "cast_time": base_time, "cooldown": cooldown,
            "casts_per_second": rate, "damage_in_default_total": False,
            "enhanced_chance": enhanced_chance, "skill_forms": skill_forms,
            "enhanced_casts_per_second": (rate * enhanced_chance if role == "base skill" and enhanced else 0.0),
            "ultimate_damage_pools": ultimate_damage_pools,
            "life_cost_pct_max_per_cast": float(life_cost_pct_max_per_cast),
            "breeze_per_cast": int(breeze_per_cast)}


def apply_merging_stream_origins(*, source, condition_state, growth, magus_skill_tags=None):
    """Apply every slotted basic Magus Origin to one Magus source under Merging Stream.

    The player-side aggregator suppresses these grants while this node is active.
    Each recipient Magus gets its own Growth-scaled Origin Effect multiplier.
    Attack and Spell Crit Rating stay scoped to the recipient's skill type.
    """
    if not condition_state.get("vigilant_breeze_merging_stream"):
        return []
    from engine.models import SourceEntry
    from engine.spirit_magus_origins import EMIT_TABLE, origin_factor, scaled_magnitude, thunder_origin_values

    effect_inc = source.total("spirit_magi_origin_effect_inc")
    effect_add = source.total("spirit_magi_origin_effect_additional")
    per_two_growth = float(condition_state.get("vigilant_breeze_origin_effect_per_2_growth", 0.0) or 0.0)
    growth_factor = 1.0 + per_two_growth * (float(growth) // 2)
    unsupported_targets = set()
    stat_map = {
        "life_regen_inc": "minion_life_regen_inc",
    }
    skill_tags = {str(tag).lower() for tag in (magus_skill_tags or [])}
    crit_targets = {
        "attack_crit_rating_flat": "attack",
        "spell_crit_rating_flat": "spell",
    }

    def emit(stat, amount, label, text):
        if not amount:
            return
        source.add_with_source(stat, amount, SourceEntry(
            stat=stat, amount=amount, source_type="minion", label=label,
            source_name="Merging Stream", text=text))

    for flag, targets, label, origin_name, text_fmt, clamp in EMIT_TABLE:
        if flag not in {"origin_of_fire", "origin_of_ice", "origin_of_rock", "origin_of_erosion"}:
            continue
        if not condition_state.get(flag):
            continue
        raw = float(condition_state.get(flag + "_value", 0.0) or 0.0)
        if not raw:
            continue
        factor = origin_factor(effect_inc, effect_add,
                               float(condition_state.get(flag + "_support_inc", 0.0) or 0.0)) * growth_factor
        value = scaled_magnitude(raw, factor, clamp)
        for target, scale in targets:
            destination = stat_map.get(target)
            if target in crit_targets:
                if magus_skill_tags is None:
                    unsupported_targets.add(target)
                    continue
                if crit_targets[target] not in skill_tags:
                    continue
                destination = "minion_crit_rating_flat"
            if destination:
                emit(destination, value * scale, f"{origin_name} (Merging Stream)", text_fmt.format(v=value))
            else:
                unsupported_targets.add(target)

    if condition_state.get("origin_of_thunder"):
        level = float(condition_state.get("origin_of_thunder_level", 20.0) or 20.0)
        factor = origin_factor(effect_inc, effect_add,
                               float(condition_state.get("origin_of_thunder_support_inc", 0.0) or 0.0)) * growth_factor
        _thunder_speed, _thunder_damage = thunder_origin_values(level, factor)
        emit("minion_attack_speed_additional", _thunder_speed, "Origin of Thunder (Merging Stream)",
             "+6% additional Attack Speed (Origin of Thunder)")
        emit("minion_cast_speed_additional", _thunder_speed, "Origin of Thunder (Merging Stream)",
             "+6% additional Cast Speed (Origin of Thunder)")
        emit("minion_dmg_additional", _thunder_damage,
             "Origin of Thunder (Merging Stream)", f"Origin of Thunder Lv {int(level)} additional damage")
    return sorted(unsupported_targets)


def status_lines(*, slot_levels, advanced_picks, season=None, skills_input=None, **_):
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    picks = set(advanced_picks or [])
    rows = []

    def line(text, source, status="working"):
        rows.append({"text": text, "source": source, "status": status})

    if _enabled(slot_levels, _SLOT_BASE):
        line("Spirit Magus skills in active slots also cast the Trait Skill; every-season line", "Vigilant Breeze")
        line("Merged Magi enter Vigilant; use-max selects the computed Breeze maximum, or set any literal stack count including zero", "Vigilant Breeze")
        line("Breeze adds +16% additional damage per current stack, linearly (owner-confirmed: 10 stacks = +160%)", "Vigilant Breeze")
        line("During Vigilant, Magi consume 20% Max Life per second outside Reconjuring; gain 1 Breeze/s to 10 while merged and lose 2/s unmerged or Reconjuring", "Vigilant Breeze", "informational")
        line("Merged Magi cast only Iris's selected skill; their normal rotation is replaced until unmerged", "Vigilant Breeze")
        line("Iris can select Base Skill (with Enhanced chance replacing individual casts) or Ultimate", "Vigilant Breeze")
        line("Selected skill damage lookup is pending each Magus module; Ultimate stays out of default DPS", "Vigilant Breeze", "informational")
        line(f"Base trait L2-L5: +{_BASE_DMG_ADD[1]*100:g}/{_BASE_DMG_ADD[2]*100:g}/{_BASE_DMG_ADD[3]*100:g}/{_BASE_DMG_ADD[4]*100:g}% additional Minion Damage", "Vigilant Breeze")
    if _pick(picks, slot_levels, "Whirlwind Tango", _SLOT_45):
        tier = _tier(slot_levels, _SLOT_45)
        line(f"Whirlwind Tango ({season or 'SS13'}): Ultimate cooldown 0; each Ultimate cast consumes {_WHIRLWIND_LIFE_COST[tier]*100:g}% Max Life and gains {_WHIRLWIND_BREEZE[tier]} Breeze", "Whirlwind Tango")
        penalty = _WHIRLWIND_SKILL_DMG.get(season or "SS13")
        if penalty is None:
            line(f"Whirlwind Tango Spirit Magus Skill Damage penalty is not modeled for {season}",
                 "Whirlwind Tango", "NYI")
        else:
            line(f"Whirlwind Tango: {penalty*100:g}% additional Spirit Magus Skill Damage to all Spirit Magi", "Whirlwind Tango")
        line("Ultimate damage is a separate per-cast form and remains outside default DPS until its Magus module is wired", "Whirlwind Tango", "informational")
    if _pick(picks, slot_levels, "Breeze's Whisper", _SLOT_45):
        tier = _tier(slot_levels, _SLOT_45)
        line(f"Breeze's Whisper: +30% Enhanced chance; Enhanced casts restore {_WHISPER_HEAL[tier]*100:g}% Max Life at {_WHISPER_INTERVAL[tier]:g}s intervals; temporary max Breeze +{_WHISPER_MAX[tier]} until Reconjuring", "Breeze's Whisper")
        line("Whisper events are rate/interval limited per Magus; excess events are not queued", "Breeze's Whisper")
    if _pick(picks, slot_levels, "Happiest Reunion", _SLOT_60):
        tier = _tier(slot_levels, _SLOT_60)
        line(f"Happiest Reunion: +1 map cap; all Magi count as merged; per-Magus damage uses (1 + {_REUNION_DMG[tier]*100:g}%)^count", "Happiest Reunion")
        line(f"Happiest Reunion: +{_REUNION_DRAIN[tier]*100:g} percentage points to the 20%/s Life drain", "Happiest Reunion")
    if _pick(picks, slot_levels, "Warmest Vigilance", _SLOT_60):
        tier = _tier(slot_levels, _SLOT_60)
        line(f"Warmest Vigilance: +1 Max Breeze per {_WARMEST_STEP[tier]*100:g}% Max Life consumed, capped at +{_WARMEST_CAP[tier]}; +1 Breeze per enemy defeated", "Warmest Vigilance")
        line("Consumed-Life and defeat counters are user-set per Magus; no event simulation", "Warmest Vigilance")
    if _pick(picks, slot_levels, "Merging Stream", _SLOT_75):
        tier = _tier(slot_levels, _SLOT_75)
        line(f"Merging Stream: Iris does not receive Origins; basic Magus Origins apply to all Spirit Magi; +{_STREAM_ORIGIN[tier]*100:g}% additional Origin Effect per 2 total Growth, including innate Growth", "Merging Stream")
        if any(sk.get("enabled", True) and sk.get("skill_id") == "summon_frost_magus"
               for sk in (skills_input or [])):
            line("Origin of Ice Energy Shield regeneration is not modeled because minion Max Energy Shield has no engine pool", "Merging Stream", "NYI")
    if _pick(picks, slot_levels, "Nurturing Breeze", _SLOT_75):
        tier = _tier(slot_levels, _SLOT_75)
        line(f"Nurturing Breeze: Iris takes {_NURTURE_DMG_TAKEN[tier]*100:g}% additional damage; copies {_NURTURE_REGEN_SHARE[tier]*100:g}% of Life Regeneration Speed/Per Second and {_NURTURE_REGAIN_SHARE[tier]*100:g}% of Life/Shield Regain and intervals to Magi", "Nurturing Breeze")
        line("Copied Life/Shield Regain pools are exposed; minion hit-based regain and interval cadence are not yet consumed", "Nurturing Breeze", "informational")
    return rows
