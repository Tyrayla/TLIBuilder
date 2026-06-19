"""
Erika — Lightning Shadow (trait_id "lightning_shadow") end-to-end engine coverage.

Locks: the additional-Numbed-Effect pool, the real-mode Numbed uptime (Feline Figure steady state),
mode safety (max default unchanged; switching to real never breaks an unmigrated build), the
inflicting-skill-by-who-hits rule (no main-slot-by-index trap), and the never-silently-drop status surface.
"""
import pytest
from server import engine_stats, EngineStatsRequest
from tests.mock_build import make_request

LIGHTNING = "chain_lightning"      # a real SS12 lightning spell
NON_LIGHTNING = "berserking_blade" # a real SS12 attack skill (no lightning)


def _val(stats, key):
    v = stats.get(key)
    return (v.get("value", v.get("total", 0)) if isinstance(v, dict) else (v or 0)) or 0


def _run(*, skill=LIGHTNING, picks=None, conds=None, uptime_mode="max", slot_levels=(5, 5, 5, 5),
         trait_id="lightning_shadow", **extra):
    req = make_request(skill, 14, trait_id=trait_id, trait_slot_levels=list(slot_levels),
                       advanced_trait_selections=list(picks or []), uptime_mode=uptime_mode,
                       extra_conditions=conds or {}, **extra)
    return engine_stats(EngineStatsRequest(**req))


def _numbed_taken(resp):
    return float(_val(resp["stats"], "numbed_lightning_taken"))


def _additional(resp):
    return float(_val(resp["stats"], "numbed_effect_additional"))


class TestRealMode:
    def test_charging_plus_source_computes_numbed(self):
        r = _run(uptime_mode="real", picks=["Dazzling Lightning", "Charging Equation"],
                 conds={"electrify_stacks": 3, "enemy_numbed": True})
        assert _numbed_taken(r) > 0           # Feline Figure sustained Numbed
        assert _additional(r) > 0.68          # base 0.68 + Charging/Wild on top

    def test_no_charging_no_sustain(self):
        r = _run(uptime_mode="real", picks=["Dazzling Lightning"],
                 conds={"electrify_stacks": 3, "enemy_numbed": True})
        assert _numbed_taken(r) == 0.0        # FF is once-per-enemy → no single-target sustain

    def test_no_external_source_no_sustain(self):
        r = _run(uptime_mode="real", picks=["Charging Equation"],
                 conds={"electrify_stacks": 3})   # no enemy_numbed (no inflict-on-lightning source)
        assert _numbed_taken(r) == 0.0

    def test_electroplated_motif_doubles_duration_raises_numbed(self):
        base = _run(uptime_mode="real", picks=["Dazzling Lightning", "Charging Equation"],
                    conds={"electrify_stacks": 2, "enemy_numbed": True})
        motif = _run(uptime_mode="real", picks=["Electroplated Motif", "Charging Equation"],
                     conds={"electrify_stacks": 2, "enemy_numbed": True})
        # Doubled FF-Numbed duration → more sustained Numbed (until both hit the 10 cap).
        assert _numbed_taken(motif) >= _numbed_taken(base)


class TestStatLines:
    def test_dazzling_raises_electrify_cap_and_adds_ms(self):
        r = _run(picks=["Dazzling Lightning"], conds={"electrify_stacks": 3}, slot_levels=(5, 5, 5, 5))
        assert r["condition_maximums"]["electrify_stacks"] == pytest.approx(7.0)   # 3 base + 4 (tier 5)
        assert float(_val(r["stats"], "movement_speed")) > 0

    def test_wild_lightning_caps_additional(self):
        # Huge Movement Speed → Wild Lightning's MS-scaled additional Numbed Effect clamps at its cap.
        r = _run(uptime_mode="real", picks=["Charging Equation"],
                 conds={"electrify_stacks": 3, "enemy_numbed": True, "movement_speed_inc": 50.0})
        # Total additional includes base 0.68 + Charging + Wild(capped 1.20 at tier5) → finite, not runaway.
        assert _additional(r) < 0.68 + 0.5 + 1.20 + 0.01

    def test_status_surface_covers_every_picked_line(self):
        r = _run(picks=["Dazzling Lightning", "Charging Equation"], conds={"electrify_stacks": 3})
        statuses = r["trait_mod_statuses"]
        assert len(statuses) >= 4
        sources = {s["source"] for s in statuses}
        assert {"Lightning Shadow", "Dazzling Lightning", "Wild Lightning", "Charging Equation"} <= sources
        assert all("status" in s for s in statuses)


class TestModeSafetyAndTrap:
    def test_max_mode_uses_user_numbed(self):
        # Default max mode: Numbed stays the user-set value (not computed).
        r = _run(uptime_mode="max", picks=["Charging Equation"],
                 conds={"electrify_stacks": 3, "enemy_numbed": True, "numbed_stacks": 4})
        # 0.05 * 4 stacks * (1 + additional) — additional > 0 so taken > 0.20.
        assert _numbed_taken(r) > 0.20

    def test_inflicting_skill_in_non_main_slot(self):
        # Main skill is NON-lightning (slot 1); the lightning inflictor is a SECONDARY slot. Numbed must be
        # driven off the lightning slot's rate — proving we resolve by who-hits, not main-slot-by-index.
        r = _run(skill=NON_LIGHTNING, uptime_mode="real", picks=["Charging Equation"],
                 conds={"electrify_stacks": 3, "enemy_numbed": True},
                 skills=[{"slot": 1, "skill_id": NON_LIGHTNING, "level": 14},
                         {"slot": 2, "skill_id": LIGHTNING, "level": 14}],
                 main_skill={"skill_id": NON_LIGHTNING, "level": 14})
        assert _numbed_taken(r) > 0.0         # found the lightning skill in slot 2

    def test_non_ls_build_real_mode_equals_max(self):
        # A build with NO bespoke trait is byte-identical in real vs max mode (nothing migrated to real).
        common = dict(picks=[], conds={"numbed_stacks": 5}, trait_id=None)
        a = _run(uptime_mode="max", **common)["stats"]
        b = _run(uptime_mode="real", **common)["stats"]
        assert _val(a, "numbed_lightning_taken") == _val(b, "numbed_lightning_taken")

    def test_no_trait_is_unchanged(self):
        r = _run(trait_id=None, conds={"numbed_stacks": 10})
        # numbed still works off the user value; no trait additional pool.
        assert _numbed_taken(r) > 0
        assert _additional(r) == 0
        assert r["trait_mod_statuses"] == []
