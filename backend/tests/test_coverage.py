"""Build-independent, 3-state DPS-coverage roll-up (`engine/coverage.py`): `skill_coverage`,
`trait_coverage`, `legendary_coverage` (+ the season-cached `legendary_coverage_for_season`).

Ground-truth values below are engine-confirmed for the SS12 season's live data (not synthetic
fixtures) — pulled straight from `data/seasons/SS12/_skills.json`, `_hero_traits.json` (via
`hero_traits.has_module`/`status_lines`), and `_legendary_gear.json`. Also exercises the
`/api/skills`, `/api/hero-traits`, `/api/legendary-gear-index` endpoint wiring.
"""
import pytest

from persistence import season_manager
from engine.coverage import skill_coverage, trait_coverage, legendary_coverage

_SEASON = season_manager.get_active_season()

pytestmark = pytest.mark.skipif(
    _SEASON != "SS12",
    reason="SS12-specific ground-truth; SS13 values pending re-verification post-flip (see data/seasons/.active)",
)

_SKILLS = {s["item_id"]: s for s in (season_manager.load_skills("SS12") or {}).get("skills", []) if "item_id" in s}
_LEGENDARIES = {it["item_id"]: it for it in (season_manager.load_legendary_gear("SS12") or {}).get("items", [])
                if "item_id" in it}


# ── Skills ─────────────────────────────────────────────────────────────────────────────────────
class TestSkillCoverage:
    def test_chain_lightning_full(self):
        status, detail = skill_coverage(_SKILLS["chain_lightning"])
        assert status == "full"
        assert detail == []

    def test_berserking_blade_partial_extra_stack_mechanic(self):
        status, detail = skill_coverage(_SKILLS["berserking_blade"])
        assert status == "partial"
        assert detail  # non-empty
        joined = " ".join(detail)
        assert "50" in joined and "stack" in joined.lower() and "buff" in joined.lower()

    def test_split_shot_partial_on_defeat_extra_projectile(self):
        status, detail = skill_coverage(_SKILLS["split_shot"])
        assert status == "partial"
        assert detail
        joined = " ".join(detail).lower()
        assert "defeat" in joined and "projectile" in joined

    def test_unregistered_skill_is_none(self):
        # aegis_of_fire has no skill_resolver._REGISTRY entry -> 'none', no detail.
        status, detail = skill_coverage(_SKILLS["aegis_of_fire"])
        assert status == "none"
        assert detail == []

    def test_icebound_beam_full(self):
        """2026-07-12 reclassification: the beam-quantity/refraction exemption clause is a limitation on
        an already-unmodeled stat (no consumer reads it for Icebound), so all of Icebound Beam's intrinsic
        lines now resolve/classify as modeled -> 'full' (see skill_resolver._SKILL_MODELED_PHRASES)."""
        status, detail = skill_coverage(_SKILLS["icebound_beam"])
        assert status == "full"
        assert detail == []

    def test_howling_gale_full(self):
        """2026-07-12 reclassification: the 3 per-channeled-stack Duration/Skill-Area/Movement-Speed lines
        are non-DPS informational properties of the persistent Gale area (not omitted mechanics), so they
        now classify as modeled -> 'full' (was 'partial' before the reclassification)."""
        status, detail = skill_coverage(_SKILLS["howling_gale"])
        assert status == "full"
        assert detail == []

    def test_chromatic_shot_still_partial_explode_proc_unmodeled(self):
        """Chromatic Shot's compulsory-conversion line is glued to a genuinely unmodeled "10% chance to
        explode ... dealing True Damage" on-kill proc — the reclassification recognizes the base-state/
        flavor lines but must NOT swallow this still-unmodeled clause, so the item stays 'partial'."""
        status, detail = skill_coverage(_SKILLS["chromatic_shot"])
        assert status == "partial"
        assert detail
        joined = " ".join(detail).lower()
        assert "explode" in joined and "true damage" in joined

    def test_berserking_blade_still_partial_unchanged(self):
        """Anchor: berserking_blade's own on-defeat/Elite buff-grant condition is assumed-max, not
        modeled — unaffected by the 2026-07-12 reclassification of the other 4 skills."""
        status, detail = skill_coverage(_SKILLS["berserking_blade"])
        assert status == "partial"
        assert detail


