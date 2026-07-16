"""Selena — Sing with the Tide (trait_id "sing_with_the_tide").

Built around **Tide** zones and a **Bard / Loud Song** state toggle. The DPS payoff is a set of additional-damage
buffs/debuffs that apply while you (and the enemy) stand on a Tide, all scaled by **Tide Effect** — a standard
effect scalar (`tide_mult = (1 + Σ tide_effect_inc) × Π(1 + tide_effect_additional)`, like Numbed Effect). The
trait's positional machinery (Bard Song channel, bubbles, Tide placement, movement, collisions, auto-channel
delivery) is spatial and not modelled on a stationary dummy — those lines are surfaced via `status_lines`
(never silently dropped).

Tyra-confirmed modeling (2026-06-22):
- Two SEPARATE state conditions (`selena_bard` default ON, `selena_loud_song` default OFF) — the UI toggle flips
  between them, but a future revival memory (Ceaseless Tide) enables BOTH at once, so they're independent.
- `player_on_tide` gates your buffs; `enemy_on_tide` gates the enemy damage-taken / "vs enemies on Tide" lines.
- Undersea Ballad converts GLOBAL Skill Area increase → INCREASED Tide Effect (`source.total("skill_area_inc")`
  excludes slot-local support skill area by construction). Sea Foam scales off channeled stacks (min counts ×2 in
  Bard, cap 5). Ramp picks (Idyll metres, Chantey seconds) are user-set conditions defaulting to max.
- Bard converts non-Channeled/Instant/Mobility skills to Bard Song (unusable) → surfaced as a WARNING naming the
  main skill (the bubble delivery itself is not modelled).
- Ceaseless Tide (future): forces Loud Song while Bard + removes the Loud Song speed penalties. The penalties are
  emitted behind a `ceaseless_tide` flag so that lands as a one-line change.
"""
from __future__ import annotations

TRAIT_ID = "sing_with_the_tide"

