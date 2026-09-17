"""Warcry timing and power summaries for the Calcs panel."""
from __future__ import annotations

from engine.models import SourceEntry
from engine.uptime import is_real, uptime_fraction


# Trusted SS13 skill data. All six Warcries recharge in eight seconds; Raging
# Warcry alone has a 3.5-second base effect duration.
_BASES: dict[str, tuple[float, float]] = {
    "charging_warcry": (8.0, 3.0),
    "commanding_warcry": (8.0, 3.0),
    "fearless_warcry": (8.0, 3.0),
    "raging_warcry": (8.0, 3.5),
    "resurrection_warcry": (8.0, 3.0),
    "shockwave_warcry": (8.0, 3.0),
}
WARCRY_SKILL_IDS = frozenset(_BASES)

# Trusted SS13 skill-data values. A contribution uses Warcry Power only when
# its source text explicitly says it applies for/per enemy affected; all other
# lines receive normal total Warcry Effect alone (unless their own exception
# says otherwise).
_CONTRIBUTIONS: dict[str, tuple[dict, ...]] = {
    "charging_warcry": (
        {"label": "Additional Shadow Strike Damage", "level_one": 0.04, "per_power": True,
         "stat": "dmg_additional", "scope": "shadow strike"},
        {"label": "Additional Shadow Strike Ailment Damage", "level_one": 0.04, "per_power": True,
         "stat": "ailment_dmg_additional", "scope": "shadow strike"},
        {"label": "Tracking Area", "level_one": 0.20, "per_power": False,
         "stat": "shadow_strike_tracking_area_inc", "scope": "shadow strike"},
    ),
    "commanding_warcry": (
        {"label": "Additional Minion Damage", "level_one": 0.041, "level_twenty": 0.06, "per_power": True,
         "stat": "minion_dmg_additional"},
    ),
    "fearless_warcry": (
        {"label": "Additional Slash-Strike Damage", "level_one": 0.04, "level_twenty": 0.059, "per_power": True,
         "stat": "dmg_additional", "scope": "slash-strike"},
        {"label": "Additional Slash-Strike Ailment Damage", "level_one": 0.04, "level_twenty": 0.059, "per_power": True,
         "stat": "ailment_dmg_additional", "scope": "slash-strike"},
    ),
    "raging_warcry": (
        {"label": "Additional Demolisher Damage", "level_one": 0.04, "level_twenty": 0.0495, "per_power": True,
         "stat": "dmg_additional", "scope": "demolisher"},
        {"label": "Additional Demolisher Ailment Damage", "level_one": 0.04, "level_twenty": 0.0495, "per_power": True,
         "stat": "ailment_dmg_additional", "scope": "demolisher"},
        {"label": "Demolisher Charge Recovery Speed", "level_one": 0.04, "per_power": True,
         "stat": "demolisher_charge_speed_inc"},
    ),
    "resurrection_warcry": (
        {"label": "Additional Damage Taken", "level_one": -0.02, "per_power": True,
         "minimum_amount": -0.60, "stat": "dmg_taken_additional"},
    ),
    "shockwave_warcry": (
        # SS13 exposes the shared Combo tag but not a distinct finisher tag. Apply to
        # Combo skills until the sequence model can isolate the third (finisher) cast.
        {"label": "Additional Combo Finisher Damage", "level_one": 0.031, "level_twenty": 0.0595, "per_power": True,
         "stat": "dmg_additional", "scope": "combo"},
        {"label": "Additional Combo Finisher Ailment Damage", "level_one": 0.031, "level_twenty": 0.0595, "per_power": True,
         "stat": "ailment_dmg_additional", "scope": "combo"},
        {"label": "Additional Combo Skill Area per Combo Finisher", "level_one": 0.06,
         "per_power": False, "per_stack": True, "max_stacks": 5,
         "stat": "skill_area_additional", "scope": "combo"},
    ),
}


def _at_level(level_one: float, level_twenty: float | None, level: int) -> float:
    """Interpolate the default description (Lv1) to the detailed description (Lv20)."""
    if level_twenty is None:
        return level_one
    ratio = min(1.0, max(0.0, (level - 1) / 19.0))
    return level_one + (level_twenty - level_one) * ratio