# ── Cross-module `resolve_line_keys` scoping (2026-07-12 accuracy fix) ────────────────────────────
class TestResolveLineKeysScoping:
    """Pins `skill_effects.resolve_line_keys`'s `item_id` scoping: an unscoped/global search is plain
    text-similarity with no notion of which support a clause belongs to, so a genuinely-unmodeled line on
    one support can phrase-collide with an unrelated module's spec and silently borrow its stat key. The
    canonical case: `groundshaker_cripple_noble`'s NYI "+30% additional Skill Area when the supported skill
    consumes Demolisher Charge" has no spec of its own in `groundshaker.py` and used to borrow
    `berserking_blade`'s Sweep spec (phrase: "additional\\s+skill\\s+area") via the unscoped global search."""

    _SKILL_AREA_TEXT = "+30 % additional Skill Area when the supported skill consumes Demolisher Charge"

    def test_unscoped_search_still_borrows_the_generic_phrase(self):
        """Documents WHY scoping is needed: the bare phrase, searched with no item_id, still matches
        Berserking Blade Sweep's spec (nothing-to-do-with-Groundshaker) — this is the collision the
        `item_id` scope exists to prevent for callers that supply one."""
        from engine import skill_effects
        assert skill_effects.resolve_line_keys(self._SKILL_AREA_TEXT) == ["skill_area_additional"]

    def test_scoped_to_its_own_item_does_not_borrow(self):
        """Scoped to the item that ACTUALLY carries this NYI line, the borrow must not happen — `None`
        (no spec of groundshaker_cripple_noble's own recognizes it), never Sweep's key."""
        from engine import skill_effects
        assert skill_effects.resolve_line_keys(self._SKILL_AREA_TEXT, "groundshaker_cripple_noble") is None

    def test_scoped_to_the_owning_item_still_resolves(self):
        """Scoping must not blanket-suppress the phrase — the item that legitimately owns this spec
        (Berserking Blade Sweep) still resolves it when its own item_id is passed."""
        from engine import skill_effects
        assert skill_effects.resolve_line_keys(
            self._SKILL_AREA_TEXT, "berserking_blade_sweep_magnificent"
        ) == ["skill_area_additional"]

    def test_groundshaker_cripple_noble_coverage_is_partial_not_full(self):
        """End-to-end: with the scoping fix, `skill_coverage` for the item carrying the NYI line must not
        overclaim 'full' by silently inheriting Sweep's key."""
        status, detail = skill_coverage(_SKILLS["groundshaker_cripple_noble"])
        assert status == "partial"
        assert detail

    def test_scoped_only_spec_never_matches_without_an_item_id(self):
        """`scoped_only` specs (Howling Gale Rapid Sweep's stack-cap lines): the phrase is too generic to
        trust in an unscoped/global search ("Stacks up to N time(s)" could belong to any stacking buff), so
        it resolves ONLY once a caller has already identified this exact item — never via the plain
        `resolve_line_keys(text)` contract other callers rely on."""
        from engine import skill_effects
        text = "Stacks up to 10 time(s)"
        assert skill_effects.resolve_line_keys(text) is None
        assert skill_effects.resolve_line_keys(text, "howling_gale_rapid_sweep_magnificent") == []
        # A DIFFERENT item_id must not pick it up either — scoping is per support_ids, not a free pass.
        assert skill_effects.resolve_line_keys(text, "howling_gale_headwind_magnificent") is None


# ── Overclaim flips (2026-07-12, two upstream defects — see test_dps_coverage_defect_fixes.py for the
# low-level mechanics) ─────────────────────────────────────────────────────────────────────────────
class TestOverclaimFlips:
    """Both fixes flip specific items from a wrongly-`full` (or wrongly-swallowed-line) `skill_coverage`
    to an honest `partial`. Pinned here as the coverage-level regression guard; the underlying
    map_conditional_line / _is_dup mechanics are pinned directly in test_dps_coverage_defect_fixes.py."""

    def test_thunder_core_lightning_lasso_noble_now_partial(self):
        """Defect 1 (map_conditional_line scope guard): the bolt-count mechanic line used to be silently
        swallowed as 'modeled' via the pre-fix bare 'numbed enem' substring match — now correctly
        surfaces as an unmodeled mechanic clause, so the item can't overclaim 'full'."""
        status, detail = skill_coverage(_SKILLS["thunder_core_lightning_lasso_noble"])
        assert status == "partial"
        assert detail

    def test_modularization_compress_noble_now_partial(self):
        """Defect 2 (_is_dup scope-qualifier strip): the Physique/Aggressiveness minion-stat lines used
        to be falsely deduped against the damage line (shared 'for Minions summoned by the supported
        skill' scope) and dropped entirely — now they surface as unmodeled lines."""
        status, detail = skill_coverage(_SKILLS["modularization_compress_noble"])
        assert status == "partial"
        joined = " ".join(detail).lower()
        assert "aggressiveness" in joined
        assert "physique" in joined

    _OTHER_TWELVE = [
        "crescent_slash_vile_magnificent", "flame_jet_offshoot_noble",
        "frost_impact_ice_cluster_magnificent", "modularization_superconductivity_noble",
        "spectral_slash_detonation_magnificent", "summon_erosion_magus_malady_noble",
        "summon_grim_phantom_undercurrent_noble", "summon_thunder_magus_agility_noble",
        "summon_thunder_magus_continuation_magnificent", "summon_thunder_magus_heavy_arrow_noble",
        "whirlwind_blade_swift_slash_magnificent", "whirlwind_endless_wind_magnificent",
    ]

    @pytest.mark.parametrize("item_id", _OTHER_TWELVE)
    def test_other_flipped_supports_now_partial(self, item_id):
        """The remaining 12 supports the same two defects flipped full→partial: never re-overclaim
        'full', and always carry the explanatory detail (never silently 'none')."""
        status, detail = skill_coverage(_SKILLS[item_id])
        assert status == "partial", f"{item_id}: expected 'partial', got {status!r}"
        assert detail, f"{item_id}: expected non-empty coverage_detail"

    def test_chain_lightning_still_full_anchor(self):
        """Anchor: the fixes narrow overclaims, they don't touch a genuinely fully-modeled skill."""
        status, detail = skill_coverage(_SKILLS["chain_lightning"])
        assert status == "full"
        assert detail == []

    def test_berserking_blade_split_shot_still_partial(self):
        assert skill_coverage(_SKILLS["berserking_blade"])[0] == "partial"
        assert skill_coverage(_SKILLS["split_shot"])[0] == "partial"

    def test_dance_of_the_deep_trait_still_none(self):
        status, detail = trait_coverage("dance_of_the_deep")
        assert status == "none"
        assert detail == []

    def test_sing_with_the_tide_trait_still_partial(self):
        status, detail = trait_coverage("sing_with_the_tide")
        assert status == "partial"
        assert detail


