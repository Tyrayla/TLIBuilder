"""
Tests: per-build modifier consumption tracing (the "inert modifier" badge backend).

Covers the two pieces that drive the feature:
  1. BuildSource.total() consumption recorder + its scoping (the offense/defense/derive read
     paths), incl. the headline skill-sensitivity behavior (a damage mod's stat is consumed under
     a modeled skill and not under an unmodeled one).
  2. aggregator.resolve_effect_stat_keys — the spirit/memory text -> stat key mapping the
     /api/map-modifiers endpoint reuses (so the mapping can't drift from the engine).

Full compute()-level + HTTP integration of these is deferred with the other season-fixture server
tests (see docs/TEST_BACKLOG.md); the functions exercised here are exactly the ones compute() calls
with the same recorder scoping.
"""
import pytest
from engine.models import BuildSource
from engine.offense import calculate_offense
from engine.defense import calculate_defense
from engine.derive import derive_stats
from engine.aggregator import resolve_effect_stat_keys
from engine.skill_resolver import ResolvedSkill, SkillHitForm
from models.stat_meta import STAT_META


def _source(**stats) -> BuildSource:
    s = BuildSource()
    for k, v in stats.items():
        s.add(k, v)
    return s


def _hit(eff=1.0, form_type="additive", proc=None) -> SkillHitForm:
    return SkillHitForm(name="Hit", effectiveness_pct=eff, form_type=form_type, proc_stat_key=proc)


def _skill(tags=("attack",), max_level=1, supported=True) -> ResolvedSkill:
    return ResolvedSkill(
        skill_id="t", name="T", tags=list(tags), max_level=max_level,
        hit_forms_by_level={1: [_hit()]}, supported=supported, base_steep_strike_chance=0.0,
    )


class TestRecorder:
    def test_off_by_default(self):
        s = _source(crit_damage=0.5)
        assert s.total("crit_damage") == 0.5
        assert s.consumed_stats == set()

    def test_records_only_while_recording(self):
        s = _source(crit_damage=0.5)
        s._recording = True
        s.total("crit_damage")
        s._recording = False
        s.total("max_life")  # read while NOT recording
        assert "crit_damage" in s.consumed_stats
        assert "max_life" not in s.consumed_stats

    def test_missing_stat_still_recorded(self):
        # A read of an absent stat returns 0 but is still "consumed" (the pipeline asked for it).
        s = BuildSource()
        s._recording = True
        assert s.total("fire_dmg_inc") == 0.0
        assert "fire_dmg_inc" in s.consumed_stats


class TestSkillSensitivity:
    """The headline behavior: the same modifier's stat is consumed by a modeled skill and not by
    an unmodeled one — so its badge flips working -> unused on a skill change."""

    def _consumed_via_offense(self, skill) -> set[str]:
        s = _source(crit_damage=0.4)
        s._recording = True
        calculate_offense(s, skill, 1)
        s._recording = False
        return set(s.consumed_stats)

    def test_modeled_skill_consumes_offense_stat(self):
        assert "crit_damage" in self._consumed_via_offense(_skill(supported=True))

    def test_unmodeled_skill_consumes_nothing(self):
        # calculate_offense returns early for unsupported skills, before any total() read.
        assert self._consumed_via_offense(_skill(supported=False)) == set()


class TestDefenseAndDerive:
    def test_defense_consumes_its_stats(self):
        s = _source(max_life=1000.0)
        s._recording = True
        calculate_defense(s)
        s._recording = False
        # max_life is read by the defense pass regardless of skill -> defensive mods stay "working".
        assert "max_life" in s.consumed_stats

    def test_derive_consumes_component_mods(self):
        # A "+x% increased Life" mod maps to max_life_inc, which derive_stats reads.
        s = _source(max_life_flat=100.0, max_life_inc=0.5)
        s._recording = True
        derive_stats(s)
        s._recording = False
        assert "max_life_inc" in s.consumed_stats
        assert "max_life_flat" in s.consumed_stats


class TestEffectMapping:
    """resolve_effect_stat_keys mirrors the engine's spirit/memory matching (drift guard by reuse)."""

    def test_unrecognized_returns_empty(self):
        assert resolve_effect_stat_keys("+5% Nonexistent Flibberflab Stat", is_memory=False) == []
        assert resolve_effect_stat_keys("", is_memory=True) == []

    def test_single_percent_stat_roundtrips(self):
        # Build an effect string from a real %-unit stat's display name; it must map to a key.
        pick = next(((e, m) for e, m in STAT_META.items() if m.unit == "%"), None)
        assert pick is not None
        _enum, meta = pick
        keys = resolve_effect_stat_keys(f"+10% {meta.display_name}", is_memory=False)
        assert keys, f"expected '{meta.display_name}' to map to a stat key"

    def test_memory_multi_stat_phrase(self):
        keys = resolve_effect_stat_keys("+12% Attack and Cast Speed", is_memory=True)
        assert set(keys) == {"attack_speed_inc", "cast_speed_inc"}

    def test_spirit_does_not_split_dual(self):
        # The dual-split + multi/alias lookups are memory-only; a spirit sees one phrase.
        spirit = resolve_effect_stat_keys("+12% Attack and Cast Speed", is_memory=False)
        assert spirit == []  # "attack and cast speed" isn't a single-stat display name
