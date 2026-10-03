"""BuildSource.materialize_for_skill builds a new source when a scoped or slot-local contribution matches the
skill. It must carry the editable calc-target ("dummy") and incoming-enemy configs forward; otherwise that
skill's vs-target DPS and the dummy panel silently fall back to the Lv85 constants (found 2026-09-30 when the
Affliction condition catalog added a skill-scoped contribution and test_target_config started failing).
"""
from engine.models import BuildSource, SourceEntry

TARGET = {"level": 40, "armor": 0.20, "fire_res": 0.10, "cold_res": 0.10, "lightning_res": 0.10, "erosion_res": 0.10}
ENEMY = {"enemyId": "e1", "skillId": "s1", "kind": "hit", "damage": {"fire_hit": 1000.0}}


def _entry(stat, amount):
    return SourceEntry(stat=stat, amount=amount, source_type="custom", label="test", text=f"test {stat}")


def test_scoped_match_keeps_target_and_enemy_config():
    src = BuildSource(target_config=TARGET, enemy_config=ENEMY)
    src.add_scoped("dot_dmg_inc", 0.5, "dot", _entry("dot_dmg_inc", 0.5))

    m = src.materialize_for_skill({"dot", "cold"})

    assert m is not src                      # a new source was actually built
    assert m.total("dot_dmg_inc") == 0.5     # the scoped contribution folded in
    assert m.target_config == TARGET
    assert m.enemy_config == ENEMY


def test_slot_local_match_keeps_target_and_enemy_config():
    src = BuildSource(target_config=TARGET, enemy_config=ENEMY)
    src.add_slotted("cold_dmg_inc", 0.25, 1, None, _entry("cold_dmg_inc", 0.25))

    m = src.materialize_for_skill({"cold"}, slot=1)

    assert m is not src
    assert m.total("cold_dmg_inc") == 0.25
    assert m.target_config == TARGET
    assert m.enemy_config == ENEMY
