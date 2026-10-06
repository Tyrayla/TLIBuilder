"""
Tests: Flame Slash (flame_slash) — the Sweep Slash/Steep Strike base skill (reusing
skill_resolver._resolve_slash_skill, same family as Berserking Blade/Focused Slash/Moon Strike),
its Area-bonus-driven torrent count + 50% Shotgun override + Physical->Fire conversion, and its two
canvas supports: Immediate Threat (linear enemy-distance proximity bonus) and Inverted Blaze
(returning-torrent extra hits). Design fully recorded in .wolf/plans/flame-slash.md
(owner-reviewed 2026-10-04).
"""
import pytest

from engine.models import BuildSource
from engine.skill_resolver import resolve_skill, _REGISTRY, flame_slash_torrent_count
from engine.offense import calculate_offense
from engine.skill_effects import flame_slash as fs


def _fss_data():
    return {
        "item_id": "flame_slash", "name": "Flame Slash",
        "skill_tags": ["Attack", "Melee", "Area", "Fire", "Slash-Strike"], "max_level": 20,
        "main_stat": "Strength",
        "raw_text": "Sweep Slash: Deals 346% Weapon Attack Damage. Steep Strike: For every 115% "
                    "Area bonus for this skill, the number of fire torrents +2. For every 115% Area "
                    "bonus for this skill, the distance of fire torrents +30%. The damage from "
                    "multiple fire torrents can be stacked. This skill's Shotgun Effect falloff "
                    "coefficient is 50% Converts 100 % of the skill's Physical Damage to Fire "
                    "Damage This skill +20 % Steep Strike chance.",
        "progression": [
            {"level": 1, "values": {"Descript":
                "Sweep Slash: Deals 120% Weapon Attack Damage. Steep Strike: Deals 150% Weapon "
                "Attack Damage."}},
            {"level": 20, "values": {"Descript":
                "Sweep Slash: Deals 346% Weapon Attack Damage. Steep Strike: Deals 346% Weapon "
                "Attack Damage."}},
        ],
    }


def _immediate_threat_data():
    return {
        "item_id": fs.IMMEDIATE_THREAT, "name": "Flame Slash: Immediate Threat (Magnificent)",
        "skill_type": "magnificent_support_skill",
        "progression": [
            {"level": 0, "values": {"name": "The supported skill deals more damage to enemies "
                                             "that are closer within 8 m, dealing up to "
                                             "+(43–47) % additional damage to enemies within 3 m"}},
            {"level": 1, "values": {"name": "The supported skill deals more damage to enemies "
                                             "that are closer within 8 m, dealing up to "
                                             "+(38–40) % additional damage to enemies within 3 m"}},
            {"level": 2, "values": {"name": "The supported skill deals more damage to enemies "
                                             "that are closer within 8 m, dealing up to "
                                             "+(34–36) % additional damage to enemies within 3 m"}},
        ],
    }


def _inverted_blaze_data():
    return {
        "item_id": fs.INVERTED_BLAZE, "name": "Flame Slash: Inverted Blaze (Noble)",
        "skill_type": "noble_support_skill",
        "progression": [
            {"level": 1, "values": {"name": "(-33.5–-32.5) % additional damage for the "
                                             "supported skill"}},
        ],
    }


class TestResolution:
    def test_registered(self):
        assert "flame_slash" in _REGISTRY

    def test_forms(self):
        sk = resolve_skill(_fss_data())
        assert sk.supported
        forms1 = sk.hit_forms_by_level[1]
        assert [f.effectiveness_pct for f in forms1] == [120.0, 150.0]
        sweep, steep = forms1
        assert sweep.proc_stat_key == "_complement_steep_strike_chance"
        assert steep.proc_stat_key == "steep_strike_chance"

    def test_steep_strike_overrides(self):
        steep = resolve_skill(_fss_data()).hit_forms_by_level[1][1]
        assert steep.scales_with_skill_area is True
        assert steep.shotgun_falloff == pytest.approx(0.50)
        assert steep.hit_count == 3  # fallback base, real count resolved per-slot

    def test_sweep_unaffected(self):
        sweep = resolve_skill(_fss_data()).hit_forms_by_level[1][0]
        assert sweep.scales_with_skill_area is False
        assert sweep.shotgun_falloff == 0.0

    def test_intrinsic_steep_chance(self):
        assert resolve_skill(_fss_data()).base_steep_strike_chance == pytest.approx(0.20)

    def test_intrinsic_convert(self):
        assert resolve_skill(_fss_data()).intrinsic_convert == {"physical": {"fire": 1.0}}

    def test_main_stat(self):
        assert resolve_skill(_fss_data()).main_stat == ["strength"]


