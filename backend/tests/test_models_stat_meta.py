"""
Tests: models/stat_meta.py — structure and validity of every STAT_META entry.
"""
from models.stat import Stat
from models.stat_meta import STAT_META, StatMeta, CATEGORIES


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

    def test_all_stat_meta_keys_are_valid_enum_members(self):
        """Every key in STAT_META must be a live Stat enum member.
        Guards against stat_meta entries surviving after a rename/delete in stat.py."""
        stat_values = {s.value for s in Stat}
        stale = [stat.value for stat in STAT_META if stat.value not in stat_values]
        assert not stale, f"STAT_META has entries for deleted/renamed stats: {stale}"