def _life_restoration(data: dict, level: int) -> float | None:
    """Read Resurrection's precise level-table value; this effect explicitly ignores Warcry Effect."""
    for row in data.get("progression") or []:
        if int(row.get("level") or 0) != level:
            continue
        for key, value in (row.get("values") or {}).items():
            if "restore" in str(key).lower() and "life" in str(key).lower():
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
    return None


def _warcry_selection_key(skill_id: str, slot: int | None) -> str:
    """Return a selector key for this equipped Warcry instance."""
    return f"warcry_sel_{skill_id}_{slot}"


def apply_warcry_buffs(skills_input, skills_by_id, source, condition_state, uptime_mode, *, power_is_manual=False) -> tuple[list[dict], list[dict], dict | None]:
    """Inject active Warcry effects into their normal stat pools.

    The configurable Warcry buffs are full strength in Full Uptime and scaled by their
    resolved uptime in Real mode. Resurrection's restoration instead occurs on each
    resolved cooldown; its fixed total is spread over its independently duration-scaled
    four-second window.
    """
    summaries = summarize_warcries(
        skills_input, skills_by_id, source, condition_state, power_is_manual=power_is_manual)
    # Different Warcry skills are distinct buffs and can coexist. Only duplicate
    # copies of the same skill need a most-recent-cast resolution.
    by_skill: dict[str, list[dict]] = {}
    for summary in summaries:
        by_skill.setdefault(summary["skill_id"], []).append(summary)
    active: list[dict] = []
    groups: list[dict] = []
    for instances in by_skill.values():
        if len(instances) == 1:
            active.extend(instances)
            continue
        chosen = [s for s in instances if condition_state.get(_warcry_selection_key(s["skill_id"], s["slot"]))]
        if len(chosen) == 1:
            active.extend(chosen)
        groups.append({
            "name": instances[0]["name"],
            "active": [{"name": s["name"], "source": f"slot {s['slot']}",
                        "sel_key": _warcry_selection_key(s["skill_id"], s["slot"])} for s in instances],
            "resolved": len(chosen) == 1,
        })
    conflict = None if not groups else {"groups": groups, "resolved": all(g["resolved"] for g in groups)}
    restoration: list[dict] = []
    for summary in active:
        buff_scale = summary["uptime"] if is_real(uptime_mode) else 1.0
        for contribution in summary["contributions"]:
            stat = next((item.get("stat") for item in _CONTRIBUTIONS[summary["skill_id"]]
                         if item["label"] == contribution["label"]), None)
            if not stat:
                continue
            amount = contribution["amount"]
            if contribution.get("per_stack"):
                stacks = min(float(contribution["max_stacks"] or 0), max(0.0, float(
                    condition_state.get("shockwave_warcry_combo_finisher_stacks", 0.0) or 0.0)))
                amount *= stacks
            amount *= buff_scale
            spec = next(item for item in _CONTRIBUTIONS[summary["skill_id"]]
                        if item["label"] == contribution["label"])
            entry = SourceEntry(
                stat=stat, amount=amount, source_type="warcry", label=summary["name"],
                source_name=summary["name"], text=contribution["label"],
            )
            scope = spec.get("scope")
            if scope:
                entry.scope = scope
                source.add_scoped(stat, amount, scope, entry)
            else:
                source.add_with_source(stat, amount, entry)

        if summary["skill_id"] == "resurrection_warcry":
            restored = next((c["amount"] for c in summary["contributions"] if c["label"] == "Life Restored"), None)
            if restored is not None:
                effective = source.materialize_for_skill({"warcry"}, summary["slot"])
                generic_duration = ((1.0 + effective.total("duration_inc")
                                     + effective.total("skill_effect_duration_inc"))
                                    * (1.0 + effective.total("skill_effect_duration_additional")))
                restoration.append({
                    "pool": "life", "mode": "flat", "base_amount": restored,
                    "window": 4.0 * generic_duration, "recast": summary["cooldown"],
                    "source": summary["name"],
                })
    return summaries, restoration, conflict


