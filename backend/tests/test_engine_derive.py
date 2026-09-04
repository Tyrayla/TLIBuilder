"""
Tests: engine/derive.py — derive_stats() final effective-stat computation.
Formula per stat: value = (base + sum(flat_keys)) * (1 + sum(inc_keys)) * prod(1 + sum(pool))
clamped at 0, then injected back into the source. inc/additional values are decimals.
"""
import pytest
from engine.models import BuildSource, SourceEntry
from engine.derive import derive_stats
from engine.defense import calculate_defense


def _src(**stats) -> BuildSource:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _gear(source: BuildSource, stat: str, amount: float, slot: str, *, shield: bool = False) -> None:
    source.add_with_source(stat, amount, SourceEntry(
        stat=stat, amount=amount, source_type="gear", label=f"Gear · {slot}", text=stat,
        gear_slot=slot, is_shield=shield,
    ))


class TestAttributes:
    def test_strength_flat_only(self):
        assert derive_stats(_src(strength_flat=100))["strength"] == pytest.approx(100)

    def test_all_stats_flat_adds_to_every_attribute(self):
        r = derive_stats(_src(strength_flat=100, dexterity_flat=50, all_stats_flat=10))
        assert r["strength"] == pytest.approx(110)
        assert r["dexterity"] == pytest.approx(60)
        assert r["intelligence"] == pytest.approx(10)

    def test_inc_is_decimal_and_pools_additively(self):
        # 150 flat * (1 + 0.2 strength_inc + 0.3 all_stats_inc) = 225
        r = derive_stats(_src(strength_flat=100, all_stats_flat=50, strength_inc=0.2, all_stats_inc=0.3))
        assert r["strength"] == pytest.approx(225)


class TestLifeManaEs:
    def test_max_life_inc_and_additional_pool(self):
        # 1000 * (1 + 0.5) * (1 + 0.2) = 1800
        r = derive_stats(_src(max_life_flat=1000, max_life_inc=0.5, max_life_additional=0.2))
        assert r["max_life"] == pytest.approx(1800)

    def test_max_mana_simple(self):
        assert derive_stats(_src(max_mana_flat=500, max_mana_inc=0.1))["max_mana"] == pytest.approx(550)

    def test_energy_shield_gear_inc_is_local_not_global(self):
        # "% gear Energy Shield" is LOCAL (pre-applied per item in the gear payload), so derive does
        # NOT treat it as a global inc — only the global max_energy_shield_inc scales the flat.
        # (100 + 200) * (1 + 0.1) = 330  (the 0.2 energy_shield_gear_inc is intentionally ignored)
        r = derive_stats(_src(max_energy_shield_flat=100, energy_shield_gear_flat=200,
                              max_energy_shield_inc=0.1, energy_shield_gear_inc=0.2))
        assert r["max_energy_shield"] == pytest.approx(330)


class TestArmorEvasion:
    def test_armor_with_shared_defense_inc_and_additional(self):
        # (500 + 500) * (1 + 0.1 armor_inc + 0.4 defense_inc) * (1 + 0.1 additional) = 1650
        r = derive_stats(_src(armor_flat=500, armor_gear_flat=500, armor_inc=0.1,
                              defense_inc=0.4, armor_additional=0.1))
        assert r["armor"] == pytest.approx(1650)

    def test_defense_inc_is_shared_by_evasion(self):
        # 1000 * (1 + 0.5 defense_inc) = 1500
        assert derive_stats(_src(evasion_flat=1000, defense_inc=0.5))["evasion"] == pytest.approx(1500)


