"""Berserking Blade canvas-support mechanics + the skill's intrinsic buff.

All effects here are SLOT-LOCAL: emitted only for the Berserking Blade skill slot they belong to (folded
into that slot's offense via BuildSource.add_slotted / materialize_for_skill), so two Berserking setups in
different slots never share supports.

  - Intrinsic buff: +2.5% Skill Area per buff stack, up to 20 stacks (modeled at MAX by default).
  - Sweep (mag):  doubles the stack cap to 40 and grants additional Skill Area per buff stack.
  - Desperation (mag): handled in support_resolver (a `dmg_additional` gated on life_lost_pct, capped).
  - Decimate (noble): raises the enemy Low-Life threshold for this skill (handled in compute's loop).
  - Rampage (noble): shares the skill-area bonus into additional Steep Strike Damage (post-self-buff).

Skill Area is DPS-inert on its own (offense never multiplies by it); it matters for DPS only via Rampage.
"""
from __future__ import annotations
import re

from engine.models import SourceEntry
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "berserking_blade"
_AREA_PER_STACK = 0.025   # intrinsic buff: +2.5% Skill Area per buff stack
_BASE_STACK_CAP = 20      # default upper limit; Sweep doubles to 40

DESPERATION = "berserking_blade_desperation_magnificent"
SWEEP       = "berserking_blade_sweep_magnificent"
DECIMATE    = "berserking_blade_decimate_noble"
RAMPAGE     = "berserking_blade_rampage_noble"
BB_SUPPORT_IDS = frozenset({DESPERATION, SWEEP, DECIMATE, RAMPAGE})

# Range like "(2.7–2.9)" / "2.7-2.9" (en-dash or hyphen). Parsed from the tier's `name` line.
_RANGE = r"\(?\s*([\d.]+)\s*[–−\-]\s*([\d.]+)\s*\)?"
_DESP_PER = re.compile(r"every\s*5\s*%\s*life\s*lost\s*,?\s*\+?" + _RANGE + r"\s*%", re.I)
_DESP_CAP = re.compile(r"up to\s*([\d.]+)\s*%", re.I)
_SWEEP_RE = re.compile(r"\+?" + _RANGE + r"\s*%\s*additional\s+skill\s+area", re.I)
_DECIMATE_RE = re.compile(r"less than\s*" + _RANGE + r"\s*%\s*life", re.I)
_RAMPAGE_RE = re.compile(r"\+?" + _RANGE + r"\s*%\s*of\s+the\s+bonuses", re.I)


def _mid(m: "re.Match") -> float:
    return (float(m.group(1)) + float(m.group(2))) / 2.0


def _tier_line(data: dict, sup: dict) -> str:
    entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    return str((entry.get("values") or {}).get("name", "")) if entry else ""


def desperation_contribution(sup: dict, data: dict) -> dict | None:
    """Return the Desperation `dmg_additional` contribution: per-5%-life-lost additional damage gated on
    `life_lost_pct` with the tier's cap. None if the line can't be parsed. The universal +20% is emitted
    separately by the rank-table path (uncapped)."""
    line = _tier_line(data, sup)
    m = _DESP_PER.search(line)
    if not m:
        return None
    roll = _explicit_roll(sup, line)
    per = roll if roll is not None else _mid(m) / 100.0
    cap_m = _DESP_CAP.search(line)
    cap = float(cap_m.group(1)) / 100.0 if cap_m else None
    cond = {"key": "life_lost_pct", "op": "per", "divisor": 5.0}
    if cap is not None:
        cond["cap"] = cap
    return {
        "stat_key": "dmg_additional",
        "amount": per,
        "text": f"For every 5% Life lost, +{per * 100:.2f}% additional damage |{sup.get('item_id')}|desperation",
        "label": f"{data.get('name') or sup.get('item_id')}",
        "condition": cond,
        "slot": sup.get("slot", 1),
    }


def extract_config(attached_supports, skills_by_id) -> dict[int, dict]:
    """{slot: {sweep_per_stack, decimate_threshold, rampage_coeff}} for the Sweep/Decimate/Rampage supports
    (keyed by the host slot). `decimate_threshold` is a percent (0-100); the others are fractions. Honors a
    per-line explicit user roll, else the tier midpoint."""
    out: dict[int, dict] = {}
    if not attached_supports or not skills_by_id:
        return out
    for sup in attached_supports:
        iid = sup.get("item_id")
        if iid not in BB_SUPPORT_IDS:
            continue
        data = skills_by_id.get(iid)
        if not data:
            continue
        slot = sup.get("slot", 1)
        cfg = out.setdefault(slot, {})
        line = _tier_line(data, sup)
        roll = _explicit_roll(sup, line)
        if iid == SWEEP:
            m = _SWEEP_RE.search(line)
            cfg["sweep_per_stack"] = roll if roll is not None else (_mid(m) / 100.0 if m else 0.0)
        elif iid == DECIMATE:
            m = _DECIMATE_RE.search(line)
            if roll is not None:
                # explicit roll for a % threshold: accept either a percent (e.g. 58) or a fraction (0.58)
                cfg["decimate_threshold"] = roll * 100.0 if roll <= 1.0 else roll
            else:
                cfg["decimate_threshold"] = _mid(m) if m else 35.0
        elif iid == RAMPAGE:
            m = _RAMPAGE_RE.search(line)
            cfg["rampage_coeff"] = roll if roll is not None else (_mid(m) / 100.0 if m else 0.0)
    return out


