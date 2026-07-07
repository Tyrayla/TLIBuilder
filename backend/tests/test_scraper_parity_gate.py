"""Cross-repo parity gate: the scraper's minted pooling_uuids induce OUR pooling partition.

The scraper (tlidb-scraper) mints `pooling_uuid = uuid5(NAMESPACE, canonical_template(text))`, where
`canonical_template` is a byte-for-byte copy of engine/affix_identity.py (the matched-pair rule: neither
side may change alone — see docs/MODIFIER_UUID_REVIEW.md). Its parity deliverable
(`output/parity/pooling_parity_SS12.json`) exports template/uuid/clause data for every affix text in its
scrape scope. This gate proves, on OUR corpus (test_pooling_partition.collect_additional_damage_texts),
that keying by the scraper's `pooling_uuid` induces the exact same partition as `affix_identity` — the
precondition for switching add-vs-multiply pooling to the minted uuid (provably DPS-neutral).

Join discipline: by TEMPLATE (`affix_identity(text)`), never by raw text — our imported texts differ from
scraped texts in value formatting (`+10%` vs `+10 %`), so a raw-text join misses ~25 of 297.

Skips (does not fail) when the scraper repo/export isn't present, so the suite stays green on machines
without the sibling checkout.
"""
from __future__ import annotations
import json
import os
import uuid

import pytest

from engine.affix_identity import affix_identity
from tests.test_pooling_partition import collect_additional_damage_texts, induced_partition

# Hardcoded forever, scraper-side and here (handoff §1).
NAMESPACE = uuid.UUID("4d8c3c25-940d-453e-be66-21a9d603aa0e")

_SEASON = "SS12"
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SCRAPER_DIR = os.environ.get("TLIDB_SCRAPER_DIR") or os.path.join(
    os.path.dirname(_REPO_ROOT), "tlidb-scraper")
_EXPORT = os.path.join(_SCRAPER_DIR, "output", "parity", f"pooling_parity_{_SEASON}.json")



def _load_export() -> dict:
    if not os.path.exists(_EXPORT):
        pytest.skip(f"scraper parity export not found: {_EXPORT} (set TLIDB_SCRAPER_DIR)")
    with open(_EXPORT, encoding="utf-8") as f:
        return json.load(f)


def test_export_is_internally_consistent():
    """Namespace matches, and every exported pooling_uuid equals its uuid5 recomputation over the
    template — i.e. the scraper really minted over OUR identity function, not an approximation."""
    export = _load_export()
    assert uuid.UUID(export["namespace"]) == NAMESPACE
    for e in export["entries"].values():
        assert str(uuid.uuid5(NAMESPACE, e["line_template"])) == e["line_pooling_uuid"], (
            f"export entry does not recompute: {e['line_template']!r}"
        )


def test_pooling_uuid_induces_our_partition():
    """THE gate (handoff §4): joining our corpus to the export by template, keying by pooling_uuid
    induces byte-identically the partition affix_identity induces. Green here = switching the engine's
    pooling key to pooling_uuid cannot change any add-vs-multiply grouping."""
    export = _load_export()
    by_template = {e["line_template"]: e["line_pooling_uuid"] for e in export["entries"].values()}

    corpus = collect_additional_damage_texts(_SEASON)
    assert corpus, "empty pooling corpus — season data missing?"

    missing = {affix_identity(t) for t in corpus} - set(by_template)
    assert not missing, (
        "corpus identities with no scraped counterpart — since the corpus is now built from "
        f"crawler-canonical wordings, any miss is a real problem: {sorted(missing)}"
    )

    joinable = [t for t in corpus if affix_identity(t) in by_template]
    assert induced_partition(lambda t: by_template[affix_identity(t)], joinable) == \
        induced_partition(affix_identity, joinable)


def test_clause_uuid_tuple_induces_same_partition():
    """Informational insurance (handoff §4 second check): the clause layer — keying each line by its
    TUPLE of clause uuids — induces the same partition too. Clauses are structure, not the pooling key
    (pool by line-level pooling_uuid, never per-clause), but tuple-level agreement proves the clause
    split never merges what the line identity keeps apart."""
    export = _load_export()
    clause_key = {e["line_template"]: "|".join(e["clause_uuids"]) for e in export["entries"].values()}

    corpus = collect_additional_damage_texts(_SEASON)
    joinable = [t for t in corpus if affix_identity(t) in clause_key]
    assert induced_partition(lambda t: clause_key[affix_identity(t)], joinable) == \
        induced_partition(affix_identity, joinable)