# ── Support / activation-medium coverage (2026-07-12 fix: every support previously read 'none') ──────
class TestSupportCoverage:
    """Before the 2026-07-12 fix, `skill_coverage` gated EVERY support/activation-medium item on
    `skill_resolver.resolve_skill(...).supported` — a check that only makes sense for ACTIVE skills
    (supports are never `_REGISTRY` members), so it silently read 'none' for every support regardless of
    how well-modeled it actually was. `_SUPPORT_SKILL_TYPES` items now take their own tooltip-line
    reduction, same rule as active skills/gear: any unmodeled mechanic line -> 'partial', zero checkable
    lines -> 'none', all-modeled -> 'full'."""

    def test_berserking_blade_sweep_partial_skill_area_unconsumed(self):
        """Sweep's own tooltip carries the stack-cap-double line (recognized, no stat) AND its "additional
        Skill Area per buff" line — Skill Area is DPS-inert on its own (see berserking_blade.py's module
        docstring) and this specific per-buff-additional-Skill-Area value is never read by any consumer, so
        the item can't be 'full' even though its OTHER lines (the universal rank line, the intrinsic buff)
        are modeled."""
        status, detail = skill_coverage(_SKILLS["berserking_blade_sweep_magnificent"])
        assert status == "partial"
        assert detail
        assert any("skill area" in d.lower() for d in detail), detail

    def test_howling_gale_rapid_sweep_full(self):
        """Every checkable line on Rapid Sweep resolves to a consumed stat or a recognized (keys=[])
        behavioral clause (the steady-state stack-cap assumption) -> 'full'."""
        status, detail = skill_coverage(_SKILLS["howling_gale_rapid_sweep_magnificent"])
        assert status == "full"
        assert detail == []

    def test_activation_medium_lock_on_no_checkable_line_is_none(self):
        """(2026-07-12 rename) `activation_medium_lock_on`'s SS12 catalog entry carries an EMPTY
        `progression` list — no tiers at all, so `_am_base_tier_text` returns `(None, "")` and
        `_am_coverage` never even reaches a sentence to scan -> 'none' by the vacuous-truth guard,
        never 'full'. Replaces `activation_medium_boss` as this guard's anchor: now that AM coverage
        is derived from real wiring (`_am_coverage`, not the blanked-tooltip carve-out), Boss's
        'Trigger radius (metres)'/'Interval: 0.1s' sentences surface as genuinely unwired clauses, so
        Boss itself now reads 'partial' (see `test_activation_medium_boss_partial_...` below) and can
        no longer serve as the 'zero checkable lines' anchor."""
        status, detail = skill_coverage(_SKILLS["activation_medium_lock_on"])
        assert status == "none"
        assert detail == []

    def test_activation_medium_boss_partial_trigger_radius_and_interval_unwired(self):
        """Anchor for the reclassification noted above: Boss's own base-tier text carries a bare
        'Trigger radius (metres)' descriptor and an 'Interval: 0.1s' clause, neither of which
        `activation_medium.parse_am_rolls`/`_classify` wires to a consumed stat -> 'partial', never
        'none' (it DOES have checkable content) and never 'full' (that content isn't actually modeled)."""
        status, detail = skill_coverage(_SKILLS["activation_medium_boss"])
        assert status == "partial"
        assert detail
        joined = " ".join(detail).lower()
        assert "trigger radius" in joined or "interval" in joined

    def test_activation_medium_sentry_partial_fixed_count_carveout(self):
        """The AM-fixed-count carve-out (`_am_unmodeled_fixed_counts`): Sentry's '+2 Sentries...deployed at
        a time' clause has no `(lo-hi)` roll at any tier, so `parse_am_rolls`'s `_RANGE` regex can never
        capture it -> unwired -> must surface as an unmodeled clause, never silently 'full'."""
        status, detail = skill_coverage(_SKILLS["activation_medium_sentry"])
        assert status == "partial"
        assert detail
        joined = " ".join(detail).lower()
        assert "sentries" in joined and "deployed at a time" in joined

    def test_activation_medium_tangle_partial_fixed_count_carveout(self):
        """Same carve-out, Tangle's shape: 'Creates 1 additional Tangle' is a bare discrete count, never
        parenthesized at any tier -> the roll parser never sees it -> unmodeled -> 'partial'."""
        status, detail = skill_coverage(_SKILLS["activation_medium_tangle"])
        assert status == "partial"
        assert detail
        joined = " ".join(detail).lower()
        assert "creates 1 additional tangle" in joined

    def test_activation_medium_full_partial_semantics_from_wiring(self):
        """(2026-07-12 rewrite) The old premise — AM coverage is a downgrade-only carve-out layered on
        top of `_reduce_tooltip_lines`'s tooltip-line reduction — is obsolete: `_am_coverage` no longer
        consults the tooltip at all (it's blanked for every AM line by design, see `_am_coverage`'s
        module-level comment); it derives full/partial/none straight from the SAME wiring
        `activation_medium.parse_am_rolls`/`_classify` use. New semantics pinned here:
          - A fully-wired AM (`activation_medium_motionless`: every `(lo-hi)` roll classifies to an
            applied, consumed stat key at every tier) -> 'full'.
          - An AM with an unwired fixed-count clause (`activation_medium_sentry`'s discrete '+2
            Sentries...deployed at a time', which has no `(lo-hi)` roll at any tier for
            `parse_am_rolls`'s `_RANGE` regex to ever capture) -> 'partial'.
          - No AM in the live SS12 catalog falsely reads 'full' while still carrying unresolved detail
            (the structural guard: 'full' implies empty `coverage_detail`, checked over the whole
            28-item catalog — the case an accidental future regression to the old blanket-none
            behavior, or a wiring change that stops checking a clause, would trip)."""
        status, detail = skill_coverage(_SKILLS["activation_medium_motionless"])
        assert status == "full"
        assert detail == []

        status, detail = skill_coverage(_SKILLS["activation_medium_sentry"])
        assert status == "partial"
        assert detail
        joined = " ".join(detail).lower()
        assert "sentries" in joined and "deployed at a time" in joined

        am_ids = [iid for iid, s in _SKILLS.items() if iid.startswith("activation_medium_")]
        assert am_ids, "expected >=1 activation-medium item in the SS12 skill catalog"
        for iid in am_ids:
            status, detail = skill_coverage(_SKILLS[iid])
            if status == "full":
                assert detail == [], f"{iid}: reported 'full' but carries non-empty coverage_detail"

    def test_activation_medium_rhythm_partial_manual_use_penalty_and_rate_gap(self):
        """Rhythm's own base-tier text carries two clauses `_am_coverage` can't wire: the per-meter-of-
        movement damage rate ('+3% additional damage for every 1m of movement made during the trigger
        interval, up to...') and the flat manually-used-skill penalty ('-80% additional damage for
        manually used Supported Skill') — neither maps to an applied, consumed stat key via `_classify`,
        so Rhythm stays 'partial' even though it's a well-modeled AM overall."""
        status, detail = skill_coverage(_SKILLS["activation_medium_rhythm"])
        assert status == "partial"
        assert detail

    def test_activation_medium_fully_wired_anchors_read_full(self):
        """Three genuinely fully-wired AMs (verified live against the SS12 catalog): every `(lo-hi)` roll
        on each classifies to an applied, consumed stat key at every tier, and neither carries a leftover
        unwired fixed-count clause -> 'full', empty detail."""
        for item_id in (
            "activation_medium_motionless", "activation_medium_minion", "activation_medium_still_attack",
        ):
            status, detail = skill_coverage(_SKILLS[item_id])
            assert status == "full", f"{item_id}: expected 'full', got {status!r} (detail={detail!r})"
            assert detail == []

    def test_activation_medium_sweep_full_implies_empty_detail(self):
        """Sweep invariant over the WHOLE 28-item AM catalog (guards against a future AM overclaim
        regression): 'full' always carries empty `coverage_detail`, and non-empty detail never coexists
        with 'full'. Mirrors `TestSkillCoverageInvariants`/`TestLegendaryCoverageInvariants`'s 'iff' naming
        convention loosely — not a true biconditional, since `activation_medium_lock_on`'s 'none' (zero
        progression tiers at all) ALSO carries empty detail, same as every other entity type here."""
        am_ids = sorted(iid for iid, s in _SKILLS.items() if iid.startswith("activation_medium_"))
        assert len(am_ids) == 28, f"expected 28 activation-medium items in the SS12 catalog, found {len(am_ids)}"
        for iid in am_ids:
            status, detail = skill_coverage(_SKILLS[iid])
            if status == "full":
                assert detail == [], f"{iid}: 'full' must carry empty coverage_detail"
            if detail:
                assert status == "partial", (
                    f"{iid}: non-empty coverage_detail implies 'partial', never 'full'/'none'"
                )


