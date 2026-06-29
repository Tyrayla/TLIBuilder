"""Rosa — Unsullied Blade (trait_id "unsullied_blade").

A mana-scaling, state-cycling ATTACK trait. Two engine-new mechanics live in offense (a Spell→Attack damage bridge
via `spell_dmg_to_attack`, and the Mercury Baptism true-damage stage via `mercury_baptism_fraction`); this module
emits the trait's stat contributions and the dominant-element Infiltration.

Owner-confirmed (2026-06-23):
- Spell DAMAGE bonuses also apply to attacks (base flag).
- Realm of Mercury (default ON, full uptime) gives +2% additional Attack Speed + +2% additional Elemental Damage per
  10% UNSEALED Max Mana, capped +20%/+20% (drops as you reserve mana — `unsealed_mana` plumbed from compute.py).
- Mercury Baptism records 12-44% of elemental attack hit damage → true damage; inflicts the dominant element's
  Infiltration (set via `set_conditions`).
- Base Max Mercury Points = 100; Utmost Devotion scales it and reads it for its per-point Elemental Damage.
- Born to Cleanse: Mystic +25% additional Ele (40% retained in Realm) + main-hand additional damage.
"""
from __future__ import annotations

TRAIT_ID = "unsullied_blade"

# ── Base trait (by base level 1-5) ─────────────────────────────────────────────────
_SPELL_DMG_ADD = [0.0, 0.05, 0.10, 0.15, 0.20]            # L2-5 additional Spell Damage (bridges to attacks)
_REALM_PER_10PCT = 0.02                                    # +2% add AS + +2% add Ele per 10% unsealed mana
_REALM_MAX_INCREMENTS = 10                                 # cap +20%/+20%
_BASE_MAX_MERCURY = 100.0
# ── Advanced picks (per tier 0-4) ───────────────────────────────────────────────────
_BAPTISM_FRACTION = [0.12, 0.20, 0.28, 0.36, 0.44]       # Baptism of Purity: recorded % of elemental hit damage
_BAPTISM_MAX_MANA_ADD = 0.20                              # +20% additional Max Mana
_CLEANSE_MANA_BEFORE_LIFE = 0.25                          # 25% of damage from Mana before Life
_CLEANSE_ELE_PER_1000 = [0.02, 0.025, 0.03, 0.035, 0.04]  # additional Ele per 1000 Max Mana
_CLEANSE_ELE_CAP = [0.40, 0.50, 0.60, 0.70, 0.80]
_BOUNDLESS_ELE_PER_ENEMY = [0.06, 0.07, 0.08, 0.09, 0.10]  # additional Ele per (weighted) enemy in Realm
_BOUNDLESS_ELE_CAP = [0.60, 0.70, 0.80, 0.90, 1.00]
_UTMOST_MAX_MERCURY_PER_1000 = 0.10                      # +10% Max Mercury Pts per 1000 Max Mana
_UTMOST_MAX_MERCURY_CAP = [2.0, 2.5, 3.0, 3.5, 4.0]
_UTMOST_ELE_PER_POINT = [0.0008, 0.0008, 0.001, 0.001, 0.001]  # additional Ele per Mercury Pt
_BORN_ELE_MYSTIC = 0.25                                   # Mystic +25% additional Ele
_BORN_REALM_RETAIN = 0.40                                 # Mystic effects retain 40% in Realm
_BORN_MAINHAND = [0.20, 0.27, 0.34, 0.41, 0.48]         # additional Main-Hand Weapon damage (Mystic)

_SLOT_BASE, _SLOT_45, _SLOT_60, _SLOT_75 = 0, 1, 2, 3


def _contrib(stat_key, amount, text, source):
    return {"stat_key": stat_key, "amount": amount, "text": text, "source": source}


def _tier(slot_levels, idx):
    lvl = slot_levels[idx] if idx < len(slot_levels) else 1
    return max(0, min(4, int(abs(lvl)) - 1))


def _enabled(slot_levels, idx):
    lvl = slot_levels[idx] if idx < len(slot_levels) else 1
    return lvl >= 1


def _flag(condition_state, key, default):
    v = condition_state.get(key, default)
    return bool(v) if v is not None else default


