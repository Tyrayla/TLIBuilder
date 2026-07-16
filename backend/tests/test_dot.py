"""Damage over Time (DoT) skill-DoT damage stage — Mind Control, Path of Flames.

Every pinned number below is HAND-DERIVED from `data/verification/dot-model.json`'s formula
    dot_dps = base_per_second(level) × (1 + Σ increased) × Π(1 + additional) × resist_only_mult
independently of `engine.offense.compute_dot`'s own source — this suite does not recompute the
formula from the implementation, it pins literals computed by hand (see the comment above each
assertion) so a real behavior change in the engine would make these FAIL, not silently agree.

Base rates (dot-model.json, both at skill level 16 — the level the 12 in-game data points were
taken at): Mind Control (Erosion) 222/sec, Path of Flames (Fire) 299/sec. Target: the standard
Lvl-85 dummy, 30% erosion resistance / 30% elemental (fire/cold/lightning) resistance / 50% armor
(`engine.offense.TARGET_EROSION_RESIST` / `TARGET_ELEMENTAL_RESIST` / `TARGET_ARMOR_MITIGATION`) —
the engine's default target_config (None) reproduces exactly this dummy.
"""
import pytest

from engine.models import BuildSource
from engine.offense import (
    calculate_offense, compute_dot, _target_mitigation_dot,
    _dot_type_increased_keys, _dot_type_additional_keys,
)
from engine.skill_resolver import ResolvedSkill, SkillHitForm, DotForm
from engine.compute import _eval_intrinsic_additional
from persistence import season_manager

MIND_CONTROL_BASE = 222.0   # dot-model.json: "Mind Control (Erosion, base 222/sec at L16)"
PATH_OF_FLAMES_BASE = 299.0  # dot-model.json: "Path of Flames (Fire, base 299/sec at L16)"
_LEVEL = 16

_SS12_ONLY = pytest.mark.skipif(
    season_manager.get_active_season() != "SS12",
    reason="SS12-specific ground truth: Mind Control's base Erosion DoT rate was rebalanced in SS13 "
           "(675/sec -> 519/sec at L20). Pending SS13 re-verification post-flip, not a deletion.",
)


def _source(**stats) -> BuildSource:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _dot_skill(dtype: str, base: float, level: int = _LEVEL, extra_tags: list[str] | None = None) -> ResolvedSkill:
    """A pure skill-DoT host (no hit component) shaped like Mind Control / Path of Flames — Spell + its
    damage type, dot_forms_by_level carrying exactly one DotForm at `level`."""
    tags = ["spell", dtype] + (extra_tags or [])
    return ResolvedSkill(
        skill_id="test_dot", name="Test DoT", tags=tags, max_level=20,
        hit_forms_by_level={}, supported=True, is_spell=True,
        base_cast_time=0.333, damage_types=[dtype],
        dot_forms_by_level={level: [DotForm(base_per_second=base, dtype=dtype, duration=2.0)]},
    )


def _dot_dps_vs_target(skill: ResolvedSkill, source: BuildSource) -> float:
    r = calculate_offense(source, skill, _LEVEL)
    dot_rows = [row for row in r.damage_rows if row.kind == "dot"]
    assert len(dot_rows) == 1
    return dot_rows[0].dps_vs_target_final


# ── 1. Acceptance — both skills, no gear, standard dummy ───────────────────────────────────────
class TestAcceptance:
    def test_mind_control_baseline(self):
        # 222 × (1+0) × (1+0)^0 × (1 − 0.30) = 222 × 0.70 = 155.4
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        r = calculate_offense(_source(), skill, _LEVEL)
        assert r.total_dps == pytest.approx(MIND_CONTROL_BASE)
        assert r.total_dps_vs_target == pytest.approx(155.4)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        assert dot_row.dps_vs_target_final == pytest.approx(155.4)

    def test_path_of_flames_baseline(self):
        # 299 × 0.70 = 209.3
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        r = calculate_offense(_source(), skill, _LEVEL)
        assert r.total_dps == pytest.approx(PATH_OF_FLAMES_BASE)
        assert r.total_dps_vs_target == pytest.approx(209.3)