class TestTorrentCountFormula:
    def test_zero_area_bonus(self):
        assert flame_slash_torrent_count(0.0) == 3

    def test_below_first_threshold(self):
        assert flame_slash_torrent_count(1.149) == 3

    def test_one_step(self):
        assert flame_slash_torrent_count(1.15) == 5

    def test_two_steps(self):
        assert flame_slash_torrent_count(2.30) == 7

    def test_between_steps_floors_down(self):
        assert flame_slash_torrent_count(2.0) == 5


class TestOffenseHitCount:
    """Steep Strike's n_proj/shotgun math at the OFFENSE layer — flame_slash_torrent_count_flat /
    flame_slash_return_hits_flat set directly, mirroring how apply_slot_effects would emit them."""

    def _src(self, torrents=None, returns=None):
        s = BuildSource()
        s.add("weapon_attack_speed", 1.0)
        s.add("physical_attack_dmg_flat_min", 100.0)
        s.add("physical_attack_dmg_flat_max", 100.0)
        if torrents is not None:
            s.add("flame_slash_torrent_count_flat", float(torrents))
        if returns is not None:
            s.add("flame_slash_return_hits_flat", float(returns))
        return s

    def test_base_three_torrents_no_support(self):
        sk = resolve_skill(_fss_data())
        result = calculate_offense(self._src(torrents=3), sk, 20)
        steep = next(f for f in result.hit_forms if f.proc_stat_key == "steep_strike_chance")
        assert steep.hits_per_fire == 3
        assert steep.shotgun_mult == pytest.approx(1.0 + 2 * 0.5)  # 1 full + 2 at 50%

    def test_fallback_without_emission(self):
        """No flame_slash_torrent_count_flat set at all (e.g. a test that skips apply_slot_effects)
        falls back to the resolver's base torrent count (3), never to 0."""
        sk = resolve_skill(_fss_data())
        result = calculate_offense(self._src(), sk, 20)
        steep = next(f for f in result.hit_forms if f.proc_stat_key == "steep_strike_chance")
        assert steep.hits_per_fire == 3

    def test_five_torrents_from_area_bonus(self):
        sk = resolve_skill(_fss_data())
        result = calculate_offense(self._src(torrents=5), sk, 20)
        steep = next(f for f in result.hit_forms if f.proc_stat_key == "steep_strike_chance")
        assert steep.hits_per_fire == 5
        assert steep.shotgun_mult == pytest.approx(1.0 + 4 * 0.5)

    def test_inverted_blaze_adds_return_hits(self):
        sk = resolve_skill(_fss_data())
        result = calculate_offense(self._src(torrents=3, returns=3), sk, 20)
        steep = next(f for f in result.hit_forms if f.proc_stat_key == "steep_strike_chance")
        assert steep.hits_per_fire == 6  # 3 outbound + 3 returning, same shotgun group
        assert steep.shotgun_mult == pytest.approx(1.0 + 5 * 0.5)

    def test_sweep_form_unaffected_by_torrent_stats(self):
        sk = resolve_skill(_fss_data())
        result = calculate_offense(self._src(torrents=7, returns=7), sk, 20)
        sweep = next(f for f in result.hit_forms if f.proc_stat_key == "_complement_steep_strike_chance")
        assert sweep.hits_per_fire == 1
        assert sweep.shotgun_mult == pytest.approx(1.0)


