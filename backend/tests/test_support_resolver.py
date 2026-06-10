"""
Tests: engine/support_resolver.py — attached supports → dmg_additional contributions, and the
multiplicative pooling (confirmed in-game: every support 'additional damage' line is its own ×(1+x)
factor; nothing sums). Phase 4a covers the additional-damage lines only.
"""
import os
import json
import pytest
from engine.support_resolver import resolve_support_contributions, _range_mid_fraction
from engine.models import BuildSource, SourceEntry
from engine.offense import _build_additional_factors, _additional_product


# ── Fixtures shaped like real _skills.json support entries ─────────────────────
def _support(item_id, skill_type, desc, progression):
    return {"item_id": item_id, "name": item_id, "skill_type": skill_type,
            "description_lines": [desc], "progression": progression}


def _prog(*pairs):  # (level, name) → progression entries
    return [{"level": lvl, "values": {"name": name}} for lvl, name in pairs]


_WEB = _support(
    "web", "magnificent_support_skill",
    "Supports X. +20 % additional damage for the supported skill [chain stuff] "
    "+(16-18) % additional damage for the supported skill",
    _prog((2, "+(13-15) % additional damage for the supported skill"),
          (1, "+(16-18) % additional damage for the supported skill"),
          (0, "+(20-24) % additional damage for the supported skill")),
)
_MERGE = _support(
    "merge", "noble_support_skill",
    "Supports X. +20 % additional damage for the supported skill [merge stuff] "
    "(-14.0 to -12.0) % additional damage for the supported skill",
    _prog((2, "(-16.0 to -15.0) % additional damage for the supported skill"),
          (1, "(-14.0 to -12.0) % additional damage for the supported skill"),
          (0, "(-10.0 to -8.0) % additional damage for the supported skill")),
)
_AUG = _support(
    "aug", "magnificent_support_skill",
    "Supports X. +20 % additional damage for the supported skill",
    _prog((1, "+(5.5-5.9) % additional damage for every 1 Jump remaining of the supported skill (multiplies)")),
)
_SUMMON = _support(  # noble with NO universal additional-damage phrase (minion buff)
    "summon", "noble_support_skill",
    "Supports X. Increases the damage of summoned minions by a lot.",
    _prog((1, "+(10-12) % minion damage")),
)
_BY_ID = {s["item_id"]: s for s in (_WEB, _MERGE, _AUG, _SUMMON)}


def _amounts(contribs):
    return sorted(round(c["amount"], 4) for c in contribs)


class TestRangeParser:
    def test_positive(self):
        assert _range_mid_fraction("+(16-18) % additional…") == pytest.approx(0.17)

    def test_negative(self):
        assert _range_mid_fraction("(-14.0 to -12.0) % additional…") == pytest.approx(-0.13)

    def test_single_value(self):
        assert _range_mid_fraction("+20 %") == pytest.approx(0.20)


