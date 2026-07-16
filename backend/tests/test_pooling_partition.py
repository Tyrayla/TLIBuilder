"""(b) No-regression gate for the ADDITIONAL-damage pooling PARTITION.

Why this exists
---------------
Add-vs-multiply for additional damage is keyed on `(stat_key, affix_identity(text))` — the normalized
WORDING of the affix (see engine/offense.py::_build_additional_factors, docs/ADDITIONAL_DAMAGE_POOLING.md).
Same identity → SUM into one factor; distinct identities → separate MULTIPLICATIVE factors. So the
*partition* of affixes into identity groups literally is the DPS behavior: merge two groups that should be
distinct and they wrongly add; split one group and it wrongly multiplies.

The planned modifier-identity work (mint our own persistent IDs, tlidb ids as fallback, English text
replaced by a language-independent key — see docs/MODIFIER_UUID_REVIEW.md) will REPLACE the pooling key.
This fixture freezes today's partition so that swap can be proven behavior-identical as a pure data diff,
with no engine/DPS run:

    induced_partition(new_key_fn, CORPUS) == induced_partition(affix_identity, CORPUS)

Match the partition on the current locale's English → grouping is unchanged → DPS is unchanged, by
construction. That is the no-regression gate, made mechanical and exhaustive (every real affix, not the
10 skill goldens — which don't even exercise the multiply path).

Scope: offensive additional-damage affixes (`additional … damage`, excluding "taken" which is defensive
and pools per-entry, not per-identity), pulled from the STRUCTURED affix-text fields that actually flow
through per-affix pooling at runtime — legendary-gear affix `raw_text` (explicits/implicits/random, both
variants) and talent recipe `text` lines. It deliberately does NOT string-walk whole catalogs: that drags
in skill-description tooltips (which are parsed for base damage, never pooled) and would churn the gate
with non-affix noise. `#`-template strings are skipped. Follow-up extensions (same mechanism, not yet
covered): speed-additional (`_speed_additional_product`, no "damage" token) and memory/spirit effect lines.

Re-capture deliberately (delete the fixture) ONLY when a data import legitimately changes the affix corpus;
the diff is the signal. A change you did NOT intend is a caught regression.
"""
from __future__ import annotations
import json
import os
import re
from collections import defaultdict
from typing import Callable, Iterable

from engine.affix_identity import affix_identity
from persistence import season_manager

_REPO_DATA = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "pooling_partition")

# Same filter as tools/audit_affix_identities.py, so this golden freezes exactly the audited set.
_ADD_RE = re.compile(r"additional\b.*\bdamage\b", re.I)
_HAS_NUM_RE = re.compile(r"\d")

_SEASON = season_manager.get_active_season() or "SS12"
_FIXTURE = os.path.join(_FIXTURE_DIR, f"additional_damage_{_SEASON}.json")


def _collect_field(obj, field: str) -> Iterable[str]:
    """Every `obj[field]` string, recursively — i.e. only the schema's designated affix-text fields,
    not arbitrary catalog prose."""
    if isinstance(obj, dict):
        v = obj.get(field)
        if isinstance(v, str):
            yield v
        for val in obj.values():
            yield from _collect_field(val, field)
    elif isinstance(obj, list):
        for val in obj:
            yield from _collect_field(val, field)


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def collect_additional_damage_texts(season: str) -> set[str]:
    """Distinct offensive additional-damage affix texts from the structured affix-text fields that flow
    through per-affix pooling: gear affix `raw_text` + talent recipe `text`.

    `#`-template strings are skipped (they don't flow as runtime affix text); "taken" is excluded
    (defensive, per-entry pooled). This is the corpus whose identity-partition == DPS behavior.
    """
    raw: list[str] = []
    gear = _load(os.path.join(_REPO_DATA, "seasons", season, "_legendary_gear.json"))
    if gear is not None:
        raw += _collect_field(gear, "raw_text")
    talents = _load(os.path.join(_REPO_DATA, "node_type_filter.json"))
    if talents is not None:
        raw += _collect_field(talents.get("recipes", {}), "text")

    texts: set[str] = set()
    for s in raw:
        if "#" in s:
            continue
        if _ADD_RE.search(s) and _HAS_NUM_RE.search(s) and "taken" not in s.lower():
            texts.add(s.strip())
    return texts


