"""
Tests: engine/offense.py — calculate_offense() orchestration: the supported flag, crit-chance
and APS formulas, dummy-target mitigation, hit-form summing, and steep-strike proc splitting.
"""
import pytest
from engine.models import BuildSource, SourceEntry
from engine.offense import calculate_offense, _enemy_vuln_mult
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

    def test_unsupported_skill_generic_fields_populated(self):
        # Partial-support display (docs/BACKLOG.md §5): an unregistered skill runs the full pipeline —
        # damage stays zeroed (no hit forms), but the registry-independent outputs (tags, rates, crit,
        # level) come back populated so the UI can show them without stating a damage number.
        r = calculate_offense(
            _source(weapon_attack_speed=2.0, weapon_crit_rating_flat=500.0),
            _skill(supported=False), 1,
        )
        assert r.supported is False
        assert r.total_dps == 0.0 and r.hit_forms == []
        assert r.skill_tags == ["attack"]
        assert r.skills_per_second == pytest.approx(2.0)
        assert r.crit_chance == pytest.approx(0.05)
        assert r.crit_multiplier == pytest.approx(1.5)
        assert r.effective_level >= 1

    def test_unsupported_skill_does_not_record_consumption(self):
        # Damage-mod badges must keep reading "unused" on a skill whose damage isn't modeled — the full
        # pipeline runs, but with consumption recording suspended (and restored afterwards).
        s = _source(weapon_attack_speed=2.0, crit_dmg_inc=0.4)
        s._recording = True
        calculate_offense(s, _skill(supported=False), 1)
        assert s.consumed_stats == set()
        assert s._recording is True   # restored, not left off


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
        # Critical Strike Damage feeds the crit multiplier additively (1.5 base + the crit-damage pool).
        assert calculate_offense(_source(crit_dmg_inc=0.4), _skill(), 1).crit_multiplier == pytest.approx(1.9)
        assert calculate_offense(_source(crit_dmg_additional=0.4), _skill(), 1).crit_multiplier == pytest.approx(1.9)


class TestAttackSpeed:
    def test_base_aps(self):
        assert calculate_offense(_source(weapon_attack_speed=2.0), _skill(), 1).skills_per_second == pytest.approx(2.0)

    def test_gear_and_mh_are_additive(self):
        r = calculate_offense(_source(weapon_attack_speed=2.0, attack_speed_gear=0.3, attack_speed_mh=0.2), _skill(), 1)
        assert r.skills_per_second == pytest.approx(2.0 * 1.5)

    def test_inc_multiplies(self):
        r = calculate_offense(_source(weapon_attack_speed=2.0, attack_speed_inc=0.5), _skill(), 1)
        assert r.skills_per_second == pytest.approx(3.0)

    def test_additional_pool_is_independent(self):
        r = calculate_offense(_source(weapon_attack_speed=2.0, attack_speed_additional=0.25), _skill(), 1)
        assert r.skills_per_second == pytest.approx(2.5)

    def test_combined(self):
        # 2 * (1+0.5) * (1+0.5) * (1+0.2) = 5.4
        r = calculate_offense(
            _source(weapon_attack_speed=2.0, attack_speed_gear=0.5, attack_speed_inc=0.5, attack_speed_additional=0.2),
            _skill(), 1,
        )
        assert r.skills_per_second == pytest.approx(5.4)


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


