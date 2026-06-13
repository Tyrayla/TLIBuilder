"""Engine guardrails — tripwires for states the damage model cannot yet represent correctly.

These raise loudly rather than letting the engine silently produce wrong numbers, so the
underlying modelling gap gets revisited instead of shipping bad output.
"""
from __future__ import annotations

from models.stat_meta import STAT_META


class ImmunityThresholdError(ValueError):
    """A single damage-taken stat reached >=100% reduction, implying immunity.

    Today the engine sums same-key 'additional damage taken' contributions. Once a single
    stat's reduction reaches 100% the resulting multiplier hits zero (target/we take no
    damage) — i.e. immunity. The correct model multiplies *distinct* reduction sources (so
    you asymptotically approach, but never reach, zero), which is not built yet. Until it is,
    crossing this threshold is treated as an error so it is surfaced and revisited rather than
    silently zeroing damage. See the additional-damage pooling plan.
    """


def _damage_taken_immunity_violations(source) -> list[tuple[str, float, float]]:
    """Return (stat_key, total, multiplier) for every damage-taken stat at/over immunity.

    Amplify-style stats ('additional/increased damage taken') use multiplier (1 + total),
    so immunity is total <= -1.0. Reduction/mitigation-style stats use (1 - total), so
    immunity is total >= 1.0. 'taken_as' conversion stats are not magnitude stats and are
    excluded.
    """
    violations: list[tuple[str, float, float]] = []
    for stat, meta in STAT_META.items():
        if "dmg_taken" not in stat.value or meta.modifier_type not in ("additional", "increased", "reduced"):
            continue
        total = source.total(stat.value)
        is_reduction = "reduction" in stat.value or meta.modifier_type == "reduced"
        mult = (1.0 - total) if is_reduction else (1.0 + total)
        if mult <= 0.0:
            violations.append((stat.value, round(total, 4), round(mult, 4)))
    return violations


def check_damage_taken_immunity(source) -> None:
    """Raise ImmunityThresholdError if any single damage-taken stat implies immunity."""
    violations = _damage_taken_immunity_violations(source)
    if violations:
        details = "; ".join(f"{k}: total={t} -> x{m}" for k, t, m in violations)
        raise ImmunityThresholdError(
            "Damage-taken reduction reached immunity (>=100%) on a single stat: "
            f"{details}. Distinct reduction sources should multiply, not sum past -100%; "
            "this case is unmodelled. Revisit additional-damage pooling before trusting this build."
        )
