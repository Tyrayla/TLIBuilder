"""Ethereal-Prism Plan A: the crafting-catalog categorizer + the over-allocation cap on PassiveTree.allocate.
(No engine DPS yet — that is Plan B.)"""
import pytest
from tools.prism_catalog import categorize_prism_catalog
from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType


# ── Categorizer ──────────────────────────────────────────────────────────────
_RAW = {
    "items": [
        {"name": "Ethereal Prism: Haze", "kind": "ethereal_prism", "icon_url": "haze.webp", "tags": [], "detail": []},
        {"name": "Ethereal Prism: Phantasmagoria", "kind": "ethereal_prism", "icon_url": "ph.webp", "tags": [], "detail": []},
        {"name": "Ethereal Prism: Juggernaut", "kind": "ethereal_prism", "icon_url": "jug.webp", "tags": [], "detail": []},
        {"name": "Inverse Image", "kind": "inverse_image", "icon_url": "inv.webp", "tags": [], "detail": []},
    ],
    "base_affixes": [
        "Adds an additional effect to the Core Talent on the X/Y Advanced Talent Panel: +12 % additional Attack Damage",
        "Adds an additional effect to the Core Talent on the X/Y Advanced Talent Panel: +8 % Critical Strike Damage",
        "+75 % to the effects of Random Affixes on this Prism",
        "Replaces the Core Talent on the X/Y Advanced Talent Panel with Juggernaut",
        "Replaces the Core Talent on the X/Y Advanced Talent Panel with One For All",
    ],
    "random_affixes": [
        {"modifier": "The Effect Area expands to 3x4 Rectangle", "type": ""},
        {"modifier": "The Effect Area expands to 3x4 Rectangle", "type": ""},   # dup
        {"modifier": "All Micro Talent within the area also gain: +6 % Attack Damage", "type": "Prism Gauge - Rare"},
        {"modifier": "All Legendary Medium Talent within the area also gain: +5 % Block Ratio", "type": "Prism Gauge - Rare"},
        {"modifier": "All Legendary Medium Talent within the area also gain: +9 % Block Ratio", "type": "Prism Gauge - Rare"},  # ×1.75 dupe
        {"modifier": "Points can be allocated to all Medium Talent within the area 1 additional time(s)", "type": "Prism Gauge - Legendary"},
        {"modifier": "Points can be allocated to all Medium Talent within the area 2 additional time(s)", "type": "Prism Gauge - Legendary"},
        {"modifier": "Points can be allocated to all Medium Talent within the area 3 additional time(s)", "type": "Prism Gauge - Legendary"},
        {"modifier": "All Legendary Medium Talent within the area can ignore prerequisite point requirements", "type": "Prism Gauge - Legendary"},
        {"modifier": "-8 % Defense Mutated Core Talents no longer replace the original talent, but add the following to the Core Talent in the current Talent Panel: Juggernaut", "type": ""},
    ],
}


def test_items_resolve_implicit_and_rarity():
    cat = categorize_prism_catalog(_RAW)
    by = {i["short_name"]: i for i in cat["items"]}
    assert "Inverse Image" not in by   # only ethereal items
    assert by["Haze"]["rarities"] == ["rare"] and by["Haze"]["implicit"]["kind"] == "add_choice"
    assert len(by["Haze"]["implicit"]["options"]) == 2
    assert by["Phantasmagoria"]["rarities"] == ["legendary"] and by["Phantasmagoria"]["implicit"]["kind"] == "amplify"
    assert by["Juggernaut"]["rarities"] == ["rare", "legendary"]
    assert by["Juggernaut"]["default_rarity"] == "legendary" and by["Juggernaut"]["tint_when_rare"] is True
    assert by["Juggernaut"]["implicit"]["text"].endswith("Juggernaut")


def test_random_affix_pools_split_and_dedupe():
    cat = categorize_prism_catalog(_RAW)
    assert cat["area_size"] == [{"modifier": "The Effect Area expands to 3x4 Rectangle", "cols": 3, "rows": 4}]
    assert cat["middle"][0]["tier"] == "micro"
    kinds = {a["kind"] for a in cat["advanced"]}
    assert {"over_alloc", "ignore_prereq"} <= kinds
    oa = next(a for a in cat["advanced"] if a["kind"] == "over_alloc")
    assert oa["tier"] == "medium"
    assert cat["do_not_replace"]["Juggernaut"][0]["penalty"] == "-8 % Defense"


def test_phantasmagoria_scaled_dupe_stripped_but_overalloc_counts_kept():
    cat = categorize_prism_catalog(_RAW)
    blocks = [m["modifier"] for m in cat["middle"] if "Block Ratio" in m["modifier"]]
    assert blocks == ["All Legendary Medium Talent within the area also gain: +5 % Block Ratio"]   # +9 % dropped
    # the over-allocation 1/2/3-additional-time counts share a skeleton but must all survive
    counts = sorted(a["count"] for a in cat["advanced"] if a["kind"] == "over_alloc")
    assert counts == [1, 2, 3]


# ── Over-allocation cap ──────────────────────────────────────────────────────
def _tree_two_micro():
    t = PassiveTree("t")
    t.add_node(PassiveNode(id="a", node_type=NodeType.MICRO, column=0, row=0, max_points=3))
    t.add_node(PassiveNode(id="b", node_type=NodeType.MICRO, column=1, row=0, max_points=3))
    t.add_connection("a", "b")
    return t


def test_over_allocation_raises_cap():
    t = _tree_two_micro()
    for _ in range(3):
        t.allocate("a")
    with pytest.raises(ValueError):           # normal cap is 3
        t.allocate("a")
    t.allocate("a", max_overrides={"a": 5})   # raised cap lets a 4th point in
    assert t.nodes["a"].current_points == 4


def test_over_allocation_does_not_relax_prereq():
    # 'b' still needs 'a' >= 3 (the Micro threshold); over-allocation only adds headroom, never lowers the gate.
    t = _tree_two_micro()
    t.allocate("a"); t.allocate("a")          # a has 2 pts (< threshold 3)
    with pytest.raises(ValueError):
        t.allocate("b", max_overrides={"b": 9})
    t.allocate("a")                           # a now at 3 → prereq met
    t.allocate("b")
    assert t.nodes["b"].current_points == 1
