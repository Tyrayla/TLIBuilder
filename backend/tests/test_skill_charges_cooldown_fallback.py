"""engine.skill_charges.skill_cooldown — the _COOLDOWN_RE regex fallback against description_lines /
detailed_description when no usable structured `cooldown` field exists (missing, None, or an unparseable
string). Per the payload-fidelity mandate, the primary case is a REAL skill from the active season's data
(not a hand-rolled fixture) whose structured `cooldown` is null but a cooldown is embedded in its
description text; the remaining cases document the general contract with minimal hand-built shapes.
"""
from __future__ import annotations

import json
import os

import pytest

import persistence.season_manager as season_manager
from engine.skill_charges import is_charge_ambiguous, skill_cooldown


def _skills_path(season: str) -> str:
    return os.path.join(os.path.dirname(season_manager.__file__), "..", "..", "data", "seasons", season,
                         "_skills.json")


def _load_season_skills() -> list[dict]:
    season = season_manager.get_active_season() or "SS12"
    with open(_skills_path(season), encoding="utf-8") as f:
        return json.load(f)["skills"]


def _find(skills: list[dict], name: str) -> dict:
    return next(sk for sk in skills if sk.get("name") == name)


class TestRealSkillData:
    def test_wind_rhythm_falls_back_to_description_text(self):
        """Activation Medium: Wind Rhythm has a structured `cooldown` field that is null in the real season
        data — the only way skill_cooldown can report anything for it is the _COOLDOWN_RE fallback against
        its description_lines ("... Cooldown: 0.6 s")."""
        skills = _load_season_skills()
        wind_rhythm = _find(skills, "Activation Medium: Wind Rhythm")
        assert wind_rhythm.get("cooldown") is None   # structured field present but unusable -> must fall back
        assert skill_cooldown(wind_rhythm) == pytest.approx(0.6)

    def test_bombard_fission_falls_back_across_split_description_lines(self):
        """Bombard: Fission (Noble) has its "Cooldown:" label and the "1.5 s" value split across separate
        description lines in the real data — _skill_text joins every line before the regex runs, so the
        fallback still finds it."""
        skills = _load_season_skills()
        fission = _find(skills, "Bombard: Fission (Noble)")
        assert fission.get("cooldown") is None
        assert skill_cooldown(fission) == pytest.approx(1.5)


class TestGeneralContract:
    def test_plain_description_lines_list(self):
        skill = {"description_lines": ["Deals damage to a single target.", "Cooldown: 8 s"]}
        assert skill_cooldown(skill) == pytest.approx(8.0)

    def test_detailed_description_string(self):
        skill = {"detailed_description": "This skill has a CD of 4.5s before it can be used again."}
        assert skill_cooldown(skill) == pytest.approx(4.5)

    def test_no_cooldown_mention_returns_none(self):
        skill = {"description_lines": ["A simple buff that lasts 5 s and grants a Movement Speed bonus."]}
        assert skill_cooldown(skill) is None

    def test_cd_word_boundary_does_not_false_positive(self):
        # \bcd\b requires "cd" as its own word — an unrelated word that merely contains the letters "cd"
        # embedded inside it (not a real English word, but exercises the boundary directly) must not match.
        skill = {"description_lines": ["Reduces incdent radius by 5 s."]}
        assert skill_cooldown(skill) is None

    def test_ambiguous_when_cooldown_mentioned_but_unparseable(self):
        skill = {"description_lines": ["Has a cooldown, shown only as an icon, not as text."]}
        assert skill_cooldown(skill) is None
        assert is_charge_ambiguous(skill) is True

    def test_clean_cooldown_less_skill_not_flagged_ambiguous(self):
        # A skill that never mentions cooldown/CD at all (as opposed to mentioning it but failing to parse)
        # is NOT ambiguous — a clean cooldown-less skill is a legitimate, common shape.
        clean_skill = {"description_lines": ["A passive buff with no timing restrictions."]}
        assert skill_cooldown(clean_skill) is None
        assert is_charge_ambiguous(clean_skill) is False