def stacks(condition_state: dict, has_sweep: bool) -> float:
    """The buff stack count for this slot, clamped to its cap (20, or 40 with Sweep). Defaults to the cap
    (full uptime) when the user hasn't set it."""
    cap = float(_BASE_STACK_CAP * (2 if has_sweep else 1))
    raw = condition_state.get("berserking_blade_stacks")
    raw = cap if raw is None else float(raw)
    return min(max(raw, 0.0), cap)


def emit_self_buff(source, slot: int, n_stacks: float, sweep_per_stack: float) -> None:
    """Emit the intrinsic buff's Skill Area (and Sweep's additional Skill Area) into the slot overlay."""
    inc = _AREA_PER_STACK * n_stacks
    if inc:
        source.add_slotted("skill_area_inc", inc, slot, None, SourceEntry(
            stat="skill_area_inc", amount=inc, source_type="skill",
            label="Berserking Blade Buff",
            text=f"+{_AREA_PER_STACK * 100:.1f}% Skill Area per buff stack ×{n_stacks:.0f} |bb|buff",
            points=1))
    if sweep_per_stack:
        add = sweep_per_stack * n_stacks
        source.add_slotted("skill_area_additional", add, slot, None, SourceEntry(
            stat="skill_area_additional", amount=add, source_type="support",
            label="Berserking Blade: Sweep",
            text=f"+{sweep_per_stack * 100:.2f}% additional Skill Area per buff ×{n_stacks:.0f} |bb|sweep",
            points=1))


def emit_rampage(source, slot: int, eff, coeff: float) -> None:
    """Rampage: share `coeff` of the slot's skill-area bonus into additional Steep Strike Damage. Increased
    pool sums additively, additional pools multiply: bonus = (1+Σinc)·Π(1+add) − 1. Reads the materialized
    slot source (so the self-buff + Sweep are included); emits into the slot overlay for offense to consume."""
    if not coeff:
        return
    inc_sum = eff.total("skill_area_inc")
    add_prod = 1.0
    for e in eff.source_log:
        if e.stat == "skill_area_additional":
            add_prod *= (1.0 + e.amount)
    area_bonus = (1.0 + inc_sum) * add_prod - 1.0
    amt = coeff * area_bonus
    if amt:
        source.add_slotted("steep_strike_additional_dmg", amt, slot, None, SourceEntry(
            stat="steep_strike_additional_dmg", amount=amt, source_type="support",
            label="Berserking Blade: Rampage",
            text=f"Skill Area bonus → +{amt * 100:.1f}% additional Steep Strike Damage |bb|rampage",
            points=1))


# ── skill_effects registry interface ──────────────────────────────────────────
GUARD_IDS = BB_SUPPORT_IDS                       # specific lines handled here, not the generic parser
CONTRIB_HOOKS = {DESPERATION: desperation_contribution}  # type-A support-path contributions


def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    """Slot-local emissions for a Berserking Blade slot: the intrinsic Skill-Area buff (always), Sweep's
    additional Skill Area, and Rampage's skill-area→Steep-Strike share. No offense overrides."""
    cfg = extract_config(attached_supports, skills_by_id).get(slot, {})
    n = stacks(condition_state, "sweep_per_stack" in cfg)
    emit_self_buff(source, slot, n, cfg.get("sweep_per_stack", 0.0))
    emit_rampage(source, slot, source.materialize_for_skill(mod_tags, slot), cfg.get("rampage_coeff", 0.0))
    return {}


def preseed(*, slot, condition_state, attached_supports, skills_by_id, **_) -> None:
    """Decimate: force enemy_low_life for this computation when the enemy is below the rolled threshold
    (set before aggregation so the build's 'vs Low Life' mods emit). Scoped to the BB main slot."""
    cfg = extract_config(attached_supports, skills_by_id).get(slot, {})
    thr = cfg.get("decimate_threshold")
    if thr is not None and float(condition_state.get("enemy_life_pct", 100.0) or 0.0) < thr:
        condition_state["enemy_low_life"] = True
