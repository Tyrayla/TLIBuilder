import pytest
from tools.season_importer import _effect_line, _make_display_name_key, import_crawler_tree


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


def test_max_active_divinity_suffix_is_structured_for_ss14():
    effect = _effect_line("Shadow Quantity +1 (Max Active Divinity: 1)")
    assert effect["text"] == "Shadow Quantity +1 (Max Active Divinity: 1)"
    assert effect["max_divinity_effect"] == 1


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


def test_trait_replacement_talent_keeps_its_prerequisite_connection():
    parent = {
        **_MINIMAL_NODE,
        "talent_id": "32030100", "name": "Parent", "column": 3, "row": 1,
        "prerequisites": [],
    }
    replacement = {
        **_MINIMAL_NODE,
        "talent_id": "32050101", "name": "Replacement", "column": 5, "row": 1,
        "type": "legendary_medium_talent",
        "effects": ["+3 % Attack Speed Source:Hero Trait -Prophecy of Revelation"],
        "prerequisites": ["32030100"],
    }

    result = import_crawler_tree({"nodes": [parent, replacement]}, "Arcanist")

    assert result["connections"] == [{"from": "arcanist_c2_r0", "to": "arcanist_c4_r0"}]


def test_missing_crawler_connections_preserve_existing_edges_with_valid_endpoints():
    node_b = {**_MINIMAL_NODE, "talent_id": "01030100", "column": 3, "row": 1}
    existing = {"connections": [
        {"from": "alchemist_c1_r0", "to": "alchemist_c2_r0"},
        {"from": "alchemist_c8_r8", "to": "alchemist_c9_r9"},
    ]}

    result = import_crawler_tree({"nodes": [_MINIMAL_NODE, node_b]}, "Alchemist", existing)

    assert result["connections"] == [{"from": "alchemist_c1_r0", "to": "alchemist_c2_r0"}]


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


def test_nether_king_unpositioned_pool_rows_become_distinct_core_choices():
    rows = [
        {"talent_id": f"9000000{i}", "name": name, "type": kind,
         "column": None, "row": None, "max_rank": 1,
         "effects": [effect], "pts_required": None, "icon_url": "", "prerequisites": []}
        for i, (name, kind, effect) in enumerate([
            ("Micro Nether King Talent Node", "micro_talent", "+5% damage"),
            ("Medium Nether King Talent Node", "medium_talent", "+10% damage"),
            ("Legendary Medium Nether King Talent Node", "legendary_medium_talent", "+15% damage"),
            ("Ultimate Nether King Talent Node", "ultimate_talent", "+20% damage"),
        ])
    ]

    result = import_crawler_tree({"nodes": rows}, "Nether King")

    assert result["nodes"] == []
    assert [ct["effects"][0]["text"] for ct in result["core_talents"]] == [
        "+5% damage", "+10% damage", "+15% damage", "+20% damage",
    ]
    assert {ct["display_name_key"] for ct in result["core_talents"]} == {
        "nether_king_micro_nether_king_talent_node",
        "nether_king_medium_nether_king_talent_node",
        "nether_king_legendary_medium_nether_king_talent_node",
        "nether_king_ultimate_nether_king_talent_node",
    }


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


def test_empty_crawled_glossary_keeps_existing_definitions():
    existing = {"glossary": {
        "719": {"name": "Tenacity Blessing", "description": "Existing definition."},
    }}

    result = import_crawler_tree({"nodes": [], "glossary": []}, "Alchemist", existing)

    assert result["glossary"]["719"] == {
        "name": "Tenacity Blessing", "description": "Existing definition."
    }


def test_trait_replacement_talents_share_one_node_and_keep_both_variants():
    base = {
        **_MINIMAL_NODE,
        "talent_id": "32050100",
        "name": "Legendary Medium Talent",
        "type": "legendary_medium_talent",
        "column": 5,
        "row": 1,
        "pts_required": 12,
        "effects": ["+10 % Attack and Cast Speed when at Full Mana", "+15 % Max Mana"],
    }
    revelation = {
        **base,
        "talent_id": "32050101",
        "effects": [
            "+3 % Attack and Cast Speed for each stack of Max Focus Blessing while at Full Mana . "
            "Stacks up to 18 time(s) Source:Hero Trait -Prophecy of Revelation"
        ],
    }

    result = import_crawler_tree({"nodes": [base, revelation]}, "Arcanist")

    assert len(result["nodes"]) == 1
    node = result["nodes"][0]
    assert node["id"] == "arcanist_c4_r0"
    assert [effect["text"] for effect in node["effects"]] == [
        "+10 % Attack and Cast Speed when at Full Mana",
        "+15 % Max Mana",
    ]
    assert node["trait_variants"] == [{
        "trait_id": "wisdom_of_the_gods",
        "unlock_level": 60,
        "advanced_selection": "Prophecy of Revelation",
        "effects": [{
            "text": "+3 % Attack and Cast Speed for each stack of Max Focus Blessing while at Full Mana . "
                    "Stacks up to 18 time(s)",
            "uuid": None,
            "pooling_uuid": None,
            "modifier_id": None,
        }],
    }]


def test_trait_variant_strips_source_markup_and_keeps_max_divinity_metadata():
    base = {
        **_MINIMAL_NODE,
        "talent_id": "32050100",
        "name": "Legendary Medium Talent",
        "type": "legendary_medium_talent",
        "column": 5,
        "row": 1,
        "effects": ["+10 % Attack Speed"],
    }
    replacement = {
        **base,
        "talent_id": "32050101",
        "effects": [
            "+1 Max Tenacity Blessing stacks at Full Life (Max Active Divinity: 1) "
            '<div class="prophecy"> Source:Hero Trait -Prophecy of Revelation</div>'
        ],
    }

    result = import_crawler_tree({"nodes": [base, replacement]}, "Arcanist")

    assert result["nodes"][0]["trait_variants"] == [{
        "trait_id": "wisdom_of_the_gods",
        "unlock_level": 60,
        "advanced_selection": "Prophecy of Revelation",
        "effects": [{
            "text": "+1 Max Tenacity Blessing stacks at Full Life (Max Active Divinity: 1)",
            "uuid": None,
            "pooling_uuid": None,
            "modifier_id": None,
            "max_divinity_effect": 1,
        }],
    }]
