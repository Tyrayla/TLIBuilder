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


def compute(
    build_input: BuildInput,
    season_trees: dict[str, dict],
    filter_data: dict,
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
        # back into source so the pipeline and condition system can read them
        from engine.derive import derive_stats
        derive_stats(source)

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

    return StatResult(
        stat_map=stat_map,
        condition_maximums=maxes,
        clamp_report=clamp_report,
    )
