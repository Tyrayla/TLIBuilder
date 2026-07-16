"""Rosa — High Court Chariot (trait_id "high_court_chariot").

Payoff is conditional / per-resource *additional damage* while inside the Holy Domain, plus (Desperation) a
**No Guard** enemy debuff. Values below are the SS12 `_hero_traits.json` constants, indexed by trait tier
(level 1-5 → index 0-4). Advanced "pick-one" traits apply only when selected.

Scenario inputs are user-set conditions (`inside_holy_domain` default ON, `murderous_intent` 0-100 default 100,
`enemies_in_holy_domain` default 1, `improvision_active` default OFF). Murderous-Intent regen/restore lines are
informational (surfaced, not computed). The "for each enemy in the Holy Domain" lines scale on the Enemy-Count
*weighted* total — the calc target (training dummy) is a Boss → ×5 (engine/offense.TARGET_ENEMY_COUNT_WEIGHT).

No Guard (Desperation): base +10% damage taken, scaled by the channeled stacks lost on the at-max dump
(0.50×min(lost,2) + 1.00×max(0,lost−2): 2→+100%, 3→+200%) and by an additional pool from Block Ratio
(per 1% Block Ratio → +2.4-2.8% No Guard Effect). No Guard is ALSO cast on the player (a self-debuff that the
"−No Guard Effect on you per 1% Block Ratio" line reduces) — emitted as `no_guard_self_dmg_taken`, which the
defense engine does not consume yet (NYI badge until the conditional-defense path lands).

Season-catalog-sourced values (2026-07-16 SS12->SS13 drift fix): Unbreakable Stand's per-enemy damage bonus
AND its cap were confirmed drifted — read live from `_hero_traits.json` via `engine.hero_traits._catalog`
(identity-joined on `TRAIT_ID` + "Unbreakable Stand"), not hardcoded — see `_unbreakable_per_enemy`/
`_unbreakable_cap`. The cap is also a REAL shape change (owner-approved): SS12 applied one flat scalar cap
(+100%) to every tier; SS13 made the cap per-tier (+50/60/70/80/90%). `_catalog.tier_values(allow_scalar=True)`
resolves both shapes from the SAME code path with no `season ==` branch. Every other per-tier value in this
module was audited and verified still matching SS13; those stay Python literals for this pass (narrowly
scoped to the confirmed drift, not a full literal-elimination sweep).
"""
from __future__ import annotations

from engine.hero_traits import _catalog
from persistence import season_manager

TRAIT_ID = "high_court_chariot"

# ── Base trait (by base level 1-5) ──────────────────────────────────────────────
_BASE_BLOCK_CHANCE = 0.30                                   # +30% Attack & Spell Block Chance (flat, always)
_INSIDE_ADDITIONAL = [0.20, 0.26, 0.32, 0.38, 0.44]        # while inside Holy Domain, +X% additional damage
_ARTIFICIAL_MOON_BLOCK_PER_10MI = 0.01                      # base L5: +1% Attack & Spell Block Chance / 10 MI
# ── Advanced picks ──────────────────────────────────────────────────────────────
_WHIRLWIND_MS = [0.20, 0.30, 0.40, 0.40, 0.50]             # +X% Movement Speed (gated buff, assumed up)
_INVULN_BLOCK_RATIO = [0.07, 0.09, 0.11, 0.13, 0.15]       # +X% Block Ratio & Upper Limit (inside domain)
_DIVINE_PER_MI = [0.003, 0.0037, 0.0044, 0.0051, 0.0058]   # +X% additional dmg per 1 Murderous Intent (inside)
_DESPERATION_NOGUARD_PER_BR = [0.024, 0.025, 0.026, 0.028, 0.028]   # +X% No Guard Effect (enemy) per 1% Block Ratio
_DESPERATION_NOGUARD_SELF_PER_BR = [0.0067, 0.008, 0.01, 0.01, 0.012]  # −X% No Guard Effect (you) per 1% Block Ratio
_IMPROVISION_CAP = [0.40, 0.50, 0.60, 0.70, 0.80]          # block in domain → +20%/10s up to +cap
_IMPROVISION_PER_BLOCK = 0.20

_NOGUARD_BASE = 0.10                                        # +10% damage taken
_HOLY_DOMAIN_MAX_CHANNELED = 2                             # Desperation base Max Channeled Stacks

