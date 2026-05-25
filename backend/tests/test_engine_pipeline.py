"""
Tests: engine/pipeline.py — damage formula correctness.
Scope: mathematical stages only; no file I/O or season data.
Each test verifies one pipeline stage in isolation using synthetic BuildSource inputs.
"""
import pytest
from engine.models import BuildSource, SkillConfig, EnemyConfig
from engine.pipeline import run_pipeline, ARMOR_K


def _skill(
    skill_type="attack",
    tags=None,
    damage_types=None,
    base_dmg_min=100.0,
    base_dmg_max=100.0,
    base_level=1,
    base_csr=0.0,
) -> SkillConfig:
    return SkillConfig(
        name="test",
        skill_type=skill_type,
        tags=tags or [skill_type],
        damage_types=damage_types or ["physical"],
        base_level=base_level,
        extra_levels=0,
        base_dmg_min=base_dmg_min,
        base_dmg_max=base_dmg_max,
        base_csr=base_csr,
    )


def _enemy(**kwargs) -> EnemyConfig:
    return EnemyConfig(**kwargs)


def _source(**stats) -> BuildSource:
    s = BuildSource()
    for key, val in stats.items():
        s.add(key, val)
    return s


class TestBaselinePipeline:
    def test_no_stats_no_mitigation_equals_base(self):
        """Zero stats, no enemy mitigation → result equals base damage."""
        result = run_pipeline(_source(), _skill(base_dmg_min=50.0, base_dmg_max=50.0), _enemy())
        assert result.avg_hit == pytest.approx(50.0, rel=1e-3)

    def test_avg_hit_is_midpoint(self):
        result = run_pipeline(_source(), _skill(base_dmg_min=100.0, base_dmg_max=200.0), _enemy())
        assert result.avg_hit == pytest.approx(150.0, rel=1e-3)
        assert result.min_hit == pytest.approx(100.0, rel=1e-3)
        assert result.max_hit == pytest.approx(200.0, rel=1e-3)


