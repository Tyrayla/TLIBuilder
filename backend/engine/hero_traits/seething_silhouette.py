"""Rehan — Seething Silhouette (trait_id "seething_silhouette").

Built around Rage (a Berserker-exclusive resource, glossary id 614, cap 100) and, on two advanced
picks, Seething Spirit (glossary id 638) — an ancestor spirit that casts the player's own
Non-Mobility, Non-Channeled Main Melee Attack Skill on its own cadence. Rage and Seething Spirit
are DIFFERENT things: Rage is a resource, Seething Spirit is a damage-dealing entity.

Tyra-confirmed modeling (2026-09-03):
- Rage is NOT simulated. `rage_amount` (0-100, default 100) and `berserk_active` (bool, default
  True) are plain user-set conditions — every Rage generation/drain clause is informational text.
  Both are named generically (not trait-prefixed) since Rehan's other Rage trait, "Anger"
  (rehan1), would read the same character-level resource if it's ever implemented.
- "Gains bonuses twice the Max Rage while Berserk is active" only affects the two Rage-scaled
  lines (Attack Speed per Rage; Artificial Moon's Double Damage chance) — modeled as
  `effective_rage = rage_amount * (2 if berserk_active else 1)`, everything else reads
  `rage_amount`/`berserk_active` directly.
- The Attack-Speed-per-Rage line is ALWAYS active (independent of Berserk state) — confirmed
  against the base tooltip's own placement of that clause.
- Seething Spirit's own DPS (Ritual of Offering's permanent Spirit; Fury's Onslaught's
  use-triggered Spirit) and Ritual of Offering's player-Disarm zero-out are NOT modeled here.
  `apply()` runs pre-offense (inside the stat-aggregation loop) and cannot zero or derive from an
  already-resolved main-skill `OffenseResult` — that needs a new post-offense compute.py pass
  (a `StatResult.spirit_offense` sibling field, mirroring how `minion_offense` is computed),
  scoped as a separate follow-up. Surfaced here as explicit `warning`/`informational` status rows,
  never silently dropped. Ritual of Offering's own tiered +Spirit Damage and Fury's Onslaught's
  -30% Spirit Attack Speed are Spirit-only modifiers — also deferred to that follow-up, not
  applied to the player's own stats.
- No `_catalog` season-catalog lookups: this is a first-time implementation off current SS13 data
  (not a season-drift fix), so per-tier values are plain literals, matching the more common
  module convention (e.g. `wind_stalker.py`) rather than the 3 modules confirmed to need
  live-catalog reads.

Values are the SS13 `_hero_traits.json` constants, indexed by node tier (level 1-5 -> index 0-4).
Advanced "pick" traits apply only when selected (their name is in `advanced_picks`) and their
node is enabled.
"""
from __future__ import annotations

TRAIT_ID = "seething_silhouette"

# ── Base trait (by base level 1-5) ──────────────────────────────────────────────
_BASE_MOVEMENT_SPEED = 0.20                                # +20% Movement Speed while Berserk is active
_BASE_SKILL_AREA = 0.45                                     # +45% Skill Area while Berserk is active
_BASE_DMG_BERSERK = [0.20, 0.26, 0.32, 0.38, 0.44]          # +X% additional damage while Berserk is active
_AS_PER_5_RAGE = 0.01                                       # +1% Attack Speed for every 5 (effective) Rage — always active
_ARTIFICIAL_MOON_DD_PER_5_RAGE = 0.01                       # Artificial Moon: +1% Double Damage chance per 5 (effective) Rage

# ── Advanced picks ────────────────────────────────────────────────────────────────
_RITUAL_OF_OFFERING_MS = -0.30                              # -30% Movement Speed while Berserk is active (flat, all tiers)
_FURYS_ONSLAUGHT_PLAYER_DMG = [0.50, 0.57, 0.64, 0.71, 0.78]  # +X% additional damage dealt by the player, while Berserk
_HYSTERIA_PER_MISSING_LIFE = [0.003, 0.004, 0.005, 0.006, 0.007]  # +X% additional Attack Damage per 1% Missing Life
_SPLIT_FORM_MAX_LIFE = [-0.15, -0.10, -0.05, 0.0, 0.05]     # signed +X% additional Max Life
_RAGE_INFUSION_CAP = [4, 5, 6, 7, 8]                        # max Rage Infusion stacks by tier
_RAGE_INFUSION_PER_STACK = 0.05                             # +5% additional damage per stack (flat, all tiers)

# Node -> slot_levels index. trait_slot_levels = [base, lv45, lv60, lv75].
_SLOT_BASE, _SLOT_45, _SLOT_60, _SLOT_75 = 0, 1, 2, 3

_CHANNEL_OK_TAGS = {"channeled", "mobility"}


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


def apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks, **_):
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    contribs: list[dict] = []

    base_lvl = slot_levels[0] if slot_levels else 1
    base_on = _enabled(slot_levels, _SLOT_BASE)

    rage = max(0.0, min(100.0, float(condition_state.get("rage_amount", 100.0) or 0.0)))
    berserk = _flag(condition_state, "berserk_active", True)
    effective_rage = rage * (2.0 if berserk else 1.0)

    if base_on:
        # Always active, independent of Berserk state.
        as_bonus = _AS_PER_5_RAGE * (effective_rage / 5.0)
        if as_bonus > 0:
            contribs.append(_contrib("attack_speed_inc", as_bonus,
                                     f"Seething Silhouette: +{as_bonus * 100:.1f}% Attack Speed "
                                     f"(1%/5 Rage x {effective_rage:.0f} effective Rage)", "Seething Silhouette"))

        if berserk:
            contribs.append(_contrib("movement_speed_inc", _BASE_MOVEMENT_SPEED,
                                     f"Seething Silhouette: +{_BASE_MOVEMENT_SPEED * 100:.0f}% Movement Speed "
                                     f"(Berserk)", "Seething Silhouette"))
            contribs.append(_contrib("skill_area_inc", _BASE_SKILL_AREA,
                                     f"Seething Silhouette: +{_BASE_SKILL_AREA * 100:.0f}% Skill Area (Berserk)",
                                     "Seething Silhouette"))
            dmg = _BASE_DMG_BERSERK[_tier([base_lvl], 0)]
            contribs.append(_contrib("dmg_additional", dmg,
                                     f"Seething Silhouette: +{dmg * 100:.0f}% additional damage (Berserk)",
                                     "Seething Silhouette"))

        # ── Artificial Moon (base L5): +Double Damage chance per 5 effective Rage — always active ──
        if abs(base_lvl) >= 5:
            dd = _ARTIFICIAL_MOON_DD_PER_5_RAGE * (effective_rage / 5.0)
            if dd > 0:
                contribs.append(_contrib("double_dmg_chance", dd,
                                         f"Artificial Moon: +{dd * 100:.1f}% Double Damage chance "
                                         f"(1%/5 Rage x {effective_rage:.0f} effective Rage)", "Artificial Moon"))

    # ── Ritual of Offering (45): -30% Movement Speed while Berserk. Seething Spirit's own damage
    #    and the player-Disarm zero-out are NOT modeled here — see module docstring. ──
    if "Ritual of Offering" in picks and _enabled(slot_levels, _SLOT_45) and berserk:
        contribs.append(_contrib("movement_speed_inc", _RITUAL_OF_OFFERING_MS,
                                 f"Ritual of Offering: {_RITUAL_OF_OFFERING_MS * 100:.0f}% Movement Speed "
                                 f"(Berserk)", "Ritual of Offering"))

    # ── Fury's Onslaught (45): +additional damage dealt by the player, while Berserk. Seething
    #    Spirit's own damage/Attack Speed are NOT modeled here — see module docstring. ──
    if "Fury's Onslaught" in picks and _enabled(slot_levels, _SLOT_45) and berserk:
        t = _tier(slot_levels, _SLOT_45)
        dmg = _FURYS_ONSLAUGHT_PLAYER_DMG[t]
        contribs.append(_contrib("dmg_additional", dmg,
                                 f"Fury's Onslaught: +{dmg * 100:.0f}% additional damage (Berserk)",
                                 "Fury's Onslaught"))

    # ── Hysteria (60): +additional Attack Damage per 1% Missing Life. Not Berserk-gated. ──
    if "Hysteria" in picks and _enabled(slot_levels, _SLOT_60):
        t = _tier(slot_levels, _SLOT_60)
        life_lost = float(condition_state.get("life_lost_pct", 0.0) or 0.0)
        amt = _HYSTERIA_PER_MISSING_LIFE[t] * life_lost
        if amt > 0:
            contribs.append(_contrib("attack_dmg_additional", amt,
                                     f"Hysteria: +{amt * 100:.2f}% additional Attack Damage "
                                     f"({_HYSTERIA_PER_MISSING_LIFE[t] * 100:.2f}%/1% Missing Life x "
                                     f"{life_lost:.0f}% missing)", "Hysteria"))

    # ── Split Form (75): signed +additional Max Life. Not Berserk-gated. ──
    if "Split Form" in picks and _enabled(slot_levels, _SLOT_75):
        t = _tier(slot_levels, _SLOT_75)
        amt = _SPLIT_FORM_MAX_LIFE[t]
        if amt != 0:
            contribs.append(_contrib("max_life_additional", amt,
                                     f"Split Form: {amt * 100:+.0f}% additional Max Life", "Split Form"))

    # ── Rage Infusion (75): +additional damage per stack of "Rage gained recently" (user-set,
    #    defaults to the tier's cap). Not Berserk-gated. ──
    if "Rage Infusion" in picks and _enabled(slot_levels, _SLOT_75):
        t = _tier(slot_levels, _SLOT_75)
        cap = float(_RAGE_INFUSION_CAP[t])
        raw = condition_state.get("rage_infusion_stacks")
        stacks = cap if raw is None else max(0.0, min(float(raw), cap))
        amt = _RAGE_INFUSION_PER_STACK * stacks
        if amt > 0:
            contribs.append(_contrib("dmg_additional", amt,
                                     f"Rage Infusion: +{amt * 100:.0f}% additional damage "
                                     f"({_RAGE_INFUSION_PER_STACK * 100:.0f}%/stack x {stacks:.0f}, cap {cap:.0f})",
                                     "Rage Infusion"))

    return {"contributions": contribs}


