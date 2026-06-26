"""Erika — Wind Stalker (trait_id "wind_stalker").

Built entirely on Multistrike (the Phase-1 offense system). The base trait grants Movement Speed, Stalker stacks
(+13% additional damage during Multistrike each), and per-level additional Attack Damage; the advanced picks scale
Multistrike further. All of Wind Stalker's own stats are PLAYER-GLOBAL buffs (not slot-local) — the only
main-skill-specific piece is Have Fun's free Lv10 Multistrike support, which is injected as a virtual support
(see `virtual_supports` + server-side folding) so the existing support resolver produces its slot-local chance.

Values are the SS12 `_hero_traits.json` constants, indexed by node tier (level 1-5 → index 0-4). Advanced "pick"
traits apply only when selected (their name is in `advanced_picks`) and their node is enabled.

Owner-confirmed modeling (2026-06-22):
- "Max Multistrike Count reached" = the final attack of the CURRENT chain (every chain reaches it), so the
  "at max count" picks (Cat's Scratch increment, Cat's Vision +Max Stalker) are effectively always-on in sustained
  multistrike → modeled as active. Cat Dive feeds the realized-L hook in offense (`multistrike_max_count_proc_chance`).
- Cat's Vision's additional damage is a FLAT bonus whenever the pick is selected (not multistrike-gated, not per-stack);
  its "+1 Max Stalker" raises the Stalker cap (3 → up to 6). Tiers are signed (L1 is −4%).
- Stalker stacks are a user-set `stalker_stacks` condition defaulting to the effective max (3 base, 6 w/ Cat's Vision).
- Artificial Moon's enemy Mark is a damage-taken debuff — NYI (surfaced, not computed).
- Cat's Punches (L75, pick-one with Cat Dive; owner-confirmed 2026-06-26): +1 Initial Multistrike Count per 3
  Stalker stacks (hard steps of 3 → floor(stacks/3)) + a per-rank flat additional-damage bonus that is ALWAYS
  active (not multistrike-gated). Its "generates a Stalker stack at max count" clause is flavor — no cap change.
"""
from __future__ import annotations

TRAIT_ID = "wind_stalker"
HAVE_FUN_SUPPORT_ID = "multistrike"
HAVE_FUN_SUPPORT_LEVEL = 10

# ── Base trait ────────────────────────────────────────────────────────────────────
_MS_BASE = 0.26                                            # +26% Movement Speed (all base levels)
_BASE_ATK_DMG_ADDITIONAL = [0.0, 0.05, 0.10, 0.15, 0.20]  # +additional Attack Damage by base level 1-5
_STALKER_PER_STACK = 0.13                                  # +13% additional damage during Multistrike per stack
_STALKER_MAX_BASE = 3
_STALKER_MAX_CATS_VISION = 6                               # Cat's Vision: +1 Max Stalker at max count, up to +3
# ── Advanced picks ──────────────────────────────────────────────────────────────────
_INTEREST_RATE = [0.20, 0.24, 0.28, 0.32, 0.36]           # % of Movement-Speed increase → additional Attack Damage
_INTEREST_CAP = [0.30, 0.36, 0.42, 0.48, 0.54]            # cap on the converted additional Attack Damage
_HAVE_FUN_AS_ADDITIONAL = [0.02, 0.06, 0.12, 0.18, 0.24]  # general additional Attack Speed (ALL attacks)
_CATS_VISION_DMG = [-0.04, 0.02, 0.08, 0.14, 0.20]        # flat additional damage (signed) while picked
_CATS_SCRATCH_INC_ADDITIONAL = [0.27, 0.34, 0.41, 0.48, 0.55]  # additional Multistrike Damage Increment (max-count)
_CAT_DIVE_PER_MS = [0.0024, 0.0027, 0.003, 0.0033, 0.0036]     # proc chance per +1% Movement Speed
_CATS_PUNCHES_DMG = [-0.18, -0.12, -0.06, 0.0, 0.06]          # flat additional damage (signed, ALWAYS active)

# Node → slot_levels index. trait_slot_levels = [base, lv45, lv60, lv75].
_SLOT_BASE, _SLOT_45, _SLOT_60, _SLOT_75 = 0, 1, 2, 3


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


def _flag(condition_state, key, default):
    v = condition_state.get(key, default)
    return bool(v) if v is not None else default


