"""Regression: `lightning_shot_crossed_lightning_noble`'s progression `name` glues two independent
sentences with no separating punctuation:

    "+1 Chain Lightning Quantity for the supported skill for every (70-80) Dexterity, stacking up to
    6 time(s) When having at least 240 Dexterity, +(42-44) % additional damage for the supported skill"

Before the fix, `_split_condition` (engine/core_talent_resolver.py, called from
engine/support_resolver.py) matched the FIRST condition keyword in the combined string — "for every",
which sits INSIDE the Chain Lightning Quantity clause — so `cond_part` swallowed everything from there
to the end, including the entire second sentence's otherwise-independent "+42% additional damage" line.
When that combined `cond_part` failed to translate (untranslatable gate), the WHOLE specific-tier line
was zeroed, silently dropping both the Quantity grant's own text AND the unrelated damage sentence.

The fix (support_resolver._RUNON_SENTENCE_RE) splits the progression `name` into independent sentences
at the "stacking up to N time(s) When/While/If ..." glue point *before* any condition-splitting, so one
clause's gate can no longer swallow an unrelated adjacent clause.

Scope note: the damage clause's own gate ("when having at least 240 Dexterity") has no condition
translator today (out of scope here — see docs/BACKLOG.md §3) and "Chain Lightning Quantity" has no
stat-key mapping at all (also out of scope), so `resolve_support_contributions` still emits nothing
beyond the universal rank line for this support even after the fix — that's expected. What the fix
guarantees is that the run-on split can no longer cross-contaminate an UNRELATED, otherwise-resolvable
adjacent clause, which the synthetic fixture below demonstrates directly.
"""
import re
import pytest

from engine.support_resolver import resolve_support_contributions, _RUNON_SENTENCE_RE
from persistence import season_manager
from server import _get_skills_data, _translate_condition_expr

_SKILLS = _get_skills_data(season_manager.get_active_season())
_NOB = "noble_support_skill"


def _sup(item_id, **kw):
    return {"item_id": item_id, "skill_type": _NOB, "rank": kw.get("rank", 1),
            "level": kw.get("level", 1), "slot": 1}


class TestCrossedLightningRunOnSplit:
    def test_progression_name_is_split_into_two_sentences(self):
        line = _SKILLS["lightning_shot_crossed_lightning_noble"]["progression"][1]["values"]["name"]
        parts = _RUNON_SENTENCE_RE.split(line)
        assert len(parts) == 2
        assert "chain lightning quantity" in parts[0].lower()
        assert parts[0].rstrip().endswith("time(s)")
        assert parts[1].lower().startswith("when having at least 240 dexterity")

    def test_generic_resolver_emits_no_bogus_or_double_counted_damage(self):
        # rank 1 -> universal contributes 0%; neither sub-clause has a stat/condition mapping today (Chain
        # Lightning Quantity has no stat key; the Dexterity-threshold gate has no translator), so this must
        # stay empty — not silently emit a wrong/ungated amount from the old cross-contaminated split.
        c = resolve_support_contributions([_sup("lightning_shot_crossed_lightning_noble")], _SKILLS,
                                          _translate_condition_expr)
        assert c == []

    def test_universal_rank_line_still_resolves(self):
        c = resolve_support_contributions(
            [_sup("lightning_shot_crossed_lightning_noble", rank=5)], _SKILLS, _translate_condition_expr)
        uni = [x for x in c if x["stat_key"] == "dmg_additional" and "universal" in x["text"]]
        assert len(uni) == 1 and uni[0]["amount"] == pytest.approx(0.20)


# ── Synthetic fixture: proves the cross-contamination mechanism directly ──────────────────────────
def _synthetic_skills(name_line: str) -> dict:
    return {"synthetic_runon": {
        "item_id": "synthetic_runon", "name": "Synthetic Run-On", "skill_type": _NOB,
        "description_lines": ["Supports X. +20 % additional damage for the supported skill"],
        "progression": [{"level": 1, "values": {"name": name_line}}],
    }}


def _dex_cond(text: str):
    m = re.search(r"when having at least (\d+)\s*dexterity", text, re.I)
    return {"key": "dexterity", "op": ">=", "value": float(m.group(1))} if m else None


class TestRunOnCrossContaminationFixture:
    def test_glued_gate_no_longer_swallows_the_next_sentence(self):
        # Sentence 1 has its own untranslatable "for every ... stacking" gate glued (no punctuation) to
        # sentence 2, which has ITS OWN translatable gate. Pre-fix, `_split_condition` over the combined
        # string would split at "for every" (inside sentence 1) and hand the ENTIRE remainder — including
        # sentence 2's stat text — to `translate_cond` as one blob, which fails to match the compound
        # condition text and drops sentence 2's damage entirely. Post-fix, each sentence is condition-split
        # independently, so sentence 2's own gate resolves correctly to its own dmg_additional contribution.
        glued = ("+1 Widget Quantity for the supported skill for every (70-80) Dexterity, stacking up to "
                 "6 time(s) When having at least 240 Dexterity, +(42-44) % additional damage for the supported skill")
        skills = _synthetic_skills(glued)
        c = resolve_support_contributions([_sup("synthetic_runon", rank=1)], skills, _dex_cond)
        specific = [x for x in c if x["stat_key"] == "dmg_additional" and "specific" in x["text"]]
        assert len(specific) == 1
        assert specific[0]["amount"] == pytest.approx(0.43)
        assert specific[0]["condition"] == {"key": "dexterity", "op": ">=", "value": 240.0}

    def test_split_matches_only_the_documented_glue_point(self):
        # Sanity: the split regex must not fire on ordinary "for every"/"when" phrasing that ISN'T glued to
        # a "time(s)" clause (it should require the exact "time(s) When/While/If" boundary).
        assert _RUNON_SENTENCE_RE.split("+20 % additional damage for the supported skill") == \
            ["+20 % additional damage for the supported skill"]
        assert _RUNON_SENTENCE_RE.split("When having at least 240 Dexterity, +20% additional damage") == \
            ["When having at least 240 Dexterity, +20% additional damage"]
