"""
engine/compute.py — pure BuildInput → StatResult entry point.

The fixed-point loop iterates: aggregate → derive condition maximums → clamp
numeric condition values → re-derive boolean *_active flags → repeat until
stable (or max 10 iterations). Converges in ~2 passes for normal data.

server.py is a thin HTTP wrapper; all calculation logic lives here.
"""
from __future__ import annotations
import logging
from engine.models import BuildInput, BuildSource, StatResult

log = logging.getLogger(__name__)

_MAX_ITERS = 10

# Support ids that turn a Spell into a Tangle (the skill is then cast by attached tangles, not the player).
# Manifold Entanglement is NOT here — it's a normal damage support that spawns all tangles at once.
_TANGLE_ACTIVATORS = frozenset({"spell_tangle", "activation_medium_tangle"})

# ── Spell Burst ────────────────────────────────────────────────────────────────
# Supports that GRANT Spell Burst eligibility to a skill that wouldn't burst on its own (e.g. an Attack or a
# channeled skill): "The supported skill can activate Spell Burst". An eligible Spell bursts inherently once
# Max Spell Burst ≥ 1, so it needs no enabler.
_SPELL_BURST_ENABLERS = frozenset({
    "lightning_storm_raging_storm_noble",   # Raging Storm — "The supported skill can activate Spell Burst"
    "moon_strike_wax_and_wane_noble",       # Wax and Wane — same, + a flat burst-damage bonus
    "psychic_burst",                        # supports Spell Skills / skills that can activate Spell Burst
})
# Auto-trigger is stat-driven (the mod lines parse to spell_burst_auto_trigger_flag / _auto_charge_threshold and
# offense finalizes it against charge_factor) plus the manual spell_burst_auto_trigger condition toggle.
# Tags that make a Spell INELIGIBLE for inherent Spell Burst (still burstable via an enabler support if stated).
_SPELL_BURST_DISALLOWED_TAGS = frozenset({
    "channeled", "sentry", "combo", "trigger", "triggered", "persistent", "aura", "passive", "mark",
})
# Per-support Spell-Burst damage bonuses that SCALE with stacks/activations (the generic parser maps only the
# FLAT "for skills cast by Spell Burst" lines; these ramped lines are hand-modeled here — owner §7). Each adds
# to spell_burst_hit_dmg_additional in burst mode. "per_stack" scales by min(M, cap) (stacks consumed = M);
# "per_activation" assumes sustained DPS at the cap (×cap). pct values are mid-roll — flagged for in-game
# verification (SPELLBURST-01). Cap from the line ("Stacks up to N").
_SPELL_BURST_BONUS_SUPPORTS = {
    "fire_burst_heart_of_flame_magnificent": {"mode": "per_stack",      "pct": 0.105, "cap": 6},
    "fire_burst_prairie_fire_noble":         {"mode": "per_activation", "pct": 0.18,  "cap": 6},
}


# "Gain on hit" automax flag → the numeric condition pinned to its derived max (full-uptime approximation).
_AUTOMAX_TARGETS = [
    ("automax_focus_blessings",    "focus_blessings"),
    ("automax_agility_blessings",  "agility_blessings"),
    ("automax_tenacity_blessings", "tenacity_blessings"),
    ("automax_fervor",             "fervor_rating"),
]


def derive_condition_maximums(source: BuildSource) -> dict[str, float]:
    """Return {condition_key: max_value} for all numeric conditions that have a defined max."""
    from models.conditions import ALL_CONDITIONS
    maxes: dict[str, float] = {}
    for c in ALL_CONDITIONS:
        if c.value_type != "numeric":
            continue
        if c.max_from_stat:
            maxes[c.key] = c.max_base + source.total(c.max_from_stat)
        elif c.numeric_max is not None:
            maxes[c.key] = float(c.numeric_max)
        elif c.max_base:
            maxes[c.key] = float(c.max_base)
    return maxes


def derive_condition_minimums(source: BuildSource) -> dict[str, float]:
    """Return {condition_key: min_value} for all numeric conditions that have a defined min floor."""
    from models.conditions import ALL_CONDITIONS
    mins: dict[str, float] = {}
    for c in ALL_CONDITIONS:
        if c.value_type != "numeric":
            continue
        if c.min_from_stat:
            mins[c.key] = c.min_base + source.total(c.min_from_stat)
        elif c.min_base:
            mins[c.key] = float(c.min_base)
    return mins


def _derive_views(
    condition_state: dict[str, float | bool],
) -> tuple[frozenset[str], dict[str, float]]:
    """Split unified condition_state into the two evaluation views the evaluator needs."""
    active_booleans: set[str] = set()
    numeric_vals: dict[str, float] = {}
    for k, v in condition_state.items():
        if isinstance(v, bool):
            if v:
                active_booleans.add(k)
        elif isinstance(v, (int, float)):
            numeric_vals[k] = float(v)
    return frozenset(active_booleans), numeric_vals


