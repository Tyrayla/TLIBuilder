"""Icebound Beam canvas-support mechanics.

Three bound supports, all carrying the universal "+20% additional damage for the supported skill" rank line
(handled generically by support_resolver's rank table — NOT here). All mechanics below are Tyra-validated in-game
(level 16 / dummy). Their SPECIFIC lines are bespoke:

  - Chilling Spike (Noble, 5th): (1) DISABLES the Cold Beam 1/3 suppression — the beam runs full even while the
        Icy Blades fire (in-game: beam 30-40 vs the normal 9-12; this is the dominant single-target value).
        (2) Adds 4 large penetrating Icy Blades at 110% of BASE blade damage, ignoring shotgun falloff AND the
        channel's blade-redistribution boost. In single-target their NET contribution is ~0.69 blade-equivalents
        (decomposition: pure beam 280 + 2 base blades 225 + 4 CS blades 115 = 620; 0-base 280+115=395), so it's
        emitted as `icy_blade_extra_blade_equiv` (offense adds it at the burst rate, no shotgun). (3) A small
        +/-% additional Hit Damage tier roll (its default tier is NEGATIVE) → signed `dmg_additional`.
  - Frostbitten (Magnificent, 3rd): Beam inflicts an on-hit debuff, up to 8 stacks, each +(~4%) additional
        damage; the 1s debuff is refreshed by the fast beam hit-rate so it sustains at max during channel →
        assume-max 8 (validated 125→160). A type-A `dmg_additional` gated per-`frostbitten_stacks` (cap = per×8).
  - Ring Blade (Noble, 5th): (1) +1 Projectile AND fires from the enemy location so all blades hit single-target
        (the shotgun model already assumes all-hit → just `projectile_quantity_flat += 1`). (2) FROZEN proc: while
        `enemy_frozen`, every 1s a beam-hit triggers a full extra Icy Blade burst (all projectiles) — flat 1/s,
        CDR-independent (validated: a lvl-20 CDR support changed nothing). Emitted as `icy_blade_frozen_burst_rate`
        (offense adds a full shotgun burst/sec). (3) The +(8-10)% specific roll → `dmg_additional`.

Values come from the equipped tier (progression[tier], default tier 1), honoring an explicit roll.
"""
from __future__ import annotations
import re

from engine.models import SourceEntry
from engine.support_resolver import _progression_for_tier, _tier_value, _explicit_roll

SKILL_ID = "icebound_beam"

CHILLING = "icebound_beam_chilling_spike_noble"
FROSTBITTEN = "icebound_beam_frostbitten_magnificent"
RING_BLADE = "icebound_beam_ring_blade_noble"
IB_SUPPORT_IDS = frozenset({CHILLING, FROSTBITTEN, RING_BLADE})

# Tuned constants (Tyra-validated; one knob each, easy to re-fit against the recounts).
CHILLING_BLADE_EQUIV = 0.69   # net single-target blade-equivalents from CS's 4 penetrating blades (no shotgun)
FROZEN_BURST_RATE = 1.0       # Ring Blade Frozen proc: full Icy Blade bursts per second (flat, CDR-independent)

# Chilling Spike's "(-2–-1) %" / "+(1–4) %" Hit Damage. Capture UNSIGNED magnitudes (the optional leading
# "-" is consumed, not captured) and derive the sign from a "(-" prefix — matching the shared roll-range
# convention in skill_effects.modeled_rolls so the slider shows the correct sign (the default tier is negative).
_CHILLING_RE = re.compile(r"[+]?\s*\(?\s*-?([\d.]+)\s*[–−]\s*-?([\d.]+)\s*\)?\s*%\s*additional Hit Damage", re.I)
# Frostbitten per-stack % (anchored on "damage by").
_FROST_RE = re.compile(r"damage by\s*\+?\s*\(?\s*([\d.]+)\s*[–−\-]\s*([\d.]+)\s*\)?\s*%", re.I)
# Ring Blade's specific "+(8–10) % additional damage for the supported skill".
_RING_RE = re.compile(r"\+?\s*\(?\s*([\d.]+)\s*[–−\-]\s*([\d.]+)\s*\)?\s*%\s*additional damage for the supported skill", re.I)