class TestPoolingUuidKey:
    """The minted-identity pooling key (engine/modifier_lines.pool_identity + identity_index).

    With a source-attached index, the key is a pure function of the text: index.get(identity,
    identity). Different wordings sharing one minted uuid (the localization case) ADD; suffix-minted
    per-instance texts miss the index and keep multiplying; without an index a stamped entry's
    pooling_uuid is honored and unstamped entries fall back to text identity."""

    def _src(self, *entries, index=None):
        s = _add_src(*[(stat, amount, text) for stat, amount, text, _pu in entries])
        # restamp the per-entry uuids (helper builds text-only entries)
        for e, (_s, _a, _t, pu) in zip(s.source_log, entries):
            e.pooling_uuid = pu
        s.identity_index = index
        return s

    def test_shared_uuid_across_wordings_adds(self):
        # Two wordings joined to ONE minted identity by the index (how CN/RU text will join) → SUM.
        from engine.affix_identity import affix_identity
        idx = {affix_identity("+8 % additional Attack Damage"): "u-shared",
               affix_identity("8% additional attack damage!"): "u-shared"}
        s = self._src((_ATK, 0.08, "+8 % additional Attack Damage", None),
                      (_ATK, 0.08, "8% additional attack damage!", None), index=idx)
        r = calculate_offense(s, _skill(tags=("attack",)), 1)
        assert r.type_add["physical"] == pytest.approx(1.16)

    def test_index_misses_keep_per_instance_identity(self):
        # Suffix-minted support-instance texts never hit the index → still their own ×(1+x) factors.
        from engine.affix_identity import affix_identity
        idx = {affix_identity("+8 % additional Attack Damage"): "u-cat"}
        s = self._src((_ATK, 0.08, "+8 % additional damage for the supported skill |web|universal", None),
                      (_ATK, 0.08, "+8 % additional damage for the supported skill |merge|universal", None),
                      index=idx)
        r = calculate_offense(s, _skill(tags=("attack",)), 1)
        assert r.type_add["physical"] == pytest.approx(1.08 * 1.08)

    def test_same_wording_keys_identically_with_index(self):
        # Consistency: same wording always one key through the index, whether or not a catalog entry
        # exists for it (both hit or both miss) — no stamped/unstamped split is possible.
        from engine.affix_identity import affix_identity
        idx = {affix_identity(_SENT_POS): "u-sent"}
        s = self._src((_SENT, 0.08, _SENT_POS, "u-sent"), (_SENT, 0.05, _SENT_POS, None), index=idx)
        r = calculate_offense(s, _skill(tags=("attack", "sentry")), 1)
        assert r.type_add["physical"] == pytest.approx(1.13)

    def test_no_index_stamped_uuid_wins_none_falls_back(self):
        # Legacy/no-index regime: distinct stamped uuids on identical texts multiply; unstamped
        # entries pool by text identity (the pre-migration behavior).
        s = self._src((_ATK, 0.08, "+8 % additional Attack Damage", "u-1"),
                      (_ATK, 0.08, "+8 % additional Attack Damage", "u-2"))
        r = calculate_offense(s, _skill(tags=("attack",)), 1)
        assert r.type_add["physical"] == pytest.approx(1.08 * 1.08)
        s2 = self._src((_ATK, 0.08, "+8 % additional Attack Damage", None),
                       (_ATK, 0.08, "+8 % additional Attack Damage", None))
        r2 = calculate_offense(s2, _skill(tags=("attack",)), 1)
        assert r2.type_add["physical"] == pytest.approx(1.16)

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


def _spell(base=(25.0, 482.0), eff=1.36, cast=0.65, max_level=20, level=16, dtype="lightning", jumps=0):
    """A resolved spell skill (Chain Lightning shape): per-level intrinsic base damage, cast-driven
    hit rate, added-damage effectiveness that scales ADDED flat only."""
    return ResolvedSkill(
        skill_id="cl", name="Chain Lightning", tags=["spell", dtype], max_level=max_level,
        hit_forms_by_level={level: [SkillHitForm("Chain Lightning", 100.0, "additive")]},
        supported=True, is_spell=True,
        base_dmg_by_level={level: {dtype: base}},
        base_cast_time=cast, added_dmg_effectiveness=eff, damage_types=[dtype], jumps_base=jumps,
    )


class TestSpellPathway:
    def test_base_unscaled_by_effectiveness(self):
        # Verified in-game: the listed base (25–482) is NOT scaled by the 136% effectiveness.
        r = calculate_offense(_source(), _spell(), 16)
        assert r.hit_forms[0].hit_min_by_type["lightning"] == pytest.approx(25.0)
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0)

    def test_added_flat_scaled_by_effectiveness(self):
        # A 2–58 added-lightning ring (spell-tagged) is scaled by 136%: max delta 58 × 1.36 = 78.88.
        s = _source(lightning_spell_dmg_flat_min=2.0, lightning_spell_dmg_flat_max=58.0)
        r = calculate_offense(s, _spell(), 16)
        assert r.hit_forms[0].hit_min_by_type["lightning"] == pytest.approx(25.0 + 2.0 * 1.36)
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0 + 58.0 * 1.36)  # 560.88

    def test_excludes_weapon_base(self):
        # Weapon implicit flat must NOT contribute to a spell's pool.
        s = _source(lightning_dmg_gear_flat_min=1000.0, lightning_dmg_gear_flat_max=1000.0)
        r = calculate_offense(s, _spell(), 16)
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0)

    def test_cast_hit_rate_inc(self):
        # casts/sec = (1 / 0.65) × (1 + 0.20) = 1.84615
        r = calculate_offense(_source(cast_speed_inc=0.20), _spell(), 16)
        assert r.skills_per_second == pytest.approx((1.0 / 0.65) * 1.20)

    def test_cast_hit_rate_additional(self):
        # spell-tagged cast_speed_additional applies: (1 / 0.65) × 1.10
        r = calculate_offense(_source(cast_speed_additional=0.10), _spell(), 16)
        assert r.skills_per_second == pytest.approx((1.0 / 0.65) * 1.10)

    def test_end_to_end_dps(self):
        # avg (25+482)/2 = 253.5, cast 0.65 → 1/0.65 casts/s, base 5% spell crit → ×1.025.
        r = calculate_offense(_source(), _spell(), 16)
        assert r.total_dps == pytest.approx(253.5 * (1.0 / 0.65) * 1.025)

    def test_base_spell_crit(self):
        # Spells have an innate 500 CSR = 5% base crit at 0 gear; attacks do not.
        assert calculate_offense(_source(), _spell(), 16).crit_chance == pytest.approx(0.05)
        assert calculate_offense(_source(), _skill(tags=("attack",)), 1).crit_chance == 0.0

    def test_base_spell_crit_scaled_by_inc(self):
        # +100% Critical Strike Rating scales the 500 base → 1000 CSR → 10%.
        r = calculate_offense(_source(crit_rating_inc=1.0), _spell(), 16)
        assert r.crit_chance == pytest.approx(0.10)


