"""
engine/compute.py — pure BuildInput → StatResult entry point.

The fixed-point loop iterates: aggregate → derive condition maximums → clamp
numeric condition values → re-derive boolean *_active flags → repeat until
stable (or max 10 iterations). Converges in ~2 passes for normal data.

server.py is a thin HTTP wrapper; all calculation logic lives here.
"""
from __future__ import annotations
import logging
from engine.models import BuildInput, BuildSource, StatResult

log = logging.getLogger(__name__)

_MAX_ITERS = 10


def derive_condition_maximums(source: BuildSource) -> dict[str, float]:
    """Return {condition_key: max_value} for all numeric conditions that have a defined max."""
    from models.conditions import ALL_CONDITIONS
    maxes: dict[str, float] = {}
    for c in ALL_CONDITIONS:
        if c.value_type != "numeric":
            continue
        if c.max_from_stat:
            maxes[c.key] = c.max_base + source.total(c.max_from_stat)
        elif c.numeric_max is not None:
            maxes[c.key] = float(c.numeric_max)
        elif c.max_base:
            maxes[c.key] = float(c.max_base)
    return maxes


def derive_condition_minimums(source: BuildSource) -> dict[str, float]:
    """Return {condition_key: min_value} for all numeric conditions that have a defined min floor."""
    from models.conditions import ALL_CONDITIONS
    mins: dict[str, float] = {}
    for c in ALL_CONDITIONS:
        if c.value_type != "numeric":
            continue
        if c.min_from_stat:
            mins[c.key] = c.min_base + source.total(c.min_from_stat)
        elif c.min_base:
            mins[c.key] = float(c.min_base)
    return mins


def _derive_views(
    condition_state: dict[str, float | bool],
) -> tuple[frozenset[str], dict[str, float]]:
    """Split unified condition_state into the two evaluation views the evaluator needs."""
    active_booleans: set[str] = set()
    numeric_vals: dict[str, float] = {}
    for k, v in condition_state.items():
        if isinstance(v, bool):
            if v:
                active_booleans.add(k)
        elif isinstance(v, (int, float)):
            numeric_vals[k] = float(v)
    return frozenset(active_booleans), numeric_vals


def _clamp_and_rederive(
    condition_state: dict[str, float | bool],
    maxes: dict[str, float],
    mins: dict[str, float],
) -> dict[str, float | bool]:
    """Clamp numeric values to their derived maxes/mins; re-derive *_active booleans from stack counts."""
    from models.conditions import DERIVED_ACTIVE_KEYS
    new_state: dict[str, float | bool] = dict(condition_state)

    for k in new_state:
        if not isinstance(new_state[k], bool) and isinstance(new_state[k], (int, float)):
            val = float(new_state[k])
            if k in maxes:
                val = min(val, maxes[k])
            if k in mins:
                val = max(val, mins[k])
            new_state[k] = val

    # Re-derive boolean *_active flags from their clamped stack-count siblings
    for bool_key, stack_key in DERIVED_ACTIVE_KEYS.items():
        if stack_key in new_state:
            new_state[bool_key] = float(new_state[stack_key]) > 0

    return new_state


def _state_snapshot(condition_state: dict[str, float | bool]) -> frozenset:
    return frozenset((k, v) for k, v in condition_state.items())


def _eval_intrinsic_additional(skill, source: BuildSource, condition_state: dict[str, float | bool]) -> float:
    """Sum a skill's intrinsic 'additional damage' bonuses. Each bonus is
        min(per * (rating / per_n) * (1 + effect_value), cap)
    where rating comes from a condition (Focused Slash's Fervor Rating) or an aggregated stat
    (Moon Strike's Max Mana). Returns 0.0 for skills with none."""
    total = 0.0
    for ia in getattr(skill, "intrinsic_additional", []):
        if getattr(ia, "rating_source", "condition") == "stat":
            rating = source.total(ia.rating_key)
        else:
            rating = float(condition_state.get(ia.rating_key, 0.0) or 0.0)
        if rating <= 0.0:
            continue
        effect = source.total(ia.effect_key) if ia.effect_key else 0.0
        amount = ia.per * (rating / getattr(ia, "per_n", 1.0)) * (1.0 + effect)
        cap = getattr(ia, "cap", None)
        if cap is not None:
            amount = min(amount, cap)
        total += amount
    return total


