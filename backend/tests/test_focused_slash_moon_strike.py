"""Focused Slash + Moon Strike canvas supports, driven end-to-end with baseline 1H swords.

Implemented: Duel (generic conditional), Behead, Fervor (noble), Tranquility, Rainbow, Lunar Ring.
Deferred (universal +20% still applies): Lunar Eclipse (mana sealing), Wax and Wane (Spell Burst).
"""
import pytest

from server import engine_stats, EngineStatsRequest, _get_skills_data, _translate_condition_expr
from engine.support_resolver import resolve_support_contributions
from persistence import season_manager

_SKILLS = _get_skills_data(season_manager.get_active_season())


def _sword(slot, mana=0):
    def c(stat, val):
        return {"stat": stat, "display_value": val, "unit": "", "item_name": "BL", "text": "base",
                "slot": slot, "condition": None}
    cc = [c("physical_dmg_gear_flat_min", 100), c("physical_dmg_gear_flat_max", 150),
          c("weapon_attack_speed", 1.5), c("weapon_crit_rating_flat", 500)]
    if mana:
        cc.append(c("max_mana_flat", mana))
    return {"item_name": "BL", "base_type": "One-Handed Sword", "slot": slot, "contributions": cc}


def _run(skill, *, supports=None, cond=None, mana=0, gear_extra=None, custom=None):
    gear = [_sword("weapon1", mana), _sword("weapon2")] + (gear_extra or [])
    return engine_stats(EngineStatsRequest(
        slots=[None, None, None, None], condition_state=cond or {}, gear=gear, custom_mods=custom or [],
        skills=[{"slot": 1, "skill_id": skill, "level": 14}],
        main_skill={"skill_id": skill, "level": 14}, attached_supports=supports or [], characterLevel=100))


def _dps(skill, **kw):
    return _run(skill, **kw)["offense"]["total_dps"]


def _sup(item_id, stype, **kw):
    return {"item_id": item_id, "skill_type": stype, "rank": kw.get("rank", 1),
            "level": kw.get("level", 1), "slot": 1}


_MAG = "magnificent_support_skill"
_NOB = "noble_support_skill"


class TestFocusedSlash:
    def test_duel_gates_on_single_enemy(self):
        duel = [_sup("focused_slash_duel_magnificent", _MAG)]
        one = _dps("focused_slash", supports=duel, cond={"enemies_nearby": 1, "fervor_rating": 100})
        many = _dps("focused_slash", supports=duel, cond={"enemies_nearby": 2, "fervor_rating": 100})
        assert one > many   # +65–70% additional only when exactly 1 enemy nearby

    def test_behead_guarantees_steep_strike(self):
        base = _run("focused_slash", cond={"fervor_rating": 100})["offense"]
        beh = _run("focused_slash", supports=[_sup("focused_slash_behead_noble", _NOB)],
                   cond={"fervor_rating": 100})["offense"]
        assert beh["steep_strike_chance"] == pytest.approx(1.0)   # guaranteed
        assert beh["total_dps"] > base["total_dps"]

    def test_behead_removes_area_tag(self):
        sa = {"item_name": "Ring", "unresolved_texts": ["+40 % Skill Area"]}
        without = _run("focused_slash", cond={"fervor_rating": 100}, gear_extra=[sa])["offense"]
        beh = _run("focused_slash", supports=[_sup("focused_slash_behead_noble", _NOB)],
                   cond={"fervor_rating": 100}, gear_extra=[sa])["offense"]
        assert without["skill_area_inc"] > 0
        assert beh["skill_area_inc"] == pytest.approx(0.0)   # Area tag removed → area mods drop

    def test_fervor_noble_gated_on_fervor(self):
        fer = [_sup("focused_slash_fervor_noble", _NOB)]
        on = _dps("focused_slash", supports=fer, cond={"fervor_rating": 100})
        off_base = _dps("focused_slash", cond={"fervor_rating": 0})
        off_sup = _dps("focused_slash", supports=fer, cond={"fervor_rating": 0})
        assert on > _dps("focused_slash", cond={"fervor_rating": 100})   # steep additional applies
        assert off_sup == pytest.approx(off_base)                        # gated off below 5 Fervor

    def test_tranquility_amplifies_fervor_bonus(self):
        # Focused Slash intrinsic: 0.004*fervor*(1 + inc + skill_inc). Tranquility's 10 stacks ADD into the
        # increased pool: +10×12.5% = +125% (tier-1 mid roll), scoped to the skill's Fervor damage bonus
        # only (not global crit). With no other Fervor Effect: bonus 0.40 → 0.40*(1+1.25)=0.90, ratio ×1.40.
        base = _dps("focused_slash", cond={"fervor_rating": 100})
        tr = _dps("focused_slash", supports=[_sup("focused_slash_tranquility_magnificent", _MAG)],
                  cond={"fervor_rating": 100})
        assert tr == pytest.approx(base * (1.90 / 1.40), rel=2e-3)

    def test_tranquility_stacks_as_increased_with_fervor_effect(self):
        # The discriminator (verified vs recount): with +40% Fervor Effect, Tranquility ADDS into the same
        # increased pool — bonus 0.40*(1+0.40+1.25)=1.06 — it does NOT multiply (additional would give
        # 0.40*1.40*2.25=1.26). Both runs carry the +40% so global crit cancels in the ratio.
        fe = ["+40 % Fervor Effect"]
        no_tr = _dps("focused_slash", cond={"fervor_rating": 100}, custom=fe)
        tr = _dps("focused_slash", supports=[_sup("focused_slash_tranquility_magnificent", _MAG)],
                  cond={"fervor_rating": 100}, custom=fe)
        increased = (1.0 + 0.40 * (1 + 0.40 + 1.25)) / (1.0 + 0.40 * (1 + 0.40))   # ×1.321
        additional = (1.0 + 0.40 * 1.40 * 2.25) / (1.0 + 0.40 * 1.40)              # ×1.449
        assert tr / no_tr == pytest.approx(increased, rel=5e-3)
        assert abs(tr / no_tr - additional) > 0.05   # clearly NOT the additional model


