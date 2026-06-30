"""Skill mana/life COST model — the active skill's per-cast Mana (and Arcane-converted Life) cost.

Single source of truth for cost. engine.compute computes it once per pass (after reservation); engine.consumption
folds the result into the per-second drain at the skill's USE rate. Distinct from self-consume affixes
(engine.consumption) and from reservation/sealing (engine.utility.apply_reservation).

Formula (owner best-guess — flat-joins-base then scaled; VERIFY IN-GAME):
    cost = max(0, (base + flat) × Π(support mana multipliers)
                  × (1 + skill_cost_inc + skill_cost_additional − skill_cost_reduction))
  • base = ResolvedSkill.mana_cost, or pct × Max Mana when mana_cost_is_percent (e.g. Moon Strike "1%").
  • "Skills no longer cost Mana" (Frozen Lotus core talent / a support's skill_no_mana_cost flag) ⇒ base = 0
    — the BASE only; flat additions and multipliers still apply (per the stat.py MANA_COST_OVERRIDE note).
  • mana_cost_override (a support that SETS the final cost) ⇒ replaces the final value.
  • Arcane (mana_cost_to_life_cost f) ⇒ life_cost = cost×f, mana_cost = cost×(1−f). Awakening Skull = f 1.0 + a
    big skill_cost_inc/flat ⇒ large life cost per cast (life death spiral).
Triggered/repeated casts (Tangle, Spell Burst, Preparation, Activation Medium) IGNORE the cost (owner-confirmed),
so consumption multiplies the per-cast cost by the base USE rate only.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from engine.models import BuildSource
from engine.utility import _mana_multiplier

# Every cost stat read here — one place so the consumable-universe scan + the recording below stay in sync.
_COST_STATS = ("skill_cost_inc", "skill_cost_additional", "skill_cost_reduction", "skill_cost_flat",
               "attack_skill_cost_flat", "spell_skill_cost_flat", "mana_cost_to_life_cost",
               "mana_cost_override", "skill_no_mana_cost")


@dataclass
class SkillCostResult:
    skill_name: str = ""           # the active skill the cost belongs to (for the per-skill breakdown row)
    base_cost: float = 0.0
    support_mult: float = 1.0
    inc: float = 0.0
    additional: float = 0.0
    reduction: float = 0.0
    flat: float = 0.0
    mana_cost: float = 0.0          # final per-cast Mana cost (after the Arcane split)
    life_cost: float = 0.0          # final per-cast Life cost (Arcane-converted)
    arcane_fraction: float = 0.0
    base_is_percent: bool = False
    support_breakdown: list = field(default_factory=list)   # [{name, mult}]
    flags: list = field(default_factory=list)               # surfaced approximations / NYI


def has_skill_cost(sc: "SkillCostResult | None") -> bool:
    """True when the build's active skill drains mana or life per cast (gates the consumption stage)."""
    return bool(sc) and (sc.mana_cost > 1e-9 or sc.life_cost > 1e-9)


def _supports_mult(attached_supports, skills_by_id, slot, otbt) -> tuple[float, list]:
    """Π of the active skill's attached supports' Mana Multipliers (their `mana_cost` %, e.g. 110% → ×1.10),
    multiplicative (owner-confirmed). Off the Beaten Track forces 95% (handled in _mana_multiplier)."""
    mult = 1.0
    breakdown: list[dict] = []
    for s in (attached_supports or []):
        if s.get("slot") != slot or not s.get("enabled", True) or not s.get("item_id"):
            continue
        sd = (skills_by_id or {}).get(s["item_id"]) or {}
        m = _mana_multiplier(sd, otbt)
        if m != 1.0:
            mult *= m
            breakdown.append({"name": sd.get("name") or s["item_id"], "mult": m})
    return mult, breakdown


def compute_skill_cost(resolved_skill, source: BuildSource, attached_supports, skills_by_id, *,
                       slot: int = 1, is_attack: bool = False, otbt: bool = False,
                       condition_state: dict | None = None) -> SkillCostResult:
    cs = condition_state or {}
    res = SkillCostResult()
    if resolved_skill is None:
        return res
    res.skill_name = getattr(resolved_skill, "name", "") or ""

    # Base cost. Percentage base ("1%"/"15%") = % of Max Mana per use.
    res.base_is_percent = bool(getattr(resolved_skill, "mana_cost_is_percent", False))
    base = float(getattr(resolved_skill, "mana_cost", 0.0) or 0.0)
    if res.base_is_percent:
        base = (base / 100.0) * (source.total("max_mana") or 0.0)

    # Frozen Lotus / "Skills no longer cost Mana" → zero the BASE only (flat + multipliers still resolve to 0×base).
    no_cost = bool(cs.get("skill_no_mana_cost")) or source.total("skill_no_mana_cost") > 0
    if no_cost:
        base = 0.0
    res.base_cost = base

    # Cost-modifier pools.
    res.inc = source.total("skill_cost_inc")
    res.additional = source.total("skill_cost_additional")
    res.reduction = source.total("skill_cost_reduction")
    res.flat = source.total("skill_cost_flat") + source.total(
        "attack_skill_cost_flat" if is_attack else "spell_skill_cost_flat")
    res.support_mult, res.support_breakdown = _supports_mult(attached_supports, skills_by_id, slot, otbt)

    # Flat joins base, then everything scales (owner best-guess — VERIFY IN-GAME).
    cost = max(0.0, (base + res.flat) * res.support_mult * (1.0 + res.inc + res.additional - res.reduction))

    # Override: a support that SETS the final cost (rare; never falsy-0 here — "set to 0" uses skill_no_mana_cost).
    _override = source.total("mana_cost_override")
    if _override:
        cost = max(0.0, _override)
        res.flags.append("mana_cost_override applied (final cost replaced)")

    # Arcane: pay a fraction of the cost as Life instead of Mana.
    f = min(max(source.total("mana_cost_to_life_cost"), 0.0), 1.0)
    res.arcane_fraction = f
    res.life_cost = cost * f
    res.mana_cost = cost * (1.0 - f)

    # Record reads so the consumable-universe scan + badges stay in sync.
    if getattr(source, "_recording", False):
        for k in _COST_STATS:
            source.consumed_stats.add(k)
        if res.base_is_percent:
            source.consumed_stats.add("max_mana")
    return res
