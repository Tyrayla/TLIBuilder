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
    res.base_is_percent = bool(getattr(resolved_skill, "mana_cost_is_percent", False))
    _base_pct_or_flat = float(getattr(resolved_skill, "mana_cost", 0.0) or 0.0)
    no_cost = bool(cs.get("skill_no_mana_cost")) or source.total("skill_no_mana_cost") > 0   # Frozen Lotus → base 0

    # Arcane fraction f = the global "Mana Cost → Life Cost" stat + the skill's OWN intrinsic conversion (Bull's Rage),
    # capped at 1. The conversion is applied BEFORE the %-base resolves against a pool (owner-confirmed), so the life
    # portion of a "%" base resolves against Max LIFE and the mana portion against Max Mana.
    f = min(max(source.total("mana_cost_to_life_cost") + float(getattr(resolved_skill, "intrinsic_mana_to_life", 0.0)), 0.0), 1.0)
    res.arcane_fraction = f
    max_mana = source.total("max_mana") or 0.0
    max_life = source.total("max_life") or 0.0

    def _base_portion(frac, pool_max):
        """The base cost going to one pool: a % base resolves against THAT pool's max (post-conversion); a flat base
        is pool-agnostic. 0 under Frozen Lotus."""
        if no_cost:
            return 0.0
        b = (_base_pct_or_flat / 100.0) * pool_max if res.base_is_percent else _base_pct_or_flat
        return frac * b

    base_mana = _base_portion(1.0 - f, max_mana)
    base_life = _base_portion(f, max_life)
    res.base_cost = base_mana + base_life   # total pre-scale base (for the display breakdown)

    # Cost-modifier pools.
    res.inc = source.total("skill_cost_inc")
    res.additional = source.total("skill_cost_additional")
    res.reduction = source.total("skill_cost_reduction")
    res.flat = source.total("skill_cost_flat") + source.total(
        "attack_skill_cost_flat" if is_attack else "spell_skill_cost_flat")
    res.support_mult, res.support_breakdown = _supports_mult(attached_supports, skills_by_id, slot, otbt)
    _scale = res.support_mult * (1.0 + res.inc + res.additional - res.reduction)

    # Flat additions join the base (pool-agnostic, split by f), then everything scales (owner best-guess — VERIFY IN-GAME).
    res.mana_cost = max(0.0, (base_mana + (1.0 - f) * res.flat) * _scale)
    res.life_cost = max(0.0, (base_life + f * res.flat) * _scale)

    # Override: a support that SETS the final cost (rare; "set to 0" uses skill_no_mana_cost). Splits by f.
    _override = source.total("mana_cost_override")
    if _override:
        res.mana_cost = max(0.0, _override) * (1.0 - f)
        res.life_cost = max(0.0, _override) * f
        res.flags.append("mana_cost_override applied (final cost replaced)")

    # Record reads so the consumable-universe scan + badges stay in sync.
    if getattr(source, "_recording", False):
        for k in _COST_STATS:
            source.consumed_stats.add(k)
        if res.base_is_percent:
            source.consumed_stats.add("max_mana")
            source.consumed_stats.add("max_life")
    return res