class TestGluedClauseFullLineRule:
    """Regression guard for the 2026-07-12 "class-closing" fix in `_reduce_tooltip_lines`: a tooltip line
    is only 'modeled' if EVERY distinct clause it carries (split at the same boundary
    `support_mapper._strip_support_target` truncates at) independently resolves to a confident, CONSUMED
    stat key — not just the first clause's key, which is all the live resolver ever reports for a glued
    multi-clause `badge_text`. No dedicated test existed for this rule before this fix; this class is that
    coverage."""

    def test_fragile_resurrection_partial_with_unmodeled_damage_taken_clause(self):
        """The specific overclaim this fix closed: fragile_resurrection's 3rd description line glues onto
        a single `badge_text` alongside the (dropped, unconsumed) '+10% additional damage taken during the
        supported skill's restoration effect' clause. Pre-fix, resolving the whole glued blob only ever
        surfaced the FIRST clause's key, so this item could read 'full' despite the damage-taken clause
        never being consumed anywhere (`dmg_taken_additional` is tracked-only in `mod_parser.py`, never
        wired into a consumer, so never in `consumable_universe()`)."""
        status, detail = skill_coverage(_SKILLS["fragile_resurrection"])
        assert status == "partial"
        joined = " ".join(detail).lower()
        assert "additional damage taken" in joined
        assert "restoration effect" in joined

    def test_glued_line_with_one_unconsumed_clause_is_not_full(self):
        """Focused unit test of the rule itself, through `skill_coverage`'s public entry point (not the
        private clause helpers directly, so this also pins the wiring between `_split_coverage_clauses`/
        `_clause_resolves` and `_reduce_tooltip_lines`). A single `badge_text` carrying two distinct
        clauses glued at the live `_strip_support_target` truncation boundary — one that resolves to a
        confident, CONSUMED key ("+50% Cold Damage for the supported skill" -> `cold_dmg_inc`, which the
        engine reads) and one that resolves but to a key the engine never consumes (fragile_resurrection's
        own real "+10% additional damage taken during the supported skill's restoration effect" ->
        `dmg_taken_additional`) — must NOT count as modeled even though the first clause alone would.
        `item_id='fragile_resurrection'` is passed so the second clause resolves via that item's own
        bespoke scoping (mirrors the live resolver's item-scoped lookup), same as production."""
        skill_data = {"item_id": "fragile_resurrection", "skill_type": "support_skill"}
        bt = (
            "+50 % Cold Damage for the supported skill. "
            "+10 % additional damage taken during the supported skill's restoration effect"
        )
        tooltip = {"lines": [{"badge_text": bt, "text": bt}]}
        status, detail = skill_coverage(skill_data, tooltip)
        assert status == "partial"
        assert detail
        joined = " ".join(detail).lower()
        assert "additional damage taken" in joined
        # The RESOLVING clause must not itself be reported as unmodeled — only the genuinely unconsumed
        # clause belongs in coverage_detail.
        assert "cold damage" not in joined

    def test_glued_line_with_both_clauses_consumed_is_full(self):
        """Isn't-over-tight companion: the same glued-line machinery, but with BOTH clauses resolving to
        consumed keys, must still read 'full' — the rule gates on an unconsumed clause existing, not on
        the mere presence of multiple clauses."""
        skill_data = {"item_id": "fragile_resurrection", "skill_type": "support_skill"}
        bt = "+50 % Cold Damage for the supported skill. +50 % Fire Damage for the supported skill"
        tooltip = {"lines": [{"badge_text": bt, "text": bt}]}
        status, detail = skill_coverage(skill_data, tooltip)
        assert status == "full"
        assert detail == []

    def test_single_fully_resolving_line_still_reads_full(self):
        """Positive control: the rule isn't over-tight for the overwhelming majority of lines, which are
        already atomic (no internal clause-split boundary at all). `added_cold_damage` is a generic
        single-clause support ("Adds 2 - 3 Cold Damage to the supported skill") with nothing to split —
        `_split_coverage_clauses` is a no-op for it — and must still read 'full'."""
        status, detail = skill_coverage(_SKILLS["added_cold_damage"])
        assert status == "full"
        assert detail == []