class TestApplySlotEffectsTorrentCount:
    """apply_slot_effects' own Area-bonus read (mirrors berserking_blade.py's emit_rampage formula)."""

    def _resolved(self):
        return resolve_skill(_fss_data())

    @pytest.mark.parametrize("parts, expected", [
        ((0.30, 0.85), 5), ((0.30, 2.00), 7), ((0.30, 3.15), 9),
        ((0.30, 4.30), 11), ((0.30, 3.14999999), 7),
        ((0.30, 0.84999999), 3),
    ])
    def test_accumulated_thresholds_through_returns_and_offense(self, parts, expected):
        # Tooltip: 3 + 2 per full 115% Area. Returns equal outbound torrents;
        # both trips share the 50% shotgun group. A real shortfall stays below.
        s = TestOffenseHitCount()._src()
        for part in parts:
            s.add("skill_area_inc", part)
        sk = self._resolved()
        fs.apply_slot_effects(
            source=s, resolved=sk, slot=1, condition_state={}, mod_tags={"attack"},
            attached_supports=[{"item_id": fs.INVERTED_BLAZE, "level": 1}],
            skills_by_id={fs.INVERTED_BLAZE: _inverted_blaze_data()})
        eff = s.materialize_for_skill({"attack"}, 1)
        assert eff.total("flame_slash_torrent_count_flat") == expected
        assert eff.total("flame_slash_return_hits_flat") == expected
        steep = calculate_offense(eff, sk, 20).hit_forms[1]
        assert steep.hits_per_fire == 2 * expected
        assert steep.shotgun_mult == 1 + (2 * expected - 1) * 0.5

    def test_no_area_source_gives_base_three(self):
        s = BuildSource()
        fs.apply_slot_effects(source=s, resolved=self._resolved(), slot=1, condition_state={},
                              mod_tags={"attack"}, attached_supports=[], skills_by_id={})
        eff = s.materialize_for_skill({"attack"}, 1)
        assert eff.total("flame_slash_torrent_count_flat") == pytest.approx(3.0)

    def test_115_pct_area_bonus_gives_five(self):
        s = BuildSource()
        s.add("skill_area_inc", 1.15)
        fs.apply_slot_effects(source=s, resolved=self._resolved(), slot=1, condition_state={},
                              mod_tags={"attack"}, attached_supports=[], skills_by_id={})
        eff = s.materialize_for_skill({"attack"}, 1)
        assert eff.total("flame_slash_torrent_count_flat") == pytest.approx(5.0)

    @pytest.mark.parametrize("parts", [
        (0.60, 0.55), (0.45, 0.40, 0.30), (0.23,) * 5, (0.575, 0.575),
    ])
    def test_multi_source_accumulation_still_hits_115_pct_threshold(self, parts):
        """A real build sums the 115% Area-bonus threshold from SEVERAL gear/talent sources, not
        one literal 1.15 — correctness-council finding (2026-10-04) that this could, in principle,
        float-point-drift a few ulps below the threshold and silently undercount by one step. Locks
        in that the realistic (2-decimal-affix) accumulation patterns do NOT lose the step."""
        s = BuildSource()
        for p in parts:
            s.add("skill_area_inc", p)
        fs.apply_slot_effects(source=s, resolved=self._resolved(), slot=1, condition_state={},
                              mod_tags={"attack"}, attached_supports=[], skills_by_id={})
        eff = s.materialize_for_skill({"attack"}, 1)
        assert eff.total("flame_slash_torrent_count_flat") == pytest.approx(5.0)

    def test_negative_area_bonus_never_drops_below_base(self):
        """No tooltip clause reduces torrent count below the base 3 — a negative aggregated Area
        bonus (e.g. a 'reduced Skill Area' source) must floor at the base, not go negative or
        below 3."""
        s = BuildSource()
        s.add("skill_area_inc", -0.50)
        fs.apply_slot_effects(source=s, resolved=self._resolved(), slot=1, condition_state={},
                              mod_tags={"attack"}, attached_supports=[], skills_by_id={})
        eff = s.materialize_for_skill({"attack"}, 1)
        assert eff.total("flame_slash_torrent_count_flat") == pytest.approx(3.0)


class TestBothSupportsSameSlot:
    """Immediate Threat (slot 3) and Inverted Blaze (slot 5) are mutually compatible — a real build
    can socket both into the SAME Flame Slash slot's 5 support sockets. Neither branch in
    apply_slot_effects' per-support loop should affect the other."""

    def _skills_by_id(self):
        return {fs.IMMEDIATE_THREAT: _immediate_threat_data(), fs.INVERTED_BLAZE: _inverted_blaze_data()}

    def test_both_attached_both_contribute(self):
        s = BuildSource()
        fs.apply_slot_effects(
            source=s, resolved=resolve_skill(_fss_data()), slot=1, condition_state={},
            mod_tags={"attack"},
            attached_supports=[{"item_id": fs.IMMEDIATE_THREAT, "level": 1},
                                {"item_id": fs.INVERTED_BLAZE, "level": 1}],
            skills_by_id=self._skills_by_id())
        eff = s.materialize_for_skill({"attack"}, 1)
        assert eff.total("dmg_additional") == pytest.approx(0.39)  # Immediate Threat, point-blank
        assert eff.total("flame_slash_return_hits_flat") == pytest.approx(3.0)  # Inverted Blaze default


