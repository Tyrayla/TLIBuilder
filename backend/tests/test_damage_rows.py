"""OffenseResult.damage_rows — the engine-owned breakdown-row contract (engine.offense.DamageRow) that
replaces the frontend's hand-reconstruction of `_delivery` (cast/tangle/spell-burst/multistrike multiplier)
and its back-solved per-type mitigation (see the bug write-up this shipped against: PlayerStatsScreen's
`breakdownMult` dropped multistrike_mult, and its per-type share used a PRE-mitigation ratio against a
POST-mitigation total).

Covers the four guarantees DamageRow makes:
  (a) pct_of_total sums to 100.0 across ALL rows, including builds with a "true" row (Mercury Baptism /
      Spell Ripple) that has no HitFormResult of its own.
  (b) on a multistrike build, row.dps_vs_target_final == form.dps_vs_target * multistrike_mult, and every
      row's dps_vs_target_final sums to total_dps_vs_target.
  (c) the {physical: 70, lightning: 30} + Numbed worked example: true per-type post-mitigation DPS is
      35 / 22.05 (not the frontend's old pre-mit-ratio-times-post-mit-total number).
  (d) target_mitigation_by_type[d] * enemy_vuln_by_type[d] == enemy_mult_by_type[d] for every d.
"""
import copy

import pytest

from engine.models import BuildSource
from engine.offense import (
    calculate_offense, _build_hit_damage_rows, _finalize_damage_row_pcts, HitFormResult,
)
from engine.skill_resolver import ResolvedSkill, SkillHitForm


def _source(**stats) -> BuildSource:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _hit(eff=100.0) -> SkillHitForm:
    return SkillHitForm(name="Hit", effectiveness_pct=eff, form_type="additive")


def _attack_skill(level=16) -> ResolvedSkill:
    return ResolvedSkill(
        skill_id="t", name="T", tags=["attack"], max_level=20,
        hit_forms_by_level={level: [_hit()]}, supported=True,
    )


def _spell_skill(dtype="lightning", base=(100.0, 100.0), level=16) -> ResolvedSkill:
    return ResolvedSkill(
        skill_id="s", name="S", tags=["spell", dtype], max_level=20,
        hit_forms_by_level={level: [_hit()]}, supported=True, is_spell=True,
        base_dmg_by_level={level: {dtype: base}},
        base_cast_time=1.0, added_dmg_effectiveness=1.0, damage_types=[dtype],
    )


def _multi_form_spell_skill(level=16) -> ResolvedSkill:
    """Icebound-Beam-shaped multi-form spell: two forms, each with its OWN base_dmg (native type) — Beam deals
    lightning, Blade deals fire — so a "you can only deal <type>" filter can zero one form while the other
    still contributes."""
    forms = [
        SkillHitForm(name="Beam", effectiveness_pct=100.0, form_type="additive",
                     base_dmg={"lightning": (100.0, 100.0)}),
        SkillHitForm(name="Blade", effectiveness_pct=100.0, form_type="additive",
                     base_dmg={"fire": (50.0, 50.0)}),
    ]
    return ResolvedSkill(
        skill_id="mf", name="MF", tags=["spell", "lightning", "fire"], max_level=20,
        hit_forms_by_level={level: forms}, supported=True, is_spell=True,
        base_cast_time=1.0, added_dmg_effectiveness=1.0, damage_types=["lightning", "fire"],
    )


