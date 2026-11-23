"""Star Trail aggregates same-branch Micro Fates before rounding their contribution."""

from server import EngineStatsRequest, engine_stats
from engine.aggregator import _apply_effect_contribs
from engine.models import BuildSource
from tests.mock_build import make_request


def _stats(effects):
    request = make_request("split_shot", 1)
    request["spirit_effects"] = effects
    result = engine_stats(EngineStatsRequest(**request))
    return result["stats"], result["defense"]


def _fate(text, group="0", multiplier=190):
    return {
        "text": text,
        "source": "Fate: Regression",
        "microFateGroup": group,
        "microFateMultiplierPercent": multiplier,
    }


def test_two_star_trails_scale_combined_micro_fate_max_fire_resistance():
    # In-game measurement: 3 x 2% = 6%; 6% x 1.90 = 11.4%, rounded down to 11%.
    # The unrelated +4% talent is intentionally absent from this regression input.
    _, defense = _stats([_fate("+2 % Max Fire Resistance") for _ in range(3)])

    assert defense["fire_resist_max"] == 71.0


def test_one_star_trail_aggregates_three_micro_fates_before_flooring():
    # 3 x 2% x 1.45 = 8.7%, floored to 8%; the base maximum is 60%.
    _, defense = _stats([_fate("+2 % Max Fire Resistance", multiplier=145) for _ in range(3)])

    assert defense["fire_resist_max"] == 68.0


def test_each_branch_floors_its_own_combined_percentage_before_adding():
    # Each branch: 3 x 1% x 1.90 = 5.7%, floored to 5%; two branches add to 10%.
    effects = [
        _fate("+1 % Max Fire Resistance", group)
        for group in ("0", "1")
        for _ in range(3)
    ]
    _, defense = _stats(effects)

    assert defense["fire_resist_max"] == 70.0


def test_positive_resistance_percentage_uses_same_fractional_stat_units():
    effects = [_fate("+2 % Fire Resistance") for _ in range(3)]
    stats, _ = _stats(effects)

    assert stats["fire_resistance"]["total"] == 0.11


def test_negative_percentage_preserves_legacy_per_fate_rounding_until_verified():
    # Legacy behavior: each -3.8% Fate rounds half away from zero to -4%; three sum to -12%.
    effects = [_fate("-2 % Fire Resistance") for _ in range(3)]
    _, defense = _stats(effects)

    assert defense["fire_resist"] == -12.0


def test_flat_strength_keeps_legacy_per_fate_integer_rounding():
    # Legacy behavior: each +3 Strength scales to 4.35 and rounds to 4 before source aggregation.
    effects = [_fate("+3 Strength", multiplier=145) for _ in range(3)]
    stats, _ = _stats(effects)

    assert stats["strength_flat"]["total"] == 12.0


def test_grouped_percentage_breakdown_identifies_all_micro_fates():
    effects = [_fate("+2 % Max Fire Resistance") for _ in range(3)]
    stats, _ = _stats(effects)

    source = stats["fire_resistance_max_inc"]["sources"][0]
    assert source["amount"] == 0.11
    assert source["source_name"] == "Fate: Regression (3 Micro Fates)"
    assert source["text"] == "+2 % Max Fire Resistance"


def test_mixed_sign_percentages_keep_negative_fates_on_legacy_rounding():
    effects = ([_fate("+2 % Fire Resistance") for _ in range(3)]
               + [_fate("-2 % Fire Resistance") for _ in range(3)])
    stats, _ = _stats(effects)

    assert stats["fire_resistance"]["total"] == -0.01


def test_unmapped_percentage_text_keeps_legacy_per_fate_rounding():
    source = BuildSource()
    effects = [
        {
            "stat_key": "unmodeled_stat",
            "amount": 0.02,
            "text": "+2 % Unmodeled Effect",
            "source": "Fate: Regression",
            "micro_fate_group": "0",
            "micro_fate_multiplier_percent": 145,
        }
        for _ in range(3)
    ]

    _apply_effect_contribs(source, effects, "pact_spirit", "Pact Spirit", frozenset(), {})

    assert source.total("unmodeled_stat") == 0.09
