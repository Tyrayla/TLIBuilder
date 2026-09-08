"""Engine guardrails — tripwires for states the damage model cannot yet represent correctly.

These raise loudly rather than letting the engine silently produce wrong numbers, so the
underlying modelling gap gets revisited instead of shipping bad output.
"""
from __future__ import annotations

from engine.defense import _dmg_taken_keys, _INCOMING_TYPES
from models.stat_meta import STAT_META


class ImmunityThresholdError(ValueError):
    """A single damage-taken source reached >=100% reduction on its own, implying true immunity.

    Distinct reduction sources MULTIPLY (see derive._additional_pool_factor / defense._dmg_taken_factor):
    stacking several genuinely independent reductions asymptotically approaches, but can never reach,
    zero — that's mathematically guaranteed once they're multiplied instead of summed. So the only way
    this can still legitimately fire is a SINGLE source, by itself, reaching or crossing -100% — which
    the engine doesn't model as real (in-game) unconditional immunity, so it's surfaced as an error
    instead of silently zeroing incoming damage.
    """


# Player/friendly-unit-only. Deliberately excludes stat keys that look like a "damage taken" stat by
# name but describe the ENEMY/target taking more damage (offense-side vulnerability/amplification, e.g.
# Licorice Note's "additional damage taken by enemies within Nm" in offense.py) — those have no immunity
# concept and stacking them well past 100% is normal, intended play, not a modelling gap.
_OFFENSE_SIDE_DMG_TAKEN_STATS = frozenset({"enemy_nearby_dmg_taken_additional"})


def _grouped_pool_keys() -> list[frozenset[str]]:
    """The distinct stat-key GROUPS defense._dmg_taken_factor actually combines (one per damage-type /
    delivery combination — e.g. physical-hit pools dmg_taken_additional + physical_dmg_taken_additional +
    hit_dmg_taken_additional together), deduped. Checking these key-by-key (as a flat scan over
    STAT_META would) misses a combined total crossing -100% across keys that each stay under it alone."""
    seen: dict[frozenset[str], None] = {}
    for dtype in _INCOMING_TYPES:
        for is_dot in (False, True):
            seen.setdefault(frozenset(_dmg_taken_keys(dtype, is_dot)), None)
    return list(seen.keys())


def _grouped_violations(source) -> list[tuple[str, float]]:
    """One violation per pooled key-group where a SINGLE source alone reaches immunity (raw, unclamped
    (1 + amount) <= 0). Multiplying several distinct sources that are each individually fine can never
    produce a combined factor <= 0 (product of positive numbers < 1 is always > 0), so per-source is the
    only thing left to check once the math is multiplicative — see ImmunityThresholdError's docstring.
    Falls back to the OLD flat-sum-across-the-group check when the source carries no per-entry
    source_log metadata (e.g. tests that call BuildSource.add() directly), mirroring
    derive._additional_pool_factor's own fallback."""
    violations: list[tuple[str, float]] = []
    reported_entries: set[int] = set()   # id(entry) — the SAME source can belong to several key-groups
    for keys in _grouped_pool_keys():
        entries = [e for e in source.source_log if e.stat in keys]
        if not entries:
            total = sum(source.total(k) for k in keys)
            mult = 1.0 + total
            if mult <= 0.0:
                violations.append((f"{'+'.join(sorted(keys))} (summed, no per-source data): total={round(total, 4)}",
                                    round(mult, 4)))
            continue
        for e in entries:
            if id(e) in reported_entries:
                continue   # e.g. dmg_taken_additional belongs to every group — report it once, not per-group
            mult = 1.0 + e.amount
            if mult <= 0.0:
                reported_entries.add(id(e))
                violations.append((f"single source {e.label!r} ({e.text!r})", round(mult, 4)))
    return violations


def _legacy_single_stat_violations(source) -> list[tuple[str, float, float]]:
    """Everything else that reads as a 'damage taken' stat but isn't part of the grouped multiplicative
    pool above — e.g. crit_dmg_taken_reduction (reduction-style) and any minion/synth-troop/spirit-magus
    variant. Preserves the ORIGINAL flat-sum-per-stat check for these until each is individually
    confirmed to need (or not need) the same multiplicative treatment — narrower scope than fixing the
    ones actually reproduced (see docs/verification), not a claim the others are already correct.
    """
    grouped_keys = {k for group in _grouped_pool_keys() for k in group}
    violations: list[tuple[str, float, float]] = []
    for stat, meta in STAT_META.items():
        if stat.value in grouped_keys or stat.value in _OFFENSE_SIDE_DMG_TAKEN_STATS:
            continue
        if "dmg_taken" not in stat.value or meta.modifier_type not in ("additional", "increased", "reduced"):
            continue
        total = source.total(stat.value)
        is_reduction = "reduction" in stat.value or meta.modifier_type == "reduced"
        mult = (1.0 - total) if is_reduction else (1.0 + total)
        if mult <= 0.0:
            violations.append((stat.value, round(total, 4), round(mult, 4)))
    return violations


def check_damage_taken_immunity(source) -> None:
    """Raise ImmunityThresholdError if any single damage-taken source implies immunity."""
    grouped = _grouped_violations(source)
    legacy = _legacy_single_stat_violations(source)
    if not grouped and not legacy:
        return
    details = "; ".join(f"{k}: x{m}" for k, m in grouped)
    if legacy:
        legacy_details = "; ".join(f"{k}: total={t} -> x{m}" for k, t, m in legacy)
        details = f"{details}; {legacy_details}" if details else legacy_details
    raise ImmunityThresholdError(
        "Damage-taken reduction reached immunity (>=100%) from a single source: "
        f"{details}. Multiple distinct reduction sources multiply toward zero and can never reach it on "
        "their own — this means one source alone is at or past -100%, which isn't modelled as real "
        "immunity. Revisit that source before trusting this build."
    )