class TestIncreasedStage:
    def test_100pct_inc_doubles_damage(self):
        source = _source(dmg_inc=1.0)
        result = run_pipeline(source, _skill(base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(200.0, rel=1e-3)

    def test_attack_dmg_inc_applies_to_attack_skill(self):
        source = _source(attack_dmg_inc=0.50)
        result = run_pipeline(source, _skill(tags=["attack"], base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(150.0, rel=1e-3)

    def test_spell_dmg_inc_does_not_apply_to_attack(self):
        source = _source(spell_dmg_inc=1.0)
        result = run_pipeline(source, _skill(tags=["attack"], base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(100.0, rel=1e-3)

    def test_inc_pools_are_additive(self):
        """50% generic + 50% attack-specific = 100% total → ×2."""
        source = _source(dmg_inc=0.50, attack_dmg_inc=0.50)
        result = run_pipeline(source, _skill(tags=["attack"], base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(200.0, rel=1e-3)


class TestAdditionalStage:
    def test_additional_multiplies_independently_from_inc(self):
        """100% inc + 30% additional: base × 2.0 × 1.3 = 260."""
        source = _source(dmg_inc=1.0, attack_dmg_additional=0.30)
        result = run_pipeline(source, _skill(tags=["attack"], base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(260.0, rel=1e-3)

    def test_same_additional_stat_pools_additively(self):
        """Two sources of attack_dmg_additional sum before the factor is applied."""
        source = _source(attack_dmg_additional=0.30)
        source.add("attack_dmg_additional", 0.20)
        result = run_pipeline(source, _skill(tags=["attack"], base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(150.0, rel=1e-3)


class TestAttributeStage:
    def test_strength_boosts_physical_attack(self):
        """200 STR → +100% additional → ×2."""
        source = _source(strength=200.0)
        result = run_pipeline(
            source,
            _skill(tags=["attack"], damage_types=["physical"], base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(),
        )
        assert result.avg_hit == pytest.approx(200.0, rel=1e-3)

    def test_intelligence_boosts_elemental_spell(self):
        """200 INT → +100% additional → ×2 on fire spell."""
        source = _source(intelligence=200.0)
        result = run_pipeline(
            source,
            _skill(skill_type="spell", tags=["spell"], damage_types=["fire"],
                   base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(),
        )
        assert result.avg_hit == pytest.approx(200.0, rel=1e-3)

    def test_strength_does_not_boost_spell(self):
        source = _source(strength=200.0)
        result = run_pipeline(
            source,
            _skill(skill_type="spell", tags=["spell"], damage_types=["fire"],
                   base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(),
        )
        assert result.avg_hit == pytest.approx(100.0, rel=1e-3)


class TestSkillLevelStage:
    def test_level_30_gives_no_bonus(self):
        result = run_pipeline(_source(), _skill(base_level=30, base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(100.0, rel=1e-3)

    def test_level_31_gives_1_08_multiplier(self):
        result = run_pipeline(_source(), _skill(base_level=31, base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(108.0, rel=1e-3)

    def test_level_32_gives_1_08_squared(self):
        result = run_pipeline(_source(), _skill(base_level=32, base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(100.0 * 1.08 ** 2, rel=1e-3)


class TestCriticalStrike:
    def test_zero_csr_means_zero_crit_chance(self):
        result = run_pipeline(_source(), _skill(base_csr=0.0, base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.crit_chance == 0.0

    def test_100_csr_means_1_0_crit_chance(self):
        result = run_pipeline(_source(), _skill(base_csr=100.0, base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.crit_chance == pytest.approx(1.0)

    def test_csr_capped_at_1_0(self):
        result = run_pipeline(_source(), _skill(base_csr=500.0, base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.crit_chance == pytest.approx(1.0)

    def test_100pct_crit_with_default_150pct_crit_dmg(self):
        """100% crit + 150% crit_dmg → crit_factor = 1 + 1.0 × (1.5 - 1) = 1.5 → ×1.5 avg."""
        result = run_pipeline(_source(), _skill(base_csr=100.0, base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(150.0, rel=1e-3)

    def test_additional_crit_dmg_stacks_on_base(self):
        """50% crit, +50% crit_dmg bonus (total 200%): factor = 1 + 0.5 × (2.0 - 1) = 1.5."""
        source = _source(crit_dmg_inc=0.50)
        result = run_pipeline(source, _skill(base_csr=50.0, base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.crit_chance == pytest.approx(0.5)
        assert result.avg_hit == pytest.approx(150.0, rel=1e-3)


class TestDoubleDamage:
    def test_100pct_double_chance_doubles_avg(self):
        source = _source(double_dmg_chance=1.0)
        result = run_pipeline(source, _skill(base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(200.0, rel=1e-3)

    def test_double_chance_clamped_at_1(self):
        """Overfilling double chance stays capped at ×2."""
        source = _source(double_dmg_chance=2.0)
        result = run_pipeline(source, _skill(base_dmg_min=100.0, base_dmg_max=100.0), _enemy())
        assert result.avg_hit == pytest.approx(200.0, rel=1e-3)


class TestMitigation:
    def test_armor_reduces_physical_damage(self):
        """armor=1000, ARMOR_K=1000 → 50% reduction → avg_hit = 50."""
        result = run_pipeline(
            _source(),
            _skill(damage_types=["physical"], base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(armor=1000.0),
        )
        expected_reduction = 1000.0 / (1000.0 + ARMOR_K)
        assert result.avg_hit == pytest.approx(100.0 * (1.0 - expected_reduction), rel=1e-3)

    def test_armor_pen_reduces_effective_armor(self):
        """50% armor pen halves effective armor → less mitigation."""
        source = _source(armor_pen=0.50)
        result_with_pen = run_pipeline(
            source,
            _skill(damage_types=["physical"], base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(armor=1000.0),
        )
        result_no_pen = run_pipeline(
            _source(),
            _skill(damage_types=["physical"], base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(armor=1000.0),
        )
        assert result_with_pen.avg_hit > result_no_pen.avg_hit

    def test_fire_resistance_reduces_fire_damage(self):
        """50% fire resistance → 50% mitigation → avg_hit = 50."""
        result = run_pipeline(
            _source(),
            _skill(skill_type="spell", tags=["spell"], damage_types=["fire"],
                   base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(fire_resistance=0.50),
        )
        assert result.avg_hit == pytest.approx(50.0, rel=1e-3)

    def test_elemental_pen_reduces_effective_resistance(self):
        source = _source(fire_pen=0.50)
        result = run_pipeline(
            source,
            _skill(skill_type="spell", tags=["spell"], damage_types=["fire"],
                   base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(fire_resistance=0.50),
        )
        assert result.avg_hit == pytest.approx(100.0, rel=1e-3)

    def test_armor_does_not_affect_elemental(self):
        """High armor should not reduce elemental (fire) damage."""
        result = run_pipeline(
            _source(),
            _skill(skill_type="spell", tags=["spell"], damage_types=["fire"],
                   base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(armor=9999.0),
        )
        assert result.avg_hit == pytest.approx(100.0, rel=1e-3)

    def test_resistance_does_not_affect_physical(self):
        """High elemental resistance should not reduce physical damage."""
        result = run_pipeline(
            _source(),
            _skill(damage_types=["physical"], base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(fire_resistance=0.99, cold_resistance=0.99),
        )
        # Only armor (0) affects physical; result should be full 100
        assert result.avg_hit == pytest.approx(100.0, rel=1e-3)

    def test_negative_resistance_amplifies_damage(self):
        """Enemy at -50% fire resistance → 150% fire damage taken."""
        result = run_pipeline(
            _source(),
            _skill(skill_type="spell", tags=["spell"], damage_types=["fire"],
                   base_dmg_min=100.0, base_dmg_max=100.0),
            _enemy(fire_resistance=-0.50),
        )
        assert result.avg_hit == pytest.approx(150.0, rel=1e-3)


class TestFullFormula:
    def test_synthetic_composite(self):
        """
        Reference calculation verified manually:
          base 100-200 → avg 150
          × (1 + 1.0 inc)          = 300
          × (1 + 0.3 additional)   = 390
          × (1 + 200×0.005 attr)   = 780   (200 STR on physical/attack)
          × 1.0 (level ≤ 30)
          × (1 + 0 crit)           = 780
          × 1.0 (no double)
          × (1 - 1000/(1000+1000)) = 390  (1000 armor, ARMOR_K=1000 → 50%)
        """
        source = _source(
            dmg_inc=1.0,
            attack_dmg_additional=0.30,
            strength=200.0,
        )
        skill = _skill(
            tags=["attack"],
            damage_types=["physical"],
            base_dmg_min=100.0,
            base_dmg_max=200.0,
            base_level=1,
            base_csr=0.0,
        )
        result = run_pipeline(source, skill, _enemy(armor=1000.0))
        assert result.avg_hit == pytest.approx(390.0, rel=1e-3)