class TestEnemyVulnerability:
    def test_numbed_amplifies_lightning(self):
        # numbed_lightning_taken = +50% → lightning hit ×1.50 (base 482 → 723).
        r = calculate_offense(_source(numbed_lightning_taken=0.5), _spell(), 16)
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0 * 1.5)
        assert r.hit_forms[0].hit_min_by_type["lightning"] == pytest.approx(25.0 * 1.5)

    def test_vuln_helper_lightning_only(self):
        s = _source(numbed_lightning_taken=0.5)
        assert _enemy_vuln_mult(s, "lightning") == pytest.approx(1.5)
        assert _enemy_vuln_mult(s, "physical") == pytest.approx(1.0)
        assert _enemy_vuln_mult(s, "fire") == pytest.approx(1.0)

    def test_no_numbed_no_amplification(self):
        r = calculate_offense(_source(), _spell(), 16)
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0)


_WEBMERGE = {"same_target_shotgun": True, "falloff_coefficient": 0.80, "chains_per_jump": 1}


class TestShotgun:
    def test_web_merge_2_jumps(self):
        # n = 1 + 2 jumps; subsequent ×0.20 → cast_multiplier 1.40; per-hit damage unchanged.
        base = calculate_offense(_source(), _spell(jumps=2), 16).total_dps
        r = calculate_offense(_source(), _spell(jumps=2), 16, support_behavior=_WEBMERGE)
        assert r.cast_multiplier == pytest.approx(1.40)
        assert r.shotgun_hits == 3
        assert r.total_dps == pytest.approx(base * 1.40)
        # per-hit tooltip damage is NOT scaled by the shotgun
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0)

    def test_extra_jumps_scale(self):
        # +4 extra jumps → 6 total → 1 + 6×0.20 = 2.20, 7 hits.
        r = calculate_offense(_source(extra_jumps_flat=4), _spell(jumps=2), 16, support_behavior=_WEBMERGE)
        assert r.cast_multiplier == pytest.approx(2.20)
        assert r.shotgun_hits == 7

    def test_merge_only_no_shotgun(self):
        beh = {"same_target_shotgun": True, "falloff_coefficient": 0.80}  # no chains (no Web)
        r = calculate_offense(_source(), _spell(jumps=2), 16, support_behavior=beh)
        assert r.cast_multiplier == pytest.approx(1.0) and r.shotgun_hits == 1

    def test_web_only_no_shotgun(self):
        beh = {"chains_per_jump": 1}  # no same-target (no Merge)
        r = calculate_offense(_source(), _spell(jumps=2), 16, support_behavior=beh)
        assert r.cast_multiplier == pytest.approx(1.0)

    def test_no_behavior_unaffected(self):
        r = calculate_offense(_source(), _spell(jumps=2), 16)
        assert r.cast_multiplier == pytest.approx(1.0) and r.shotgun_hits == 1

    def test_attack_skill_unaffected(self):
        # Regression: a normal attack with no support_behavior is untouched.
        r = calculate_offense(_source(weapon_attack_speed=2.0), _skill(tags=("attack",)), 1)
        assert r.cast_multiplier == 1.0


class TestAugmentation:
    def test_per_jump_compounds(self):
        # (1 + per)^total_jumps on the per-hit damage (shows in the tooltip range).
        beh = {"augmentation_per_jump": 0.057}
        r = calculate_offense(_source(), _spell(jumps=2), 16, support_behavior=beh)
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0 * 1.057 ** 2)

    def test_scales_with_extra_jumps(self):
        beh = {"augmentation_per_jump": 0.057}
        r = calculate_offense(_source(extra_jumps_flat=4), _spell(jumps=2), 16, support_behavior=beh)
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0 * 1.057 ** 6)

    def test_absent_no_effect(self):
        r = calculate_offense(_source(), _spell(jumps=2), 16, support_behavior={})
        assert r.hit_forms[0].hit_max_by_type["lightning"] == pytest.approx(482.0)