def _tier_line(data: dict, sup: dict) -> str:
    entry = _progression_for_tier(data.get("progression"), _tier_value(sup.get("level")))
    return str((entry.get("values") or {}).get("name", "")) if entry else ""


def _signed_frac(sup: dict, line: str, rex: "re.Pattern") -> float | None:
    """The rolled fraction for a `(lo-hi)%` line: explicit user roll if set, else the tier midpoint. The
    captured magnitudes are unsigned; a `(-` prefix (e.g. Chilling Spike's "(-5–-3)%") makes the roll negative."""
    roll = _explicit_roll(sup, line)
    if roll is not None:
        return roll
    m = rex.search(line)
    if not m:
        return None
    mid = (float(m.group(1)) + float(m.group(2))) / 2.0
    if "(-" in m.group(0) or "(−" in m.group(0):
        mid = -mid
    return mid / 100.0


# ── Type-A support-path contributions (slot-local dmg_additional) ──────────────────────────────
def chilling_spike_contribution(sup: dict, data: dict) -> dict | None:
    """Chilling Spike's small +/-% additional Hit Damage (signed; default tier is negative). The +4 blades and
    the beam-suppression disable are emitted in apply_slot_effects; the universal +20% rides the rank path."""
    line = _tier_line(data, sup)
    frac = _signed_frac(sup, line, _CHILLING_RE)
    if frac is None:
        return None
    return {
        "stat_key": "dmg_additional",
        "amount": frac,
        "text": f"{frac * 100:+.2f}% additional Hit Damage |{sup.get('item_id')}|chilling_spike",
        "label": data.get("name") or sup.get("item_id"),
        "slot": sup.get("slot", 1),
    }


def frostbitten_contribution(sup: dict, data: dict) -> dict | None:
    """+X% additional damage per Frostbitten debuff stack, capped at 8 (sustained at max during channel). Gated
    per-`frostbitten_stacks` (default 8)."""
    line = _tier_line(data, sup)
    per = _signed_frac(sup, line, _FROST_RE)
    if per is None:
        return None
    return {
        "stat_key": "dmg_additional",
        "amount": per,
        "text": f"+{per * 100:.2f}% additional damage per Frostbitten stack (cap 8) |{sup.get('item_id')}|frostbitten",
        "label": data.get("name") or sup.get("item_id"),
        "condition": {"key": "frostbitten_stacks", "op": "per", "divisor": 1.0, "cap": per * 8.0},
        "slot": sup.get("slot", 1),
    }


def ring_blade_contribution(sup: dict, data: dict) -> dict | None:
    """Ring Blade's +(8-10)% specific additional damage roll (the projectile + Frozen-proc effects are emitted in
    apply_slot_effects; the universal +20% rides the rank path)."""
    line = _tier_line(data, sup)
    frac = _signed_frac(sup, line, _RING_RE)
    if frac is None:
        return None
    return {
        "stat_key": "dmg_additional",
        "amount": frac,
        "text": f"+{frac * 100:.2f}% additional damage for the supported skill |{sup.get('item_id')}|ring_blade",
        "label": data.get("name") or sup.get("item_id"),
        "slot": sup.get("slot", 1),
    }


# ── Modeled-line specs (coverage badges + roll sliders) ────────────────────────
LINE_SPECS = [
    {"support_ids": {CHILLING}, "phrase": re.compile(r"additional Hit Damage", re.I),
     "keys": ["dmg_additional"], "range_re": _CHILLING_RE},
    {"support_ids": {CHILLING}, "phrase": re.compile(r"large Icy Blade Projectiles", re.I),
     "keys": ["icy_blade_extra_blade_equiv"], "range_re": None},
    {"support_ids": {FROSTBITTEN}, "phrase": re.compile(r"increasing the skill's damage by", re.I),
     "keys": ["dmg_additional"], "range_re": _FROST_RE},
    {"support_ids": {RING_BLADE}, "phrase": re.compile(r"additional damage for the supported skill", re.I),
     "keys": ["dmg_additional"], "range_re": _RING_RE},
    {"support_ids": {RING_BLADE}, "phrase": re.compile(r"Projectile Quantity", re.I),
     "keys": ["projectile_quantity_flat"], "range_re": None},
    {"support_ids": {RING_BLADE}, "phrase": re.compile(r"hits a Frozen enemy", re.I),
     "keys": ["icy_blade_frozen_burst_rate"], "range_re": None},
]