def _clamp_and_rederive(
    condition_state: dict[str, float | bool],
    maxes: dict[str, float],
    mins: dict[str, float],
) -> dict[str, float | bool]:
    """Clamp numeric values to their derived maxes/mins; re-derive *_active booleans from stack counts
    and derived numerics (e.g. any_blessings) from their source sums."""
    from models.conditions import DERIVED_ACTIVE_KEYS, DERIVED_NUMERIC_KEYS
    new_state: dict[str, float | bool] = dict(condition_state)

    for k in new_state:
        if not isinstance(new_state[k], bool) and isinstance(new_state[k], (int, float)):
            val = float(new_state[k])
            if k in maxes:
                val = min(val, maxes[k])
            if k in mins:
                val = max(val, mins[k])
            new_state[k] = val

    # Re-derive boolean *_active flags from their clamped stack-count siblings
    for bool_key, stack_key in DERIVED_ACTIVE_KEYS.items():
        if stack_key in new_state:
            new_state[bool_key] = float(new_state[stack_key]) > 0

    # Re-derive numeric aggregates (sum of source conditions), e.g. any_blessings = focus+agility+tenacity.
    for derived_key, source_keys in DERIVED_NUMERIC_KEYS.items():
        new_state[derived_key] = sum(
            float(new_state.get(sk, 0.0) or 0.0)
            for sk in source_keys
            if not isinstance(new_state.get(sk), bool)
        )

    return new_state


def _state_snapshot(condition_state: dict[str, float | bool]) -> frozenset:
    return frozenset((k, v) for k, v in condition_state.items())


def _eval_intrinsic_additional(skill, source: BuildSource, condition_state: dict[str, float | bool]) -> float:
    """Sum a skill's intrinsic 'additional damage' bonuses. Each bonus is
        min(per * (rating / per_n) * (1 + effect_value), cap)
    where rating comes from a condition (Focused Slash's Fervor Rating) or an aggregated stat
    (Moon Strike's Max Mana). Returns 0.0 for skills with none."""
    total = 0.0
    for ia in getattr(skill, "intrinsic_additional", []):
        if getattr(ia, "rating_source", "condition") == "stat":
            rating = source.total(ia.rating_key)
        else:
            rating = float(condition_state.get(ia.rating_key, 0.0) or 0.0)
        if rating <= 0.0:
            continue
        # effect_key (global, e.g. fervor_effect_inc) and skill_effect_key (skill-local, e.g. Tranquility)
        # are BOTH increased — they add into the same (1 + Σ increased) pool. The skill-local one scales
        # the skill's bonus only, not the global crit (which reads effect_key elsewhere).
        effect = source.total(ia.effect_key) if ia.effect_key else 0.0
        skill_effect = source.total(ia.skill_effect_key) if getattr(ia, "skill_effect_key", None) else 0.0
        amount = ia.per * (rating / getattr(ia, "per_n", 1.0)) * (1.0 + effect + skill_effect)
        cap = getattr(ia, "cap", None)
        if cap is not None:
            amount = min(amount, cap)
        total += amount
    return total


def _apply_cond_effects(condition_state, effects, main_dtypes, manual_keys) -> None:
    """Apply auto-derived support condition effects (from map_autoderive_line) to condition_state,
    respecting manually-set values (never lower / never override). Gated by the supported skill's
    damage types (requires_dtype) and any precondition (requires_cond, e.g. enemy_cursed for Paralyze)."""
    dtypes = {d.lower() for d in (main_dtypes or [])}
    _ELEMENTAL = {"fire", "cold", "lightning", "erosion"}
    for e in effects or []:
        if e.condition_key in manual_keys:
            continue
        if e.requires_dtype == "elemental":
            if not (dtypes & _ELEMENTAL):
                continue
        elif e.requires_dtype and e.requires_dtype not in dtypes:
            continue
        if e.requires_cond and not condition_state.get(e.requires_cond):
            continue
        if e.mode == "set_true":
            condition_state[e.condition_key] = True
        elif e.mode == "max":
            cur = condition_state.get(e.condition_key, 0.0)
            cur = (1.0 if cur else 0.0) if isinstance(cur, bool) else float(cur or 0.0)
            condition_state[e.condition_key] = max(cur, e.value)


