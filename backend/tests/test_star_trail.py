"""Star Trail aggregates same-branch Micro Fates before rounding their contribution."""

from server import EngineStatsRequest, engine_stats
from tests.mock_build import make_request


def test_two_star_trails_scale_combined_micro_fate_max_fire_resistance():
    # In-game measurement: 3 x 2% = 6%; 6% x 1.90 = 11.4%, rounded down to 11%.
    # The unrelated +4% talent is intentionally absent from this regression input.
    effects = [
        {
            "text": "+2 % Max Fire Resistance",
            "source": "Fate: Max Fire Resistance",
            "microFateGroup": "0",
            "microFateMultiplierPercent": 190,
        }
        for _ in range(3)
    ]
    request = make_request("split_shot", 1)
    request["spirit_effects"] = effects

    result = engine_stats(EngineStatsRequest(**request))

    assert result["defense"]["fire_resist_max"] == 71.0