class TestSupportCoverageInvariants:
    """Sweep EVERY support/activation-medium item in the catalog: the same no-overclaim rules already
    proven for legendary gear (`TestLegendaryCoverageInvariants`), now also guarding the support path that
    was the 2026-07-12 fix's actual blind spot — this is the invariant that was missing and let the
    overclaim risk hide (nothing could ever reach 'full' before the fix, so the question was moot by
    accident; now that supports CAN reach 'full', this sweep is the guard that catches a future regression)."""

    def test_full_iff_empty_detail_and_none_never_by_default(self):
        from engine.coverage import _SUPPORT_SKILL_TYPES
        supports = {iid: s for iid, s in _SKILLS.items() if s.get("skill_type") in _SUPPORT_SKILL_TYPES}
        assert supports, "support/activation-medium catalog is empty — cannot run the sweep"
        checked = 0
        for item_id, s in supports.items():
            status, detail = skill_coverage(s)
            checked += 1
            if status == "full":
                assert detail == [], f"{item_id}: 'full' must carry empty coverage_detail"
            if detail:
                assert status == "partial", (
                    f"{item_id}: non-empty coverage_detail implies 'partial', never 'full'/'none'"
                )
            if status == "none":
                # 'none' means zero checkable lines at all -> detail must be empty (mirrors the gear-affix
                # "none's detail is a subset of its own line texts" rule; here the subset is always the
                # empty set since coverage.py never appends detail before returning 'none' for a support).
                assert detail == [], f"{item_id}: 'none' but carries non-empty coverage_detail"
        assert checked == len(supports)

    def test_full_support_every_clause_independently_consumed(self):
        """Mechanizes the 'full <=> every clause consumed' property (2026-07-12 glued-clause fix), not
        merely 'full <=> empty coverage_detail' (already covered above). For every support currently
        reading 'full', independently re-derive each of its OWN tooltip lines' clause-level resolution —
        walking `build_tooltip`'s lines directly and re-splitting/re-resolving with the SAME coverage-local
        primitives `_reduce_tooltip_lines` itself uses (`_split_coverage_clauses` + `_clause_resolves`) —
        and confirm there is no clause left unconsumed. This is the exact guard that would have caught the
        `fragile_resurrection` overclaim before this fix landed (its glued 3rd clause resolves to
        `dmg_taken_additional`, a recognized-but-never-consumed key): a regression that stops splitting a
        glued line, or starts trusting an unconsumed clause, flips a 'full' item without necessarily
        emptying `coverage_detail` in a way the simpler invariant above would catch on its own."""
        from engine.coverage import _SUPPORT_SKILL_TYPES, _split_coverage_clauses, _clause_resolves
        from engine.tooltip import build_tooltip
        from engine.consumable_universe import consumable_universe

        universe = consumable_universe()
        supports = {iid: s for iid, s in _SKILLS.items() if s.get("skill_type") in _SUPPORT_SKILL_TYPES}
        checked_full = 0
        for item_id, s in supports.items():
            status, _detail = skill_coverage(s)
            if status != "full":
                continue
            checked_full += 1
            tooltip = build_tooltip(s)
            for ln in tooltip.get("lines") or []:
                if ln.get("coverage") == "modeled":
                    continue
                bt = (ln.get("badge_text") or "").strip()
                if not bt:
                    continue
                for clause in _split_coverage_clauses(bt) or [bt]:
                    assert _clause_resolves(clause, item_id, universe), (
                        f"{item_id}: reported 'full' but clause {clause!r} does not resolve to a "
                        "confident, consumed stat key"
                    )
        assert checked_full > 0, "expected >=1 support to read 'full' for this sweep to be meaningful"