def compute(
    build_input: BuildInput,
    season_trees: dict[str, dict],
    filter_data: dict,
    skill_data: dict | None = None,
    skills_input: list[dict] | None = None,
    skills_by_id: dict[str, dict] | None = None,
) -> StatResult:
    """
    Run the fixed-point aggregation loop and return a StatResult.

    season_trees: {tree_slug: season_tree_dict}
    filter_data:  loaded node_type_filter.json dict
    """
    from engine.aggregator import aggregate
    from engine.models import SourceEntry
    from engine.support_resolver import resolve_standard_supports
    from models.stat_meta import STAT_META

    condition_state: dict[str, float | bool] = dict(build_input.condition_state)
    manual_cond_keys = set(build_input.condition_state.keys())
    prev_snapshot = None

    # Core-talent set-value overrides ("Max Life is set to 100"): force a derived stat to a fixed final
    # value in derive_stats (these ride in core_talent_contributions tagged set_value, skipped by the
    # aggregator's additive loop).
    _set_value_overrides: dict[str, float] = {
        c["stat_key"]: float(c["amount"])
        for c in (build_input.core_talent_contributions or [])
        if c.get("set_value") and c.get("stat_key")
    }

    # Resolve the main skill once for standard-support gating + the inflicts-Numbed damage-type gate:
    # category (spell|attack) + damage types. Computed whenever a main skill exists (not only with
    # supports) so the inflict_cond_effects lightning/elemental gate works on a support-less build too.
    main_cat: str | None = None
    main_dtypes: list[str] = []
    if skill_data:
        from engine.skill_resolver import resolve_skill
        _rm = resolve_skill(skill_data)
        if _rm.supported:
            _tags = {t.lower() for t in _rm.tags}
            main_cat = "spell" if _rm.is_spell else ("attack" if "attack" in _tags else None)
            main_dtypes = [d.lower() for d in _rm.damage_types]

    # Per-slot category map so a support is gated/categorized by ITS host skill, not the main skill — a
    # support on a non-main slot (e.g. an attack skill in slot 2) must resolve as that skill's category,
    # else its added-flat lands in the wrong pool / is gated out and contributes nothing.
    slot_cats: dict[int, str | None] = {}
    curse_slots: set[int] = set()     # slots whose host skill is a Curse (for the curse-only support gate)
    empower_slots: set[int] = set()   # slots whose host skill is an Empower (for the empower-only support gate)
    slot_skill: dict[int, str] = {}   # slot -> skill_id (lets a support find its host skill, e.g. Mass Effect charges)
    if build_input.attached_supports and skills_input and skills_by_id is not None:
        from engine.skill_resolver import resolve_skill as _resolve_skill
        for _sk in skills_input:
            slot_skill[_sk["slot"]] = _sk["skill_id"]
            _sd = skills_by_id.get(_sk["skill_id"])
            if not _sd:
                continue
            _sd_tags = _sd.get("skill_tags") or []
            if "Curse" in _sd_tags:
                curse_slots.add(_sk["slot"])
            if "Empower" in _sd_tags:
                empower_slots.add(_sk["slot"])
            _rs = _resolve_skill(_sd)
            if not _rs.supported:
                continue
            _t = {t.lower() for t in _rs.tags}
            slot_cats[_sk["slot"]] = "spell" if _rs.is_spell else ("attack" if "attack" in _t else None)

    # The main skill's slot (folds its slot-local supports/self-buffs + drives skill-effect dispatch).
    # main_enabled: a disabled main skill produces NO offense (DPS 0), not just its supports dropped.
    from engine import skill_effects
    main_slot = 1
    main_enabled = True
    if build_input.main_skill and skills_input:
        for _sk in skills_input:
            if _sk["skill_id"] == build_input.main_skill.skill_id:
                main_slot = _sk["slot"]
                main_enabled = _sk.get("enabled", True)
                break
    # Type-C preseed before aggregation (e.g. Berserking Blade Decimate forcing enemy_low_life when the
    # enemy is below the rolled threshold) — dispatched for EVERY equipped skill, scoped by its slot, so a
    # skill's preseed mechanic runs no matter which slot it's in (and per-slot for two-of-the-same-skill).
    _main_id = build_input.main_skill.skill_id if build_input.main_skill else None
    _main_covered = False
    for _sk in (skills_input or []):
        if not _sk.get("enabled", True):
            continue
        if _sk["skill_id"] == _main_id:
            _main_covered = True
        skill_effects.preseed(_sk["skill_id"], slot=_sk["slot"],
                              condition_state=condition_state,
                              attached_supports=build_input.attached_supports, skills_by_id=skills_by_id)
    # Fallback: a main skill provided without a matching slot entry (legacy payloads) still preseeds.
    if _main_id and not _main_covered:
        skill_effects.preseed(_main_id, slot=main_slot,
                              condition_state=condition_state,
                              attached_supports=build_input.attached_supports, skills_by_id=skills_by_id)

    # ── Hero traits (Erika Lightning Shadow, …) ───────────────────────────────
    # A bespoke trait module owns its resolution: each loop pass it (re)computes build_input.trait_contributions
    # (folded by aggregate) and, in real uptime mode, the converged Numbed steady-state. The Numbed application
    # rate is driven by the lightning skill actually hitting — resolved by who/what hits, NEVER slot-by-index.
    from engine import hero_traits
    from engine import uptime as _uptime
    from engine.offense import compute_skill_rates
    from engine.skill_resolver import resolve_skill as _resolve_skill_for_trait
    _trait_id = build_input.trait_id
    _trait_active = hero_traits.has_module(_trait_id)
    _uptime_real = _uptime.is_real(build_input.uptime_mode)
    _ls_state: dict = {}
    _inflict_resolved = None
    if _trait_active and _uptime_real:
        def _deals_lightning(sd):
            rs = _resolve_skill_for_trait(sd)
            return rs.supported and "lightning" in [d.lower() for d in rs.damage_types]
        if skill_data and _deals_lightning(skill_data):
            _inflict_resolved = _resolve_skill_for_trait(skill_data)          # main skill (slot may be non-1)
        elif skills_input and skills_by_id:
            for _sk in skills_input:
                _sd = skills_by_id.get(_sk["skill_id"])
                if _sd and _sk["slot"] != main_slot and _sk.get("enabled", True) and _deals_lightning(_sd):
                    _inflict_resolved = _resolve_skill_for_trait(_sd)          # lightning skill in a non-main slot
                    break

    aura_summaries: list[dict] = []
    empower_summaries: list[dict] = []
    curse_summaries: list[dict] = []
    curse_conflict: dict | None = None
    reservation: dict | None = None
    _converged_iters = _MAX_ITERS
    for iteration in range(_MAX_ITERS):
        # Loop-top: the trait module recomputes its contributions + Numbed override from the prior pass's
        # converged scalars (in _ls_state), so MS↔Numbed coupling settles like auras.
        if _trait_active:
            _tr = hero_traits.apply(
                _trait_id, build_input=build_input, condition_state=condition_state, ls_state=_ls_state,
                uptime_mode=build_input.uptime_mode, slot_levels=build_input.trait_slot_levels,
                advanced_picks=build_input.advanced_trait_selections)
            build_input.trait_contributions = _tr.get("contributions") or []
            _numbed_override = _tr.get("numbed_stacks")
            if _numbed_override is not None:
                # Engine-owned in real mode: mark manual so _apply_cond_effects' support max-rule won't clobber it.
                condition_state["numbed_stacks"] = _numbed_override
                manual_cond_keys.add("numbed_stacks")
        active_booleans, numeric_vals = _derive_views(condition_state)

        source = aggregate(
            build_input,
            season_trees,
            filter_data,
            active_booleans=active_booleans,
            numeric_vals=numeric_vals,
        )

        # Standard support_skill / activation_medium contributions, resolved against the CURRENT
        # condition_state so conditional lines see converged values and inflicted debuffs feed back.
        std_contribs, cond_effects = resolve_standard_supports(
            build_input.attached_supports, skills_by_id, main_cat, main_dtypes, condition_state, slot_cats,
            source=source, curse_slots=curse_slots, empower_slots=empower_slots, slot_skill=slot_skill)
        for c in std_contribs:
            _se = SourceEntry(
                stat=c["stat_key"], amount=c["amount"], source_type="support",
                label=c.get("label", "Support"), text=c.get("text", ""), points=1,
                # The breakdown's Source Name column reads source_name; without it, it fell back to the
                # (level-1) effect text. Use the support's name so the row shows e.g. "Overload".
                source_name=c.get("source_name") or c.get("label"))
            # Standard supports are slot-local to their host skill (default slot 1) — fold only into that
            # slot's offense pass, like the Noble/Magnificent contributions above.
            _slot = c.get("slot")
            if _slot is not None:
                source.add_slotted(c["stat_key"], c["amount"], _slot, None, _se)
            else:
                source.add_with_source(c["stat_key"], c["amount"], _se)

        # Aura / Focus buffs: scale by the now-fully-aggregated Aura Effect (gear + talents + custom +
        # standard supports + the auras' own) and fold into the source BEFORE derive (so life-regen/resist
        # auras feed derived stats too). Runs each pass so the self-feedback converges with the loop.
        from engine.utility import apply_aura_buffs, apply_empower_buffs
        aura_summaries = apply_aura_buffs(
            source, build_input.aura_buffs, build_input.aura_meta, active_booleans, numeric_vals)

        # Empower (Euphoria) buffs: scale by the now-aggregated Empower Skill Effect (global + slot-local from
        # the skill + its empower supports) and fold in player-wide. Runs each pass like the auras.
        empower_summaries = apply_empower_buffs(
            source, build_input.empower_buffs, build_input.empower_meta, active_booleans, numeric_vals)

        # Curses: scale each applied curse by the now-aggregated Curse Effect and bake the per-final-type
        # *_curse_taken enemy-vulnerability pools (consumed by offense). Runs each pass like the auras so curse
        # effect / curse limit converge. enemy_cursed is auto-set server-side from curse presence (see server.py).
        from engine.curse_resolver import apply_curses
        curse_summaries, curse_conflict = apply_curses(source, build_input.curses, condition_state)

        # Compute derived stats (strength, armor, max_life, etc.) and inject
        # back into source so the pipeline and condition system can read them.
        # Record consumption here (a derived stat reads its component mod stats, e.g.
        # max_life_inc); the condition-system reads that follow stay untraced.
        from engine.derive import derive_stats
        source._recording = True
        derive_stats(source, _set_value_overrides)
        source._recording = False

        # Loop-bottom: capture the converged scalars the trait module's next pass needs (MS total,
        # ailment duration, and the inflicting skill's APS — computed only in real mode so max-mode pays nothing).
        if _trait_active:
            _inflict_aps = (compute_skill_rates(source, _inflict_resolved)["aps"]
                            if (_uptime_real and _inflict_resolved is not None) else None)
            hero_traits.stash(_trait_id, source=source, ls_state=_ls_state, inflict_aps=_inflict_aps)

        # Mana / Life sealing & reservation — after derive (Max Mana/Life final). Computes Sealed/Unsealed
        # pools from each sealing skill's base seal × support Mana Multipliers ÷ (1 + Compensation); emits Ward
        # ES + Lunar Eclipse damage into the source (converges with the loop). Runs each pass.
        from engine.utility import apply_reservation
        reservation = apply_reservation(
            source, skills_input, skills_by_id, build_input.attached_supports, active_booleans, numeric_vals)

        # Inject auto-computed condition values from aggregated stats
        from models.conditions import ALL_CONDITIONS
        for _c in ALL_CONDITIONS:
            if _c.source == "computed_stat":
                condition_state[_c.key] = source.total(_c.key)

        # Attribute-comparison conditions (Tradeoff core talent) — derived from STR vs DEX each pass
        # so the gated contributions converge with the rest of the fixed-point loop.
        _str_t, _dex_t = source.total("strength"), source.total("dexterity")
        condition_state["strength_ge_dexterity"] = _str_t >= _dex_t
        condition_state["dexterity_ge_strength"] = _dex_t >= _str_t

        # "Enemy is Nearby" (boolean) implies at least one nearby enemy → keep the numeric enemies_nearby
        # count at >= 1 so "when only/at least N enemies nearby" gates resolve (doesn't drop a higher count).
        if condition_state.get("enemy_nearby"):
            condition_state["enemies_nearby"] = max(float(condition_state.get("enemies_nearby", 0) or 0), 1.0)

        # Player current-life % → low_life / at_full_life / life_lost_pct (Desperation reads life_lost_pct).
        # Settable derived stat; auto-deriving it from life reservation/consumption is a follow-up. Only
        # touched when the build sends current_life_pct, so older payloads keep low_life byte-identical.
        if "current_life_pct" in condition_state:
            _clp = float(condition_state.get("current_life_pct", 100.0) or 0.0)
            condition_state["low_life"] = bool(condition_state.get("low_life")) or _clp < 35.0
            condition_state["at_full_life"] = _clp >= 100.0
            condition_state["life_lost_pct"] = max(0.0, 100.0 - _clp)

        # Squidnova (Squiddle pact spirit): auto-enable "having Squidnova" when Squiddle is equipped (its source
        # line emits has_squidnova_flag), since bursting reliably grants it — sustained-uptime approximation. The
        # gated "when having Squidnova" lines (+Spell Damage, rank-6 +1 Max Spell Burst) then apply.
        if source.total("has_squidnova_flag") > 0:
            condition_state["has_squidnova"] = True

        # Apply auto-derived support condition effects (Inflicts Numbed/Frostbite, Grudge→Paralyze,
        # Electric Overload, Willpower) before clamp/rederive, respecting manually-set values. Non-support
        # "inflicts Numbed" sources (talents/gear/custom mods) ride the same path via inflict_cond_effects.
        _apply_cond_effects(condition_state, list(cond_effects) + list(build_input.inflict_cond_effects),
                            main_dtypes, manual_cond_keys)
        # H — "cannot inflict Numbed" overrides everything (even a user-set value): no Numbed at all.
        if build_input.numbed_blocked:
            condition_state["enemy_numbed"] = False
            condition_state["numbed_stacks"] = 0.0

        maxes = derive_condition_maximums(source)
        mins = derive_condition_minimums(source)

        # "Gain on hit" core talents (Chilly/Perception/Tenacity, Ambition) → model the blessing/Fervor at
        # MAX (full-uptime approximation; future: selectable uptime calc modes). Flags arrive in
        # condition_state via the server's core override-flag seeding. Fervor only counts if the build has a
        # Have-Fervor source (`fervor`); the broader "which talents grant Have Fervor + gate the existing
        # unconditional Fervor application" rework is a separate follow-up.
        for _flag, _key in _AUTOMAX_TARGETS:
            if not condition_state.get(_flag):
                continue
            if _key == "fervor_rating" and not condition_state.get("fervor"):
                continue
            if _key in maxes:
                condition_state[_key] = maxes[_key]

        # Frostbite Rating (auto-derived, NOT user-set): 10 base + Max Frostbite Rating sources, only while
        # the enemy is Frostbitten. Capped at 120 normally; Condensed Frost lifts the cap to 200 (its over-120
        # bonus is applied in the aggregator's enemy-vuln bake). Freeze: rating > 100 auto-sets enemy_frozen.
        if condition_state.get("enemy_frostbitten"):
            _raw = 10.0 + source.total("max_frostbite_rating_flat")
            _cap = 200.0 if condition_state.get("condensed_frost") else 120.0
            condition_state["frostbite_rating"] = min(_raw, _cap)
        else:
            condition_state["frostbite_rating"] = 0.0
        if "enemy_frozen" not in manual_cond_keys:
            condition_state["enemy_frozen"] = condition_state["frostbite_rating"] > 100.0

        new_state = _clamp_and_rederive(condition_state, maxes, mins)
        snapshot = _state_snapshot(new_state)

        if snapshot == prev_snapshot:
            _converged_iters = iteration + 1
            break
        prev_snapshot = snapshot
        condition_state = new_state
    else:
        log.error(
            "Condition resolution did not converge after %d iterations. "
            "Returning last computed state. Check for circular/contradictory mechanics.",
            _MAX_ITERS,
        )

    if _trait_active:
        log.debug("hero trait %s (uptime=%s) converged in %d passes",
                  _trait_id, build_input.uptime_mode, _converged_iters)

    # The numeric-condition cap/floor reads (max_*_blessing_stacks_flat, max_fervor_rating, …) happen in
    # the fixed-point loop above with recording OFF, so a node that ONLY raises a cap would false-badge
    # "Inactive" (in the universe but not this build's consumed_stats). Re-run the cap/floor derivation once
    # WITH recording so those always-read stats register as Consumed — the values are already converged, so
    # this pass only traces consumption and changes no state.
    source._recording = True
    derive_condition_maximums(source)
    derive_condition_minimums(source)
    source._recording = False

    # Tripwire: a single damage-taken stat reaching >=100% reduction implies immunity, which
    # the current additive pooling can't represent (distinct sources should multiply). Raise
    # so it's revisited rather than silently zeroing damage.
    from engine.guards import check_damage_taken_immunity
    check_damage_taken_immunity(source)

    # Build stat_map from final source
    stat_map: dict = {}
    for entry in source.source_log:
        if entry.stat not in stat_map:
            meta = next((m for s, m in STAT_META.items() if s.value == entry.stat), None)
            stat_map[entry.stat] = {
                "display_name": meta.display_name if meta else entry.stat,
                "category": meta.category if meta else "Other",
                "unit": meta.unit if meta else "",
                "total": 0.0,
                "sources": [],
            }
        stat_map[entry.stat]["total"] = round(stat_map[entry.stat]["total"] + entry.amount, 6)
        stat_map[entry.stat]["sources"].append({
            "source_type": entry.source_type,
            "label": entry.label,
            "text": entry.text,
            "source_name": entry.source_name,
            "amount": entry.amount,
            "points": entry.points,
        })

    # (Slot-local contributions are merged into stat_map AFTER the offense pass below — apply_slot_effects emits
    # some of them during offense, so they aren't all in source.slot_log yet here. See the slot_log merge near
    # the return.)

    # Add derived effective stats as the "Character" section of the stat sheet
    from engine.derive import ALL_DERIVED_STATS as _DERIVED
    for _d in _DERIVED:
        val = source.total(_d.key)
        if val == 0.0:
            continue
        _meta = next((m for s, m in STAT_META.items() if s.value == _d.key), None)
        stat_map[_d.key] = {
            "display_name": _meta.display_name if _meta else _d.key.replace("_", " ").title(),
            "category": "Character",
            "unit": "",
            "total": round(val, 2),
            "sources": [],
        }

    # Movement speed — shown at a 0% baseline (the NET bonus; reductions go negative). Stored directly so the
    # UI never has to subtract 100%. final = (1 + Σincreased) × (1 + Σadditional) − 1.
    _ms = (1.0 + source.total("movement_speed_inc")) * (1.0 + source.total("movement_speed_additional")) - 1.0
    source.add("movement_speed", _ms)
    stat_map["movement_speed"] = {
        "display_name": "Movement Speed", "category": "Character", "unit": "%",
        "total": round(_ms, 4), "sources": [],
    }

    # Clamp report: numeric conditions where the user's requested value exceeded the derived max
    clamped_numeric = {
        k: float(v) for k, v in condition_state.items()
        if k in maxes
    }
    clamp_report: dict[str, dict] = {}
    for k, applied in clamped_numeric.items():
        requested = float(build_input.condition_state.get(k, 0))
        if requested > applied:
            clamp_report[k] = {"requested": requested, "applied": applied}

    # Post-loop offense and defense (not part of the fixed-point convergence)
    from dataclasses import asdict
    from engine.defense import calculate_defense
    from engine.offense import calculate_offense, skill_effective_level
    from engine.skill_resolver import resolve_skill
    from engine import skill_charges

    # Record stat consumption across the offense + defense passes (defensive stats always read;
    # offense reads only what the active/modeled skill's pipeline touches — an unmodeled skill
    # reads nothing, so its damage mods fall out of consumed_stats and read as inert).
    source._recording = True
    result_defense = asdict(calculate_defense(source, reservation))

    # Per-slot support_behavior ({slot: {...}}) — the headline reads its own slot's behavior. Tolerate a
    # legacy flat dict (no per-slot keys) by treating it as slot 1's behavior.
    _behavior = build_input.support_behavior or {}
    _behavior_by_slot = _behavior if all(isinstance(k, int) for k in _behavior) else {1: _behavior}

    def _offense_for_slot(resolved, level, slot, is_main, skill_dict=None):
        """Compute one slot's offense, folding only that slot's slot-local contributions. The skill's
        skill_effects module (if any) emits its slot-local effects first — Berserking Blade's intrinsic
        buff + Sweep/Rampage, Focused Slash's Behead/Tranquility, Moon Strike's Rainbow/Lunar Ring — and
        may return offense overrides (e.g. Behead removing the Area tag)."""
        _mt = ({t.lower() for t in resolved.tags}
               | {t.lower() for t in getattr(resolved, "extra_damage_mod_tags", [])})
        overrides = skill_effects.apply_slot_effects(
            resolved.skill_id, source=source, resolved=resolved, slot=slot,
            condition_state=condition_state, mod_tags=_mt,
            attached_supports=build_input.attached_supports, skills_by_id=skills_by_id)
        eff = source.materialize_for_skill(_mt, slot)
        # Intrinsic additionals read the slot-EFFECTIVE source so a slot-local amplifier (e.g. Tranquility's
        # fervor_effect_additional) scopes to the skill's bonus without touching the global Fervor→crit.
        extra = _eval_intrinsic_additional(resolved, eff, new_state)
        # ── Tangle mode ── the slot is "tangled" if an activator support (Spell Tangle / Activation Medium:
        # Tangle) is enabled on a Spell skill: the spell is cast by N attached tangles, not the player.
        tangle = None
        if resolved.is_spell and any(
                s.get("item_id") in _TANGLE_ACTIVATORS and s.get("enabled", True)
                for s in (build_input.attached_supports or []) if s.get("slot", 1) == slot):
            placeable = 2 + int(eff.total("max_tangle_quantity_flat"))
            attach_cap = max(0, min(1 + int(eff.total("extra_tangle_applied_flat")), placeable))
            user = new_state.get("active_tangles")
            active = min(int(user), attach_cap) if (user and float(user) > 0) else attach_cap
            inactivated = max(0, placeable - active)
            # Dormant Entanglement: +40% additional Tangle Damage per INACTIVATED tangle. Enabled by the user
            # condition OR a granting source flag (Acquaintance core talent / gear). One pooled additional factor
            # (1 + 0.40·n), applied via the tangle tag in calculate_offense.
            has_dormant = new_state.get("has_dormant_entanglement") or eff.total("has_dormant_entanglement_flag") > 0
            if has_dormant and inactivated > 0:
                eff.add("tangle_dmg_additional", 0.40 * inactivated)
            tangle = {"count": active, "placeable": placeable, "inactivated": inactivated}
        # ── Spell Burst mode ── M ≥ 1 (Max Spell Burst) makes an eligible Spell burst inherently; an enabler
        # support (Raging Storm / Wax and Wane / Psychic Burst) grants it to otherwise-ineligible skills.
        # Tangle and Spell Burst are mutually exclusive (a tangled spell is cast by the tangles, not bursting).
        spell_burst = None
        if tangle is None:
            M = int(eff.total("max_spell_burst_flat"))
            slot_supports = [s for s in (build_input.attached_supports or [])
                             if s.get("slot", 1) == slot and s.get("enabled", True)]
            slot_support_ids = {s.get("item_id") for s in slot_supports}
            enabler = bool(slot_support_ids & _SPELL_BURST_ENABLERS)
            tags_lower = {t.lower() for t in resolved.tags}
            cooldown = skill_charges.skill_cooldown(skill_dict) if skill_dict else None
            inherent = (resolved.is_spell
                        and resolved.channeled is None   # a channeled spell ramps stacks, it doesn't burst
                        and not (tags_lower & _SPELL_BURST_DISALLOWED_TAGS)
                        and not cooldown)
            able = M >= 1 and (inherent or enabler)
            active_cond = new_state.get("spell_burst_active", True)
            if able and active_cond:
                # Auto-trigger: the manual toggle here; gear/support sources (Burst Activation flag, Solid River /
                # Vorax conditional threshold) are stat-driven and finalized in offense (it needs charge_factor).
                auto_source = ""
                if new_state.get("spell_burst_auto_trigger"):
                    auto_source = "Auto-Trigger (toggled on)"
                auto = bool(auto_source)
                # Ramped per-support burst-damage bonuses (Heart of Flame / Prairie Fire — owner §7).
                for sid in slot_support_ids:
                    spec = _SPELL_BURST_BONUS_SUPPORTS.get(sid)
                    if not spec:
                        continue
                    n = min(M, spec["cap"]) if spec["mode"] == "per_stack" else spec["cap"]
                    if n > 0:
                        eff.add("spell_burst_hit_dmg_additional", spec["pct"] * n)
                spell_burst = {"count": M, "auto": auto, "auto_source": auto_source}
        return asdict(calculate_offense(
            eff, resolved, level, is_main_skill=is_main, extra_additional=extra,
            support_behavior=_behavior_by_slot.get(slot, {}),
            remove_mod_tags=overrides.get("remove_mod_tags"), tangle=tangle, spell_burst=spell_burst))

    result_offense = None
    slot_offense: dict[int, dict] = {}
    if skill_data and build_input.main_skill and main_enabled:
        result_offense = _offense_for_slot(
            resolve_skill(skill_data), build_input.main_skill.level, main_slot, True, skill_dict=skill_data)
        slot_offense[main_slot] = result_offense

    # Secondary active skill slots — each computed independently, folding only ITS slot's supports (no
    # cross-contamination between setups). Today's payloads carry only the main skill, so this is empty and
    # adds nothing to consumed_stats. Passives (slot > 5) and disabled slots are skipped.
    if skills_input and skills_by_id is not None:
        for sk in skills_input:
            if sk["slot"] > 5 or sk["slot"] == main_slot or not sk.get("enabled", True):
                continue
            sd = skills_by_id.get(sk["skill_id"])
            if not sd:
                continue
            resolved_sk = resolve_skill(sd)
            if not resolved_sk.supported:
                continue
            slot_offense[sk["slot"]] = _offense_for_slot(resolved_sk, sk["level"], sk["slot"], False, skill_dict=sd)
    source._recording = False

    # ── General build warnings (player diagnostics; extensible) ───────────────
    # Ineffective curse: an applied curse amplifies a damage type the build doesn't actually deal (e.g. an
    # Electrocute Lightning curse when 100% of the lightning is converted to cold) → it contributes nothing.
    warnings: list[dict] = []
    dealt_types: set[str] = set()
    for _off in [result_offense, *slot_offense.values()]:
        for _t, _v in ((_off or {}).get("damage_by_type") or {}).items():
            if _v and _v > 0:
                dealt_types.add(_t)
    if dealt_types:   # only when the build actually computes damage (else we can't judge effectiveness)
        for c in curse_summaries:
            sk = c.get("stat_key")
            if not (c.get("applied") and c.get("modeled") and sk) or sk == "hit_curse_taken":
                continue
            ctype = sk.replace("_curse_taken", "")
            if ctype not in dealt_types:
                warnings.append({
                    "kind": "ineffective_curse",
                    "text": f"{c['curse_name']} amplifies {ctype.capitalize()} Damage taken, but this build deals "
                            f"no {ctype.capitalize()} damage (converted away?) — this curse contributes nothing.",
                })

    # Skill slot summaries — effective level for every equipped skill
    result_skill_slots: list[dict] | None = None
    if skills_input and skills_by_id is not None:
        result_skill_slots = []
        for sk in skills_input:
            sd = skills_by_id.get(sk["skill_id"])
            if sd:
                resolved_sk = resolve_skill(sd)
                eff = skill_effective_level(
                    source, resolved_sk.tags, sk["level"],
                    is_main_skill=(sk["slot"] == 1),
                )
                result_skill_slots.append({
                    "slot":           sk["slot"],
                    "skill_id":       sk["skill_id"],
                    "skill_name":     resolved_sk.name or sd.get("name", sk["skill_id"]),
                    "level":          sk["level"],
                    "effective_level": eff,
                    "supported":      resolved_sk.supported,
                })

    # Calculation-target (dummy) profile for the enemy-stats panel: base + effective armor/resist after
    # this build's penetration, plus the active enemy debuffs (user-set / auto-derived conditions).
    from engine.offense import target_profile
    _DEBUFF_LABELS = {
        "enemy_paralyzed": "Paralysis",
        "enemy_affected_by_frail": "Frail",
        "enemy_affected_by_fire_infiltration": "Fire Infiltration",
        "enemy_affected_by_cold_infiltration": "Cold Infiltration",
        "enemy_affected_by_lightning_infiltration": "Lightning Infiltration",
    }
    _debuffs = [lbl for key, lbl in _DEBUFF_LABELS.items() if condition_state.get(key)]
    if float(condition_state.get("numbed_stacks", 0) or 0) > 0:
        _debuffs.append("Numbed")
    # Per-debuff detail: name + which damage it scopes + the damage-taken increase it applies (from the
    # engine's _enemy_vuln_mult stats). Recording is off here, so these reads are golden-neutral.
    debuff_details: list[dict] = []
    if condition_state.get("enemy_paralyzed"):
        debuff_details.append({"name": "Paralysis", "scope": "All damage",
                               "taken_inc": source.total("paralysis_dmg_taken")})
    if condition_state.get("enemy_affected_by_frail"):
        debuff_details.append({"name": "Frail", "scope": "Spell damage",
                               "taken_inc": source.total("frail_spell_taken")})
    for _t in ("fire", "cold", "lightning"):
        if condition_state.get(f"enemy_affected_by_{_t}_infiltration"):
            debuff_details.append({"name": f"{_t.title()} Infiltration", "scope": f"{_t.title()} damage",
                                   "taken_inc": source.total(f"{_t}_infiltration_taken")})
    _numbed = float(condition_state.get("numbed_stacks", 0) or 0)
    if _numbed > 0:
        debuff_details.append({"name": "Numbed", "scope": "Lightning damage", "stacks": _numbed,
                               "taken_inc": source.total("numbed_lightning_taken")})
    target_stats = {**target_profile(source), "debuffs": _debuffs, "debuff_details": debuff_details}

    # ── Numbed ailment box (player-stats display) ─────────────────────────────
    # Base +5% Lightning Damage taken per stack (11% if Conductive), scaled by the increased + additional
    # Numbed Effect pools. Duration is the per-stack lifetime (base 2s × Ailment Duration). In real uptime
    # mode the trait module also exposes the Feline Figure application rate + the (possibly doubled) FF
    # Numbed duration that produced the steady-state stacks.
    _ail_dur = source.total("ailment_duration_inc")
    _conductive = "core_conductive" in (active_booleans or frozenset())
    from engine.offense import additional_total_product
    numbed = {
        "base_per_stack": 0.11 if _conductive else 0.05,
        "conductive": _conductive,
        "duration": 2.0 * (1.0 + _ail_dur),
        "stacks": _numbed,
        "max_stacks": 10.0,
        "effect_inc": source.total("numbed_effect_inc"),
        # Effective additional = Π(1+each) − 1 (distinct sources multiply, same-text sum) — matches the calc,
        # NOT the raw sum. So the box's ×(1+effect_additional) shows the real multiplier the engine applies.
        "effect_additional": additional_total_product(source, "numbed_effect_additional") - 1.0,
        "lightning_taken": source.total("numbed_lightning_taken"),
        "uptime_mode": build_input.uptime_mode,
    }
    if _trait_active and _uptime_real:
        _ff_dur = 2.0 * (1.0 + _ail_dur)
        if "Electroplated Motif" in (build_input.advanced_trait_selections or []):
            _ff_dur *= 2.0
        numbed["ff_duration"] = _ff_dur
        numbed["application_rate"] = min(float(_ls_state.get("inflict_aps", 0.0) or 0.0), 1.0)

    from engine.aggregator import blessings_summary
    blessings = blessings_summary(active_booleans, numeric_vals, source)

    # Slot-local contributions (supports / skill self-buffs) live in slot_log, NOT source_log, so they're absent
    # from `total`/`sources`. Surface them in a parallel `slot_sources` list per stat so the breakdown can show
    # them under a "Skill-specific (slot N)" group. Done HERE (after the offense pass) because apply_slot_effects
    # emits some slot-local stats during offense (e.g. Furious Sweep's Gale-frequency-additional) — building this
    # earlier would miss them. Display-only; never touches `total`/`sources`, so totals stay byte-identical.
    for entry in source.slot_log:
        if entry.stat not in stat_map:
            meta = next((m for s, m in STAT_META.items() if s.value == entry.stat), None)
            stat_map[entry.stat] = {
                "display_name": meta.display_name if meta else entry.stat,
                "category": meta.category if meta else "Other",
                "unit": meta.unit if meta else "",
                "total": 0.0,
                "sources": [],
            }
        stat_map[entry.stat].setdefault("slot_sources", []).append({
            "source_type": entry.source_type,
            "label": entry.label,
            "text": entry.text,
            "source_name": entry.source_name,
            "amount": entry.amount,
            "points": entry.points,
            "slot": entry.slot,
            "scope": entry.scope,
        })

    return StatResult(
        stat_map=stat_map,
        condition_maximums=maxes,
        clamp_report=clamp_report,
        offense=result_offense,
        defense=result_defense,
        skill_slots=result_skill_slots,
        consumed_stats=sorted(source.consumed_stats),
        target_stats=target_stats,
        slot_offense={str(k): v for k, v in slot_offense.items()} or None,
        blessings=blessings,
        aura_summaries=aura_summaries,
        empower_summaries=empower_summaries,
        curse_summaries=curse_summaries,
        curse_conflict=curse_conflict,
        warnings=warnings,
        reservation=reservation,
        numbed=numbed,
    )
