"""SNAPSHOT golden no-change guarantee for the skill-scope feature (plan Test A).

Drives the REAL `engine_stats` endpoint function (same code path as /api/engine/stats, SS12 active) with a
set of requests built from REAL SS12 data that exercise EVERY contribution loop the scope feature touches —
custom mods, gear affixes, talent nodes, pact-spirit + hero-memory effects, supports, conditions — with NO
scoped mods. Goldens are captured ONCE on the pre-change (verified) engine into tests/fixtures/scope_golden/;
afterwards the scope feature must reproduce them BYTE-FOR-BYTE (the materialization is an identity no-op when
a build carries zero scoped entries). Re-capture deliberately (delete the fixture) only when intentionally
changing engine output.
"""
import json
import os

import pytest

from server import engine_stats, EngineStatsRequest

_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "scope_golden")

# Each request uses real SS12 ids/strings and carries NO "for/dealt by X Skills" scope.
_REQUESTS: dict[str, dict] = {
    # node loop + custom-mod loop + pact-spirit loop + conditions + a real spell skill
    "nodes_custom_spirit": dict(
        slots=[{"treeName": "Assassin",
                "nodeStates": {"assassin_c0_r2": 3, "assassin_c1_r1": 3, "assassin_c1_r2": 3},
                "coreTalentSelections": {}}, None, None, None],
        condition_state={"focus_blessings": 4, "agility_blessings": 4, "numbed_stacks": 10},
        custom_mods=["Converts 50 % of Lightning Damage to Cold Damage", "+30 % Attack Damage",
                     "+25 % increased Critical Strike Damage"],
        spirit_effects=["+10 % Affliction Effect", "+1.5 % Curse Effect"],
        skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
        main_skill={"skill_id": "chain_lightning", "level": 14},
        characterLevel=100,
    ),
    # gear loop (unresolved affix texts resolved server-side) + memory loop
    "gear_memory": dict(
        slots=[None, None, None, None],
        gear=[{"item_name": "TestWeapon",
               "unresolved_texts": ["+30 % gear Attack Speed", "+108 % Elemental Damage",
                                    "Adds 50 - 80 Physical Damage to the gear"]}],
        memory_effects=["+12 % Max Life", "+8 % Critical Strike Rating"],
        skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
        main_skill={"skill_id": "chain_lightning", "level": 14},
        characterLevel=100,
    ),
    # support loop (real attached supports) + a node tree
    "supports": dict(
        slots=[{"treeName": "Assassin", "nodeStates": {"assassin_c0_r2": 3}, "coreTalentSelections": {}},
               None, None, None],
        skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
        main_skill={"skill_id": "chain_lightning", "level": 14},
        attached_supports=[
            {"item_id": "chain_lightning_web_of_lightning_magnificent",
             "skill_type": "magnificent_support_skill", "rank": 1, "level": 1},
            {"item_id": "chain_lightning_lucky_noble",
             "skill_type": "noble_support_skill", "rank": 1, "level": 1}],
        characterLevel=100,
    ),
    # Unified spirit/memory resolver: exercises a multi-stat phrase, a dual-stat phrase, the ported
    # combo-starter/finisher entries, a skill-scoped effect, a conditional (gated) effect, a flat attribute
    # (now → _flat), and plain singles. Locks the post-unification behavior forward.
    "spirit_memory_heavy": dict(
        slots=[None, None, None, None],
        condition_state={"enemy_cursed": True},
        spirit_effects=["+10 % Affliction Effect", "+8 % Attack and Cast Speed",
                        "+20 % damage +20 % Minion Damage", "+5 % Lightning Penetration",
                        "+16 % additional damage against Cursed enemies",
                        "+14 % additional Elemental Damage dealt by Spell Skills"],
        memory_effects=["+100 Intelligence", "+12 % Max Life",
                        "+12 % Critical Strike Damage for Combo Finishers",
                        "+6 % additional Attack and Cast Speed for Combo Starters"],
        skills=[{"slot": 1, "skill_id": "chain_lightning", "level": 14}],
        main_skill={"skill_id": "chain_lightning", "level": 14},
        characterLevel=100,
    ),
}


def _canonical(resp: dict) -> dict:
    """Stable, comparable view of the engine response. Floats are deterministic for identical computation;
    lists whose order isn't guaranteed are sorted."""
    out = {
        "stats": {k: resp.get("stats", {})[k] for k in sorted(resp.get("stats", {}))},
        "offense": resp.get("offense"),
        "defense": resp.get("defense"),
        "condition_maximums": resp.get("condition_maximums"),
        "consumed_stats": sorted(resp.get("consumed_stats") or []),
    }
    return out


def _run(name: str) -> dict:
    return _canonical(engine_stats(EngineStatsRequest(**_REQUESTS[name])))


@pytest.mark.parametrize("name", sorted(_REQUESTS))
def test_no_change_vs_golden(name):
    os.makedirs(_GOLDEN_DIR, exist_ok=True)
    path = os.path.join(_GOLDEN_DIR, f"{name}.json")
    current = _run(name)
    if not os.path.exists(path):
        # First run (capture on the pre-change verified engine).
        with open(path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, sort_keys=True)
        pytest.skip(f"captured golden {name}.json (baseline) — re-run to assert")
    golden = json.load(open(path, encoding="utf-8"))
    # Round-trip current through JSON so float reprs match the stored golden exactly.
    current = json.loads(json.dumps(current, sort_keys=True))
    assert current == golden, f"engine output changed for {name} (scope feature must be byte-identical here)"
