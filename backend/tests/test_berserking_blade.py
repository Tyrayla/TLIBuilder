"""Berserking Blade canvas supports (Desperation / Sweep / Decimate / Rampage) + the intrinsic buff,
driven end-to-end through engine_stats with no-affix baseline 1H swords so the attack produces real DPS.
"""
import pytest

from server import engine_stats, EngineStatsRequest
from engine.skill_effects import berserking_blade as bb
from engine.support_resolver import resolve_support_contributions
from server import _get_skills_data, _translate_condition_expr
from persistence import season_manager

_SEASON = season_manager.get_active_season()
_SKILLS = _get_skills_data(_SEASON)


def _sword(slot):
    def c(stat, val):
        return {"stat": stat, "display_value": val, "unit": "", "item_name": "BL Sword",
                "text": "base", "slot": slot, "condition": None}
    return {"item_name": "BL Sword", "base_type": "One-Handed Sword", "slot": slot,
            "contributions": [c("physical_dmg_gear_flat_min", 100), c("physical_dmg_gear_flat_max", 150),
                              c("weapon_attack_speed", 1.5), c("weapon_crit_rating_flat", 500)]}


def _sup(item_id, stype, level=1, rank=1, slot=1):
    return {"item_id": item_id, "skill_type": stype, "rank": rank, "level": level, "slot": slot}


def _run(*, supports=None, cond=None, gear_extra=None, skill="berserking_blade"):
    gear = [_sword("weapon1"), _sword("weapon2")] + (gear_extra or [])
    return engine_stats(EngineStatsRequest(
        slots=[None, None, None, None], condition_state=cond or {}, gear=gear,
        skills=[{"slot": 1, "skill_id": skill, "level": 14}],
        main_skill={"skill_id": skill, "level": 14},
        attached_supports=supports or [], characterLevel=100))


def _dps(**kw):
    return _run(**kw)["offense"]["total_dps"]


_DESP = _sup("berserking_blade_desperation_magnificent", "magnificent_support_skill")
_SWEEP = _sup("berserking_blade_sweep_magnificent", "magnificent_support_skill")
_DECI = _sup("berserking_blade_decimate_noble", "noble_support_skill")
_RAMP = _sup("berserking_blade_rampage_noble", "noble_support_skill")


@pytest.fixture(scope="module")
def base():
    return _dps()


class TestDesperation:
    def test_no_life_lost_is_inert(self, base):
        assert _dps(supports=[_DESP], cond={"current_life_pct": 100}) == pytest.approx(base)

    def test_per_5pct_scaling(self, base):
        # 50% life lost = floor(50/5)=10 steps × tier-1 mid 2.8% = +28% additional (multiplies the pool).
        assert _dps(supports=[_DESP], cond={"current_life_pct": 50}) == pytest.approx(base * 1.28, rel=1e-3)

    def test_cap(self, base):
        # 99% lost = 19 steps × 2.8% = 53% but capped at +38% additional.
        assert _dps(supports=[_DESP], cond={"current_life_pct": 1}) == pytest.approx(base * 1.38, rel=1e-3)


class TestSweep:
    def test_dps_inert_alone(self, base):
        # Skill Area does not affect single-target DPS; Sweep only matters via Rampage.
        assert _dps(supports=[_SWEEP]) == pytest.approx(base)

    def test_stack_cap_doubles(self):
        assert bb.stacks({}, has_sweep=False) == 20
        assert bb.stacks({}, has_sweep=True) == 40
        assert bb.stacks({"berserking_blade_stacks": 100}, has_sweep=False) == 20   # clamps to cap
        assert bb.stacks({"berserking_blade_stacks": 12}, has_sweep=True) == 12     # user below cap


class TestRampage:
    def test_lifts_dps_via_steep_strike(self, base):
        assert _dps(supports=[_RAMP]) > base

    def test_sweep_feeds_rampage(self):
        # Sweep's additional Skill Area increases the pool Rampage shares → more steep-strike damage.
        assert _dps(supports=[_RAMP, _SWEEP]) > _dps(supports=[_RAMP])


