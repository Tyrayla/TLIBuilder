"""SS14 season data: Youga 3 'The Ultimate One' (selection-only tree trait).

Reads the hydrated dataset the way the app does (season_manager) and skips when the SS14 season is not
hydrated locally (data/ comes from tli-data)."""
import pytest

from persistence import season_manager

pytestmark = pytest.mark.skipif(
    "SS14" not in season_manager.list_seasons(), reason="SS14 season not hydrated in data/seasons"
)

EXPECTED_EDGES = {
    ("the_ultimate_one", "i_meet_the_selves"),
    ("the_ultimate_one", "i_hold_all_in_my_grasp"),
    ("the_ultimate_one", "i_arrive_alongside_destiny"),
    ("i_meet_the_selves", "i_am_the_measure_of_all_time"),
    ("i_meet_the_selves", "i_need_not_lift_a_finger"),
    ("i_arrive_alongside_destiny", "i_gather_the_threads_of_causality"),
    ("i_arrive_alongside_destiny", "i_command_all"),
    ("i_hold_all_in_my_grasp", "i_will_hunt_you_down"),
    ("i_will_hunt_you_down", "i_come_to_claim_my_due"),
    ("i_will_hunt_you_down", "i_see_no_doomsday_today"),
}


def _trait():
    return season_manager.load_hero_traits_indexed("SS14")["the_ultimate_one"]


def test_tree_shape():
    t = _trait()
    assert t["hero"] == "Youga"
    assert t["allocation_mode"] == "tree"
    assert t["tree_root_id"] == "the_ultimate_one"
    assert len(t["tree_nodes"]) == 11
    assert {(c["from"], c["to"]) for c in t["tree_connections"]} == EXPECTED_EDGES


def test_every_node_has_layout_and_connection_endpoints_exist():
    t = _trait()
    ids = {n["node_id"] for n in t["tree_nodes"]}
    assert len(ids) == 11
    for n in t["tree_nodes"]:
        assert 0 < n["x"] < 1 and 0 < n["y"] < 1
    for c in t["tree_connections"]:
        assert c["from"] in ids and c["to"] in ids


def test_node_text_is_verbatim_trait_level_5():
    nodes = {n["node_id"]: n for n in _trait()["tree_nodes"]}
    assert nodes["i_arrive_alongside_destiny"]["effects"][0] == "+28% Cooldown Recovery Speed"
    assert nodes["i_come_to_claim_my_due"]["effects"][0] == (
        'When projectiles are Recalled, gain 2 stacks of "Centralization", up to 54 stacks.'
    )
    assert nodes["i_come_to_claim_my_due"]["unlock_level"] == 75


def test_root_and_late_nodes_carry_real_text_and_unlock_levels():
    nodes = {n["node_id"]: n for n in _trait()["tree_nodes"]}
    assert nodes["the_ultimate_one"]["unlock_level"] is None
    assert nodes["the_ultimate_one"]["effects"][0] == (
        'Your Main Active Spell Skill, if eligible for Tangle, is supported by "Clockwork Core", '
        "replacing the Support Skill in its second support slot."
    )
    assert nodes["i_will_hunt_you_down"]["unlock_level"] == 60
    assert nodes["i_will_hunt_you_down"]["effects"][1] == (
        'During "Recall", projectiles home in on enemies within "Stasis Vault".'
    )
    assert nodes["i_see_no_doomsday_today"]["unlock_level"] == 75
    assert len(nodes["i_see_no_doomsday_today"]["effects"]) == 2


def test_no_node_text_is_an_unverified_placeholder():
    for n in _trait()["tree_nodes"]:
        assert not any(line.startswith("Unverified") for line in n["effects"])


def test_alternate_spacetime_effects_cover_19_skills():
    effects = _trait()["alternate_spacetime_effects"]
    assert len(effects) == 19
    by_skill = {e["skill"]: e["lines"] for e in effects}
    assert by_skill["Serpent Beam"] == [
        'For each "Serpent Bind" inflicted recently, this skill\'s Combo Finisher deals +10% more damage, up to +140%.'
    ]
    assert len(by_skill["Chromatic Shot"]) == 3


def test_ss13_catalog_is_unchanged():
    assert "the_ultimate_one" not in season_manager.load_hero_traits_indexed("SS13")
    assert "dance_of_the_deep" in season_manager.load_hero_traits_indexed("SS14")