# Season-catalog-sourced (2026-07-16 SS12->SS13 drift fix): CONFIRMED drifted. The literals below are the SS12
# values (SS12's cap was a flat scalar, not per-tier — broadcast to all 5 tiers here for the fallback shape),
# kept ONLY as the last-known-good fallback for a season whose catalog doesn't have this pick at all.
_UNBREAKABLE_PER_ENEMY_FALLBACK = [0.07, 0.08, 0.09, 0.095, 0.10]
_UNBREAKABLE_CAP_FALLBACK = [1.00, 1.00, 1.00, 1.00, 1.00]


def _unbreakable_per_enemy(season):
    # "( +6/+7/+8/+9/+10 )% additional damage for each enemy in the Holy Domain , up to ( +50/.../+90 )%
    # additional damage" (SS13) / "up to +100%" (SS12) — the per-enemy group is the first (only) slash-group
    # before the "up to" cap.
    return _catalog.pick_tier_values(season, TRAIT_ID, "Unbreakable Stand",
                                      fallback=_UNBREAKABLE_PER_ENEMY_FALLBACK)


def _unbreakable_cap(season):
    # allow_scalar=True: resolves BOTH the SS13 per-tier cap and the SS12 flat-scalar cap from one code path.
    return _catalog.pick_tier_values(season, TRAIT_ID, "Unbreakable Stand", marker="up to ", allow_scalar=True,
                                      fallback=_UNBREAKABLE_CAP_FALLBACK)


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


def _stacks_lost_inc(lost: float) -> float:
    """No Guard 'effect increased' from channeled stacks lost: first 2 lost give 50% each (→+100% at 2), each
    beyond gives +100% (3→+200%, 4→+300%)."""
    lost = max(0.0, float(lost))
    return 0.50 * min(lost, 2.0) + 1.00 * max(0.0, lost - 2.0)


def apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks):
    picks = set(advanced_picks or [])
    slot_levels = list(slot_levels or [1, 1, 1, 1])
    contribs: list[dict] = []

    # `build_input` is a real BuildInput (with `.season`) on the real compute path; unit tests exercise this
    # module directly with `build_input=None`, so read it defensively (falls back to the SS12 literals — see
    # `_catalog.pick_tier_values`'s `fallback` behavior for a falsy season).
    season = getattr(build_input, "season", None)
    base_lvl = slot_levels[0] if slot_levels else 1
    inside = _flag(condition_state, "inside_holy_domain", True)
    mi = float(condition_state.get("murderous_intent", 100.0))
    enemies = float(condition_state.get("enemies_in_holy_domain", 1.0))
    block_ratio = float(ls_state.get("block_ratio", 0.30))     # prev-pass clamped Block Ratio (base 30%)
    block_ratio_pct = block_ratio * 100.0                       # in "% points" for per-1%-Block-Ratio lines

    from engine.offense import TARGET_ENEMY_COUNT_WEIGHT
    # Enemy-Count weight by enemy type (Normal/Magic 1, Rare 2, Boss 5). Configurable via condition_state
    # (enemy_count_weight); defaults to the Boss training-dummy weight so unset builds are unchanged.
    weight = float(condition_state.get("enemy_count_weight") or TARGET_ENEMY_COUNT_WEIGHT)
    weighted_enemies = enemies * weight

    base_on = _enabled(slot_levels, 0)   # the base node can be disabled (right-click) while the trait stays selected

    # ── Base: +30% Attack & Spell Block Chance ───────────────────────────────────
    if base_on:
        contribs.append(_contrib("attack_block_chance_inc", _BASE_BLOCK_CHANCE,
                                 "High Court Chariot: +30% Attack Block Chance", "High Court Chariot"))
        contribs.append(_contrib("spell_block_chance_inc", _BASE_BLOCK_CHANCE,
                                 "High Court Chariot: +30% Spell Block Chance", "High Court Chariot"))
        # While inside the Holy Domain, +20→44% additional damage.
        if inside:
            amt = _INSIDE_ADDITIONAL[_tier([base_lvl], 0)]
            contribs.append(_contrib("dmg_additional", amt,
                                     f"While inside the Holy Domain: +{amt * 100:.0f}% additional damage",
                                     "High Court Chariot"))
        # ── Artificial Moon (base L5): per 10 MI → +Block Chance ─────────────────
        if abs(base_lvl) >= 5:
            block = _ARTIFICIAL_MOON_BLOCK_PER_10MI * (mi // 10.0)
            if block > 0:
                contribs.append(_contrib("attack_block_chance_inc", block,
                                         f"Artificial Moon: +{block * 100:.0f}% Attack Block Chance (per 10 MI)", "Artificial Moon"))
                contribs.append(_contrib("spell_block_chance_inc", block,
                                         f"Artificial Moon: +{block * 100:.0f}% Spell Block Chance (per 10 MI)", "Artificial Moon"))

    # ── Unbreakable Stand (45): +dmg per (weighted) enemy, capped (per-tier since SS13; see module docstring) ──
    if "Unbreakable Stand" in picks and inside and _enabled(slot_levels, 1):
        t = _tier(slot_levels, 1)
        per_enemy = _unbreakable_per_enemy(season)[t]
        cap = _unbreakable_cap(season)[t]
        amt = min(per_enemy * weighted_enemies, cap)
        if amt > 0:
            contribs.append(_contrib("dmg_additional", amt,
                                     f"Unbreakable Stand: +{amt * 100:.1f}% additional damage "
                                     f"({per_enemy * 100:.1f}%/enemy ×{weighted_enemies:.0f}, cap {cap * 100:.0f}%)",
                                     "Unbreakable Stand"))

    # ── Whirlwind Advance (45): +Movement Speed (gated buff, assumed up) ─────────
    if "Whirlwind Advance" in picks and _enabled(slot_levels, 1):
        t = _tier(slot_levels, 1)
        contribs.append(_contrib("movement_speed_inc", _WHIRLWIND_MS[t],
                                 f"Whirlwind Advance: +{_WHIRLWIND_MS[t] * 100:.0f}% Movement Speed", "Whirlwind Advance"))

    # ── Invulnerability (60): +Block Ratio & Upper Limit (inside domain) ─────────
    if "Invulnerability" in picks and inside and _enabled(slot_levels, 2):
        t = _tier(slot_levels, 2)
        contribs.append(_contrib("block_ratio_inc", _INVULN_BLOCK_RATIO[t],
                                 f"Invulnerability: +{_INVULN_BLOCK_RATIO[t] * 100:.0f}% Block Ratio", "Invulnerability"))
        contribs.append(_contrib("block_ratio_upper_limit_flat", _INVULN_BLOCK_RATIO[t],
                                 f"Invulnerability: +{_INVULN_BLOCK_RATIO[t] * 100:.0f}% Block Ratio Upper Limit", "Invulnerability"))

    # ── Divine Intervention (60): +dmg per Murderous Intent (inside domain) ──────
    if "Divine Intervention" in picks and inside and _enabled(slot_levels, 2):
        t = _tier(slot_levels, 2)
        amt = _DIVINE_PER_MI[t] * mi
        if amt > 0:
            contribs.append(_contrib("dmg_additional", amt,
                                     f"Divine Intervention: +{amt * 100:.2f}% additional damage "
                                     f"({_DIVINE_PER_MI[t] * 100:.2f}%/MI ×{mi:.0f})", "Divine Intervention"))

    # ── Desperation (75): No Guard on the at-max channeled dump ──────────────────
    if "Desperation" in picks and inside and _enabled(slot_levels, 3):
        t = _tier(slot_levels, 3)
        lost = _HOLY_DOMAIN_MAX_CHANNELED + float(ls_state.get("max_channeled_stacks_flat", 0.0))
        stacks_inc = _stacks_lost_inc(lost)
        enemy_add = block_ratio_pct * _DESPERATION_NOGUARD_PER_BR[t]            # additional No Guard Effect (enemy)
        no_guard = _NOGUARD_BASE * (1.0 + stacks_inc) * (1.0 + enemy_add)
        contribs.append(_contrib("no_guard_dmg_taken", no_guard,
                                 f"Desperation: No Guard → enemies take +{no_guard * 100:.1f}% damage "
                                 f"(10% × {1 + stacks_inc:.0f} stacks-lost × {1 + enemy_add:.2f} Block-Ratio)",
                                 "Desperation"))
        # No Guard also on the player (self-debuff) — reduced by the −No Guard Effect on you per 1% Block Ratio.
        self_add = -block_ratio_pct * _DESPERATION_NOGUARD_SELF_PER_BR[t]
        no_guard_self = max(0.0, _NOGUARD_BASE * (1.0 + stacks_inc) * (1.0 + self_add))
        contribs.append(_contrib("no_guard_self_dmg_taken", no_guard_self,
                                 f"Desperation: No Guard on you → +{no_guard_self * 100:.1f}% damage taken "
                                 f"(reduced by Block Ratio)", "Desperation"))

    # ── Improvision (75): block in domain → +additional damage (own toggle) ──────
    if "Improvision" in picks and inside and _enabled(slot_levels, 3) and _flag(condition_state, "improvision_active", False):
        t = _tier(slot_levels, 3)
        amt = _IMPROVISION_CAP[t]   # modeled at the cap (sustained blocking in the domain)
        contribs.append(_contrib("dmg_additional", amt,
                                 f"Improvision: +{amt * 100:.0f}% additional damage (blocking in the domain)",
                                 "Improvision"))

    return {"contributions": contribs}


def stash(*, source, ls_state, inflict_aps):
    """Capture the converged scalars next pass's apply() needs: the clamped Block Ratio (for the per-1%-Block-Ratio
    No Guard scaling) and any +Max Channeled Stacks (for the No Guard stacks-lost)."""
    from engine.defense import block_ratio_value
    ls_state["block_ratio"] = block_ratio_value(source)[0]
    ls_state["max_channeled_stacks_flat"] = source.total("max_channeled_stacks_flat")


def status_lines(*, slot_levels, advanced_picks, season=None, **_):
    """One status row per trait line so every line is surfaced (never silently dropped). `season` (2026-07-16
    architecture fix) is an explicit, documented input — see `engine/hero_traits/README.md` — so a
    season-catalog-sourced display number (Unbreakable Stand's cap) is a VISIBLE dependency in the function
    signature, not a global read hidden in the body. `engine.coverage.trait_coverage`'s build-independent
    probe supplies the real active season explicitly. The real `/api/engine/stats` call site (`server.py`)
    does not thread a build-pinned season through this call today, so a None/falsy `season` here falls back
    to the currently-active season (identical to the pre-fix behavior, and identical to what `apply()`
    already reads via `build_input.season` on the same request) — never a stale/wrong literal."""
    picks = set(advanced_picks or [])
    out: list[dict] = []

    def working(text, source):
        out.append({"text": text, "source": source, "status": "working"})

    def info(text, source):
        out.append({"text": text, "source": source, "status": "informational"})

    working("+30% Attack & Spell Block Chance; while inside the Holy Domain, +additional damage", "High Court Chariot")
    info("Restores Murderous Intent (per second / on Block); cast Trait Skill (15 MI) → Holy Domain + pull", "High Court Chariot")
    if (slot_levels or [1])[0] >= 5:
        working("Artificial Moon: +Block Chance per 10 Murderous Intent", "Artificial Moon")
        info("Artificial Moon: +Holy Domain radius per 10 Murderous Intent", "Artificial Moon")
    if "Unbreakable Stand" in picks:
        _season = season or season_manager.get_active_season() or ""
        t = _tier(slot_levels or [1, 1, 1, 1], 1)
        cap = _unbreakable_cap(_season)[t]
        working(f"Unbreakable Stand: +additional damage per enemy in the Holy Domain (Boss ×5), up to +{cap * 100:.0f}%", "Unbreakable Stand")
    if "Whirlwind Advance" in picks:
        working("Whirlwind Advance: +Movement Speed after entering/leaving the domain", "Whirlwind Advance")
        info("Whirlwind Advance: restores Murderous Intent on defeating an enemy in the domain", "Whirlwind Advance")
    if "Invulnerability" in picks:
        working("Invulnerability: +Block Ratio & Block Ratio Upper Limit inside the domain", "Invulnerability")
        info("Invulnerability: +Murderous Intent restoration per 1% Block Ratio; grants a Holy Domain support slot", "Invulnerability")
    if "Divine Intervention" in picks:
        working("Divine Intervention: +additional damage per Murderous Intent (inside the domain)", "Divine Intervention")
        info("Divine Intervention: +Murderous Intent restoration; grants a Holy Domain support slot", "Divine Intervention")
    if "Desperation" in picks:
        working("Desperation: channeled Holy Domain → No Guard on enemies (per Block Ratio)", "Desperation")
        info("Desperation: No Guard on you (defensive) — emitted, defense consumption NYI; −30% radius", "Desperation")
    if "Improvision" in picks:
        working("Improvision: +additional damage when Blocking in the domain (own toggle)", "Improvision")
    return out