class TestResolve:
    def test_web_r5_t1(self):
        c = resolve_support_contributions(
            [{"item_id": "web", "skill_type": "magnificent_support_skill", "rank": 5, "level": 1}], _BY_ID)
        assert _amounts(c) == [0.17, 0.20]  # specific 0.17, universal 0.20

    def test_merge_r5_t1(self):
        c = resolve_support_contributions(
            [{"item_id": "merge", "skill_type": "noble_support_skill", "rank": 5, "level": 1}], _BY_ID)
        assert _amounts(c) == [-0.13, 0.20]  # negative specific stays its own factor

    def test_rank_table(self):
        def uni(rank):
            c = resolve_support_contributions(
                [{"item_id": "web", "skill_type": "magnificent_support_skill", "rank": rank, "level": 1}], _BY_ID)
            return [x for x in c if x["text"].endswith("universal")]
        assert uni(1) == []                                  # rank 1 = 0% → no universal contribution
        assert uni(3)[0]["amount"] == pytest.approx(0.08)
        assert uni(5)[0]["amount"] == pytest.approx(0.20)

    def test_tier_selection(self):
        def spec(tier):
            c = resolve_support_contributions(
                [{"item_id": "web", "skill_type": "magnificent_support_skill", "rank": 1, "level": tier}], _BY_ID)
            return c[0]["amount"]
        assert spec(0) == pytest.approx(0.22)   # mid of 20-24
        assert spec(1) == pytest.approx(0.17)   # mid of 16-18
        assert spec(2) == pytest.approx(0.14)   # mid of 13-15

    def test_multiplies_skipped(self):
        c = resolve_support_contributions(
            [{"item_id": "aug", "skill_type": "magnificent_support_skill", "rank": 5, "level": 1}], _BY_ID)
        assert _amounts(c) == [0.20]  # only the universal; (multiplies) line deferred to 4b

    def test_summon_has_no_universal(self):
        c = resolve_support_contributions(
            [{"item_id": "summon", "skill_type": "noble_support_skill", "rank": 5, "level": 1}], _BY_ID)
        assert all(not x["text"].endswith("universal") for x in c)

    def test_unknown_support_ignored(self):
        assert resolve_support_contributions([{"item_id": "nope", "rank": 5, "level": 1}], _BY_ID) == []


def _pool_product(contribs):
    src = BuildSource()
    for c in contribs:
        src.add_with_source(c["stat_key"], c["amount"], SourceEntry(
            stat=c["stat_key"], amount=c["amount"], source_type="support",
            label=c["label"], text=c["text"], points=1))
    return _additional_product(src, _build_additional_factors(src), lambda tags: True)


class TestMultiplicativePooling:
    def test_web_merge_multiply_to_1466(self):
        c = resolve_support_contributions([
            {"item_id": "web", "skill_type": "magnificent_support_skill", "rank": 5, "level": 1},
            {"item_id": "merge", "skill_type": "noble_support_skill", "rank": 5, "level": 1},
        ], _BY_ID)
        # 1.20 × 1.17 × 1.20 × 0.87 = 1.4658 (NOT the additive 1.366)
        assert _pool_product(c) == pytest.approx(1.20 * 1.17 * 1.20 * 0.87, abs=1e-4)

    def test_two_universals_multiply_not_add(self):
        # Two supports, each only its universal +20% (rank 5), tier with no extra positive: use aug
        # (universal only) twice via distinct ids.
        by_id = {"a": _support("a", "magnificent_support_skill",
                               "+20 % additional damage for the supported skill", []),
                 "b": _support("b", "noble_support_skill",
                               "+20 % additional damage for the supported skill", [])}
        c = resolve_support_contributions([
            {"item_id": "a", "skill_type": "magnificent_support_skill", "rank": 5, "level": 1},
            {"item_id": "b", "skill_type": "noble_support_skill", "rank": 5, "level": 1},
        ], by_id)
        assert _pool_product(c) == pytest.approx(1.44, abs=1e-6)   # 1.20×1.20, NOT 1.40


# ── Real-data guard: catch support-data drift (skips if season file absent) ────
_SEASON = os.path.join(os.path.dirname(__file__), "..", "..", "data", "seasons", "SS12", "_skills.json")


@pytest.mark.skipif(not os.path.exists(_SEASON), reason="season data not present")
def test_real_web_merge_pools_to_1466():
    data = json.load(open(_SEASON, encoding="utf-8"))
    def walk(n):
        if isinstance(n, dict):
            yield n
            for v in n.values(): yield from walk(v)
        elif isinstance(n, list):
            for v in n: yield from walk(v)
    by_id = {x["item_id"]: x for x in walk(data) if isinstance(x.get("item_id"), str)}
    c = resolve_support_contributions([
        {"item_id": "chain_lightning_web_of_lightning_magnificent",
         "skill_type": "magnificent_support_skill", "rank": 5, "level": 1},
        {"item_id": "chain_lightning_merge_noble",
         "skill_type": "noble_support_skill", "rank": 5, "level": 1},
    ], by_id)
    assert _pool_product(c) == pytest.approx(1.4658, abs=2e-3)