# ── Hero traits ────────────────────────────────────────────────────────────────────────────────
class TestTraitCoverage:
    def test_sing_with_the_tide_partial_build_gated_context(self):
        """(2026-07-12 accuracy fix) `sing_with_the_tide.status_lines` takes `main_skill_tags`/
        `main_skill_name` beyond the two universal build-independent params (it warns on a Bard→Bard-Song
        main-skill conversion) — `hero_traits.build_gated_status_params` detects this structurally, so the
        build-independent probe can never rule out an unseen warning branch and downgrades to 'partial'
        instead of overclaiming 'full'. Was `test_sing_with_the_tide_full` before this fix."""
        status, detail = trait_coverage("sing_with_the_tide")
        assert status == "partial"
        assert detail, "must carry an explanatory coverage_detail, not silently downgrade with no reason"
        joined = " ".join(detail).lower()
        assert "build-specific" in joined or "main_skill" in joined

    def test_high_court_chariot_full(self):
        # status_lines(*, slot_levels, advanced_picks, **_) -> only the two universal params -> no build-gated
        # branch the probe could miss.
        status, detail = trait_coverage("high_court_chariot")
        assert status == "full"
        assert detail == []

    def test_lightning_shadow_full(self):
        status, detail = trait_coverage("lightning_shadow")
        assert status == "full"
        assert detail == []

    def test_unsullied_blade_full(self):
        status, detail = trait_coverage("unsullied_blade")
        assert status == "full"
        assert detail == []

    def test_dance_of_the_deep_none_no_module(self):
        status, detail = trait_coverage("dance_of_the_deep")
        assert status == "none"
        assert detail == []

    def test_wind_stalker_partial(self):
        status, detail = trait_coverage("wind_stalker")
        assert status == "partial"
        assert detail

    def test_licorice_note_partial(self):
        status, detail = trait_coverage("licorice_note")
        assert status == "partial"
        assert detail

    def test_build_gated_trait_never_reads_full(self):
        """Structural guard (not a hand-maintained per-trait list): ANY bespoke trait module whose
        `status_lines` signature accepts a build-specific param beyond the two universal ones
        (`hero_traits.build_gated_status_params` non-empty) must never be reported 'full' by
        `trait_coverage` — a regression here would silently re-overclaim a trait like
        `sing_with_the_tide` the moment a future module adds a similarly-gated branch."""
        from engine import hero_traits
        gated_any = False
        for trait_id in hero_traits._STATUS:
            if hero_traits.build_gated_status_params(trait_id):
                gated_any = True
                status, _detail = trait_coverage(trait_id)
                assert status != "full", f"{trait_id}: build-gated status_lines param(s) but reported 'full'"
        assert gated_any, "expected at least one trait module with a build-gated status_lines param"