# ── 2. Increased pool — dmg_inc / spell_dmg_inc / dot_dmg_inc pool identically ─────────────────
class TestIncreasedPoolHandComputed:
    # 222 × 1.27 × 0.70 = 197.358 (hand: 222*1.27=281.94; 281.94*0.7=197.358)
    EXPECTED = 197.358

    @pytest.mark.parametrize("stat_key", ["dmg_inc", "spell_dmg_inc", "dot_dmg_inc"])
    def test_each_whitelisted_increased_key_moves_it_identically(self, stat_key):
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        r = calculate_offense(_source(**{stat_key: 0.27}), skill, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        assert dot_row.dps_vs_target_final == pytest.approx(self.EXPECTED)

    def test_increased_pool_sums_before_multiplying(self):
        # dmg_inc + dot_dmg_inc pool into ONE increased term: 9% + 18% = 27%, same as a single 27% source.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        r = calculate_offense(_source(dmg_inc=0.09, dot_dmg_inc=0.18), skill, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        assert dot_row.dps_vs_target_final == pytest.approx(self.EXPECTED)


# ── 3. Additional pool — multiplies SEPARATELY from increased ─────────────────────────────────
class TestAdditionalPoolHandComputed:
    def test_control_spell_additional_value(self):
        # Control Spell's +35.5% additional (dot-model.json): 222 × 1.355 × 0.70 = 210.567
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        r = calculate_offense(_source(dmg_additional=0.355), skill, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        assert dot_row.dps_vs_target_final == pytest.approx(210.567)

    def test_dot_dmg_additional_whitelisted(self):
        # 222 × 1.20 × 0.70 = 186.48
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        r = calculate_offense(_source(dot_dmg_additional=0.20), skill, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        assert dot_row.dps_vs_target_final == pytest.approx(186.48)

    def test_increased_and_additional_multiply_separately_not_summed(self):
        # +10% increased AND +20% additional: 222 × 1.10 × 1.20 × 0.70 = 205.128 — NOT the naive
        # (1 + 0.10 + 0.20) = 1.30 single-pool answer, which would give 222 × 1.30 × 0.70 = 202.02.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        r = calculate_offense(_source(dmg_inc=0.10, dmg_additional=0.20), skill, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        assert dot_row.dps_vs_target_final == pytest.approx(205.128)
        assert dot_row.dps_vs_target_final != pytest.approx(202.02)


# ── 4. Owner-confirmed type-scoped damage-scoping rule (2026-07-10) — "X Damage" applies to BOTH a hit and
#      an X-type DoT; "Elemental Damage" applies to fire/cold/lightning DoT but NEVER erosion ─────────────────
class TestTypeScopedDamageApplies:
    """Per the owner-confirmed 2026-07-10 rule (`engine.offense`'s `_dot_type_increased_keys` /
    `_dot_type_additional_keys`, unioned into `compute_dot`'s pools): a type-matching "X Damage" stat (both
    increased and additional) now applies to an X-type DoT, and "Elemental Damage" applies to fire/cold/
    lightning DoT (never erosion — TLI "Elemental" excludes Erosion). These PIN the CORRECTED behavior —
    these used to assert exclusion; a regression back to exclusion would fail these."""

    def test_erosion_dmg_inc_applies_on_mind_control_erosion_dot(self):
        # erosion_dmg_inc is "X Damage" for X=erosion; Mind Control's DoT IS erosion, so it now applies.
        # Hand: 222 × (1 + 0.50) × 0.70 = 233.1.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(erosion_dmg_inc=0.50)) == pytest.approx(233.1)

    def test_elemental_dmg_inc_applies_on_path_of_flames_fire_dot(self):
        # elemental_dmg_inc applies to fire/cold/lightning DoT per the same rule; Path of Flames is Fire.
        # Hand: 299 × 1.50 × 0.70 = 313.95.
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        assert _dot_dps_vs_target(skill, _source(elemental_dmg_inc=0.50)) == pytest.approx(313.95)

    def test_elemental_dmg_additional_applies_on_fire_dot(self):
        # Same rule, additional side. Hand: 299 × 1.50 × 0.70 = 313.95.
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        assert _dot_dps_vs_target(skill, _source(elemental_dmg_additional=0.50)) == pytest.approx(313.95)

    def test_type_scoped_increased_and_additional_are_separate_pools(self):
        # fire_dmg_inc (increased) AND fire_dmg_additional (additional) on a fire DoT multiply as SEPARATE
        # pools — mirrors TestAdditionalPoolHandComputed.test_increased_and_additional_multiply_separately_
        # not_summed, but for the type-scoped pools instead of the generic ones.
        # Hand: 299 × 1.40 (increased) × 1.40 (additional) × 0.70 = 410.228 — NOT the collapsed single-pool
        # naive answer 299 × (1 + 0.40 + 0.40) × 0.70 = 299 × 1.80 × 0.70 = 376.74.
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        r = calculate_offense(_source(fire_dmg_inc=0.40, fire_dmg_additional=0.40), skill, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        assert dot_row.dps_vs_target_final == pytest.approx(410.228)
        assert dot_row.dps_vs_target_final != pytest.approx(376.74)

    def test_fire_dot_dmg_inc_deduped_not_double_counted(self):
        # `fire_dot_dmg_inc` sits in BOTH pools that feed a fire DoT's increased sum: the STATIC whitelist
        # (`_DOT_INCREASED_STATS`, gated `form.dtype == "fire"`) AND the TYPE-derived pool
        # (`_dot_type_increased_keys("fire")`, which includes `{dtype}_dot_dmg_inc` generically). compute_dot's
        # `_seen` guard must union these by KEY so the single stat value is only summed ONCE. This test fails
        # loudly if that guard ever breaks (e.g. someone "simplifies" the union into two independent sums).
        # Hand (correct, deduped): 299 × (1 + 0.30) × 0.70 = 299 × 1.30 × 0.70 = 272.09.
        # Hand (WRONG, double-counted, must NOT be produced): 299 × (1 + 0.30 + 0.30) × 0.70
        #     = 299 × 1.60 × 0.70 = 334.88.
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        dps = _dot_dps_vs_target(skill, _source(fire_dot_dmg_inc=0.30))
        assert dps == pytest.approx(272.09)
        assert dps != pytest.approx(334.88)

    def test_fire_dmg_inc_and_elemental_dmg_inc_sum_in_the_increased_pool(self):
        # fire_dmg_inc (type-scoped) and elemental_dmg_inc (elemental-scoped) are BOTH members of the fire
        # DoT's increased pool (`_dot_type_increased_keys("fire")` returns both, disjoint keys — no dedup
        # applies here, unlike the fire_dot_dmg_inc case above). They must SUM into the single increased term,
        # not collide/overwrite one another.
        # Hand: 299 × (1 + 0.30 + 0.20) × 0.70 = 299 × 1.50 × 0.70 = 313.95.
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        dps = _dot_dps_vs_target(skill, _source(fire_dmg_inc=0.30, elemental_dmg_inc=0.20))
        assert dps == pytest.approx(313.95)


# ── 5. Whitelist boundary — stats that remain correctly inert ──────────────────────────────────
class TestWhitelistBoundaryNegative:
    """Each of these, applied ALONE, must leave the DoT's DPS at its unmodified baseline. These are the
    guarantees that keep the 2026-07-10 type-scoping rule from over-applying: wrong-type "X Damage" stays
    off an X'-type DoT, and "Elemental Damage" stays off Erosion specifically."""

    def test_elemental_dmg_inc_excluded_on_erosion_dot(self):
        # "Elemental" excludes Erosion — elemental_dmg_inc must NOT touch Mind Control's erosion DoT even
        # though it does touch a fire DoT (see TestTypeScopedDamageApplies). Hand: 222 × 0.70 = 155.4.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(elemental_dmg_inc=0.50)) == pytest.approx(155.4)

    def test_fire_dmg_inc_excluded_on_erosion_dot(self):
        # fire_dmg_inc is Fire-only "X Damage"; Mind Control's DoT is Erosion — wrong type stays inert.
        # Hand: 222 × 0.70 = 155.4.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(fire_dmg_inc=0.50)) == pytest.approx(155.4)

    def test_erosion_dmg_inc_excluded_on_fire_dot(self):
        # erosion_dmg_inc is Erosion-only "X Damage"; Path of Flames' DoT is Fire — wrong type stays inert.
        # Hand: 299 × 0.70 = 209.3.
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        assert _dot_dps_vs_target(skill, _source(erosion_dmg_inc=0.50)) == pytest.approx(209.3)

    def test_fire_dot_dmg_inc_excluded_on_erosion_dot(self):
        # fire_dot_dmg_inc is fire-ONLY; Mind Control's DoT is erosion.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(fire_dot_dmg_inc=0.50)) == pytest.approx(155.4)

    def test_spell_dmg_additional_excluded_from_dot_additional_pool(self):
        # EXCLUDED pending an in-game measurement (owner's under-compute-and-flag policy, 2026-07-10): unlike
        # spell_dmg_inc (independently MEASURED in dot-model.json's audit and whitelisted in
        # `_DOT_INCREASED_STATS`), there is no recorded measurement of spell_dmg_additional applying to a DoT.
        # "spell" is a form tag, never covered by the owner's type/elemental damage-scoping rule (that rule is
        # about damage TYPES + Elemental, not the Spell form tag), and none of the 12 in-game data points in
        # dot-model.json isolated it on the additional side. So it stays INERT here — this used to assert it
        # APPLIES (233.1); flip back to positive deliberately, only if a future measurement confirms it.
        # Hand: 222 × (1 + 0) × 0.70 = 155.4 (baseline, unmodified).
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(spell_dmg_additional=0.50)) == pytest.approx(155.4)

    def test_crit_rating_never_affects_a_dot(self):
        # dot-no-crit.json / control_spell's -100% Crit Rating RAISED Mind Control's DPS in-game — a DoT
        # never crits, so even a huge crit-rating increase must be inert.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(crit_rating_inc=5.0)) == pytest.approx(155.4)

    def test_armor_pen_does_not_mitigate_a_dot(self):
        # Armor is in the Help DB's "does NOT affect Damage over Time" list — even 100% armor_pen changes
        # nothing for a DoT (armor was never part of its mitigation to begin with).
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(armor_pen=1.0)) == pytest.approx(155.4)


# ── 6. Resistance-only mitigation — no armor term, penetration flows through resistance ────────
class TestResistanceOnlyMitigation:
    def test_target_mitigation_dot_has_no_armor_term(self):
        # Directly at the mitigation-function level: even an enormous armor_pen changes nothing, because
        # _target_mitigation_dot never reads eff_armor at all.
        src = _source(armor_pen=999.0)
        assert _target_mitigation_dot(src, "erosion") == pytest.approx(0.70)
        assert _target_mitigation_dot(src, "fire") == pytest.approx(0.70)

    def test_erosion_pen_raises_mind_control_dps(self):
        # erosion_pen=0.10 → eff_resist = 0.30 − 0.10 = 0.20 → mult 0.80 → 222 × 0.80 = 177.6 (up from 155.4).
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        dps = _dot_dps_vs_target(skill, _source(erosion_pen=0.10))
        assert dps == pytest.approx(177.6)
        assert dps > 155.4

    def test_elemental_pen_does_not_help_an_erosion_dot(self):
        # TLI "Elemental" excludes Erosion — elemental_pen must not touch the erosion resistance branch.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(elemental_pen=0.50)) == pytest.approx(155.4)

    def test_elemental_pen_does_help_a_fire_dot(self):
        # elemental_pen=0.10 → eff_resist = 0.30 − 0.10 = 0.20 → mult 0.80 → 299 × 0.80 = 239.2 (up from 209.3).
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        dps = _dot_dps_vs_target(skill, _source(elemental_pen=0.10))
        assert dps == pytest.approx(239.2)
        assert dps > 209.3


# ── 7. Non-DoT skills are byte-unchanged; compute_dot is presence-gated ───────────────────────
class TestNonDotSkillsUnaffected:
    def test_real_chain_lightning_has_no_dot_forms_and_compute_dot_is_a_noop(self):
        # A real registered hit skill (Chain Lightning) from live season data — dot_forms_by_level must
        # be empty, and compute_dot on it must return the empty/zero no-op regardless of build stats.
        from server import _get_skills_data
        from persistence import season_manager
        from engine import skill_resolver

        season = season_manager.get_active_season()
        if not season:
            pytest.skip("no active season data available")
        skills = _get_skills_data(season)
        data = skills.get("chain_lightning")
        if not data:
            pytest.skip("chain_lightning not present in this season's data")
        resolved = skill_resolver.resolve_skill(data)
        assert resolved.dot_forms_by_level == {}

        rows, dps, dps_vt = compute_dot(
            _source(dmg_inc=0.50, dmg_additional=0.50), resolved, 16, resolved.is_spell, 0.0,
        )
        assert rows == [] and dps == 0.0 and dps_vt == 0.0

    def test_synthetic_hit_skill_total_dps_matches_hand_formula(self):
        # weapon_attack_speed=2.0, flat 50-50 physical → avg hit 50 × aps 2.0 = 100 dps; default physical
        # mitigation (no pen) = 1 − TARGET_ARMOR_MITIGATION(0.50) = 0.50 → 50 vs-target. Pure hit-formula
        # identity, independent of the DoT stage entirely (this skill has NO dot_forms_by_level).
        hit_skill = ResolvedSkill(
            skill_id="hit", name="Hit Skill", tags=["attack", "physical"], max_level=20,
            hit_forms_by_level={16: [SkillHitForm(name="Hit", effectiveness_pct=100.0, form_type="additive")]},
            supported=True,
        )
        src = _source(weapon_attack_speed=2.0, physical_attack_dmg_flat_min=50.0, physical_attack_dmg_flat_max=50.0)
        r = calculate_offense(src, hit_skill, 16)
        assert r.total_dps == pytest.approx(100.0)
        assert r.total_dps_vs_target == pytest.approx(50.0)
        assert len(r.damage_rows) == 1 and r.damage_rows[0].kind == "hit"

        rows, dps, dps_vt = compute_dot(src, hit_skill, 16, False, 0.0)
        assert rows == [] and dps == 0.0 and dps_vt == 0.0


# ── 8. The kind="dot" DamageRow shape ───────────────────────────────────────────────────────────
class TestDotDamageRowShape:
    def test_pure_dot_skill_row_shape(self):
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        r = calculate_offense(_source(), skill, _LEVEL)
        assert len(r.damage_rows) == 1
        row = r.damage_rows[0]
        assert row.kind == "dot"
        assert row.form_index == -1
        assert row.hit_min_by_type == {}
        assert row.hit_max_by_type == {}
        assert row.dps_by_type_vs_target == {"erosion": pytest.approx(155.4)}
        assert row.pct_of_total == pytest.approx(100.0, abs=1e-6)

    def test_pct_of_total_sums_to_100_with_a_hit_row_and_a_dot_row_together(self):
        # Synthetic hybrid (not a real skill) purely to exercise the merge guarantee: a skill with BOTH a
        # hit form and a DoT form must fold both into total_dps/total_dps_vs_target and reconcile pct_of_total
        # to 100.0 across the two rows — the invariant _finalize_damage_row_pcts + the compute_dot fold-in
        # in calculate_offense are jointly responsible for.
        hybrid = ResolvedSkill(
            skill_id="hybrid", name="Hybrid", tags=["attack", "physical"], max_level=20,
            hit_forms_by_level={16: [SkillHitForm(name="Hit", effectiveness_pct=100.0, form_type="additive")]},
            supported=True,
            dot_forms_by_level={16: [DotForm(base_per_second=100.0, dtype="physical", duration=2.0)]},
        )
        src = _source(weapon_attack_speed=1.0, physical_attack_dmg_flat_min=100.0, physical_attack_dmg_flat_max=100.0)
        r = calculate_offense(src, hybrid, 16)
        kinds = sorted(row.kind for row in r.damage_rows)
        assert kinds == ["dot", "hit"]
        assert sum(row.pct_of_total for row in r.damage_rows) == pytest.approx(100.0, abs=1e-6)
        assert sum(row.dps_vs_target_final for row in r.damage_rows) == pytest.approx(r.total_dps_vs_target)
        assert sum(row.dps_final for row in r.damage_rows) == pytest.approx(r.total_dps)


def _real_resolved_skill(item_id: str) -> ResolvedSkill:
    """Fetch and resolve a REAL registered skill from the active season's live data. Used where a test needs
    the skill's OWN production numbers (its actual level-20 progression base, its actual `intrinsic_additional`
    definition) rather than a hand-authored double — payload fidelity: derive the input from the real season
    data the builder actually serves, not a synthetic fixture reverse-shaped to fit the assertion."""
    from server import _get_skills_data
    from persistence import season_manager
    from engine import skill_resolver as sr

    season = season_manager.get_active_season()
    if not season:
        pytest.skip("no active season data available")
    data = _get_skills_data(season).get(item_id)
    if not data:
        pytest.skip(f"{item_id} not present in this season's data")
    return sr.resolve_skill(data)


# ── 9. Above-max-level — compute_dot now applies the SAME compounding ×1.10/level multiplier as hit forms ──
class TestAboveMaxLevelApplied:
    """PINS the owner-CONFIRMED (2026-07-10) behavior: above-max-level scaling applies to ALL damage forms,
    DoT included — not just hit forms. `compute_dot` now receives the SAME `above_mult` value
    (`_above_max_mult(effective_level, skill.max_level)`, computed once by `calculate_offense` and threaded
    into both the hit and DoT stages) instead of ignoring it. A DoT skill pushed above its max level (20)
    scales its level-20 BASE rate by that multiplier, exactly like a hit form would.

    This used to assert the OPPOSITE (that above-max was a HIT-only multiplier, deliberately NOT applied to
    DoT, filed as an open in-game verification question) — the verification entry now records this as
    CONFIRMED, not open (see dot-model.json). This test exists so a future regression back to "DoT ignores
    above-max" is a DELIBERATE diff against this pin, not a silent behavior change.
    """

    @_SS12_ONLY
    def test_mind_control_above_max_level_scales_by_above_max_mult(self):
        resolved = _real_resolved_skill("mind_control")
        assert resolved.max_level == 20
        # Hand-derived from data/seasons/SS12/_skills.json: mind_control's progression `damage` field at
        # level 20 reads "Deals 675 per second Erosion Damage Over Time" -> base 675.0/sec (confirmed by
        # direct inspection of the season data file, independent of the engine).
        assert resolved.dot_forms_by_level[20][0].base_per_second == pytest.approx(675.0)

        # +5 all_skill_level on top of base_level=16 -> effective_level = 16 + 5 = 21, one level ABOVE the
        # skill's max (20). skill_effective_level() computes this; calculate_offense then does
        # lookup_level = min(effective_level, skill.max_level) = min(21, 20) = 20, so compute_dot reads the
        # level-20 DotForm (675/sec) -- NOT a level-21 form (none exists) -- but DOES scale it by
        # above_mult = _above_max_mult(21, 20) = 1.10**1 = 1.10.
        r = calculate_offense(_source(all_skill_level=5), resolved, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        # Hand: 675 (L20 base) x (1 + 0 increased) x (1 + 0 additional) x 1.10 (above_mult) x 0.70 (dummy
        # erosion resist) = 675 x 1.10 x 0.70 = 519.75.
        assert dot_row.dps_vs_target_final == pytest.approx(519.75)
        # NOT the OLD (now-wrong) pin that ignored above_mult entirely: 675 x 0.70 = 472.5.
        assert dot_row.dps_vs_target_final != pytest.approx(472.5)


# ── 10. Intrinsic additional — "+21.5% additional damage per +1 additional Max Channeled Stack" engages ────
class TestIntrinsicAdditionalChanneledStackEngages:
    """Mind Control / Path of Flames' skill text: "+21.5% additional damage for every +1 additional Max
    Channeled Stack" (beyond the base 5-stack cap) -- `skill_resolver._resolve_dot_skill` wires this as
    `IntrinsicAdditional(per=_DOT_PER_ADDITIONAL_MAX_STACK, rating_key="max_channeled_stacks_flat",
    rating_source="stat", per_n=1.0)`. dot-model.json / the golden fixtures only assert it's STRUCTURALLY
    dormant at base 5 stacks (empty `intrinsic_additional_sources`); this test exercises it actually engaging
    when `max_channeled_stacks_flat` is pushed above 0, using the REAL resolved Mind Control skill (not a
    hand-authored double) so the multiplier under test is the one production code actually ships.
    """

    def test_multiplier_matches_skill_text_21_5_pct(self):
        from engine.skill_resolver import _DOT_PER_ADDITIONAL_MAX_STACK
        # The skill text says "+21.5% additional damage for every +1 additional Max Channeled Stack" ->
        # per-stack fraction must be exactly 0.215. If this ever drifts from 0.215, the engine no longer
        # matches the skill text -- REPORT, don't adjust this assertion to match.
        assert _DOT_PER_ADDITIONAL_MAX_STACK == pytest.approx(0.215)

    @_SS12_ONLY
    def test_dormant_at_base_five_stacks(self):
        # max_channeled_stacks_flat == 0 (the base 5-stack cap, unmodified) -> intrinsic bonus must be
        # exactly 0, and the DoT's DPS must equal the plain baseline (222 x 0.70 = 155.4, same as
        # TestAcceptance.test_mind_control_baseline).
        resolved = _real_resolved_skill("mind_control")
        extra = _eval_intrinsic_additional(resolved, _source(), {})
        assert extra == 0.0
        r = calculate_offense(_source(), resolved, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        assert dot_row.dps_vs_target_final == pytest.approx(155.4)

    @_SS12_ONLY
    def test_plus_two_max_channeled_stacks_raises_dps_by_43_pct(self):
        # +2 additional Max Channeled Stacks (7 total, 2 above the base 5) -> per the skill text,
        # +21.5% x 2 = +43% additional damage.
        resolved = _real_resolved_skill("mind_control")
        src = _source(max_channeled_stacks_flat=2.0)
        # Evaluated the SAME way the real build pipeline evaluates it (engine/compute.py's
        # _eval_intrinsic_additional, threaded into calculate_offense's extra_additional param by
        # engine/compute.py::_offense_for_slot) -- not reimplemented here.
        extra = _eval_intrinsic_additional(resolved, src, {})
        # Hand: 0.215 per stack x 2 additional stacks x (1 + 0 effect) = 0.43.
        assert extra == pytest.approx(0.43)

        r = calculate_offense(src, resolved, _LEVEL, extra_additional=extra)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        # Hand: 222 (L16 base) x (1 + 0 increased) x (1 + 0 dmg/dot_dmg additional) x (1 + 0.43 intrinsic)
        #     x 0.70 (dummy erosion resist) = 222 x 1.43 x 0.70 = 222.222.
        assert dot_row.dps_vs_target_final == pytest.approx(222.222)
        assert dot_row.dps_vs_target_final > 155.4
        # Same ratio check from the other direction: engaged / dormant == 1.43 exactly.
        assert dot_row.dps_vs_target_final == pytest.approx(155.4 * 1.43)


# ── 11. Future-type key derivation — unit tests of `_dot_type_increased_keys` / `_dot_type_additional_keys`
#       for damage types that have no DoT skill TODAY (cold, lightning, physical) ─────────────────────────────
class TestFutureTypeKeyDerivation:
    """Directly exercises the two key-derivation helpers (imported straight from `engine.offense`, not routed
    through `compute_dot`) for cold/lightning/physical — no DoT skill of these types exists yet, so this is
    the only coverage protecting the derivation logic itself. Guards against a regression the next time a
    cold/lightning/physical DoT ships: the union rule (type-scoped + elemental-scoped, `_ALL_STAT_KEYS`-gated)
    must keep producing exactly the right key set with no phantom/nonexistent stat keys."""

    def test_cold_is_elemental_increased_and_additional_keys(self):
        # cold IS elemental (ELEMENTAL = {fire, cold, lightning}) -> both the type-scoped "X Damage" keys AND
        # the elemental key must be present. cold_dot_dmg_inc does NOT exist as a real stat (only
        # fire_dot_dmg_inc does today) -> the _ALL_STAT_KEYS guard must drop it, not include a phantom key.
        assert _dot_type_increased_keys("cold") == ("cold_dmg_inc", "elemental_dmg_inc")
        assert _dot_type_additional_keys("cold") == ("cold_dmg_additional", "elemental_dmg_additional")

    def test_lightning_is_elemental_increased_and_additional_keys(self):
        # Same shape as cold -- lightning is also elemental, and lightning_dot_dmg_inc does not exist either.
        assert _dot_type_increased_keys("lightning") == ("lightning_dmg_inc", "elemental_dmg_inc")
        assert _dot_type_additional_keys("lightning") == ("lightning_dmg_additional", "elemental_dmg_additional")

    def test_physical_is_not_elemental_no_elemental_key(self):
        # Physical is explicitly excluded from ELEMENTAL (fire/cold/lightning only) -> physical_dmg_inc/
        # physical_dmg_additional apply, but elemental_dmg_inc/elemental_dmg_additional must NOT be appended.
        # physical_dot_dmg_inc does not exist as a real stat either -> dropped by the _ALL_STAT_KEYS guard.
        assert _dot_type_increased_keys("physical") == ("physical_dmg_inc",)
        assert _dot_type_additional_keys("physical") == ("physical_dmg_additional",)
        assert "elemental_dmg_inc" not in _dot_type_increased_keys("physical")
        assert "elemental_dmg_additional" not in _dot_type_additional_keys("physical")

    def test_no_phantom_dot_dmg_inc_keys_returned(self):
        # Only fire has a real `{type}_dot_dmg_inc` stat today (FIRE_DOT_DMG_INC in models/stat.py) -- for
        # every OTHER type, the generic `f"{dtype}_dot_dmg_inc"` candidate must be dropped by the
        # _ALL_STAT_KEYS guard rather than returned as a nonexistent stat key that would silently no-op
        # (or worse, collide with something unrelated) if the guard were ever removed.
        for dtype in ("cold", "lightning", "physical"):
            keys = _dot_type_increased_keys(dtype)
            assert f"{dtype}_dot_dmg_inc" not in keys
        # Fire is the one exception -- its dot_dmg_inc key DOES exist and IS returned.
        assert "fire_dot_dmg_inc" in _dot_type_increased_keys("fire")
