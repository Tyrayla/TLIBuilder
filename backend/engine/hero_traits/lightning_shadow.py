"""Erika — Lightning Shadow (trait_id "lightning_shadow").

Whole payoff is the Numbed ailment (+5% Lightning taken per stack, scaled by Numbed Effect). The trait
ramps Numbed toward 10 via Electrify → Feline Figure → Numbed, and stacks "additional Numbed Effect"
(a separate multiplicative pool) plus Movement-Speed-scaled bonuses.

Feline Figure is modelled as a PURE Numbed applicator (no direct damage). Values below are the SS12
`_hero_traits.json` constants, indexed by trait level (tier 1-5 → index 0-4). Advanced "pick-one" traits
apply only when selected; Wild Lightning (unlock 60) is mandatory so it always applies.

Numbed uptime (real mode only): Feline Figure sustains single-target Numbed ONLY when an external
"inflict Numbed on Lightning hit" source is present (enemy_numbed) AND Charging Equation is selected
(FF is "once per enemy, never reset"; Charging Equation lets inflicting Numbed re-trigger FF, ≤1/s/enemy).
In max mode (default) Numbed stays user/cap-driven and is not overwritten.
"""
from __future__ import annotations

from engine import uptime

TRAIT_ID = "lightning_shadow"

# Base trait "+X% additional Numbed Effect" by base level (1-5).
_BASE_ADDITIONAL = [0.18, 0.30, 0.43, 0.55, 0.68]
# Dazzling Lightning (unlock 45, pick): "+N to Max Electrify Stacks" / "+N% MS per Electrify stack".
_DAZZLING_MAX_ELECTRIFY = [2, 2, 3, 3, 4]
_DAZZLING_MS_PER_ELECTRIFY = [0.03, 0.05, 0.05, 0.07, 0.07]
# Electroplated Motif (unlock 45, pick): doubles FF-inflicted Numbed duration + "+N% additional Numbed Effect".
_ELECTROPLATED_ADDITIONAL = [0.20, 0.25, 0.30, 0.35, 0.40]
# Wild Lightning (unlock 60, mandatory): "0.4% additional Numbed Effect per +1% MS, up to +CAP%".
_WILD_PER_MS = 0.004                                  # 0.4% additional Numbed Effect per 1% Movement Speed
_WILD_CAP = [0.80, 0.90, 1.00, 1.10, 1.20]
# Swift as Lightning (unlock 75, pick): per 4 Numbed → +2% MS, +N% additional dmg, +N% FF Area (≤10 stacks).
_SWIFT_DMG_ADDITIONAL = [0.01, 0.015, 0.02, 0.025, 0.03]
_SWIFT_FF_AREA = [0.03, 0.04, 0.05, 0.06, 0.07]       # informational (FF is a pure applicator)
# Charging Equation (unlock 75, pick): per Numbed stack → +N% additional Numbed Effect (≤10 stacks).
_CHARGING_ADDITIONAL = [0.03, 0.035, 0.04, 0.045, 0.05]

_ARTIFICIAL_MOON_MS = 0.15                            # +15% MS if inflicted Numbed recently (base level 5)
_MAX_NUMBED = 10.0
_FF_COOLDOWN = 1.0                                    # Charging Equation re-trigger cap: ≤1/s/enemy (single target)
_NUMBED_BASE_DURATION = 2.0                           # seconds (TLI Help DB glossary 762)


def _contrib(stat_key, amount, text, source):
    return {"stat_key": stat_key, "amount": amount, "text": text, "source": source}


def _tier(slot_levels, idx):
    """0-based tier index (level-1) for slot `idx`, clamped to 0-4."""
    lvl = slot_levels[idx] if idx < len(slot_levels) else 1
    return max(0, min(4, int(abs(lvl)) - 1))


def _enabled(slot_levels, idx):
    """A node/tier is DISABLED when its slot level is < 1 (the UI stores a disabled node as a negative level)."""
    lvl = slot_levels[idx] if idx < len(slot_levels) else 1
    return lvl >= 1


def apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks):
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    contribs: list[dict] = []

    base_lvl = slot_levels[0] if slot_levels else 1
    electrify = float(condition_state.get("electrify_stacks", 0.0) or 0.0)
    numbed_now = float(condition_state.get("numbed_stacks", 0.0) or 0.0)   # prev-pass value for buff scaling
    ms_total = float(ls_state.get("ms_total", 0.0))                        # prev-pass Movement Speed fraction

    # ── Base trait ────────────────────────────────────────────────────────────
    # The base node can be disabled (right-click) while the trait stays selected → negative slot level.
    if _enabled(slot_levels, 0):
        contribs.append(_contrib("numbed_effect_additional", _BASE_ADDITIONAL[_tier([base_lvl], 0)],
                                 "Lightning Shadow: additional Numbed Effect", "Lightning Shadow"))
        # Artificial Moon (base level 5): +15% MS if inflicted Numbed recently.
        if abs(base_lvl) >= 5 and condition_state.get("inflicted_numbed_recently"):
            contribs.append(_contrib("movement_speed_inc", _ARTIFICIAL_MOON_MS,
                                     "Artificial Moon: +15% Movement Speed (inflicted Numbed recently)", "Artificial Moon"))

    # ── Dazzling Lightning (45, pick) ─────────────────────────────────────────
    if "Dazzling Lightning" in picks and _enabled(slot_levels, 1):
        t = _tier(slot_levels, 1)
        contribs.append(_contrib("max_electrify_stacks_flat", float(_DAZZLING_MAX_ELECTRIFY[t]),
                                 "Dazzling Lightning: +Max Electrify Stacks", "Dazzling Lightning"))
        contribs.append(_contrib("movement_speed_inc", _DAZZLING_MS_PER_ELECTRIFY[t] * electrify,
                                 "Dazzling Lightning: Movement Speed per Electrify stack", "Dazzling Lightning"))

    # ── Electroplated Motif (45, pick) ────────────────────────────────────────
    if "Electroplated Motif" in picks and _enabled(slot_levels, 1):
        t = _tier(slot_levels, 1)
        contribs.append(_contrib("numbed_effect_additional", _ELECTROPLATED_ADDITIONAL[t],
                                 "Electroplated Motif: additional Numbed Effect", "Electroplated Motif"))

    # ── Wild Lightning (60, mandatory): MS → additional Numbed Effect, capped ──
    t = _tier(slot_levels, 2)
    wild = min(_WILD_PER_MS * (ms_total * 100.0), _WILD_CAP[t]) if _enabled(slot_levels, 2) else 0.0
    if wild > 0:
        contribs.append(_contrib("numbed_effect_additional", wild,
                                 "Wild Lightning: additional Numbed Effect from Movement Speed", "Wild Lightning"))

    # ── Swift as Lightning (75, pick): per 4 Numbed → MS + additional damage ───
    # Buff stacks are USER-SET (swift_as_lightning_stacks): defaults to 1 for a single enemy, up to 10 —
    # the "per 4 Numbed inflicted on the enemy" count depends on enemy count / hit volume we don't model.
    if "Swift as Lightning" in picks and _enabled(slot_levels, 3):
        t = _tier(slot_levels, 3)
        buff = min(10.0, float(condition_state.get("swift_as_lightning_stacks", 1.0) or 0.0))
        if buff > 0:
            contribs.append(_contrib("movement_speed_inc", 0.02 * buff,
                                     "Swift as Lightning: Movement Speed", "Swift as Lightning"))
            contribs.append(_contrib("dmg_additional", _SWIFT_DMG_ADDITIONAL[t] * buff,
                                     "Swift as Lightning: additional damage", "Swift as Lightning"))

    # ── Charging Equation (75, pick): per Numbed stack → additional Numbed Effect ──
    if "Charging Equation" in picks and _enabled(slot_levels, 3):
        t = _tier(slot_levels, 3)
        buff = min(10.0, numbed_now)
        if buff > 0:
            contribs.append(_contrib("numbed_effect_additional", _CHARGING_ADDITIONAL[t] * buff,
                                     "Charging Equation: additional Numbed Effect per Numbed stack", "Charging Equation"))

    # ── Numbed steady-state (real mode only) ──────────────────────────────────
    numbed_override = None
    if uptime.is_real(uptime_mode):
        external = bool(condition_state.get("enemy_numbed"))
        charging = "Charging Equation" in picks
        if external and charging:
            ailment_dur_inc = float(ls_state.get("ailment_dur_inc", 0.0))
            numbed_duration = _NUMBED_BASE_DURATION * (1.0 + ailment_dur_inc)
            if "Electroplated Motif" in picks:
                numbed_duration *= 2.0          # Motif doubles FF-inflicted Numbed duration
            aps = float(ls_state.get("inflict_aps", 0.0))
            numbed_override = uptime.effective_stacks(
                aps, numbed_duration, cap=_MAX_NUMBED, per_apply=electrify, cooldown=_FF_COOLDOWN)
        # else: FF gives no sustained single-target Numbed → leave numbed_stacks as user/support-driven.

    return {"contributions": contribs, "numbed_stacks": numbed_override}


def stash(*, source, ls_state, inflict_aps):
    """Capture the converged scalars next pass's apply() needs."""
    ms = (1.0 + source.total("movement_speed_inc")) * (1.0 + source.total("movement_speed_additional")) - 1.0
    ls_state["ms_total"] = ms
    ls_state["ailment_dur_inc"] = source.total("ailment_duration_inc")
    if inflict_aps is not None:
        ls_state["inflict_aps"] = inflict_aps


def status_lines(*, slot_levels, advanced_picks):
    """One status row per trait line so every line is surfaced (never silently dropped)."""
    picks = set(advanced_picks or [])
    out: list[dict] = []

    def working(text, source):
        out.append({"text": text, "source": source, "status": "working"})

    def info(text, source):
        out.append({"text": text, "source": source, "status": "informational"})

    working("Feline Figure inflicts Numbed (Electrify stacks → Numbed stacks); additional Numbed Effect", "Lightning Shadow")
    info("Electrify generation / Feline Figure trigger / Skill Effect Duration (Electrify) — modelled via stacks", "Lightning Shadow")
    if (slot_levels or [1])[0] >= 5:
        working("Artificial Moon: +15% Movement Speed if inflicted Numbed recently", "Artificial Moon")
    if "Dazzling Lightning" in picks:
        working("+Max Electrify Stacks; +Movement Speed per Electrify stack", "Dazzling Lightning")
    if "Electroplated Motif" in picks:
        working("Doubles FF-inflicted Numbed duration; additional Numbed Effect", "Electroplated Motif")
    working("Wild Lightning: additional Numbed Effect scaling with Movement Speed (capped)", "Wild Lightning")
    if "Swift as Lightning" in picks:
        working("Per 4 Numbed: +Movement Speed, +additional damage", "Swift as Lightning")
        info("Per 4 Numbed: +Feline Figure Area (no direct FF damage modelled)", "Swift as Lightning")
    if "Charging Equation" in picks:
        working("Per Numbed stack: additional Numbed Effect (drives FF re-trigger / Numbed sustain)", "Charging Equation")
    return out