def compute(
    build_input: BuildInput,
    season_trees: dict[str, dict],
    filter_data: dict,
    skill_data: dict | None = None,
    skills_input: list[dict] | None = None,
    skills_by_id: dict[str, dict] | None = None,
) -> StatResult:
    """
    Run the fixed-point aggregation loop and return a StatResult.

    season_trees: {tree_slug: season_tree_dict}
    filter_data:  loaded node_type_filter.json dict
    """
    from engine.aggregator import aggregate
    from models.stat_meta import STAT_META

    condition_state: dict[str, float | bool] = dict(build_input.condition_state)
    prev_snapshot = None

    for iteration in range(_MAX_ITERS):
        active_booleans, numeric_vals = _derive_views(condition_state)

        source = aggregate(
            build_input,
            season_trees,
            filter_data,
            active_booleans=active_booleans,
            numeric_vals=numeric_vals,
        )

        # Compute derived stats (strength, armor, max_life, etc.) and inject
        # back into source so the pipeline and condition system can read them.
        # Record consumption here (a derived stat reads its component mod stats, e.g.
        # max_life_inc); the condition-system reads that follow stay untraced.
        from engine.derive import derive_stats
        source._recording = True
        derive_stats(source)
        source._recording = False

        # Inject auto-computed condition values from aggregated stats
        from models.conditions import ALL_CONDITIONS
        for _c in ALL_CONDITIONS:
            if _c.source == "computed_stat":
                condition_state[_c.key] = source.total(_c.key)

        maxes = derive_condition_maximums(source)
        mins = derive_condition_minimums(source)
        new_state = _clamp_and_rederive(condition_state, maxes, mins)
        snapshot = _state_snapshot(new_state)

        if snapshot == prev_snapshot:
            break
        prev_snapshot = snapshot
        condition_state = new_state
    else:
        log.error(
            "Condition resolution did not converge after %d iterations. "
            "Returning last computed state. Check for circular/contradictory mechanics.",
            _MAX_ITERS,
        )

    # Tripwire: a single damage-taken stat reaching >=100% reduction implies immunity, which
    # the current additive pooling can't represent (distinct sources should multiply). Raise
    # so it's revisited rather than silently zeroing damage.
    from engine.guards import check_damage_taken_immunity
    check_damage_taken_immunity(source)

    # Build stat_map from final source
    stat_map: dict = {}
    for entry in source.source_log:
        if entry.stat not in stat_map:
            meta = next((m for s, m in STAT_META.items() if s.value == entry.stat), None)
            stat_map[entry.stat] = {
                "display_name": meta.display_name if meta else entry.stat,
                "category": meta.category if meta else "Other",
                "unit": meta.unit if meta else "",
                "total": 0.0,
                "sources": [],
            }
        stat_map[entry.stat]["total"] = round(stat_map[entry.stat]["total"] + entry.amount, 6)
        stat_map[entry.stat]["sources"].append({
            "source_type": entry.source_type,
            "label": entry.label,
            "text": entry.text,
            "amount": entry.amount,
            "points": entry.points,
        })

    # Add derived effective stats as the "Character" section of the stat sheet
    from engine.derive import ALL_DERIVED_STATS as _DERIVED
    for _d in _DERIVED:
        val = source.total(_d.key)
        if val == 0.0:
            continue
        _meta = next((m for s, m in STAT_META.items() if s.value == _d.key), None)
        stat_map[_d.key] = {
            "display_name": _meta.display_name if _meta else _d.key.replace("_", " ").title(),
            "category": "Character",
            "unit": "",
            "total": round(val, 2),
            "sources": [],
        }

    # Clamp report: numeric conditions where the user's requested value exceeded the derived max
    clamped_numeric = {
        k: float(v) for k, v in condition_state.items()
        if k in maxes
    }
    clamp_report: dict[str, dict] = {}
    for k, applied in clamped_numeric.items():
        requested = float(build_input.condition_state.get(k, 0))
        if requested > applied:
            clamp_report[k] = {"requested": requested, "applied": applied}

    # Post-loop offense and defense (not part of the fixed-point convergence)
    from dataclasses import asdict
    from engine.defense import calculate_defense
    from engine.offense import calculate_offense, skill_effective_level
    from engine.skill_resolver import resolve_skill

    # Record stat consumption across the offense + defense passes (defensive stats always read;
    # offense reads only what the active/modeled skill's pipeline touches — an unmodeled skill
    # reads nothing, so its damage mods fall out of consumed_stats and read as inert).
    source._recording = True
    result_defense = asdict(calculate_defense(source))

    result_offense = None
    if skill_data and build_input.main_skill:
        resolved = resolve_skill(skill_data)
        # new_state is the converged, clamped condition state from the loop above.
        extra_add = _eval_intrinsic_additional(resolved, source, new_state)
        offense = calculate_offense(
            source, resolved, build_input.main_skill.level,
            is_main_skill=True, extra_additional=extra_add,
        )
        result_offense = asdict(offense)
    source._recording = False

    # Skill slot summaries — effective level for every equipped skill
    result_skill_slots: list[dict] | None = None
    if skills_input and skills_by_id is not None:
        result_skill_slots = []
        for sk in skills_input:
            sd = skills_by_id.get(sk["skill_id"])
            if sd:
                resolved_sk = resolve_skill(sd)
                eff = skill_effective_level(
                    source, resolved_sk.tags, sk["level"],
                    is_main_skill=(sk["slot"] == 1),
                )
                result_skill_slots.append({
                    "slot":           sk["slot"],
                    "skill_id":       sk["skill_id"],
                    "skill_name":     resolved_sk.name or sd.get("name", sk["skill_id"]),
                    "level":          sk["level"],
                    "effective_level": eff,
                    "supported":      resolved_sk.supported,
                })

    return StatResult(
        stat_map=stat_map,
        condition_maximums=maxes,
        clamp_report=clamp_report,
        offense=result_offense,
        defense=result_defense,
        skill_slots=result_skill_slots,
        consumed_stats=sorted(source.consumed_stats),
    )