# ── skill_effects registry interface ──────────────────────────────────────────
GUARD_IDS = IB_SUPPORT_IDS
CONTRIB_HOOKS = {
    CHILLING: chilling_spike_contribution,
    FROSTBITTEN: frostbitten_contribution,
    RING_BLADE: ring_blade_contribution,
}


def _slot_supports(attached_supports, slot) -> dict[str, dict]:
    """{item_id: support} for the Icebound Beam canvas supports enabled on THIS slot."""
    out: dict[str, dict] = {}
    for sup in attached_supports or []:
        iid = sup.get("item_id")
        if iid in IB_SUPPORT_IDS and sup.get("slot", 1) == slot and sup.get("enabled", True):
            out[iid] = sup
    return out


def apply_slot_effects(*, source, resolved, slot, condition_state, mod_tags, attached_supports,
                       skills_by_id, **_) -> dict:
    """Chilling Spike (disable beam suppression + extra penetrating blades) and Ring Blade (+1 projectile +
    Frozen-proc burst). All slot-local. No offense overrides."""
    sups = _slot_supports(attached_supports, slot)

    # Chilling Spike — disable the Cold Beam suppression + add the net extra-blade contribution.
    if sups.get(CHILLING):
        source.add_slotted("continuous_suppression_disable", 1.0, slot, None, SourceEntry(
            stat="continuous_suppression_disable", amount=1.0, source_type="support",
            label="Icebound Beam: Chilling Spike",
            text=f"Cold Beam is no longer suppressed while Icy Blades fire |{CHILLING}|chilling_spike", points=1))
        source.add_slotted("icy_blade_extra_blade_equiv", CHILLING_BLADE_EQUIV, slot, None, SourceEntry(
            stat="icy_blade_extra_blade_equiv", amount=CHILLING_BLADE_EQUIV, source_type="support",
            label="Icebound Beam: Chilling Spike",
            text=f"4 large penetrating Icy Blades (≈{CHILLING_BLADE_EQUIV:.2f} single-target blade-equiv) |{CHILLING}|chilling_spike",
            points=1))

    # Ring Blade — +1 projectile (fired from the enemy, so all blades hit) + Frozen-proc full burst/sec.
    if sups.get(RING_BLADE):
        source.add_slotted("projectile_quantity_flat", 1.0, slot, None, SourceEntry(
            stat="projectile_quantity_flat", amount=1.0, source_type="support",
            label="Icebound Beam: Ring Blade",
            text=f"Projectile Quantity +1 (fired from the enemy → all blades hit) |{RING_BLADE}|ring_blade", points=1))
        if condition_state.get("enemy_frozen"):
            source.add_slotted("icy_blade_frozen_burst_rate", FROZEN_BURST_RATE, slot, None, SourceEntry(
                stat="icy_blade_frozen_burst_rate", amount=FROZEN_BURST_RATE, source_type="support",
                label="Icebound Beam: Ring Blade",
                text=f"On Frozen enemy: +{FROZEN_BURST_RATE:.0f} full Icy Blade burst/s |{RING_BLADE}|ring_blade", points=1))
    return {}


def preseed(*, slot, condition_state, attached_supports, skills_by_id, **_) -> None:
    """Frostbitten ramps to its 8-stack cap at sustained channel → default `frostbitten_stacks` to the cap when
    socketed and the user hasn't set it (mirrors Howling Gale's Rapid Sweep)."""
    if _slot_supports(attached_supports, slot).get(FROSTBITTEN):
        condition_state.setdefault("frostbitten_stacks", 8)