class TestDecimate:
    _VS_LL = {"item_name": "Ring", "unresolved_texts": ["+50 % Attack Damage against Low Life enemies"]}

    def test_enables_vs_low_life_at_threshold(self, base):
        manual = _dps(cond={"enemy_low_life": True}, gear_extra=[self._VS_LL])
        assert manual > base
        # enemy at 50% < tier-1 threshold (57–59 mid 58) → Decimate makes it Low Life for BB.
        on = _dps(supports=[_DECI], cond={"enemy_life_pct": 50}, gear_extra=[self._VS_LL])
        assert on == pytest.approx(manual, rel=1e-6)

    def test_inactive_above_threshold(self, base):
        off = _dps(supports=[_DECI], cond={"enemy_life_pct": 80}, gear_extra=[self._VS_LL])
        assert off == pytest.approx(base, rel=1e-6)

    def test_scoped_to_berserking_blade(self, base):
        # Decimate attached but main skill is NOT Berserking Blade → no enemy_low_life flip (skill-scoped).
        off = _dps(supports=[_DECI], cond={"enemy_life_pct": 50}, gear_extra=[self._VS_LL], skill="focused_slash")
        on_bb = _dps(supports=[_DECI], cond={"enemy_life_pct": 50}, gear_extra=[self._VS_LL])
        base_fs = _dps(gear_extra=[self._VS_LL], skill="focused_slash")
        assert off == pytest.approx(base_fs, rel=1e-6)  # focused_slash unaffected by BB's Decimate
        assert on_bb > base                              # BB itself is affected

    def test_preseed_runs_off_slot(self):
        # Berserking Blade in slot 2 (main skill is focused_slash in slot 1): its Decimate must STILL
        # preseed enemy_low_life so slot 2's own offense gets the "vs Low Life" bonus. This guards the
        # per-slot preseed dispatch (previously preseed ran only for the main skill).
        def slot2_dps(supports):
            r = engine_stats(EngineStatsRequest(
                slots=[None, None, None, None], condition_state={"enemy_life_pct": 50},
                gear=[_sword("weapon1"), _sword("weapon2"), self._VS_LL],
                skills=[{"slot": 1, "skill_id": "focused_slash", "level": 14},
                        {"slot": 2, "skill_id": "berserking_blade", "level": 14}],
                main_skill={"skill_id": "focused_slash", "level": 14},
                attached_supports=supports, characterLevel=100))
            so = r.get("slot_offense") or {}
            return (so.get(2) or so.get("2") or {}).get("total_dps")

        on = slot2_dps([_sup("berserking_blade_decimate_noble", "noble_support_skill", slot=2)])
        off = slot2_dps([])
        assert on and off and on > off, f"off-slot Decimate preseed did not fire: {off} -> {on}"


class TestSelfBuff:
    def test_skill_area_emitted_for_bb_only(self):
        bb_off = _run()["offense"]
        # The intrinsic buff grants +2.5%/stack × 20 = +50% Skill Area (display field, DPS-inert).
        assert bb_off["skill_area_inc"] == pytest.approx(0.025 * 20, rel=1e-6)
        fs_off = _run(skill="focused_slash")["offense"]
        assert fs_off.get("skill_area_inc", 0.0) == pytest.approx(0.0)


class TestSteepStrikeFormScoped:
    def test_only_steep_form_scales(self, base):
        """Rampage's additional Steep Strike Damage lifts only the Steep Strike hit form, not Sweep Slash."""
        b = _run()["offense"]["hit_forms"]
        r = _run(supports=[_RAMP])["offense"]["hit_forms"]
        bd = {f["name"]: f for f in b}
        rd = {f["name"]: f for f in r}
        # Steep Strike form's per-hit damage goes up; the complement (Sweep Slash) is unchanged.
        assert rd["Steep Strike"]["avg_hit_pre_crit"] > bd["Steep Strike"]["avg_hit_pre_crit"]
        assert rd["Sweep Slash"]["avg_hit_pre_crit"] == pytest.approx(bd["Sweep Slash"]["avg_hit_pre_crit"])


class TestGenericPathGuard:
    @pytest.mark.parametrize("item_id", [
        "berserking_blade_sweep_magnificent",
        "berserking_blade_decimate_noble",
        "berserking_blade_rampage_noble"])
    def test_no_bogus_specific_dmg_additional(self, item_id):
        # The generic range parser would mis-emit a tiny always-on dmg_additional; the BB branch must not.
        c = resolve_support_contributions([_sup(item_id, _SKILLS[item_id]["skill_type"])], _SKILLS,
                                          _translate_condition_expr)
        # rank 1 → no universal line either; these three contribute nothing via the contribution path.
        assert [x for x in c if x["stat_key"] == "dmg_additional"] == []

    def test_desperation_emits_capped_conditional(self):
        c = resolve_support_contributions([_DESP], _SKILLS, _translate_condition_expr)
        desp = [x for x in c if "desperation" in x.get("text", "")]
        assert len(desp) == 1
        cond = desp[0]["condition"]
        assert cond["key"] == "life_lost_pct" and cond["op"] == "per" and cond["divisor"] == 5.0
        assert cond["cap"] == pytest.approx(0.38)