def induced_partition(key_fn: Callable[[str], str], texts: Iterable[str]) -> frozenset:
    """Label-agnostic equivalence classes a key function induces over `texts`.

    THE parity primitive for the modifier-identity migration: a candidate key (minted UUID, descriptor,
    …) is behavior-identical to today iff `induced_partition(candidate, CORPUS) == induced_partition(
    affix_identity, CORPUS)`. Compares GROUPINGS, not the group labels, so a new key scheme with totally
    different labels still passes as long as the same texts group together.
    """
    groups: dict[str, set[str]] = defaultdict(set)
    for t in texts:
        groups[key_fn(t)].add(t)
    return frozenset(frozenset(g) for g in groups.values())


def _current_partition_map(season: str) -> dict[str, list[str]]:
    """identity -> sorted texts (the readable, committed form)."""
    ident: dict[str, set[str]] = defaultdict(set)
    for t in collect_additional_damage_texts(season):
        ident[affix_identity(t)].add(t)
    return {k: sorted(v) for k, v in sorted(ident.items())}


# ── The golden ────────────────────────────────────────────────────────────────
def test_additional_damage_pooling_partition_is_frozen():
    """Current affix_identity partition == the committed fixture (captures on first run)."""
    current = _current_partition_map(_SEASON)
    if not os.path.exists(_FIXTURE):
        os.makedirs(_FIXTURE_DIR, exist_ok=True)
        payload = {
            "season": _SEASON,
            "note": "Frozen additional-damage identity partition. Gate for the modifier-identity "
                    "migration (docs/MODIFIER_UUID_REVIEW.md). Regenerate ONLY on an intended data change.",
            "identity_count": len(current),
            "affix_count": sum(len(v) for v in current.values()),
            "partition": current,
        }
        with open(_FIXTURE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        import pytest
        pytest.skip(f"captured pooling-partition fixture ({payload['identity_count']} identities, "
                    f"{payload['affix_count']} affixes) — re-run to compare")

    with open(_FIXTURE, encoding="utf-8") as f:
        frozen = json.load(f)["partition"]
    assert current == frozen, (
        "additional-damage pooling partition changed vs the frozen fixture. If this is an intended data "
        "import, delete the fixture to re-capture; otherwise a modifier's identity grouping shifted "
        "(add<->multiply DPS change)."
    )


def test_parity_primitive_reproduces_the_fixture_partition():
    """The parity harness the migration will use: affix_identity's induced partition over the fixture's
    corpus equals the fixture's grouping. Proves induced_partition() is a faithful gate before any new
    key exists to test with."""
    if not os.path.exists(_FIXTURE):
        import pytest
        pytest.skip("fixture not captured yet")
    with open(_FIXTURE, encoding="utf-8") as f:
        partition = json.load(f)["partition"]
    corpus = [t for texts in partition.values() for t in texts]
    frozen_grouping = frozenset(frozenset(texts) for texts in partition.values())
    assert induced_partition(affix_identity, corpus) == frozen_grouping


def test_identity_index_induces_the_same_partition():
    """THE index-equivalence gate for the runtime key switch: keying by
    `identity_index.get(affix_identity(t), affix_identity(t))` — exactly what engine/modifier_lines.
    pool_identity does with the source-attached index — induces byte-identically the partition
    affix_identity induces. Holds for index misses too (suffix-minted texts, custom rolls) by the
    same-fallback argument: same identity → both hit or both miss → same key either way."""
    from engine.identity_index import build_identity_index

    idx = build_identity_index(_SEASON)
    assert idx, "empty identity index — season data missing pooling_uuids?"
    corpus = collect_additional_damage_texts(_SEASON)
    assert induced_partition(lambda t: idx.get(affix_identity(t), affix_identity(t)), corpus) == \
        induced_partition(affix_identity, corpus)


# ── Intent anchors (data-independent — document the two invariants a new key MUST preserve) ─────────
def test_anchor_tier_and_format_variants_share_identity():
    """Same affix at different rolls/formatting → ONE identity → they ADD. (Gravel + Sun-shooter case.)"""
    base = affix_identity("+8 % additional Attack Damage")
    assert affix_identity("+(8–10) % additional Attack Damage") == base
    assert affix_identity("16% additional Attack Damage.") == base
    assert affix_identity("-5 % additional Attack Damage") == base  # sign stripped (pos/neg re-split downstream)


def test_anchor_scope_variants_stay_distinct():
    """Different scope wording → DISTINCT identities → they MULTIPLY. A key that collapses these regresses."""
    one = affix_identity("+5 % additional Attack Damage for One-Handed Weapons")
    two = affix_identity("+5 % additional Attack Damage for Two-Handed Weapons")
    plain = affix_identity("+5 % additional Attack Damage")
    supported = affix_identity("+5 % additional Attack Damage for the supported skill")
    assert len({one, two, plain, supported}) == 4
