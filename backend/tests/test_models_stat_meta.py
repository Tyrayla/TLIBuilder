"""
Tests: models/stat_meta.py and models/node_modifier_pool.py — coverage and cross-reference.
Scope: every pool entry has a meta entry; meta fields are non-empty and valid.
"""
import pytest
from models.stat import Stat
from models.stat_meta import STAT_META, StatMeta, CATEGORIES
from models.node_modifier_pool import NODE_MODIFIER_POOL


VALID_MODIFIER_TYPES = {
    "base_stat", "added_flat", "increased", "increased_reduced",
    "additional", "skill_level", "crit_rating", "crit_damage",
    "double_damage", "penetration", "conversion", "chance", "flat",
    "additive_chance", "speed", "other",
}


class TestStatMetaStructure:
    def test_all_entries_are_stat_meta(self):
        for key, meta in STAT_META.items():
            assert isinstance(meta, StatMeta), f"{key}: expected StatMeta, got {type(meta)}"

    def test_display_names_non_empty(self):
        for stat, meta in STAT_META.items():
            assert meta.display_name.strip(), f"{stat.name}: display_name is empty"

    def test_categories_are_known(self):
        for stat, meta in STAT_META.items():
            assert meta.category in CATEGORIES, (
                f"{stat.name}: unknown category '{meta.category}'. "
                f"Known: {CATEGORIES}"
            )


class TestPoolMetaCoverage:
    def test_every_pool_entry_has_meta(self):
        """Every stat in NODE_MODIFIER_POOL must have a STAT_META entry."""
        missing = [
            stat.name for stat in NODE_MODIFIER_POOL if stat not in STAT_META
        ]
        assert not missing, (
            f"Pool stats missing from STAT_META: {missing}"
        )

    def test_pool_stats_are_valid_enum_members(self):
        for stat in NODE_MODIFIER_POOL:
            assert isinstance(stat, Stat), f"Non-Stat key in pool: {stat!r}"

    def test_no_orphaned_meta_for_pool_stats(self):
        """
        Every Stat that has a StatMeta should still be a valid Stat enum member.
        (Guards against stale entries after enum renames.)
        """
        stat_values = {s.value for s in Stat}
        for stat in STAT_META:
            assert stat.value in stat_values, (
                f"STAT_META has entry for '{stat.value}' which is not in Stat enum"
            )