# ── Legendary gear ─────────────────────────────────────────────────────────────────────────────
class TestLegendaryCoverage:
    def test_berserker_bracer_full(self):
        status, detail = legendary_coverage(_LEGENDARIES["berserker_bracer"])
        assert status == "full"
        assert detail == []

    def test_aeterna_martyr_partial_defensive_mod_unconsumed(self):
        """The key strict-definition case: aeterna_martyr carries a defensive "-additional Physical
        Damage taken" affix the engine never consumes (no damage-taken-reduction stat is read for
        this item). Even though the item has plenty of modeled offense affixes, the strict rule
        means ANY unconsumed affix drops it to 'partial' — never silently promoted to 'full'."""
        status, detail = legendary_coverage(_LEGENDARIES["aeterna_martyr"])
        assert status == "partial"
        assert any("physical damage taken" in d.lower() for d in detail), detail

    def test_elemental_whirl_partial(self):
        status, detail = legendary_coverage(_LEGENDARIES["elemental_whirl"])
        assert status == "partial"
        assert detail


# ── Invariants (more robust than any single point value) ─────────────────────────────────────────
class TestSkillCoverageInvariants:
    @pytest.mark.parametrize("skill_id", sorted(_SKILLS.keys()))
    def test_full_iff_empty_detail(self, skill_id):
        status, detail = skill_coverage(_SKILLS[skill_id])
        if status == "full":
            assert detail == [], f"{skill_id}: 'full' must carry empty coverage_detail"
        else:
            assert status in ("partial", "none")
        if detail:
            assert status == "partial", f"{skill_id}: non-empty detail implies 'partial', never 'full'/'none'"


class TestTraitCoverageInvariants:
    _TRAIT_IDS = (
        "high_court_chariot", "licorice_note", "lightning_shadow", "sing_with_the_tide",
        "unsullied_blade", "wind_stalker", "dance_of_the_deep",
    )

    @pytest.mark.parametrize("trait_id", _TRAIT_IDS)
    def test_full_iff_empty_detail(self, trait_id):
        status, detail = trait_coverage(trait_id)
        if status == "full":
            assert detail == [], f"{trait_id}: 'full' must carry empty coverage_detail"
        if detail:
            assert status == "partial", f"{trait_id}: non-empty detail implies 'partial', never 'full'/'none'"


class TestLegendaryCoverageInvariants:
    """Sweep the WHOLE legendary catalog: guards against future overclaiming regressions."""

    def test_full_iff_empty_detail_and_none_means_zero_modeled(self):
        assert _LEGENDARIES, "legendary gear catalog is empty — cannot run the sweep"
        checked = 0
        for item_id, item in _LEGENDARIES.items():
            status, detail = legendary_coverage(item)
            checked += 1
            if status == "full":
                assert detail == [], f"{item_id}: 'full' must carry empty coverage_detail"
            if detail:
                assert status in ("partial", "none"), (
                    f"{item_id}: non-empty detail implies 'partial' or 'none', never 'full'"
                )
            if status == "none":
                # A 'none' item contributes zero modeled mods: EVERY distinct affix text must appear
                # in coverage_detail (nothing was silently counted as modeled).
                from engine.coverage import _iter_affixes
                affixes = _iter_affixes(item)
                affix_texts = {(a.get("raw_text") or "").strip() for a in affixes}
                assert set(detail) <= affix_texts or not affixes, (
                    f"{item_id}: 'none' but coverage_detail doesn't match its own affix texts"
                )
        assert checked == len(_LEGENDARIES)