class TestLucky:
    def test_lifts_avg_not_range(self):
        # [100,120]: lucky_mult = (100 + ⅔·20)/(100 + ½·20) = 113.33/110 = 1.0303. DPS up, range same.
        beh = {"lucky_damage": True}
        base = calculate_offense(_source(), _spell(base=(100.0, 120.0)), 16)
        r = calculate_offense(_source(), _spell(base=(100.0, 120.0)), 16, support_behavior=beh)
        lucky_mult = (100 + (2 / 3) * 20) / (100 + 0.5 * 20)
        assert r.total_dps == pytest.approx(base.total_dps * lucky_mult)
        assert r.hit_forms[0].hit_max_by_type["lightning"] == base.hit_forms[0].hit_max_by_type["lightning"]

    def test_no_spread_no_effect(self):
        beh = {"lucky_damage": True}
        base = calculate_offense(_source(), _spell(base=(100.0, 100.0)), 16)
        r = calculate_offense(_source(), _spell(base=(100.0, 100.0)), 16, support_behavior=beh)
        assert r.total_dps == pytest.approx(base.total_dps)


class TestMainStatDamageBonus:
    """Each point of a skill's main-stat attribute → +0.5% damage; multi-main-stat skills SUM the
    attributes. Generic additional pool — folded into generic_add and scales total DPS."""
    def _dmg_skill(self, main_stat):
        return ResolvedSkill(
            skill_id="t", name="T", tags=["attack"], max_level=1,
            hit_forms_by_level={1: [_hit(eff=100.0)]},
            supported=True, main_stat=list(main_stat),
        )

    def _src(self, **extra):
        return _source(physical_attack_dmg_flat_min=100.0, physical_attack_dmg_flat_max=100.0,
                       weapon_attack_speed=1.0, **extra)

    def test_no_main_stat_no_bonus(self):
        r = calculate_offense(self._src(), self._dmg_skill([]), 1)
        assert r.main_stat_damage_bonus == 0.0
        assert r.main_stats == []

    def test_single_main_stat(self):
        # dexterity 200 × 0.005 = +100% → factor 2.0
        r = calculate_offense(self._src(dexterity=200.0), self._dmg_skill(["dexterity"]), 1)
        assert r.main_stat_damage_bonus == pytest.approx(1.0)
        assert r.main_stats == ["dexterity"]

    def test_dual_main_stats_sum(self):
        # (dex 100 + int 100) × 0.005 = +100%
        r = calculate_offense(self._src(dexterity=100.0, intelligence=100.0),
                              self._dmg_skill(["dexterity", "intelligence"]), 1)
        assert r.main_stat_damage_bonus == pytest.approx(1.0)
        assert set(r.main_stats) == {"dexterity", "intelligence"}

    def test_bonus_scales_dps_and_generic_add(self):
        base = calculate_offense(self._src(), self._dmg_skill([]), 1)
        # dex 100 × 0.005 = +50% → ×1.5 on both total DPS and the displayed generic additional
        boosted = calculate_offense(self._src(dexterity=100.0), self._dmg_skill(["dexterity"]), 1)
        assert boosted.total_dps == pytest.approx(base.total_dps * 1.5)
        assert boosted.generic_add == pytest.approx(base.generic_add * 1.5)

    def test_folds_into_type_add_so_ratio_is_clean(self):
        # The generic main-stat multiplier folds into BOTH type_add and generic_add, so the stats-screen
        # per-type ratio (type_add / generic_add) cancels to 1.0 — no phantom per-type reduction.
        r = calculate_offense(self._src(dexterity=100.0), self._dmg_skill(["dexterity"]), 1)
        assert r.type_add["physical"] == pytest.approx(r.generic_add)


class TestSpeedAdditionalPooling:
    """Additional attack/cast speed pools PER-AFFIX (distinct sources multiply) — verified in-game."""
    def _src(self, *entries):
        s = BuildSource()
        s.add("weapon_attack_speed", 1.0)
        for amt, text in entries:
            s.add_with_source("attack_speed_additional", amt, SourceEntry(
                stat="attack_speed_additional", amount=amt, source_type="x", label="x", text=text, points=1))
        return s

    def test_distinct_sources_multiply(self):
        # 10% (Dual Wield) + 22.5% (Quick Decision) on a 1.0/s base → ×1.10×1.225, NOT ×1.325
        r = calculate_offense(self._src((0.10, "Dual Wield"), (0.225, "Quick Decision")), _skill(tags=("attack",)), 1)
        assert r.skills_per_second == pytest.approx(1.0 * 1.10 * 1.225)

    def test_same_identity_sums(self):
        # identical mod text from two sources sums into one factor (×1.20), like the damage pool
        r = calculate_offense(self._src((0.10, "Same Mod"), (0.10, "Same Mod")), _skill(tags=("attack",)), 1)
        assert r.skills_per_second == pytest.approx(1.20)