# ── Base trait ────────────────────────────────────────────────────────────────────
_TIDE_BASE_DMG = 0.15                                       # on-Tide +15% additional damage (you)
_ENEMY_TIDE_DMG_TAKEN = [0.0, 0.05, 0.10, 0.15, 0.20]      # +additional damage taken by enemies on Tide, by level
_LOUD_SONG_SPEED_PENALTY = -0.20                           # additional Attack/Cast/Movement Speed in Loud Song
_LOUD_SONG_TIDE_EFFECT = 0.80                              # +80% additional Tide Effect in Loud Song
_BARD_CHANNELED_PENALTY = -0.20                            # -20% additional Channeled Skill Damage in Bard
_ARTIFICIAL_MOON_SKILL_AREA = 0.10                        # base L5, on Tide
_ARTIFICIAL_MOON_DURATION = 0.15                          # base L5, on Tide
# ── Advanced picks (per tier 0-4) ───────────────────────────────────────────────────
_UNDERSEA_CAP = [0.90, 1.00, 1.10, 1.20, 1.30]            # cap on Skill-Area → Tide Effect (increased)
_WAVE_ARIA_DMG = [0.10, 0.13, 0.16, 0.19, 0.22]          # +additional damage vs enemies on Tide
_SEA_FOAM_PER_STACK = [0.16, 0.18, 0.20, 0.22, 0.24]     # +additional Tide Effect per ±1 channeled stack
_SEA_FOAM_MAX_STACKS = 5
_IDYLL_PER_STACK = [0.01, 0.013, 0.016, 0.019, 0.022]   # +additional damage per 1 m moved in Tide (max 15)
_CHANTEY_PER_STACK = [0.35, 0.45, 0.55, 0.65, 0.75]     # +additional Tide Effect per 1s in Loud Song (max 2)
_MURMURS_TIDE_EFFECT = [0.60, 0.70, 0.80, 0.90, 1.00]   # +additional Tide Effect in Bard

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
    if not _enabled(slot_levels, _SLOT_BASE):                # base node disabled → whole trait off
        return {"contributions": []}

    base_lvl = slot_levels[0] if slot_levels else 1
    bard = _flag(condition_state, "selena_bard", True)
    loud = _flag(condition_state, "selena_loud_song", False)
    player_tide = _flag(condition_state, "player_on_tide", True)
    enemy_tide = _flag(condition_state, "enemy_on_tide", True)

    # Converged scalars from the previous pass (empty first pass → tide_mult 1, picks 0; settles in a few passes).
    tide_mult = float(ls_state.get("tide_mult", 1.0))
    skill_area = float(ls_state.get("skill_area_inc", 0.0))
    max_ch = float(ls_state.get("max_channeled_stacks_flat", 0.0))
    min_ch = float(ls_state.get("min_channeled_stacks_flat", 0.0))

    c: list[dict] = []

    def add(stat, amt, text, source):
        c.append(_contrib(stat, amt, text, source))

    # ── Tide Effect contributions (folded into source; next pass scales the Tide damage) ──
    if loud:
        add("tide_effect_additional", _LOUD_SONG_TIDE_EFFECT, "Loud Song: +80% additional Tide Effect", "Loud Song")
    if "Undersea Ballad" in picks and _enabled(slot_levels, _SLOT_45):
        t = _tier(slot_levels, _SLOT_45)
        amt = min(skill_area, _UNDERSEA_CAP[t])
        if abs(amt) > 1e-9:
            add("tide_effect_inc", amt,
                f"Undersea Ballad: +{amt * 100:.0f}% Tide Effect (Skill Area, cap {_UNDERSEA_CAP[t] * 100:.0f}%)",
                "Undersea Ballad")
    if "Sea Foam Nocturne" in picks and _enabled(slot_levels, _SLOT_60):
        t = _tier(slot_levels, _SLOT_60)
        stacks = min(max_ch + min_ch * (2.0 if bard else 1.0), float(_SEA_FOAM_MAX_STACKS))
        if stacks > 0:
            add("tide_effect_additional", _SEA_FOAM_PER_STACK[t] * stacks,
                f"Sea Foam Nocturne: +{_SEA_FOAM_PER_STACK[t] * stacks * 100:.0f}% additional Tide Effect "
                f"({stacks:.0f} channeled stacks)", "Sea Foam Nocturne")
    if "Chantey of Sinking" in picks and _enabled(slot_levels, _SLOT_75) and loud:
        t = _tier(slot_levels, _SLOT_75)
        stacks = _num(condition_state, "chantey_stacks", 2.0, 0.0, 2.0)
        if stacks > 0:
            add("tide_effect_additional", _CHANTEY_PER_STACK[t] * stacks,
                f"Chantey of Sinking: +{_CHANTEY_PER_STACK[t] * stacks * 100:.0f}% additional Tide Effect "
                f"({stacks:.0f}s in Loud Song)", "Chantey of Sinking")
    if "Murmurs of the Distant Tide" in picks and _enabled(slot_levels, _SLOT_75) and bard:
        t = _tier(slot_levels, _SLOT_75)
        add("tide_effect_additional", _MURMURS_TIDE_EFFECT[t],
            f"Murmurs of the Distant Tide: +{_MURMURS_TIDE_EFFECT[t] * 100:.0f}% additional Tide Effect (Bard)",
            "Murmurs of the Distant Tide")

    # ── State penalties ──
    if loud and not _flag(condition_state, "ceaseless_tide", False):   # suppressed by the future Ceaseless Tide memory
        add("attack_speed_additional", _LOUD_SONG_SPEED_PENALTY, "Loud Song: -20% additional Attack Speed", "Loud Song")
        add("cast_speed_additional", _LOUD_SONG_SPEED_PENALTY, "Loud Song: -20% additional Cast Speed", "Loud Song")
        add("movement_speed_additional", _LOUD_SONG_SPEED_PENALTY, "Loud Song: -20% additional Movement Speed", "Loud Song")
    if bard:
        add("channeled_dmg_additional", _BARD_CHANNELED_PENALTY, "Bard: -20% additional Channeled Skill Damage", "Bard")

    # ── Your on-Tide damage (scaled by Tide Effect) ──
    if player_tide:
        add("dmg_additional", _TIDE_BASE_DMG * tide_mult,
            f"On Tide: +{_TIDE_BASE_DMG * tide_mult * 100:.0f}% additional damage (×Tide Effect)", "Tide")
        if "Idyll of the Tide" in picks and _enabled(slot_levels, _SLOT_60):
            t = _tier(slot_levels, _SLOT_60)
            stacks = _num(condition_state, "idyll_stacks", 15.0, 0.0, 15.0)
            amt = _IDYLL_PER_STACK[t] * stacks * tide_mult
            if amt > 0:
                add("dmg_additional", amt,
                    f"Idyll of the Tide: +{amt * 100:.1f}% additional damage ({stacks:.0f} m in Tide, ×Tide Effect)",
                    "Idyll of the Tide")
        if abs(base_lvl) >= 5:                              # Artificial Moon (base L5)
            add("skill_area_inc", _ARTIFICIAL_MOON_SKILL_AREA, "Artificial Moon: +10% Skill Area (on Tide)", "Artificial Moon")
            add("skill_effect_duration_inc", _ARTIFICIAL_MOON_DURATION, "Artificial Moon: +15% Skill Effect Duration (on Tide)", "Artificial Moon")

    # ── Enemy on-Tide debuffs (scaled by Tide Effect) ──
    if enemy_tide:
        lvl_base = _ENEMY_TIDE_DMG_TAKEN[_tier([base_lvl], 0)]
        if lvl_base > 0:
            add("tide_dmg_taken", lvl_base * tide_mult,
                f"Enemies on Tide: +{lvl_base * tide_mult * 100:.0f}% damage taken (×Tide Effect)", "Tide")
        if "Wave Aria" in picks and _enabled(slot_levels, _SLOT_45):
            t = _tier(slot_levels, _SLOT_45)
            amt = _WAVE_ARIA_DMG[t] * tide_mult
            add("dmg_additional", amt,
                f"Wave Aria: +{amt * 100:.0f}% additional damage vs enemies on Tide (×Tide Effect)", "Wave Aria")

    return {"contributions": c}


