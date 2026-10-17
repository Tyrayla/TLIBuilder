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


def test_node_text_is_verbatim_from_dataset():
    nodes = {n["node_id"]: n for n in _trait()["tree_nodes"]}
    assert nodes["i_arrive_alongside_destiny"]["effects"][0] == (
        "(/+7 % Cooldown Recovery Speed/+14 % Cooldown Recovery Speed/"
        "+21 % Cooldown Recovery Speed/+28 % Cooldown Recovery Speed) Spacetime Conqueror"
    )
    assert nodes["i_come_to_claim_my_due"]["effects"][0] == (
        "Upon Recall , Projectiles grant (1/1/2/2/2) stack(s) of Centralization , up to "
        "(30/36/42/48/54) stack(s) Upon Recall , Projectiles extend Stasis Vault Duration by 1 s "
        "if you have at least 20 stack(s) of Centralization . Interval: 0.5s"
    )
    assert nodes["i_come_to_claim_my_due"]["unlock_level"] == 75


def test_root_and_late_nodes_carry_real_text_and_unlock_levels():
    trait = _trait()
    nodes = {n["node_id"]: n for n in trait["tree_nodes"]}
    assert nodes["the_ultimate_one"]["unlock_level"] == 1
    # The root tooltip uses the trait's rank data, not its hand-authored layout node summary.
    root_rank_effects = [level["effects"][0] for level in trait["levels"]]
    assert len(root_rank_effects) == 5
    assert [effect.split(" % of bonuses")[0] for effect in root_rank_effects] == [
        "100", "120", "140", "160", "180",
    ]
    assert "up to 36 %" in root_rank_effects[0]
    assert "up to 48 %" in root_rank_effects[-1]
    assert nodes["i_will_hunt_you_down"]["unlock_level"] == 60
    assert "Projectiles track enemies within the range of Stasis Vault when Recalled" in (
        nodes["i_will_hunt_you_down"]["effects"][0]
    )
    doomsday = nodes["i_see_no_doomsday_today"]
    assert doomsday["unlock_level"] == 75
    assert "70 % of Hit Damage taken is not settled immediately" in doomsday["effects"][0]
    assert "Clockwork Core triggers Spacetime Inversion" in doomsday["effects"][0]


def test_no_node_text_is_an_unverified_placeholder():
    for n in _trait()["tree_nodes"]:
        assert not any(line.startswith("Unverified") for line in n["effects"])


def test_alternate_spacetime_effects_cover_19_skills():
    effects = _trait()["alternate_spacetime_effects"]
    assert len(effects) == 19
    by_skill = {e["skill"]: e["lines"] for e in effects}
    assert by_skill["Serpent Beam"] == [
        "While Selves of All Realms is active, +10% additional damage for this skill's Combo "
        "Finisher for each time Serpent Bind was inflicted recently, up to +140%"
    ]
    assert len(by_skill["Chromatic Shot"]) == 3


def test_ss13_catalog_is_unchanged():
    assert "the_ultimate_one" not in season_manager.load_hero_traits_indexed("SS13")
    assert "dance_of_the_deep" in season_manager.load_hero_traits_indexed("SS14")