class TestImmediateThreat:
    def _skills_by_id(self):
        return {fs.IMMEDIATE_THREAT: _immediate_threat_data()}

    def _run(self, enemy_distance_m):
        s = BuildSource()
        cond = {} if enemy_distance_m is None else {"enemy_distance_m": enemy_distance_m}
        fs.apply_slot_effects(
            source=s, resolved=resolve_skill(_fss_data()), slot=1, condition_state=cond,
            mod_tags={"attack"}, attached_supports=[{"item_id": fs.IMMEDIATE_THREAT, "level": 1}],
            skills_by_id=self._skills_by_id())
        return s.materialize_for_skill({"attack"}, 1).total("dmg_additional")

    def test_default_distance_is_point_blank_full_roll(self):
        assert self._run(None) == pytest.approx(0.39)  # tier-1 mid (38+40)/200

    def test_within_near_band_full_roll(self):
        assert self._run(2.0) == pytest.approx(0.39)

    def test_far_band_zero_bonus(self):
        assert self._run(8.0) == pytest.approx(0.0)
        assert self._run(10.0) == pytest.approx(0.0)

    def test_midpoint_is_half_roll(self):
        assert self._run(5.5) == pytest.approx(0.39 * 0.5)

    def test_wrong_slot_does_not_leak(self):
        """attached_supports is the BUILD-WIDE list (every skill slot's supports). A support
        attached to a DIFFERENT slot must not contribute to this slot (cross-model review finding,
        2026-10-04) — a build can equip Flame Slash in more than one slot with different support
        loadouts (test_per_slot_foundation.py)."""
        s = BuildSource()
        fs.apply_slot_effects(
            source=s, resolved=resolve_skill(_fss_data()), slot=1, condition_state={},
            mod_tags={"attack"},
            attached_supports=[{"item_id": fs.IMMEDIATE_THREAT, "level": 1, "slot": 2}],
            skills_by_id=self._skills_by_id())
        assert s.materialize_for_skill({"attack"}, 1).total("dmg_additional") == 0.0

    def test_disabled_support_does_not_contribute(self):
        s = BuildSource()
        fs.apply_slot_effects(
            source=s, resolved=resolve_skill(_fss_data()), slot=1, condition_state={},
            mod_tags={"attack"},
            attached_supports=[{"item_id": fs.IMMEDIATE_THREAT, "level": 1, "enabled": False}],
            skills_by_id=self._skills_by_id())
        assert s.materialize_for_skill({"attack"}, 1).total("dmg_additional") == 0.0

    def test_explicit_roll_override(self):
        from engine.affix_identity import affix_identity
        s = BuildSource()
        line = ("The supported skill deals more damage to enemies that are closer within 8 m, "
                "dealing up to +(38–40) % additional damage to enemies within 3 m")
        sup = {"item_id": fs.IMMEDIATE_THREAT, "level": 1,
               "specific_rolls": {affix_identity(line): 0.50}}
        fs.apply_slot_effects(source=s, resolved=resolve_skill(_fss_data()), slot=1,
                              condition_state={}, mod_tags={"attack"}, attached_supports=[sup],
                              skills_by_id=self._skills_by_id())
        assert s.materialize_for_skill({"attack"}, 1).total("dmg_additional") == pytest.approx(0.50)

    def test_explicit_roll_still_scales_with_distance(self):
        """A regression that made an explicit user-rolled value bypass the distance clamp entirely
        (returning the raw roll regardless of enemy_distance_m) would NOT be caught by
        test_explicit_roll_override alone, since that test only checks the override at the
        implicit default distance (0m, frac=1.0) — correctness-council finding, 2026-10-04."""
        from engine.affix_identity import affix_identity
        s = BuildSource()
        line = ("The supported skill deals more damage to enemies that are closer within 8 m, "
                "dealing up to +(38–40) % additional damage to enemies within 3 m")
        sup = {"item_id": fs.IMMEDIATE_THREAT, "level": 1,
               "specific_rolls": {affix_identity(line): 0.50}}
        fs.apply_slot_effects(source=s, resolved=resolve_skill(_fss_data()), slot=1,
                              condition_state={"enemy_distance_m": 5.5}, mod_tags={"attack"},
                              attached_supports=[sup], skills_by_id=self._skills_by_id())
        assert s.materialize_for_skill({"attack"}, 1).total("dmg_additional") == pytest.approx(0.25)