def stash(*, source, ls_state, inflict_aps=None, **_):
    """Capture the converged Tide-Effect multiplier + the scalars Undersea Ballad / Sea Foam read next pass."""
    from engine.offense import additional_total_product
    ls_state["tide_mult"] = ((1.0 + source.total("tide_effect_inc"))
                             * additional_total_product(source, "tide_effect_additional"))
    ls_state["skill_area_inc"] = source.total("skill_area_inc")            # global only (excludes slot-local supports)
    ls_state["max_channeled_stacks_flat"] = source.total("max_channeled_stacks_flat")
    ls_state["min_channeled_stacks_flat"] = source.total("min_channeled_stacks_flat")


_CHANNEL_OK_TAGS = {"channeled", "mobility", "instant"}


def status_lines(*, slot_levels, advanced_picks, main_skill_tags=None, main_skill_name=None, **_):
    """One row per trait line (working / informational / warning). `main_skill_tags` lets us warn when the main
    skill is converted to Bard Song in the Bard state (non-Channeled/Instant/Mobility skills can't be used)."""
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    out: list[dict] = []

    def working(text, source):
        out.append({"text": text, "source": source, "status": "working"})

    def info(text, source):
        out.append({"text": text, "source": source, "status": "informational"})

    def warn(text, source):
        out.append({"text": text, "source": source, "status": "warning"})

    working("On Tide: +15% additional damage (you) + enemies on Tide take +damage by level — scaled by Tide Effect",
            "Sing with the Tide")
    working("Loud Song: -20% additional Attack/Cast/Movement Speed, +80% additional Tide Effect", "Loud Song")
    working("Bard: -20% additional Channeled Skill Damage", "Bard")
    info("Bard: move while channeling; main skill auto-channels while moving; Tide placement / bubbles / 6s Tide are spatial",
         "Bard")

    # Warn when the equipped main skill would be converted to Bard Song (deals no direct DPS) in the Bard state.
    if main_skill_tags is not None:
        tags = {str(t).lower() for t in (main_skill_tags or [])}
        is_attack_or_spell = bool(tags & {"attack", "spell"})
        if is_attack_or_spell and not (tags & _CHANNEL_OK_TAGS):
            name = main_skill_name or "the main skill"
            warn(f"In Bard, {name} is non-Channeled/Instant/Mobility → converted to Bard Song (no direct DPS). "
                 f"Use a Channeled/Instant/Mobility skill, or switch to Loud Song.", "Bard")

    if abs((slot_levels or [1])[0]) >= 5:
        info("Artificial Moon: +10% Skill Area, +15% Skill Effect Duration on Tide", "Artificial Moon")
    if "Undersea Ballad" in picks:
        working("Undersea Ballad: Skill Area increase → increased Tide Effect (capped); Tide area no longer scales with Skill Area",
                "Undersea Ballad")
    if "Wave Aria" in picks:
        working("Wave Aria: +additional damage vs enemies on Tide", "Wave Aria")
        info("Wave Aria: in Bard, you leave a Tide along your path instead of from the bubble (spatial)", "Wave Aria")
    if "Sea Foam Nocturne" in picks:
        working("Sea Foam Nocturne: +additional Tide Effect per ±1 channeled stack (min ×2 in Bard, up to 5)", "Sea Foam Nocturne")
    if "Idyll of the Tide" in picks:
        working("Idyll of the Tide: +additional damage per metre moved in the Tide (up to 15)", "Idyll of the Tide")
        info("Idyll of the Tide: auto-switch to Bard after losing all Tides (spatial)", "Idyll of the Tide")
    if "Chantey of Sinking" in picks:
        working("Chantey of Sinking: +Tide Effect per second in Loud Song (up to 2); +Tide Area is spatial", "Chantey of Sinking")
    if "Murmurs of the Distant Tide" in picks:
        working("Murmurs of the Distant Tide: +additional Tide Effect in Bard (−Tide Duration is spatial)", "Murmurs of the Distant Tide")
    return out
