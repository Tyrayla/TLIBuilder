"""GROWING golden coverage for every engine-modeled skill + its supports.

Unlike test_skill_scope_nochange.py (which pins a no-op for the scope feature using one skill), this suite
is **registry-driven**: it parametrizes over every skill in engine.skill_resolver._REGISTRY, so it
automatically covers exactly the skills the engine models — and a newly `@_register`'d skill auto-gets its
own golden captured on first run. Each case sockets the skill's bespoke canvas supports (discovered from the
data by name prefix, so new skills' canvas supports are picked up too) plus a fixed spread of standard
supports, and snapshots the offense + support-driven stats. So any change in how a support contributes
(a new mapper rule, a fix, or a regression) shows up as a golden diff for the affected skill.

Re-capture deliberately (delete the fixture) only when intentionally changing engine output. Spells
(chain_lightning) produce real DPS here; the slash/attack skills currently need extra in-build setup to
deal damage, so their goldens lock the present state until that's modeled — at which point the diff is the
signal to re-capture.
"""
import json
import os

import pytest

from server import engine_stats, EngineStatsRequest, _get_skills_data
from persistence import season_manager
from engine import skill_resolver
from tests.mock_build import make_request  # builds the payload the way the app does

_GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "support_skill_golden")

_SEASON = season_manager.get_active_season()
_SKILLS_BY_ID: dict = _get_skills_data(_SEASON) if _SEASON else {}

# Standard supports socketed on every case — a spread that exercises the mapper across damage types and
# the attack/spell category gates (incompatible ones are gated out by the engine, which is itself captured).
_STANDARD = [
    "added_physical_damage", "added_lightning_damage", "added_fire_damage",
    "overload", "jump", "electric_overload", "attack_focus",
]

# Spells use their in-game default level; everything else a representative 20.
_LEVEL = {"chain_lightning": 14}

# Conditions turned ON so CONDITIONAL supports actually contribute (otherwise overload/attack_focus/etc.
# resolve to 0 and the goldens wouldn't catch their bugs). A deliberately fully-buffed scenario.
_GOLDEN_CONDITIONS = {
    "focus_blessings": 4, "agility_blessings": 4, "tenacity_blessings": 4,
    "fervor_rating": 100,
    "enemy_cursed": True, "numbed_stacks": 10, "enemy_numbed": True,
    "ignite_stacks": 5, "standing_still": True, "willpower_stacks": 6,
}


def _canvas_supports(skill_id: str) -> list[dict]:
    """The skill's bespoke Noble/Magnificent supports, found by name prefix ('<Skill>: ...') so the set
    grows with the data. Socketed at max rank/tier to exercise the full rank table + top tier line."""
    name = (_SKILLS_BY_ID.get(skill_id) or {}).get("name", "")
    if not name:
        return []
    out = []
    for s in _SKILLS_BY_ID.values():
        if s.get("name", "").startswith(name + ":"):
            st = s.get("skill_type")
            if st in ("magnificent_support_skill", "noble_support_skill"):
                out.append({"item_id": s["item_id"], "skill_type": st, "rank": 5, "level": 5})
    return sorted(out, key=lambda x: x["item_id"])


def _request(skill_id: str) -> dict:
    """App-shaped payload (1H sword + 1H axe dual-wield, character level 90) for the skill + supports."""
    lvl = _LEVEL.get(skill_id, 20)
    supports = _canvas_supports(skill_id) + [
        {"item_id": sid, "skill_type": "support_skill", "level": 20} for sid in _STANDARD
    ]
    return make_request(skill_id, lvl, supports, extra_conditions=_GOLDEN_CONDITIONS)


def _canonical(resp: dict) -> dict:
    """Skill/support-dependent slice of the response (defense is skill-independent → omitted to cut noise)."""
    return {
        "offense": resp.get("offense"),
        "slot_offense": resp.get("slot_offense"),
        "stats": {k: resp.get("stats", {})[k] for k in sorted(resp.get("stats", {}))},
        "consumed_stats": sorted(resp.get("consumed_stats") or []),
    }


_MODELED_SKILLS = sorted(skill_resolver._REGISTRY)


def test_modeled_skills_present():
    """Sanity: the registry is non-empty so the parametrized suite below actually covers something."""
    assert _MODELED_SKILLS, "no @_register'd skills found in skill_resolver._REGISTRY"


@pytest.mark.parametrize("skill_id", _MODELED_SKILLS)
def test_support_skill_golden(skill_id):
    os.makedirs(_GOLDEN_DIR, exist_ok=True)
    path = os.path.join(_GOLDEN_DIR, f"{skill_id}.json")
    current = _canonical(engine_stats(EngineStatsRequest(**_request(skill_id))))
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, sort_keys=True)
        pytest.skip(f"captured golden {skill_id}.json (baseline) — re-run to assert")
    golden = json.load(open(path, encoding="utf-8"))
    current = json.loads(json.dumps(current, sort_keys=True))
    assert current == golden, f"engine output changed for modeled skill {skill_id} — re-capture if intended"
