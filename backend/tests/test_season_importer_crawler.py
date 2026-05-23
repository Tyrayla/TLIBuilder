import pytest
from tools.season_importer import _make_display_name_key, import_crawler_tree


# ── _make_display_name_key ──────────────────────────────────────────────────

def test_display_name_key_simple():
    assert _make_display_name_key("Alchemist", "Source") == "alchemist_source"


def test_display_name_key_compound():
    assert _make_display_name_key("God of Machines", "Shrink Back") == "god_of_machines_shrink_back"


# ── import_crawler_tree ─────────────────────────────────────────────────────

_MINIMAL_NODE = {
    "talent_id": "01020100",
    "name": "Test Node",
    "type": "micro_talent",
    "column": 2,
    "row": 1,
    "max_rank": 1,
    "effects": ["+5% damage"],
    "pts_required": 0,
    "icon_url": "https://cdn.example.com/icon.png",
    "prerequisites": [],
}


def test_col_row_adjustment():
    data = {"nodes": [_MINIMAL_NODE]}
    result = import_crawler_tree(data, "Alchemist")
    node = result["nodes"][0]
    assert node["column"] == 1   # 2 - 1
    assert node["row"] == 0      # 1 - 1


def test_type_mapping():
    types = [
        ("micro_talent",            "Micro Talent"),
        ("medium_talent",           "Medium Talent"),
        ("legendary_medium_talent", "Legendary Medium Talent"),
    ]
    for raw, expected in types:
        node = {**_MINIMAL_NODE, "type": raw}
        result = import_crawler_tree({"nodes": [node]}, "Alchemist")
        assert result["nodes"][0]["node_type"] == expected


def test_max_rank_stored_as_max_rank():
    node = {**_MINIMAL_NODE, "max_rank": 3}
    result = import_crawler_tree({"nodes": [node]}, "Alchemist")
    assert result["nodes"][0]["max_rank"] == 3
    assert "max_points" not in result["nodes"][0]


def test_connections_from_prerequisites():
    node_a = {
        "talent_id": "01010100", "name": "A", "type": "micro_talent",
        "column": 1, "row": 1, "max_rank": 1, "effects": [],
        "pts_required": 0, "icon_url": "", "prerequisites": [],
    }
    node_b = {
        "talent_id": "01020100", "name": "B", "type": "micro_talent",
        "column": 2, "row": 1, "max_rank": 1, "effects": [],
        "pts_required": 0, "icon_url": "", "prerequisites": ["01010100"],
    }
    result = import_crawler_tree({"nodes": [node_a, node_b]}, "Alchemist")
    conns = result["connections"]
    assert len(conns) == 1
    assert conns[0]["from"] == "alchemist_c0_r0"
    assert conns[0]["to"] == "alchemist_c1_r0"


def test_core_talents_fields():
    core = {
        "talent_id": "01000000", "name": "Power Surge", "type": "core_talent",
        "column": None, "row": None, "max_rank": 1,
        "effects": ["+10% power"], "pts_required": 12,
        "icon_url": "https://cdn.example.com/core.png",
        "prerequisites": [],
    }
    result = import_crawler_tree({"nodes": [core]}, "Alchemist")
    ct = result["core_talents"][0]
    assert ct["display_name_key"] == "alchemist_power_surge"
    assert ct["name"] == "Power Surge"
    assert ct["pts_required"] == 12
    assert ct["icon_url"] == "https://cdn.example.com/core.png"


def test_glossary_list_to_dict():
    glossary = [
        {"term_id": "719", "name": "Tenacity Blessing", "description": "Stacks of tenacity."},
        {"term_id": "720", "name": "Agility Blessing",  "description": "Stacks of agility."},
    ]
    result = import_crawler_tree({"nodes": [], "glossary": glossary}, "Alchemist")
    g = result["glossary"]
    assert "719" in g
    assert g["719"]["name"] == "Tenacity Blessing"
    assert "720" in g
    assert g["720"]["description"] == "Stacks of agility."
