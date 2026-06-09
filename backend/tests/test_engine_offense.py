"""
Tests: engine/offense.py — calculate_offense() orchestration: the supported flag, crit-chance
and APS formulas, dummy-target mitigation, hit-form summing, and steep-strike proc splitting.
The per-hit damage math itself is covered by test_engine_pipeline.py.
"""
import pytest
from engine.models import BuildSource, SourceEntry
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


# ── Per-affix "additional" pooling (Option A) ─────────────────────────────────────────────────
# Strings below are the EXACT affix wordings from the data (talents: data/node_type_filter.json;
# gear: data/seasons/SS12/_legendary_gear.json). ★ marks cases that fail under the old
# additive-by-stat-key pooling and pass only under correct per-affix multiplication.

_ATK = "attack_dmg_additional"
_PROJ = "projectile_dmg_additional"
_SENT = "sentry_dmg_additional"
_FIRE = "fire_dmg_additional"

_ATK_1H = "+8 % additional Attack Damage when holding a One-Handed Weapon"
_ATK_WARCRY = "+8 % additional Attack Damage if you have used a Warcry Skill in the last 8s"
_PROJ_GRAVEL = "+(20–30) % additional Projectile Damage"          # Gravel
_PROJ_SUNSHOOTER = "+(10–15) % additional Projectile Damage"      # Sun-shooter Long Bow (same affix)
_SENT_POS = "+8 % additional Sentry Damage"
_SENT_NEG = "-5 % additional Sentry Damage"
_FIRE_TXT = "+4 % additional Fire Damage"


def _add_src(*entries, types=("physical",), flat=100.0) -> BuildSource:
    """Source with flat damage of `types` plus LOGGED additional contributions carrying affix text.

    entries: (stat, amount, text) — added via add_with_source so they carry per-affix identity.
    """
    s = BuildSource()
    s.add("weapon_attack_speed", 1.0)
    for dt in types:
        s.add(f"{dt}_dmg_gear_flat_min", flat)
        s.add(f"{dt}_dmg_gear_flat_max", flat)
    for stat, amount, text in entries:
        s.add_with_source(stat, amount, SourceEntry(
            stat=stat, amount=amount, source_type="gear", label="x", text=text, points=1))
    return s


class TestAdditionalPooling:
    def test_distinct_affixes_same_key_multiply(self):  # ★ old: 1.16
        s = _add_src((_ATK, 0.08, _ATK_1H), (_ATK, 0.08, _ATK_WARCRY))
        r = calculate_offense(s, _skill(tags=("attack",)), 1)
        assert r.type_add["physical"] == pytest.approx(1.08 * 1.08)  # 1.1664

    def test_identical_affix_across_items_adds(self):  # NOT 1.30*1.15
        s = _add_src((_PROJ, 0.30, _PROJ_GRAVEL), (_PROJ, 0.15, _PROJ_SUNSHOOTER))
        r = calculate_offense(s, _skill(tags=("attack", "projectile")), 1)
        assert r.type_add["physical"] == pytest.approx(1.45)

    def test_positive_and_negative_same_identity(self):  # ★ old: 1.03
        s = _add_src((_SENT, 0.08, _SENT_POS), (_SENT, -0.05, _SENT_NEG))
        r = calculate_offense(s, _skill(tags=("attack", "sentry")), 1)
        assert r.type_add["physical"] == pytest.approx(1.08 * 0.95)  # 1.026

    def test_distinct_negatives_multiply_no_immunity(self):  # 0.4*0.4=0.16, not 1+(-1.2)
        s = _add_src((_SENT, -0.60, "-60 % additional Sentry Damage debuff A"),
                     (_SENT, -0.60, "-60 % additional Sentry Damage debuff B"))
        r = calculate_offense(s, _skill(tags=("attack", "sentry")), 1)
        assert r.type_add["physical"] == pytest.approx(0.40 * 0.40)

    def test_tag_scoping_fire_only(self):  # ★ fire factor must not touch physical
        s = _add_src((_FIRE, 0.50, _FIRE_TXT), types=("physical", "fire"))
        r = calculate_offense(s, _skill(tags=("attack",)), 1)
        assert r.type_add["fire"] == pytest.approx(1.50)
        assert r.type_add["physical"] == pytest.approx(1.0)

    def test_deferred_excluded_and_zero_noop(self):
        s = _add_src((_ATK, 0.0, _ATK_1H))            # +0% roll → no-op
        s.add("post_mobility_dmg_additional", 0.5)    # deferred → excluded
        r = calculate_offense(s, _skill(tags=("attack",)), 1)
        assert r.type_add["physical"] == pytest.approx(1.0)

    def test_order_independent(self):
        a = calculate_offense(_add_src((_ATK, 0.08, _ATK_1H), (_ATK, 0.08, _ATK_WARCRY)), _skill(tags=("attack",)), 1)
        b = calculate_offense(_add_src((_ATK, 0.08, _ATK_WARCRY), (_ATK, 0.08, _ATK_1H)), _skill(tags=("attack",)), 1)
        assert a.type_add["physical"] == pytest.approx(b.type_add["physical"])

    def test_addonly_pools_by_key_backcompat(self):
        s = _add_src()
        s.add(_ATK, 0.20)
        s.add(_ATK, 0.20)                              # add()-only → single remainder factor
        r = calculate_offense(s, _skill(tags=("attack",)), 1)
        assert r.type_add["physical"] == pytest.approx(1.40)

    def test_mixed_logged_and_addonly(self):  # logged identity factor × remainder factor
        s = _add_src((_ATK, 0.10, _ATK_1H))
        s.add(_ATK, 0.10)                              # untracked remainder
        r = calculate_offense(s, _skill(tags=("attack",)), 1)
        assert r.type_add["physical"] == pytest.approx(1.10 * 1.10)  # 1.21

    def test_consumed_stats_records_only_applied(self):
        s = _add_src((_ATK, 0.10, _ATK_1H), (_FIRE, 0.10, _FIRE_TXT))  # physical-only flat
        s._recording = True
        calculate_offense(s, _skill(tags=("attack",)), 1)
        assert "attack_dmg_additional" in s.consumed_stats
        assert "fire_dmg_additional" not in s.consumed_stats  # fire never applies to a physical-only attack

    def test_generic_add_with_extra_additional(self):
        s = _add_src((_ATK, 0.08, _ATK_1H), (_ATK, 0.08, _ATK_WARCRY))
        r = calculate_offense(s, _skill(tags=("attack",)), 1, extra_additional=0.25)
        assert r.generic_add == pytest.approx(1.08 * 1.08 * 1.25)