def _stalker_cap(picks, slot_levels):
    return _STALKER_MAX_CATS_VISION if ("Cat's Vision" in picks and _enabled(slot_levels, _SLOT_60)) else _STALKER_MAX_BASE


def apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks, **_):
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    contribs: list[dict] = []

    base_lvl = slot_levels[0] if slot_levels else 1
    base_on = _enabled(slot_levels, _SLOT_BASE)
    performing = _flag(condition_state, "performing_multistrike", True)   # MS-centric trait → assume active
    ms_total = float(ls_state.get("movement_speed_inc", 0.0))             # converged Movement Speed (prev pass)

    cap = _stalker_cap(picks, slot_levels)
    raw = condition_state.get("stalker_stacks")
    stalker_stacks = float(cap) if raw is None else max(0.0, min(float(raw), float(cap)))

    if base_on:
        contribs.append(_contrib("movement_speed_inc", _MS_BASE,
                                 "Wind Stalker: +26% Movement Speed", "Wind Stalker"))
        atk = _BASE_ATK_DMG_ADDITIONAL[_tier([base_lvl], 0)]
        if atk > 0:
            contribs.append(_contrib("attack_dmg_additional", atk,
                                     f"Wind Stalker: +{atk * 100:.0f}% additional Attack Damage", "Wind Stalker"))
        # Stalker: +13% additional damage during Multistrike per stack.
        if performing and stalker_stacks > 0:
            s = _STALKER_PER_STACK * stalker_stacks
            contribs.append(_contrib("dmg_additional", s,
                                     f"Stalker: +{s * 100:.0f}% additional damage "
                                     f"({_STALKER_PER_STACK * 100:.0f}%/stack × {stalker_stacks:.0f}, during Multistrike)",
                                     "Wind Stalker"))

    # ── Interest (45): % of Movement-Speed increase → additional Attack Damage, capped ──
    if "Interest" in picks and _enabled(slot_levels, _SLOT_45):
        t = _tier(slot_levels, _SLOT_45)
        amt = min(_INTEREST_RATE[t] * ms_total, _INTEREST_CAP[t])
        if amt != 0:
            contribs.append(_contrib("attack_dmg_additional", amt,
                                     f"Interest: +{amt * 100:.1f}% additional Attack Damage "
                                     f"({_INTEREST_RATE[t] * 100:.0f}% of {ms_total * 100:.0f}% MS, cap {_INTEREST_CAP[t] * 100:.0f}%)",
                                     "Interest"))

    # ── Have Fun (45): general additional Attack Speed (ALL attacks). The Lv10 Multistrike support is a virtual
    #    support injected server-side (see virtual_supports), so its chance/increment are slot-local to the main skill.
    if "Have Fun" in picks and _enabled(slot_levels, _SLOT_45):
        t = _tier(slot_levels, _SLOT_45)
        contribs.append(_contrib("attack_speed_additional", _HAVE_FUN_AS_ADDITIONAL[t],
                                 f"Have Fun: +{_HAVE_FUN_AS_ADDITIONAL[t] * 100:.0f}% additional Attack Speed", "Have Fun"))

    # ── Cat's Vision (60): flat additional damage (always, when picked). +Max Stalker handled via the cap above. ──
    if "Cat's Vision" in picks and _enabled(slot_levels, _SLOT_60):
        t = _tier(slot_levels, _SLOT_60)
        amt = _CATS_VISION_DMG[t]
        if amt != 0:
            contribs.append(_contrib("dmg_additional", amt,
                                     f"Cat's Vision: {amt * 100:+.0f}% additional damage", "Cat's Vision"))

    # ── Cat's Scratch (60): additional Multistrike Damage Increment (max count reached every chain → always on) ──
    if "Cat's Scratch" in picks and _enabled(slot_levels, _SLOT_60):
        t = _tier(slot_levels, _SLOT_60)
        contribs.append(_contrib("multistrike_increasing_dmg_additional", _CATS_SCRATCH_INC_ADDITIONAL[t],
                                 f"Cat's Scratch: +{_CATS_SCRATCH_INC_ADDITIONAL[t] * 100:.0f}% additional Multistrike damage increment",
                                 "Cat's Scratch"))

    # ── Cat's Punches (75, pick-one with Cat Dive): +1 Initial Multistrike Count per 3 Stalker stacks (hard steps
    #    of 3 → floor(stacks/3); pre-stacks the multistrike increment, adds no attacks) + a flat additional-damage
    #    bonus that is ALWAYS active (the line is not gated on multistriking). The "generates a Stalker stack at max
    #    count" clause is flavor — it does NOT raise the Stalker cap (owner-confirmed). ──
    if "Cat's Punches" in picks and _enabled(slot_levels, _SLOT_75):
        t = _tier(slot_levels, _SLOT_75)
        init = int(stalker_stacks // 3)
        if init > 0:
            contribs.append(_contrib("initial_multistrike_count_flat", float(init),
                                     f"Cat's Punches: +{init} Initial Multistrike Count "
                                     f"(1 per 3 Stalker stacks × {stalker_stacks:.0f})", "Cat's Punches"))
        dmg = _CATS_PUNCHES_DMG[t]
        if dmg != 0:
            contribs.append(_contrib("dmg_additional", dmg,
                                     f"Cat's Punches: {dmg * 100:+.0f}% additional damage", "Cat's Punches"))

    # ── Cat Dive (75): per-attack chance to count at the chain's max count = rate × Movement-Speed% ──
    if "Cat Dive" in picks and _enabled(slot_levels, _SLOT_75):
        t = _tier(slot_levels, _SLOT_75)
        q = _CAT_DIVE_PER_MS[t] * (ms_total * 100.0)
        if q > 0:
            contribs.append(_contrib("multistrike_max_count_proc_chance", q,
                                     f"Cat Dive: {q * 100:.1f}% chance to deal damage as the max Multistrike count "
                                     f"({_CAT_DIVE_PER_MS[t] * 100:.2f}%/1% MS × {ms_total * 100:.0f}% MS)", "Cat Dive"))

    return {"contributions": contribs}


def virtual_supports(*, slot_levels, advanced_picks, main_slot, **_):
    """Have Fun grants a free Lv10 Multistrike support to the MAIN skill (no UI slot). Returned as a virtual support
    so the existing support resolver produces its slot-local Multistrike chance + increment for the main slot."""
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    if "Have Fun" in picks and _enabled(slot_levels, _SLOT_45):
        return [{"item_id": HAVE_FUN_SUPPORT_ID, "slot": main_slot, "level": HAVE_FUN_SUPPORT_LEVEL,
                 "rank": 1, "enabled": True}]
    return []


def stash(*, source, ls_state, inflict_aps=None, **_):
    """Capture the converged Movement Speed total the next pass's Interest / Cat Dive need."""
    ls_state["movement_speed_inc"] = source.total("movement_speed_inc")


def status_lines(*, slot_levels, advanced_picks, **_):
    """One status row per trait line so every line is surfaced (never silently dropped)."""
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    out: list[dict] = []

    def working(text, source):
        out.append({"text": text, "source": source, "status": "working"})

    def info(text, source):
        out.append({"text": text, "source": source, "status": "informational"})

    def nyi(text, source):
        out.append({"text": text, "source": source, "status": "nyi"})

    working("+26% Movement Speed; Stalker → +additional damage during Multistrike (per stack); +additional Attack Damage by level",
            "Wind Stalker")
    info("Multistrike Count is not interrupted during Stalker (no DPS effect on a dummy)", "Wind Stalker")
    if abs((slot_levels or [1])[0]) >= 5:
        nyi("Artificial Moon: marks enemies (Mark debuff) — damage-taken effect not modeled yet", "Artificial Moon")
    if "Interest" in picks:
        working("Interest: a share of Movement Speed is also applied as additional Attack Damage (capped)", "Interest")
    if "Have Fun" in picks:
        working("Have Fun: the Main Skill is supported by a free Lv10 Multistrike + general additional Attack Speed", "Have Fun")
    if "Cat's Vision" in picks:
        working("Cat's Vision: +1 Max Stalker at max count (up to +3) + flat additional damage", "Cat's Vision")
    if "Cat's Scratch" in picks:
        working("Cat's Scratch: +additional Multistrike damage increment when the max count is reached", "Cat's Scratch")
    if "Cat's Punches" in picks:
        working("Cat's Punches: +1 Initial Multistrike Count per 3 Stalker stacks + flat additional damage (always active)", "Cat's Punches")
    if "Cat Dive" in picks:
        working("Cat Dive: chance per attack to deal damage as the chain's max Multistrike count (scales with Movement Speed)", "Cat Dive")
    return out