class TestInvertedBlaze:
    def _skills_by_id(self):
        return {fs.INVERTED_BLAZE: _inverted_blaze_data()}

    def _run(self, condition_state, area_inc=0.0):
        s = BuildSource()
        if area_inc:
            s.add("skill_area_inc", area_inc)
        fs.apply_slot_effects(
            source=s, resolved=resolve_skill(_fss_data()), slot=1, condition_state=condition_state,
            mod_tags={"attack"}, attached_supports=[{"item_id": fs.INVERTED_BLAZE, "level": 1}],
            skills_by_id=self._skills_by_id())
        return s.materialize_for_skill({"attack"}, 1).total("flame_slash_return_hits_flat")

    def test_default_returns_equal_torrent_count(self):
        assert self._run({}) == pytest.approx(3.0)

    @pytest.mark.parametrize("area, expected", [(115, 5), (230, 7)])
    @pytest.mark.parametrize("manual", [None, 0, 2])
    def test_endpoint_reports_auto_intent_even_with_global_override(self, area, expected, manual):
        from server import engine_stats, EngineStatsRequest
        from tests.mock_build import make_request
        req = make_request("flame_slash", 20, attached_supports=[{
            "item_id": fs.INVERTED_BLAZE, "skill_type": "noble_support_skill",
            "rank": 5, "level": 1, "slot": 1}], custom_mods=[f"+{area}% Skill Area"],
            extra_conditions={} if manual is None else {"inverted_blaze_returns": manual})
        result = engine_stats(EngineStatsRequest(**req))
        steep = result["offense"]["hit_forms"][1]
        assert steep["hits_per_fire"] == expected + (expected if manual is None else manual)
        assert result["auto_conditions"]["inverted_blaze_returns"] == {
            "value": expected, "source": "Inverted Blaze (returning torrents)",
            "slot_values": {"1": expected}}

    @pytest.mark.parametrize("manual, hits", [(None, (6, 10)), (0, (3, 5)), (2, (5, 7))])
    def test_two_slots_report_distinct_auto_counts_and_global_override(self, manual, hits):
        from server import engine_stats, EngineStatsRequest
        from tests.mock_build import make_request
        supports = [{"item_id": fs.INVERTED_BLAZE, "skill_type": "noble_support_skill",
                     "rank": 5, "level": 1, "slot": slot} for slot in (1, 2)]
        # Increased Area grants 20% to slot 2 only: 100% < 115%, 120% >= 115%.
        supports.append({"item_id": "increased_area", "skill_type": "support_skill",
                         "rank": 1, "level": 1, "slot": 2})
        req = make_request("flame_slash", 20, attached_supports=supports,
            custom_mods=["+100% Skill Area"],
            skills=[{"slot": slot, "skill_id": "flame_slash", "level": 20} for slot in (1, 2)],
            extra_conditions={} if manual is None else {"inverted_blaze_returns": manual})
        result = engine_stats(EngineStatsRequest(**req))
        assert tuple(result["slot_offense"][str(slot)]["hit_forms"][1]["hits_per_fire"]
                     for slot in (1, 2)) == hits
        assert result["auto_conditions"]["inverted_blaze_returns"] == {
            "value": None, "source": "Inverted Blaze (returning torrents)",
            "slot_values": {"1": 3, "2": 5}}

    def test_default_scales_with_area_bonus(self):
        assert self._run({}, area_inc=1.15) == pytest.approx(5.0)

    def test_explicit_override(self):
        assert self._run({"inverted_blaze_returns": 1}) == pytest.approx(1.0)

    def test_explicit_zero_means_no_returns_land(self):
        assert self._run({"inverted_blaze_returns": 0}) == pytest.approx(0.0)

    def test_wrong_slot_does_not_leak(self):
        s = BuildSource()
        fs.apply_slot_effects(
            source=s, resolved=resolve_skill(_fss_data()), slot=1, condition_state={},
            mod_tags={"attack"},
            attached_supports=[{"item_id": fs.INVERTED_BLAZE, "level": 1, "slot": 2}],
            skills_by_id=self._skills_by_id())
        assert s.materialize_for_skill({"attack"}, 1).total("flame_slash_return_hits_flat") == 0.0

    def test_not_attached_emits_nothing(self):
        s = BuildSource()
        fs.apply_slot_effects(source=s, resolved=resolve_skill(_fss_data()), slot=1,
                              condition_state={}, mod_tags={"attack"}, attached_supports=[],
                              skills_by_id={})
        assert s.materialize_for_skill({"attack"}, 1).total("flame_slash_return_hits_flat") == 0.0