class TestSlotLocalGearDefense:
    def test_chest_defense_scales_only_chest_defense_types(self):
        s = _src(chest_defense_inc=0.4, max_energy_shield_flat=50, armor_flat=25)
        _gear(s, "energy_shield_gear_flat", 100, "chest")
        _gear(s, "armor_gear_flat", 200, "chest")
        _gear(s, "evasion_gear_flat", 300, "chest")
        _gear(s, "armor_gear_flat", 400, "helmet")
        r = derive_stats(s)
        assert r["max_energy_shield"] == pytest.approx(190)
        assert r["armor"] == pytest.approx(705)
        assert r["evasion"] == pytest.approx(420)

    def test_shield_modifiers_join_normal_local_increased_pool_additively(self):
        s = _src(shield_defense_inc=0.25, shield_energy_shield_inc=0.15)
        _gear(s, "energy_shield_gear_flat", 100, "weapon2", shield=True)
        _gear(s, "energy_shield_gear_inc", 0.20, "weapon2", shield=True)
        _gear(s, "armor_gear_flat", 200, "weapon2", shield=True)
        _gear(s, "armor_gear_inc", 0.10, "weapon2", shield=True)
        _gear(s, "evasion_gear_flat", 300, "weapon2", shield=True)
        r = derive_stats(s)
        assert r["max_energy_shield"] == pytest.approx(160)  # 100 × (1 + .20 + .25 + .15)
        assert r["armor"] == pytest.approx(270)               # 200 × (1 + .10 + .25)
        assert r["evasion"] == pytest.approx(375)             # 300 × (1 + .25)
        d = calculate_defense(s)
        assert d.es_flat == pytest.approx(160)
        assert d.armor_flat == pytest.approx(270)
        assert d.evasion_flat == pytest.approx(375)
        assert len(d.local_gear_sources["energy_shield"]) == 1
        assert d.local_gear_sources["energy_shield"][0]["amount"] == pytest.approx(160)
        assert d.local_gear_sources["energy_shield"][0]["raw_amount"] == pytest.approx(100)
        assert d.local_gear_sources["energy_shield"][0]["multiplier"] == pytest.approx(1.6)
        assert {row["text"] for row in d.local_gear_sources["energy_shield"][0]["local_increases"]} == {
            "energy_shield_gear_inc", "shield_defense_inc", "shield_energy_shield_inc",
        }

    def test_local_gear_rows_aggregate_one_item_and_keep_talent_attribution(self):
        s = BuildSource()
        _gear(s, "energy_shield_gear_flat", 200, "chest")
        _gear(s, "energy_shield_gear_flat", 300, "chest")
        s.add_with_source("chest_defense_inc", 0.4, SourceEntry(
            stat="chest_defense_inc", amount=0.4, source_type="talent", label="Goddess of Knowledge · node_1",
            text="+40% Defense from Chest", source_name="Goddess of Knowledge",
        ))

        row = calculate_defense(s).local_gear_sources["energy_shield"][0]
        assert row["raw_amount"] == pytest.approx(500)
        assert row["amount"] == pytest.approx(700)
        assert row["multiplier"] == pytest.approx(1.4)
        assert row["local_increases"] == [{
            "amount": 0.4, "label": "Goddess of Knowledge · node_1", "source_name": "Goddess of Knowledge",
            "text": "+40% Defense from Chest", "source_type": "talent",
        }]

    def test_shield_modifier_does_not_scale_an_offhand_weapon(self):
        s = _src(shield_defense_inc=0.25, shield_energy_shield_inc=0.15)
        _gear(s, "energy_shield_gear_flat", 100, "weapon2")
        _gear(s, "armor_gear_flat", 200, "weapon2")
        r = derive_stats(s)
        assert r["max_energy_shield"] == pytest.approx(100)
        assert r["armor"] == pytest.approx(200)


class TestEdgeCases:
    def test_clamped_at_zero(self):
        assert derive_stats(_src(max_life_flat=-100))["max_life"] == 0.0

    def test_empty_source_all_zero(self):
        assert all(v == 0.0 for v in derive_stats(_src()).values())

    def test_results_injected_back_into_source(self):
        s = _src(strength_flat=100, max_life_flat=1000)
        derive_stats(s)
        assert s.total("strength") == pytest.approx(100)
        assert s.total("max_life") == pytest.approx(1000)