# ── Endpoint wiring ────────────────────────────────────────────────────────────────────────────
class TestEndpointWiring:
    def test_get_skills_carries_coverage(self):
        from server import get_skills
        result = get_skills()
        assert result["season"] == _SEASON
        assert result["skills"], "expected non-empty skills catalog for SS12"
        for s in result["skills"]:
            assert "coverage" in s and s["coverage"] in ("full", "partial", "none")
            assert "coverage_detail" in s and isinstance(s["coverage_detail"], list)
        by_id = {s["item_id"]: s for s in result["skills"]}
        assert by_id["chain_lightning"]["coverage"] == "full"
        assert by_id["berserking_blade"]["coverage"] == "partial"

    def test_get_hero_traits_carries_coverage(self):
        from server import get_hero_traits
        result = get_hero_traits()
        assert result["season"] == _SEASON
        assert result["traits"], "expected non-empty hero-trait catalog for SS12"
        for t in result["traits"]:
            assert "coverage" in t and t["coverage"] in ("full", "partial", "none")
            assert "coverage_detail" in t and isinstance(t["coverage_detail"], list)

    def test_get_legendary_gear_index_carries_coverage(self):
        from server import get_legendary_gear_index
        result = get_legendary_gear_index()
        assert result["season"] == _SEASON
        assert result["items"], "expected non-empty legendary-gear-index catalog for SS12"
        for it in result["items"]:
            assert "coverage" in it and it["coverage"] in ("full", "partial", "none")
            assert "coverage_detail" in it and isinstance(it["coverage_detail"], list)
        by_id = {it["item_id"]: it for it in result["items"]}
        assert by_id["berserker_bracer"]["coverage"] == "full"
        assert by_id["aeterna_martyr"]["coverage"] == "partial"

    def test_get_legendary_gear_carries_resolved_keys_on_affixes(self):
        """`/api/legendary-gear`'s per-affix `resolved_keys` (2026-07-12) — the SAME resolution
        `engine.coverage._affix_is_modeled`/`_affix_resolved_keys` compute — is now on the wire for
        every implicit/explicit affix, so a catalog hover (item not equipped in the current build) can
        classify a gear affix client-side without the build-scoped `gear_mod_statuses` fallback (see
        `ModifierBadge.tsx`'s `gearStatus`). Spot-checked against `aeterna_martyr` (used above as the
        live legendary-coverage 'partial' anchor):
          - its Attack/Spell Critical Strike Rating affix is a recognized, modeled stat pair ->
            non-empty `resolved_keys`.
          - its per-Critical-Strike Trauma-Damage stacking affix ("...Stacks up to (3-4) time(s)") is
            genuinely unrecognized text (no `_affix_stat_keys`/clause resolver hit at all, distinct from
            the ALSO-partial-but-recognized '-additional Physical Damage taken' affix that resolves to a
            real, merely-unconsumed key) -> `resolved_keys == []`.
        """
        from server import get_legendary_gear

        result = get_legendary_gear()
        assert result["season"] == _SEASON
        assert result["items"], "expected non-empty legendary-gear catalog for SS12"

        by_id = {it["item_id"]: it for it in result["items"] if "item_id" in it}
        item = by_id["aeterna_martyr"]
        base = item["variants"]["base"]

        found_any = False
        for group in ("implicits", "explicits"):
            for a in base[group]:
                assert "resolved_keys" in a and isinstance(a["resolved_keys"], list), (
                    f"affix missing resolved_keys: {a.get('raw_text')!r}"
                )
                found_any = True
        assert found_any, "expected >=1 affix on aeterna_martyr to spot-check resolved_keys against"

        crit_rating = next(
            a for a in base["explicits"] if "Critical Strike Rating" in (a.get("raw_text") or "")
        )
        assert set(crit_rating["resolved_keys"]) == {"attack_crit_rating_flat", "spell_crit_rating_flat"}

        trauma_stack = next(
            a for a in base["explicits"]
            if "Trauma Damage" in (a.get("raw_text") or "") and "Stacks up to" in (a.get("raw_text") or "")
        )
        assert trauma_stack["resolved_keys"] == []

        phys_dmg_taken = next(
            a for a in base["explicits"] if "additional Physical Damage taken" in (a.get("raw_text") or "")
        )
        assert phys_dmg_taken["resolved_keys"] == ["physical_dmg_taken_additional"], (
            "this affix is recognized (non-empty resolved_keys) but its key is never CONSUMED anywhere — "
            "the reason aeterna_martyr's legendary_coverage is 'partial' despite this affix resolving; "
            "distinct from the trauma-stacking affix above, which is genuinely unrecognized (empty list)"
        )