def _num(condition_state, key, default, lo, hi):
    raw = condition_state.get(key)
    v = default if raw is None else float(raw)
    return max(lo, min(v, hi))


def apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks, **_):
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    if not _enabled(slot_levels, _SLOT_BASE):                # base node disabled → trait off
        return {"contributions": []}

    base_lvl = slot_levels[0] if slot_levels else 1
    # Two mutually-exclusive phases. Mystic Mercury (build-up) consumes Mana; Realm of Mercury (DPS state, default)
    # restores Mana and grants the damage bonuses. `mystic` overrides → `realm` (used as "in Realm" by every bonus
    # gate below) is true only when realm is toggled on AND we're not in the Mystic build-up phase.
    mystic = _flag(condition_state, "mystic_mercury", False)
    realm = _flag(condition_state, "realm_of_mercury", True) and not mystic
    enemies = _num(condition_state, "enemies_in_realm", 1.0, 0.0, 50.0)
    mercury_pct = _num(condition_state, "mercury_points", 100.0, 0.0, 100.0) / 100.0

    # Converged scalars (compute.py plumbs max/unsealed mana after reservation; stash captures the rest).
    max_mana = float(ls_state.get("max_mana", 0.0))
    unsealed = float(ls_state.get("unsealed_mana", max_mana))
    unsealed_frac = (unsealed / max_mana) if max_mana > 0.0 else 1.0
    mm_flat = float(ls_state.get("max_mercury_points_flat", _BASE_MAX_MERCURY))
    mm_inc = float(ls_state.get("max_mercury_points_inc", 0.0))
    dominant = ls_state.get("dominant_element") or "fire"

    from engine.offense import TARGET_ENEMY_COUNT_WEIGHT
    weight = float(condition_state.get("enemy_count_weight") or TARGET_ENEMY_COUNT_WEIGHT)
    weighted_enemies = enemies * weight

    c: list[dict] = []
    set_conditions: dict = {}

    def add(stat, amt, text, source="Unsullied Blade"):
        c.append(_contrib(stat, amt, text, source))

    utmost = "Utmost Devotion" in picks and _enabled(slot_levels, _SLOT_75)

    # ── Base trait ──
    add("spell_dmg_to_attack", 1.0, "Spell Damage bonuses also apply to Attack Damage", "Unsullied Blade")
    add("max_mercury_points_flat", _BASE_MAX_MERCURY, "Base Max Mercury Points: 100", "Unsullied Blade")
    if not utmost:    # Utmost Devotion lifts the "only Mystic Mercury consumes Mana" lock → other consumers work again
        # NOT skill cost — a CONSUME lock: while set, the consumption stage zeroes every other mana-consume source
        # (Unsullied's own Mystic consume bypasses it). Emitted only here, so it can't affect any non-Rosa-2 build.
        add("mana_consume_external_blocked", 1.0, "Mana can only be consumed by Mystic Mercury", "Mystic Mercury")
    sd = _SPELL_DMG_ADD[_tier([base_lvl], 0)]
    if sd > 0:
        add("spell_dmg_additional", sd, f"+{sd * 100:.0f}% additional Spell Damage (applies to attacks)", "Unsullied Blade")
    if realm:
        incs = min(int(unsealed_frac * 10.0 + 1e-9), _REALM_MAX_INCREMENTS)
        amt = _REALM_PER_10PCT * incs
        if amt > 0:
            add("attack_speed_additional", amt, f"Realm of Mercury: +{amt * 100:.0f}% additional Attack Speed ({incs}×10% unsealed mana)", "Realm of Mercury")
            add("elemental_dmg_additional", amt, f"Realm of Mercury: +{amt * 100:.0f}% additional Elemental Damage ({incs}×10% unsealed mana)", "Realm of Mercury")

    # ── Mana cycle (per non-Channeled attack USE) — flows through the consumption / recovery subsystems ──
    # Mystic phase CONSUMES, Realm phase RESTORES (the two never overlap). Both are % of unsealed Max Mana; the engine
    # uses % of current unreserved mana × the attack-use rate (exact at full mana).
    if mystic:
        # 10% of unsealed Max Mana consumed per non-Channeled attack use (the "1% if insufficient" fallback is not
        # modelled). Routed through the lock-bypass stat so the "only Mystic consumes" lock keeps this one.
        add("mana_consumed_pct_current_per_attack_use_mystic", 0.10,
            "Mystic Mercury: consumes 10% of unsealed Max Mana per non-Channeled Attack use", "Mystic Mercury")
    if realm:
        born = "Born to Cleanse" in picks and _enabled(slot_levels, _SLOT_75)
        restore = 0.15 * (1.0 + (-0.30 if born else 0.0))   # Born to Cleanse: −30% additional Mana restoration (Realm)
        add("mana_restored_pct_current_per_attack_use", restore,
            f"Realm of Mercury: restores {restore * 100:.1f}% of unsealed Max Mana per non-Channeled Attack use"
            + (" (Born to Cleanse −30% additional)" if born else ""), "Realm of Mercury")

    # ── Baptism of Purity (L45 slot — the only L45 node) ──
    if _enabled(slot_levels, _SLOT_45):
        add("max_mana_additional", _BAPTISM_MAX_MANA_ADD, "Baptism of Purity: +20% additional Max Mana", "Baptism of Purity")
        if realm:
            frac = _BAPTISM_FRACTION[_tier(slot_levels, _SLOT_45)]
            add("mercury_baptism_fraction", frac, f"Mercury Baptism: records {frac * 100:.0f}% of elemental attack hit damage (true damage)", "Baptism of Purity")
            set_conditions[f"enemy_affected_by_{dominant}_infiltration"] = True

    # ── Cleanse Filth (L60 pick) ──
    if "Cleanse Filth" in picks and _enabled(slot_levels, _SLOT_60) and realm:
        t = _tier(slot_levels, _SLOT_60)
        add("mana_before_life_inc", _CLEANSE_MANA_BEFORE_LIFE, "Cleanse Filth: 25% of damage taken from Mana before Life", "Cleanse Filth")
        ele = min(_CLEANSE_ELE_PER_1000[t] * (max_mana / 1000.0), _CLEANSE_ELE_CAP[t])
        if ele > 0:
            add("elemental_dmg_additional", ele, f"Cleanse Filth: +{ele * 100:.1f}% additional Elemental Damage ({max_mana:.0f} Max Mana, cap {_CLEANSE_ELE_CAP[t] * 100:.0f}%)", "Cleanse Filth")

    # ── Boundless Sanctuary (L60 pick) ──
    if "Boundless Sanctuary" in picks and _enabled(slot_levels, _SLOT_60) and realm:
        t = _tier(slot_levels, _SLOT_60)
        ele = min(_BOUNDLESS_ELE_PER_ENEMY[t] * weighted_enemies, _BOUNDLESS_ELE_CAP[t])
        if ele > 0:
            add("elemental_dmg_additional", ele, f"Boundless Sanctuary: +{ele * 100:.1f}% additional Elemental Damage ({_BOUNDLESS_ELE_PER_ENEMY[t] * 100:.0f}%/enemy ×{weighted_enemies:.0f}, cap {_BOUNDLESS_ELE_CAP[t] * 100:.0f}%)", "Boundless Sanctuary")

    # ── Utmost Devotion (L75 pick) ──
    if utmost:
        t = _tier(slot_levels, _SLOT_75)
        mm_bonus = min(_UTMOST_MAX_MERCURY_PER_1000 * (max_mana / 1000.0), _UTMOST_MAX_MERCURY_CAP[t])
        if mm_bonus > 0:
            add("max_mercury_points_inc", mm_bonus, f"Utmost Devotion: +{mm_bonus * 100:.0f}% Max Mercury Points ({max_mana:.0f} Max Mana, cap {_UTMOST_MAX_MERCURY_CAP[t] * 100:.0f}%)", "Utmost Devotion")
        max_mercury = mm_flat * (1.0 + mm_inc)               # converged max (from this trait's own emitted stats)
        current = max_mercury * mercury_pct
        ele = _UTMOST_ELE_PER_POINT[t] * current
        if ele > 0:
            add("elemental_dmg_additional", ele, f"Utmost Devotion: +{ele * 100:.1f}% additional Elemental Damage ({current:.0f} Mercury Points)", "Utmost Devotion")

    # ── Born to Cleanse (L75 pick) — Mystic effects, 40% retained in Realm ──
    if "Born to Cleanse" in picks and _enabled(slot_levels, _SLOT_75):
        t = _tier(slot_levels, _SLOT_75)
        retain = _BORN_REALM_RETAIN if realm else 1.0
        where = "Realm 40%" if realm else "Mystic"
        add("elemental_dmg_additional", _BORN_ELE_MYSTIC * retain, f"Born to Cleanse: +{_BORN_ELE_MYSTIC * retain * 100:.0f}% additional Elemental Damage ({where})", "Born to Cleanse")
        mh = _BORN_MAINHAND[t] * retain
        add("main_hand_dmg_additional", mh, f"Born to Cleanse: +{mh * 100:.0f}% additional Main-Hand Weapon damage ({where})", "Born to Cleanse")

    return {"contributions": c, "set_conditions": set_conditions}