class TestPctOfTotalSumsTo100:
    def test_mercury_baptism_build(self):
        # Rosa Unsullied Blade: a non-channeled attack with mercury_baptism_fraction set adds a kind="true"
        # row with no HitFormResult of its own — the % denominator must still reconcile to 100.
        src = _source(
            weapon_attack_speed=1.0,
            physical_attack_dmg_flat_min=100.0, physical_attack_dmg_flat_max=100.0,
            fire_attack_dmg_flat_min=50.0, fire_attack_dmg_flat_max=50.0,
            mercury_baptism_fraction=0.2,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        assert r.mercury_baptism_dps > 0.0
        assert any(row.kind == "true" and "Mercury" in row.name for row in r.damage_rows)
        assert sum(row.pct_of_total for row in r.damage_rows) == pytest.approx(100.0, abs=1e-6)
        assert sum(row.dps_vs_target_final for row in r.damage_rows) == pytest.approx(r.total_dps_vs_target)

    def test_spell_ripple_build(self):
        # Ethereal Prism: any Spell with spell_ripple_fraction set adds a kind="true" row.
        src = _source(spell_ripple_fraction=0.75)
        r = calculate_offense(src, _spell_skill(), 16)
        assert r.spell_ripple_dps > 0.0
        assert any(row.kind == "true" and "Ripple" in row.name for row in r.damage_rows)
        assert sum(row.pct_of_total for row in r.damage_rows) == pytest.approx(100.0, abs=1e-6)
        assert sum(row.dps_vs_target_final for row in r.damage_rows) == pytest.approx(r.total_dps_vs_target)

    def test_plain_build_no_true_rows(self):
        # No true-damage stage present → every row is kind="hit"; still reconciles to 100.
        src = _source(weapon_attack_speed=1.0, physical_attack_dmg_flat_min=100.0, physical_attack_dmg_flat_max=100.0)
        r = calculate_offense(src, _attack_skill(), 16)
        assert all(row.kind == "hit" for row in r.damage_rows)
        assert sum(row.pct_of_total for row in r.damage_rows) == pytest.approx(100.0, abs=1e-6)


class TestMultistrikeDelivery:
    def test_row_matches_form_times_multistrike_mult_and_sums_to_total(self):
        src = _source(
            weapon_attack_speed=1.5,
            physical_attack_dmg_flat_min=350.0, physical_attack_dmg_flat_max=350.0,
            multistrike_chance=1.16,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        assert r.multistrike_mult > 1.0
        assert len(r.damage_rows) == len(r.hit_forms) == 1
        row, form = r.damage_rows[0], r.hit_forms[0]
        assert row.dps_vs_target_final == pytest.approx(form.dps_vs_target * r.multistrike_mult)
        assert row.dps_final == pytest.approx(form.dps_contribution * r.multistrike_mult)
        assert sum(x.dps_vs_target_final for x in r.damage_rows) == pytest.approx(r.total_dps_vs_target)


class TestPerTypePostMitigationWorkedExample:
    """{physical: 70, lightning: 30} + Numbed (+50% Lightning Damage taken) → true post-mit 35 / 22.05.
    (The old frontend bug used the PRE-mit ratio 70/100, 30/100 against the POST-mit TOTAL, giving 39.9 /
    17.1 instead — this asserts the engine's own per-type split, which must match hand math exactly.)
    """
    def test_physical_lightning_numbed(self):
        src = _source(
            weapon_attack_speed=1.0,
            physical_attack_dmg_flat_min=70.0, physical_attack_dmg_flat_max=70.0,
            lightning_attack_dmg_flat_min=30.0, lightning_attack_dmg_flat_max=30.0,
            numbed_lightning_taken=0.5,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        assert r.crit_chance == 0.0 and r.double_dmg_factor == pytest.approx(1.0)   # no crit/double in play
        row = r.damage_rows[0]
        assert row.dps_by_type_vs_target["physical"] == pytest.approx(35.0)
        assert row.dps_by_type_vs_target["lightning"] == pytest.approx(22.05)
        assert sum(row.dps_by_type_vs_target.values()) == pytest.approx(row.dps_vs_target_final)
        # Surfaced fields so the frontend can stop back-solving mitigation from enemy_mult_by_type.
        assert r.target_mitigation_by_type["physical"] == pytest.approx(0.50)
        assert r.target_mitigation_by_type["lightning"] == pytest.approx(0.49)
        assert r.enemy_vuln_by_type["physical"] == pytest.approx(1.0)
        assert r.enemy_vuln_by_type["lightning"] == pytest.approx(1.5)


class TestMitigationTimesVulnEqualsEnemyMult:
    def test_identity_holds_for_every_dealt_type(self):
        src = _source(
            weapon_attack_speed=1.0,
            physical_attack_dmg_flat_min=70.0, physical_attack_dmg_flat_max=70.0,
            lightning_attack_dmg_flat_min=30.0, lightning_attack_dmg_flat_max=30.0,
            numbed_lightning_taken=0.5,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        assert set(r.target_mitigation_by_type) == set(r.enemy_vuln_by_type) == set(r.enemy_mult_by_type)
        assert r.target_mitigation_by_type  # non-empty — the skill deals physical + lightning
        for d in r.target_mitigation_by_type:
            assert r.target_mitigation_by_type[d] * r.enemy_vuln_by_type[d] == pytest.approx(r.enemy_mult_by_type[d])


class TestTotalDpsUnchanged:
    """The additive emit must not perturb total_dps / total_dps_vs_target by a single float, and must not
    mutate hit_forms. NOTE: `expected_total`/`expected_vs_target` below use the SAME formula offense.py itself
    uses (offense.py:2163-2164) — that assertion is tautologically true by construction and would not catch a
    change to the total_dps formula that updated hit_forms consistently. It's kept for its original regression
    value, but the REAL independent oracle is the second block: damage_rows are built by a DIFFERENT code path
    (_build_hit_damage_rows / _finalize_damage_row_pcts) and must independently reconcile back to the same
    totals."""
    def test_total_dps_matches_pre_existing_formula(self):
        src = _source(
            weapon_attack_speed=1.5, physical_attack_dmg_flat_min=350.0, physical_attack_dmg_flat_max=350.0,
            multistrike_chance=1.16,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        expected_total = sum(f.dps_contribution for f in r.hit_forms) * r.multistrike_mult
        expected_vs_target = sum(f.dps_vs_target for f in r.hit_forms) * r.multistrike_mult
        assert r.total_dps == expected_total
        assert r.total_dps_vs_target == expected_vs_target

        # Independent oracle: damage_rows are a SEPARATE emit (_build_hit_damage_rows), not a restatement of
        # the formula above — summing them back must reproduce the same totals and reconcile to 100%.
        assert sum(row.dps_final for row in r.damage_rows) == pytest.approx(r.total_dps)
        assert sum(row.dps_vs_target_final for row in r.damage_rows) == pytest.approx(r.total_dps_vs_target)
        assert sum(row.pct_of_total for row in r.damage_rows) == pytest.approx(100.0, abs=1e-6)

    def test_build_hit_damage_rows_does_not_mutate_hit_forms(self):
        # Direct contract test for _build_hit_damage_rows's own docstring claim ("Pure read of hit_forms —
        # never mutates it") — a deep copy taken BEFORE the call must equal the list AFTER.
        forms = [HitFormResult(
            name="F", effectiveness_pct=100.0, form_type="additive", proc_chance=1.0,
            damage_by_type={"physical": 100.0, "fire": 50.0},
            avg_hit_pre_crit=150.0, avg_hit_with_crit=150.0,
            dps_contribution=150.0, dps_vs_target=75.0, fires_per_sec=1.5,
            hit_min_by_type={"physical": 100.0, "fire": 50.0}, hit_max_by_type={"physical": 100.0, "fire": 50.0},
        )]
        before = copy.deepcopy(forms)
        _build_hit_damage_rows(forms, delivery=1.6033, mitigation_fn=lambda t: 0.49 if t == "fire" else 0.5,
                               crit_factor=1.0, double_dmg_factor=1.0)
        assert forms == before


class TestFormFullyFilteredByOnlyDealTypes:
    """"You can only deal Fire Damage" (Extreme Coldness) zeroes a form dealing a DIFFERENT native type while a
    sibling form of the allowed type keeps contributing. The filtered form's row must come back with an EMPTY
    dps_by_type_vs_target (not a stale/partial share) and must not corrupt the surviving row's pct_of_total."""
    def test_lightning_form_filtered_fire_form_survives(self):
        skill = _multi_form_spell_skill()
        src = _source(can_only_deal_fire=1.0)
        r = calculate_offense(src, skill, 16)
        beam, blade = r.hit_forms[0], r.hit_forms[1]
        assert beam.name == "Beam" and blade.name == "Blade"
        assert beam.damage_by_type == {}                  # lightning fully filtered out
        assert beam.dps_vs_target == pytest.approx(0.0)
        assert blade.dps_vs_target > 0.0                   # fire form unaffected

        beam_row, blade_row = r.damage_rows[0], r.damage_rows[1]
        assert beam_row.dps_by_type_vs_target == {}
        assert beam_row.pct_of_total == pytest.approx(0.0)
        assert blade_row.pct_of_total == pytest.approx(100.0, abs=1e-6)
        assert sum(row.pct_of_total for row in r.damage_rows) == pytest.approx(100.0, abs=1e-6)


class TestZeroTotalDpsNoRaiseAndRowsStayZero:
    """total_dps_vs_target <= 0.0 must exercise _finalize_damage_row_pcts's no-op path — rows keep
    pct_of_total == 0.0 and nothing raises — whether the skill is supported-but-zero-damage or unsupported."""
    def test_supported_skill_zero_damage_rows_noop(self):
        r = calculate_offense(_source(weapon_attack_speed=1.0), _attack_skill(), 16)   # no damage stats at all
        assert r.supported and r.total_dps_vs_target == 0.0
        assert r.damage_rows and len(r.damage_rows) == len(r.hit_forms)
        assert all(row.pct_of_total == 0.0 for row in r.damage_rows)

    def test_unsupported_skill_no_damage_rows_and_no_raise(self):
        unsupported = ResolvedSkill(skill_id="x", name="X", tags=[], max_level=20,
                                    hit_forms_by_level={}, supported=False)
        r = calculate_offense(_source(), unsupported, 16)
        assert not r.supported and r.total_dps_vs_target == 0.0
        assert r.damage_rows == [] and r.hit_forms == []   # no forms at all — nothing to reconcile, no raise


class TestMultiFormPctSumsAndPerFormMatch:
    """A genuine multi-form build (Icebound-Beam-shaped: two native-type forms in one result) — damage_rows
    percentages sum to 100 and each row's dps_vs_target_final matches its own form exactly."""
    def test_two_form_spell_rows_match_forms_and_sum_to_100(self):
        r = calculate_offense(_source(), _multi_form_spell_skill(), 16)
        assert len(r.hit_forms) == len(r.damage_rows) == 2
        for form, row in zip(r.hit_forms, r.damage_rows):
            # delivery == 1.0 here (no multistrike on a spell, no tangle/spell-burst) so the row reproduces the
            # form's own dps_vs_target exactly.
            assert row.dps_vs_target_final == pytest.approx(form.dps_vs_target)
        assert sum(row.pct_of_total for row in r.damage_rows) == pytest.approx(100.0, abs=1e-6)


class TestEnemyVulnSourcesByType:
    """OffenseResult.enemy_vuln_sources_by_type — the ordered stat-key list _enemy_vuln_mult actually consulted
    per type, surfaced so the frontend's Breakdown popover can list real sources instead of keeping its own
    hand-copied `enemyVulnKeys` (the bug this closes: a parallel list that could silently drift from the
    engine). Both _enemy_vuln_mult and this field are derived from the SAME `_enemy_vuln_source_keys` function,
    so the identity below is exact, not just float-close."""

    def test_source_keys_reproduce_enemy_vuln_and_the_full_mitigation_chain(self):
        src = _source(
            weapon_attack_speed=1.0,
            physical_attack_dmg_flat_min=70.0, physical_attack_dmg_flat_max=70.0,
            lightning_attack_dmg_flat_min=30.0, lightning_attack_dmg_flat_max=30.0,
            numbed_lightning_taken=0.5,
            paralysis_dmg_taken=0.25,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        assert set(r.enemy_vuln_sources_by_type) == set(r.enemy_vuln_by_type) == set(r.target_mitigation_by_type)
        assert r.enemy_vuln_sources_by_type  # non-empty — the skill deals physical + lightning
        for d, keys in r.enemy_vuln_sources_by_type.items():
            product = 1.0
            for k in keys:
                product *= 1.0 + src.total(k)
            assert product == pytest.approx(r.enemy_vuln_by_type[d])
            assert r.target_mitigation_by_type[d] * r.enemy_vuln_by_type[d] == pytest.approx(r.enemy_mult_by_type[d])
        # Type-scoping: Numbed only feeds lightning; Paralysis is global (every type).
        assert "numbed_lightning_taken" in r.enemy_vuln_sources_by_type["lightning"]
        assert "numbed_lightning_taken" not in r.enemy_vuln_sources_by_type["physical"]
        assert "paralysis_dmg_taken" in r.enemy_vuln_sources_by_type["physical"]
        assert "paralysis_dmg_taken" in r.enemy_vuln_sources_by_type["lightning"]

    def test_frail_key_only_present_for_spell_skills(self):
        spell = calculate_offense(_source(frail_spell_taken=0.3), _spell_skill(), 16)
        for keys in spell.enemy_vuln_sources_by_type.values():
            assert "frail_spell_taken" in keys

        attack = calculate_offense(
            _source(weapon_attack_speed=1.0, physical_attack_dmg_flat_min=1.0, physical_attack_dmg_flat_max=1.0),
            _attack_skill(), 16,
        )
        for keys in attack.enemy_vuln_sources_by_type.values():
            assert "frail_spell_taken" not in keys


class TestFormIndexIsTheStableJoinKey:
    """DamageRow.form_index — NOT `name` — is the stable join key back to `hit_forms` (see DamageRow's
    docstring). kind="hit" rows carry the 0-based index of their source HitFormResult in `hit_forms`
    (same order, via enumerate); kind="true"/"dot" rows (no HitFormResult of their own) always carry -1."""

    def test_hit_rows_carry_enumerate_index_into_hit_forms(self):
        r = calculate_offense(_source(), _multi_form_spell_skill(), 16)
        assert [row.form_index for row in r.damage_rows] == [0, 1]
        for i, (form, row) in enumerate(zip(r.hit_forms, r.damage_rows)):
            assert row.form_index == i
            assert r.hit_forms[row.form_index] is form   # the actual join, not a name lookup

    def test_true_row_form_index_is_negative_one(self):
        src = _source(
            weapon_attack_speed=1.0,
            physical_attack_dmg_flat_min=100.0, physical_attack_dmg_flat_max=100.0,
            fire_attack_dmg_flat_min=50.0, fire_attack_dmg_flat_max=50.0,
            mercury_baptism_fraction=0.2,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        hit_rows = [row for row in r.damage_rows if row.kind == "hit"]
        true_rows = [row for row in r.damage_rows if row.kind == "true"]
        assert hit_rows and hit_rows[0].form_index == 0
        assert true_rows and all(row.form_index == -1 for row in true_rows)

    def test_build_hit_damage_rows_direct_enumerate(self):
        forms = [
            HitFormResult(name="Hit", effectiveness_pct=100.0, form_type="additive", proc_chance=1.0,
                          damage_by_type={"physical": 100.0}, avg_hit_pre_crit=100.0, avg_hit_with_crit=100.0,
                          dps_contribution=100.0, dps_vs_target=50.0),
            HitFormResult(name="Hit", effectiveness_pct=100.0, form_type="additive", proc_chance=1.0,
                          damage_by_type={"fire": 50.0}, avg_hit_pre_crit=50.0, avg_hit_with_crit=50.0,
                          dps_contribution=50.0, dps_vs_target=25.0),
        ]
        rows = _build_hit_damage_rows(forms, delivery=1.0, mitigation_fn=lambda t: 0.5,
                                      crit_factor=1.0, double_dmg_factor=1.0)
        # Same name on both forms ("Hit") — form_index (not name) is what disambiguates them.
        assert [row.form_index for row in rows] == [0, 1]


class TestEnemyVulnMultPinnedLiteral:
    """`_enemy_vuln_mult`'s multiplication order (Paralysis → No Guard → Knockback → Tide → Enemy Nearby →
    Frostbite/Numbed/Infiltration → Frail → {dtype}_curse → hit_curse) is pinned against a HAND-COMPUTED
    literal, not a recomputation over the same `enemy_vuln_sources_by_type` key list (that's what
    TestEnemyVulnSourcesByType does, and it's a self-consistency check, not an oracle — it would pass
    unchanged even if a future reorder silently changed the product for float-order-sensitive inputs).
    Three simultaneous sources on a lightning hit: Paralysis (+25%, global) x Numbed (+50%, lightning-only)
    x a lightning curse (+30%) = 1.25 x 1.5 x 1.3 = 2.4375, computed here by hand, independent of the engine."""

    def test_paralysis_numbed_lightning_curse_matches_hand_literal(self):
        src = _source(
            weapon_attack_speed=1.0,
            lightning_attack_dmg_flat_min=100.0, lightning_attack_dmg_flat_max=100.0,
            paralysis_dmg_taken=0.25,
            numbed_lightning_taken=0.5,
            lightning_curse_taken=0.30,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        assert r.enemy_vuln_by_type["lightning"] == pytest.approx(2.4375)


class TestDamageRowNyiMirrorsHitForm:
    """DamageRow.nyi — kind="hit" rows mirror hit_forms[i].nyi exactly (empty for the true/dot kinds), so the
    frontend can filter NYI rows out of the breakdown table from the row alone (no index-zip against
    hit_forms). NYI forms carry 0 DPS, so pct_of_total must land at 0.0 without corrupting the surviving
    row's 100%."""

    def test_nyi_form_row_carries_reason_and_zero_pct_while_real_row_stays_100(self):
        real = HitFormResult(
            name="Real", effectiveness_pct=100.0, form_type="additive", proc_chance=1.0,
            damage_by_type={"physical": 100.0}, avg_hit_pre_crit=100.0, avg_hit_with_crit=100.0,
            dps_contribution=100.0, dps_vs_target=50.0,
            hit_min_by_type={"physical": 100.0}, hit_max_by_type={"physical": 100.0},
        )
        nyi_form = HitFormResult(
            name="Locked Ultimate", effectiveness_pct=0.0, form_type="additive", proc_chance=0.0,
            damage_by_type={}, avg_hit_pre_crit=0.0, avg_hit_with_crit=0.0,
            dps_contribution=0.0, dps_vs_target=0.0,
            nyi=["Locked — not yet modelled."],
        )
        rows = _build_hit_damage_rows(
            [real, nyi_form], delivery=1.0, mitigation_fn=lambda t: 0.5,
            crit_factor=1.0, double_dmg_factor=1.0,
        )
        real_row, nyi_row = rows
        assert real_row.nyi == []
        assert nyi_row.nyi == ["Locked — not yet modelled."]

        _finalize_damage_row_pcts(rows, sum(row.dps_vs_target_final for row in rows))
        assert nyi_row.pct_of_total == pytest.approx(0.0)
        assert real_row.pct_of_total == pytest.approx(100.0, abs=1e-6)
        assert sum(row.pct_of_total for row in rows) == pytest.approx(100.0, abs=1e-6)

    def test_true_row_nyi_stays_empty(self):
        # kind="true" rows (Mercury Baptism / Spell Ripple) are never NYI — confirm the default holds end-to-end.
        src = _source(
            weapon_attack_speed=1.0,
            physical_attack_dmg_flat_min=100.0, physical_attack_dmg_flat_max=100.0,
            fire_attack_dmg_flat_min=50.0, fire_attack_dmg_flat_max=50.0,
            mercury_baptism_fraction=0.2,
        )
        r = calculate_offense(src, _attack_skill(), 16)
        true_rows = [row for row in r.damage_rows if row.kind == "true"]
        assert true_rows and all(row.nyi == [] for row in true_rows)
