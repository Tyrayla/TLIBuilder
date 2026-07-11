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
from engine.offense import calculate_offense, compute_dot, _target_mitigation_dot
from engine.skill_resolver import ResolvedSkill, SkillHitForm, DotForm
from engine.compute import _eval_intrinsic_additional

MIND_CONTROL_BASE = 222.0   # dot-model.json: "Mind Control (Erosion, base 222/sec at L16)"
PATH_OF_FLAMES_BASE = 299.0  # dot-model.json: "Path of Flames (Fire, base 299/sec at L16)"
_LEVEL = 16


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


# ── 4. Whitelist boundary — stats a naive implementation WOULD wrongly apply ───────────────────
class TestWhitelistBoundaryNegative:
    """Each of these, applied ALONE, must leave the DoT's DPS at its unmodified baseline."""

    def test_erosion_dmg_inc_excluded_on_mind_control(self):
        # erosion_dmg_inc is UNVERIFIED for DoT per dot-model.json's audit — not in the whitelist.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(erosion_dmg_inc=0.50)) == pytest.approx(155.4)

    def test_elemental_dmg_inc_excluded_on_path_of_flames(self):
        # Not whitelisted at all (and "Elemental" excludes Erosion anyway — irrelevant here since this
        # is a Fire DoT, but elemental_dmg_inc is still not in the DoT increased whitelist).
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        assert _dot_dps_vs_target(skill, _source(elemental_dmg_inc=0.50)) == pytest.approx(209.3)

    def test_fire_dot_dmg_inc_excluded_on_erosion_dot(self):
        # fire_dot_dmg_inc is fire-ONLY; Mind Control's DoT is erosion.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(fire_dot_dmg_inc=0.50)) == pytest.approx(155.4)

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

    def test_spell_dmg_additional_excluded_from_dot_additional_pool(self):
        # The DoT additional whitelist is exactly {dmg_additional, dot_dmg_additional} — spell_dmg_additional
        # is a hit-only pool member and must not leak in even on a Spell-tagged DoT.
        skill = _dot_skill("erosion", MIND_CONTROL_BASE)
        assert _dot_dps_vs_target(skill, _source(spell_dmg_additional=0.50)) == pytest.approx(155.4)

    def test_elemental_dmg_additional_excluded_on_fire_dot(self):
        skill = _dot_skill("fire", PATH_OF_FLAMES_BASE)
        assert _dot_dps_vs_target(skill, _source(elemental_dmg_additional=0.50)) == pytest.approx(209.3)


# ── 5. Resistance-only mitigation — no armor term, penetration flows through resistance ────────
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


# ── 6. Non-DoT skills are byte-unchanged; compute_dot is presence-gated ───────────────────────
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


# ── 7. The kind="dot" DamageRow shape ───────────────────────────────────────────────────────────
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


# ── 8. Above-max-level — compute_dot deliberately does NOT apply the HIT-only ×1.10/level multiplier ─────
class TestAboveMaxLevelPinnedNotApplied:
    """PINS the CURRENT deliberate behavior: `_above_max_mult` (engine/offense.py) applies a compounding
    ×1.10/level (then ×1.08/level past +10) to HIT forms once `effective_level` exceeds a skill's max level —
    but `compute_dot` never reads it (see its docstring: "No crit_factor / double_dmg_factor ... and no
    `_delivery`" — above-max is the same story, just not spelled out there). A DoT skill pushed above its
    max level (20) caps at the level-20 BASE rate, full stop.

    This is NOT sourced in-game either way (no in-game measurement of a DoT skill above its max level exists
    in data/verification/) — it is a deliberate engineering default (lookup_level clamps via
    `min(effective_level, skill.max_level)`, and `compute_dot` has no above-max term at all), flagged as an
    OPEN in-game verification item. This test exists so a future change to that default is a DELIBERATE diff
    against this pin, not a silent behavior change: if you add above-max scaling to compute_dot on purpose,
    update this test's expected number on purpose.
    """

    def test_mind_control_above_max_level_caps_at_level_20_base(self):
        resolved = _real_resolved_skill("mind_control")
        assert resolved.max_level == 20
        # Hand-derived from data/seasons/SS12/_skills.json: mind_control's progression `damage` field at
        # level 20 reads "Deals 675 per second Erosion Damage Over Time" -> base 675.0/sec (confirmed by
        # direct inspection of the season data file, independent of the engine).
        assert resolved.dot_forms_by_level[20][0].base_per_second == pytest.approx(675.0)

        # +5 all_skill_level on top of base_level=16 -> effective_level = 16 + 5 = 21, one level ABOVE the
        # skill's max (20). skill_effective_level() computes this; calculate_offense then does
        # lookup_level = min(effective_level, skill.max_level) = min(21, 20) = 20, so compute_dot reads the
        # level-20 DotForm (675/sec) -- NOT a level-21 form (none exists) and NOT 675 scaled by any
        # above-max multiplier.
        r = calculate_offense(_source(all_skill_level=5), resolved, _LEVEL)
        dot_row = next(row for row in r.damage_rows if row.kind == "dot")
        # Hand: 675 (L20 base) x (1 + 0 increased) x (1 + 0 additional) x 0.70 (dummy erosion resist) = 472.5.
        assert dot_row.dps_vs_target_final == pytest.approx(472.5)
        # NOT what a HIT-form's _above_max_mult(21, 20) = 1.10**1 = 1.10 would give if it were (wrongly, per
        # current design) applied to this DoT: 675 x 1.10 x 0.70 = 519.75.
        assert dot_row.dps_vs_target_final != pytest.approx(519.75)


# ── 9. Intrinsic additional — "+21.5% additional damage per +1 additional Max Channeled Stack" engages ────
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