def stash(*, source, ls_state, inflict_aps=None, **_):
    """Capture converged Max Mercury Points stats + the dominant elemental damage type (for Mercury Baptism's
    Infiltration). Max/Unsealed Mana are plumbed from compute.py after reservation, not here."""
    ls_state["max_mercury_points_flat"] = source.total("max_mercury_points_flat")
    ls_state["max_mercury_points_inc"] = source.total("max_mercury_points_inc")
    best, best_t = 0.0, None
    for t in ("fire", "cold", "lightning"):
        v = (source.total(f"{t}_dmg_inc") + source.total(f"{t}_dmg_additional")
             + source.total(f"{t}_dmg_gear_flat_min") + source.total(f"{t}_attack_dmg_flat_min"))
        if v > best:
            best, best_t = v, t
    ls_state["dominant_element"] = best_t


def status_lines(*, slot_levels, advanced_picks, **_):
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    out: list[dict] = []

    def working(text, source):
        out.append({"text": text, "source": source, "status": "working"})

    def info(text, source):
        out.append({"text": text, "source": source, "status": "informational"})

    working("Spell Damage bonus + additional also apply to Attack Damage", "Unsullied Blade")
    working("Per base level: +5/10/15/20% additional Spell Damage", "Unsullied Blade")
    working("Realm of Mercury: +2% additional Attack Speed + Elemental Damage per 10% unsealed Max Mana (cap +20%)", "Realm of Mercury")
    working("Mana cycle (per non-Channeled Attack use): Mystic Mercury consumes 10% of unsealed Max Mana; Realm of Mercury restores 15%. Toggle the Mystic Mercury phase to model build-up (default = Realm)", "Unsullied Blade")
    working("Mana can only be consumed by Mystic Mercury — other mana consumers are blocked (Utmost Devotion lifts this)", "Mystic Mercury")
    info("Realm of Mercury consumes 30 Mercury Points/s (Mercury-point economy not simulated)", "Unsullied Blade")
    info("Artificial Moon: +Attack Speed per Mercury Baptism — not yet modelled (pending in-game verification)", "Artificial Moon")
    if _enabled(slot_levels, _SLOT_45):
        working("Baptism of Purity: +20% additional Max Mana; Mercury Baptism deals true damage from your elemental attack damage; inflicts the dominant element's Infiltration", "Baptism of Purity")
    if "Cleanse Filth" in picks:
        working("Cleanse Filth: +additional Elemental Damage per 1000 Max Mana (capped); 25% of damage taken from Mana before Life", "Cleanse Filth")
    if "Boundless Sanctuary" in picks:
        working("Boundless Sanctuary: +additional Elemental Damage per enemy in Realm (Boss ×5, capped)", "Boundless Sanctuary")
        info("Boundless Sanctuary: +Realm Area per Max Mana; +Mercury Points on kill (spatial / resource)", "Boundless Sanctuary")
    if "Utmost Devotion" in picks:
        working("Utmost Devotion: +additional Elemental Damage per Mercury Point (Max Mercury Points scale with Max Mana); lifts the Mystic-Mercury mana-consumption override", "Utmost Devotion")
    if "Born to Cleanse" in picks:
        working("Born to Cleanse: Mystic +25% additional Elemental Damage + additional Main-Hand Weapon damage (40% retained in Realm)", "Born to Cleanse")
        working("Born to Cleanse: −30% additional Mana restoration for Realm of Mercury (folded into the per-use restore)", "Born to Cleanse")
    return out