class TestMoonStrike:
    def test_rainbow_steep_chance_scales_with_mana(self):
        rb = [_sup("moon_strike_rainbow_magnificent", _MAG)]
        lo = _run("moon_strike", supports=rb, mana=500)["offense"]["steep_strike_chance"]
        hi = _run("moon_strike", supports=rb, mana=2000)["offense"]["steep_strike_chance"]
        base = _run("moon_strike", mana=2000)["offense"]["steep_strike_chance"]
        assert hi > lo > base   # +1% per 100 Max Mana

    def test_rainbow_caps(self):
        rb = [_sup("moon_strike_rainbow_magnificent", _MAG)]
        base = _run("moon_strike", mana=100000)["offense"]["steep_strike_chance"]
        capped = _run("moon_strike", supports=rb, mana=100000)["offense"]["steep_strike_chance"]
        assert capped - base == pytest.approx(0.425, abs=0.02)   # tier-1 cap ~ (41–44)% mid

    def test_lunar_ring_dps_neutral(self):
        base = _dps("moon_strike", mana=2000)
        ring = _dps("moon_strike", supports=[_sup("moon_strike_lunar_ring_magnificent", _MAG)], mana=2000)
        assert ring == pytest.approx(base)   # circular form does not change single-target DPS


class TestGuardsAndDeferrals:
    @pytest.mark.parametrize("item_id,stype", [
        ("focused_slash_tranquility_magnificent", _MAG),
        ("moon_strike_lunar_ring_magnificent", _MAG),
        ("moon_strike_lunar_eclipse_noble", _NOB),
        ("moon_strike_wax_and_wane_noble", _NOB),
    ])
    def test_guarded_specifics_emit_no_bogus_damage(self, item_id, stype):
        c = resolve_support_contributions([_sup(item_id, stype)], _SKILLS, _translate_condition_expr)
        assert [x for x in c if x["stat_key"] == "dmg_additional"] == []

    def test_fervor_noble_emits_steep_contribution(self):
        c = resolve_support_contributions([_sup("focused_slash_fervor_noble", _NOB)], _SKILLS,
                                          _translate_condition_expr)
        steep = [x for x in c if x["stat_key"] == "steep_strike_additional_dmg"]
        assert len(steep) == 1
        assert steep[0]["condition"] == {"key": "fervor_rating", "op": ">=", "value": 5.0}

    def test_deferred_universal_still_applies(self):
        # Lunar Eclipse is deferred, but its universal +20% (rank 5) must still resolve.
        c = resolve_support_contributions(
            [_sup("moon_strike_lunar_eclipse_noble", _NOB, rank=5)], _SKILLS, _translate_condition_expr)
        uni = [x for x in c if x["stat_key"] == "dmg_additional" and "universal" in x["text"]]
        assert len(uni) == 1 and uni[0]["amount"] == pytest.approx(0.20)
