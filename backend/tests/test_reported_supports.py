"""Canonical SS13 Willpower behavior through the player's engine request."""
import pytest

from server import EngineStatsRequest, engine_stats
from tests.mock_build import make_request


@pytest.mark.parametrize('level,stacks,factor', [(1, 6, 1.041 ** 6), (16, 6, 1.056 ** 6),
                                               (20, 6, 1.06 ** 6), (20, 0, 1.0)])
def test_willpower_has_only_its_compounded_stack_bonus(level, stacks, factor):
    # SS13 Willpower Descript: 4.1/5.6/6% additional per stack, multiplies.
    # No standalone additional-damage bonus exists on this support.
    conditions = {'standing_still': True, 'willpower_stacks': stacks}
    base = engine_stats(EngineStatsRequest(**make_request('thunder_spike', 20,
                       extra_conditions=conditions)))
    supported = engine_stats(EngineStatsRequest(**make_request('thunder_spike', 20,
        [{'item_id': 'willpower', 'skill_type': 'support_skill', 'level': level, 'slot': 1}],
        extra_conditions=conditions)))
    assert supported['offense']['total_dps'] / base['offense']['total_dps'] == pytest.approx(factor)


def test_willpower_has_no_steady_state_moving_bonus():
    # Canonical buff persists for 0.5s after movement starts. This request represents
    # steady movement after that grace period; the engine has no transition clock.
    base = engine_stats(EngineStatsRequest(**make_request('thunder_spike', 20,
                       extra_conditions={'standing_still': False})))
    supported = engine_stats(EngineStatsRequest(**make_request('thunder_spike', 20,
        [{'item_id': 'willpower', 'skill_type': 'support_skill', 'level': 20, 'slot': 1}],
        extra_conditions={'standing_still': False, 'willpower_stacks': 6})))
    assert supported['offense']['total_dps'] / base['offense']['total_dps'] == pytest.approx(1.0)


@pytest.mark.parametrize('enabled,factor', [(True, 1.06 ** 6), (False, 1.0)])
def test_willpower_on_second_slot_does_not_change_main_spell(enabled, factor):
    skills = [{'slot': 1, 'skill_id': 'chain_lightning', 'level': 20},
              {'slot': 2, 'skill_id': 'thunder_spike', 'level': 20}]
    conditions = {'standing_still': True, 'willpower_stacks': 6}
    base = engine_stats(EngineStatsRequest(**make_request('chain_lightning', 20,
                       skills=skills, extra_conditions=conditions)))
    supported = engine_stats(EngineStatsRequest(**make_request('chain_lightning', 20,
        [{'item_id': 'willpower', 'skill_type': 'support_skill', 'level': 20,
          'slot': 2, 'enabled': enabled}], skills=skills, extra_conditions=conditions)))
    assert supported['slot_offense']['1']['total_dps'] / base['slot_offense']['1']['total_dps'] == pytest.approx(1.0)
    assert supported['slot_offense']['2']['total_dps'] / base['slot_offense']['2']['total_dps'] == pytest.approx(factor)