def summarize_warcries(skills_input, skills_by_id, source, condition_state, *, power_is_manual=False) -> list[dict]:
    """Return display-only timing/effect summaries for each enabled Warcry slot."""
    selected_power = float(condition_state.get("warcry_power", 0.0) or 0.0)
    enemy_power = float(condition_state.get("enemy_count_weight") or 5.0)
    power_cap = 16.0 if condition_state.get("formless_warcry_effects") else 8.0
    summaries: list[dict] = []
    previous_recording = source._recording
    source._recording = True
    try:
        for equipped in skills_input or []:
            if equipped.get("enabled") is False:
                continue
            skill_id = equipped.get("skill_id")
            if skill_id not in _BASES:
                continue
            data = (skills_by_id or {}).get(skill_id) or {}
            tags = {str(tag).lower() for tag in data.get("skill_tags") or []}
            if "warcry" not in tags:
                continue
            base_cooldown, base_duration = _BASES[skill_id]
            effective = source.materialize_for_skill(tags, equipped.get("slot"))
            base_charges = float(data.get("charges") or 1.0)
            extra_charges = effective.total("max_warcry_skill_charges_flat")
            minimum_enemy_power = effective.total("warcry_min_targets_flat")
            cdr_inc = effective.total("cdr_speed_inc") + effective.total("warcry_cdr_speed_inc")
            cdr_additional = effective.total("cdr_speed_additional") + effective.total("warcry_cdr_speed_additional")
            cooldown = base_cooldown / ((1.0 + cdr_inc) * (1.0 + cdr_additional))
            duration_inc = (effective.total("duration_inc")
                            + effective.total("skill_effect_duration_inc")
                            + effective.total("warcry_skill_effect_duration_inc"))
            duration_additional = effective.total("skill_effect_duration_additional") + effective.total("warcry_skill_effect_duration_additional")
            duration = base_duration * (1.0 + duration_inc) * (1.0 + duration_additional)
            effect_inc = effective.total("warcry_effect_inc")
            effect_additional = effective.total("warcry_effect_additional")
            warcry_effect = (1.0 + effect_inc) * (1.0 + effect_additional) - 1.0
            contributions = []
            for contribution in _CONTRIBUTIONS[skill_id]:
                level_one = contribution["level_one"]
                level_twenty = contribution.get("level_twenty")
                base = _at_level(level_one, level_twenty, int(equipped.get("level") or 1))
                factor = selected_power if contribution["per_power"] else 1.0
                raw_amount = base * factor * (1.0 + warcry_effect)
                minimum_amount = contribution.get("minimum_amount")
                contributions.append({
                    "label": contribution["label"], "base": base, "level_one": level_one,
                    "level_twenty": level_twenty, "per_power": contribution["per_power"],
                    "per_stack": contribution.get("per_stack", False),
                    "max_stacks": contribution.get("max_stacks"), "unit": "pct", "minimum_amount": minimum_amount,
                    "amount": max(minimum_amount, raw_amount) if minimum_amount is not None else raw_amount,
                })
            if skill_id == "resurrection_warcry":
                restored = _life_restoration(data, int(equipped.get("level") or 1))
                if restored is not None:
                    contributions.append({
                        "label": "Life Restored", "base": restored, "level_one": 40.0,
                        "level_twenty": None, "per_power": False, "per_stack": False,
                        "max_stacks": None, "unit": " Life / 4 s", "amount": restored,
                        "scales_warcry_effect": False,
                    })
            summaries.append({
                "skill_id": skill_id, "name": data.get("name") or skill_id,
                "level": equipped.get("level", 1), "slot": equipped.get("slot"),
                "warcry_effect_inc": effect_inc,
                "warcry_effect_additional": effect_additional,
                "warcry_effect": warcry_effect,
                "contributions": contributions,
                "power_base": enemy_power, "power_minimum": minimum_enemy_power,
                "power_selected": selected_power, "power_is_manual": power_is_manual,
                "power_cap": power_cap,
                "power": selected_power,
                "base_cooldown": base_cooldown, "cooldown": cooldown,
                "cdr_inc": cdr_inc, "cdr_additional": cdr_additional,
                "base_charges": base_charges, "extra_charges": extra_charges,
                "max_charges": base_charges + extra_charges,
                "base_duration": base_duration, "duration": duration,
                "duration_inc": duration_inc, "duration_additional": duration_additional,
                "uptime": uptime_fraction(1.0 / cooldown, duration, cooldown=cooldown),
            })
    finally:
        source._recording = previous_recording
    return summaries