def status_lines(*, slot_levels, advanced_picks, main_skill_tags=None, main_skill_name=None, **_):
    """One status row per trait line so every line is surfaced (never silently dropped)."""
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    out: list[dict] = []

    def working(text, source):
        out.append({"text": text, "source": source, "status": "working"})

    def info(text, source):
        out.append({"text": text, "source": source, "status": "informational"})

    def warn(text, source):
        out.append({"text": text, "source": source, "status": "warning"})

    base_lvl = slot_levels[0] if slot_levels else 1

    working("+Attack Speed per 5 (effective) Rage — always active", "Seething Silhouette")
    info("Each Melee Attack Skill use generates 10 Rage when not in Berserk; auto-enters Berserk at Max Rage",
         "Seething Silhouette")
    working("While Berserk is active: +20% Movement Speed, +45% Skill Area, +additional damage by level",
            "Seething Silhouette")
    info("Bonuses that scale with Rage use 2x Max Rage while Berserk is active (modeled as doubled effective Rage)",
         "Seething Silhouette")
    info("While Berserk is active: 10 Rage/s consumed; Melee Attack Skill use consumes 10 Rage instead of "
         "generating it; Berserk ends when Rage runs out", "Seething Silhouette")
    if abs(base_lvl) >= 5:
        working("Artificial Moon: +Double Damage chance per 5 (effective) Rage", "Artificial Moon")

    # Warn when the equipped main skill doesn't qualify as a melee Attack skill at all — Rage
    # generation only needs "a Melee Attack Skill" (no Mobility/Channeled restriction in the base
    # tooltip). Seething Spirit (glossary 638) is the one that additionally requires Non-Mobility,
    # Non-Channeled — call that out only when a Spirit-granting pick is actually selected.
    if main_skill_tags is not None:
        tags = {str(t).lower() for t in (main_skill_tags or [])}
        is_attack = "attack" in tags
        is_melee = "melee" in tags
        name = main_skill_name or "the main skill"
        if not (is_attack and is_melee):
            warn(f"{name} is not a melee Attack Skill — Seething Silhouette's Rage generation requires one.",
                 "Seething Silhouette")
        elif (tags & _CHANNEL_OK_TAGS) and ({"Ritual of Offering", "Fury's Onslaught"} & picks):
            warn(f"{name} is Channeled or a Mobility skill — Seething Spirit requires a Non-Mobility, "
                 f"Non-Channeled melee Attack Skill and will not cast it.", "Seething Silhouette")

    if "Ritual of Offering" in picks:
        warn("Ritual of Offering: Seething Spirit's own damage and the player-Disarm zero-out while Berserk "
             "are NOT YET MODELED — pending a Seething Spirit engine pass. -30% Movement Speed is modeled.",
             "Ritual of Offering")
        info("Ritual of Offering: while Berserk, takes 1% of current Life as Secondary Physical Damage every "
             "0.2s (unaffected by bonuses) — defensive, not modeled (DPS calculator)", "Ritual of Offering")
    if "Fury's Onslaught" in picks:
        warn("Fury's Onslaught: Seething Spirit's own damage/-30% Attack Speed are NOT YET MODELED — pending "
             "a Seething Spirit engine pass. The player's own +additional damage is modeled.", "Fury's Onslaught")
        info("Fury's Onslaught: Rage no longer naturally consumed while Berserk; Melee Attack Skill Rage cost "
             "halved — not simulated (Rage isn't modeled)", "Fury's Onslaught")
    if "Hysteria" in picks:
        working("Hysteria: +additional Attack Damage per 1% Missing Life", "Hysteria")
        info("Hysteria: generates Rage on taking damage / on Max Life consumed — not simulated", "Hysteria")
    if "Growing Anger" in picks:
        if not ({"Ritual of Offering", "Fury's Onslaught"} & picks):
            warn("Growing Anger requires a Seething Spirit (Ritual of Offering or Fury's Onslaught) to trigger "
                 "off of — neither is selected, so this pick currently does nothing.", "Growing Anger")
        info("Growing Anger: +Rage when Seething Spirit uses a skill (doubled on Double Damage) — not simulated",
             "Growing Anger")
    if "Split Form" in picks:
        working("Split Form: signed +additional Max Life", "Split Form")
        info("Split Form: Life Regain no longer requires a hit to activate (defensive, not modeled); "
             "+Rage gained per 40 Max Life — not simulated", "Split Form")
    if "Rage Infusion" in picks:
        working("Rage Infusion: +additional damage per stack of Rage gained recently (user-set, defaults to cap)",
                "Rage Infusion")
        info("Rage Infusion: no longer Disarmed after Berserk has been active for 5s (interacts with Ritual of "
             "Offering's Disarm — not modeled until the Disarm zero-out lands); +40% Rage gained — not simulated",
             "Rage Infusion")

    return out
