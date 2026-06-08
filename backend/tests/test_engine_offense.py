"""
Tests: engine/offense.py — calculate_offense() orchestration: the supported flag, crit-chance
and APS formulas, dummy-target mitigation, hit-form summing, and steep-strike proc splitting.
The per-hit damage math itself is covered by test_engine_pipeline.py.
"""
import pytest
from engine.models import BuildSource
from engine.offense import calculate_offense
from engine.skill_resolver import ResolvedSkill, SkillHitForm


def _source(**stats) -> BuildSource:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _hit(eff=1.0, form_type="additive", proc=None) -> SkillHitForm:
    return SkillHitForm(name="Hit", effectiveness_pct=eff, form_type=form_type, proc_stat_key=proc)


def _skill(tags=("attack",), max_level=1, forms=None, supported=True, base_steep=0.0) -> ResolvedSkill:
    return ResolvedSkill(
        skill_id="t", name="T", tags=list(tags), max_level=max_level,
        hit_forms_by_level=forms if forms is not None else {1: []},
        supported=supported, base_steep_strike_chance=base_steep,
    )


class TestSupportedFlag:
    def test_unsupported_skill_zeroed(self):
        r = calculate_offense(_source(weapon_attack_speed=2.0), _skill(supported=False), 1)
        assert r.supported is False
        assert r.total_dps == 0.0
        assert r.total_dps_vs_target == 0.0


class TestCrit:
    def test_zero_csr_zero_crit(self):
        assert calculate_offense(_source(), _skill(), 1).crit_chance == 0.0

    def test_weapon_csr_500_is_5pct(self):
        # 100 CSR = 1% → 500 / 10000 = 0.05
        r = calculate_offense(_source(weapon_crit_rating_flat=500.0), _skill(), 1)
        assert r.crit_chance == pytest.approx(0.05)

    def test_gear_mult_scales_only_weapon_csr(self):
        # 500 * (1 + 0.5) = 750 → 7.5%
        r = calculate_offense(_source(weapon_crit_rating_flat=500.0, attack_crit_rating_gear=0.5), _skill(), 1)
        assert r.crit_chance == pytest.approx(0.075)

    def test_inc_scales_total_csr(self):
        # (500 weapon + 500 flat) * (1 + 1.0 inc) = 2000 → 20%
        r = calculate_offense(
            _source(weapon_crit_rating_flat=500.0, attack_crit_rating_flat=500.0, attack_crit_rating_inc=1.0),
            _skill(), 1,
        )
        assert r.crit_chance == pytest.approx(0.20)

    def test_generic_crit_rating_inc_applies(self):
        # crit_rating_inc = generic "+% Critical Strike Rating" (both attacks + spells); scales the
        # whole CSR pool like attack_crit_rating_inc. 500*(1+1.0)=1000 -> 10%.
        r = calculate_offense(_source(weapon_crit_rating_flat=500.0, crit_rating_inc=1.0), _skill(), 1)
        assert r.crit_chance == pytest.approx(0.10)

    def test_generic_and_attack_crit_inc_stack(self):
        # 500*(1 + 1.0 generic + 1.0 attack) = 1500 -> 15%.
        r = calculate_offense(
            _source(weapon_crit_rating_flat=500.0, crit_rating_inc=1.0, attack_crit_rating_inc=1.0),
            _skill(), 1,
        )
        assert r.crit_chance == pytest.approx(0.15)

    def test_crit_chance_capped_at_1(self):
        r = calculate_offense(_source(weapon_crit_rating_flat=50000.0), _skill(), 1)
        assert r.crit_chance == pytest.approx(1.0)

    def test_crit_multiplier_default_and_bonus(self):
        assert calculate_offense(_source(), _skill(), 1).crit_multiplier == pytest.approx(1.5)
        assert calculate_offense(_source(crit_damage=0.4), _skill(), 1).crit_multiplier == pytest.approx(1.9)


class TestAttackSpeed:
    def test_base_aps(self):
        assert calculate_offense(_source(weapon_attack_speed=2.0), _skill(), 1).attacks_per_second == pytest.approx(2.0)

    def test_gear_and_mh_are_additive(self):
        r = calculate_offense(_source(weapon_attack_speed=2.0, attack_speed_gear=0.3, attack_speed_mh=0.2), _skill(), 1)
        assert r.attacks_per_second == pytest.approx(2.0 * 1.5)

    def test_inc_multiplies(self):
        r = calculate_offense(_source(weapon_attack_speed=2.0, attack_speed_inc=0.5), _skill(), 1)
        assert r.attacks_per_second == pytest.approx(3.0)

    def test_additional_pool_is_independent(self):
        r = calculate_offense(_source(weapon_attack_speed=2.0, attack_speed_additional=0.25), _skill(), 1)
        assert r.attacks_per_second == pytest.approx(2.5)

    def test_combined(self):
        # 2 * (1+0.5) * (1+0.5) * (1+0.2) = 5.4
        r = calculate_offense(
            _source(weapon_attack_speed=2.0, attack_speed_gear=0.5, attack_speed_inc=0.5, attack_speed_additional=0.2),
            _skill(), 1,
        )
        assert r.attacks_per_second == pytest.approx(5.4)


class TestDpsAndMitigation:
    def _phys_src(self):
        return _source(weapon_attack_speed=1.0, physical_dmg_gear_flat_min=100.0, physical_dmg_gear_flat_max=100.0)

    def test_dummy_target_halves_physical_dps(self):
        r = calculate_offense(self._phys_src(), _skill(forms={1: [_hit()]}), 1)
        assert r.total_dps > 0
        assert r.total_dps_vs_target == pytest.approx(r.total_dps * 0.5, rel=1e-3)  # 50% dummy armor

    def test_total_dps_sums_hit_forms(self):
        r = calculate_offense(self._phys_src(), _skill(forms={1: [_hit(eff=1.0), _hit(eff=0.5)]}), 1)
        assert len(r.hit_forms) == 2
        assert r.total_dps == pytest.approx(sum(f.dps_contribution for f in r.hit_forms))


class TestSteepStrike:
    def test_proc_and_complement_split(self):
        src = _source(weapon_attack_speed=1.0, physical_dmg_gear_flat_min=100.0,
                      physical_dmg_gear_flat_max=100.0, steep_strike_chance=0.3)
        forms = {1: [
            _hit(eff=2.0, proc="steep_strike_chance"),
            _hit(eff=1.0, proc="_complement_steep_strike_chance"),
        ]}
        r = calculate_offense(src, _skill(forms=forms), 1)
        assert r.steep_strike_chance == pytest.approx(0.3)
        assert sorted(f.proc_chance for f in r.hit_forms) == pytest.approx([0.3, 0.7])
