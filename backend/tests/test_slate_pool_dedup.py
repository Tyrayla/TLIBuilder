"""Tests: server._collect_pool core-talent dedup (SS13 go-live centerpiece fix).

Nether King's SS13 divinity-slate tree packs 92 core_talents behind only 4 raw `name`/`display_name_key`
values ("Micro/Medium/Legendary Medium/Ultimate Nether King Talent Node") — each of the 92 is a genuinely
different draftable option, distinguished only by its granted effect text. `_collect_pool` used to dedup
core talents on the bare raw_key alone, silently collapsing all 92 down to 4 (see .wolf/buglog.json
"nether-king-core-talent-name-dedup-collapse"). The fix dedups on (raw_key, tuple(effects)) instead, and
suffixes the pool entry `key` with "#2", "#3", ... whenever a raw_key repeats with DISTINCT effects, so every
draftable option survives with a unique key. A raw_key's first occurrence keeps the plain "tree:raw_key" key
form unchanged — the SS12-byte-identical guarantee for every pre-existing tree, where raw_key already
uniquely identified one talent.
"""
import json

from persistence import season_manager
from server import _collect_pool, _tree_name_to_slug


def _core_for(pool: dict, tree_name: str) -> list[dict]:
    """Isolate a single tree's core-pool entries — `_collect_pool` also appends unrelated "New God" talent
    entries (season_manager.load_new_god_talents) to the SAME `core` list, so a raw length check would be
    contaminated by however many new-god talents that season happens to carry."""
    return [c for c in pool["core"] if c["treeName"] == tree_name]


def test_nether_king_all_effect_distinct_core_talents_survive(monkeypatch):
    """The real SS13 Nether King tree: 92 core_talents built from only 4 raw name values, every one of the 92
    carrying a distinct effect text. All 92 must survive as pool entries with unique keys — not collapse to 4."""
    monkeypatch.setattr(season_manager, "get_active_season", lambda: "SS13")
    raw = json.load(open(season_manager._season_dir("SS13") + "/nether_king.json", encoding="utf-8"))
    raw_cts = raw.get("core_talents", [])
    expected_total = len(raw_cts)
    assert expected_total > 50   # sanity: this really is the ~92-entry tree, not a stub/placeholder fixture

    pool = _collect_pool(["Nether King"])
    core = _core_for(pool, "Nether King")
    assert len(core) == expected_total   # NOT collapsed to 4

    keys = [c["key"] for c in core]
    assert len(set(keys)) == len(keys)   # every entry individually addressable (no key collisions)

    # Spot-check the suffix scheme against the raw tree order: a raw_key's Nth occurrence (effects always
    # distinct here, confirmed above by expected_total == 92 surviving) gets "#N" for N > 1, plain for N == 1.
    raw_keys_in_order = [ct.get("display_name_key") or ct.get("name") for ct in raw_cts]
    counts: dict[str, int] = {}
    key_set = set(keys)
    for rk in raw_keys_in_order:
        counts[rk] = counts.get(rk, 0) + 1
        n = counts[rk]
        expected_key = f"Nether King:{rk}" if n == 1 else f"Nether King:{rk}#{n}"
        assert expected_key in key_set, f"missing expected key {expected_key!r}"
    # Only 4 distinct raw_keys in this tree, so at least one of them must repeat far past #2 to reach 92 total.
    assert max(counts.values()) > 10


def test_genuine_duplicate_core_talent_still_collapses(monkeypatch):
    """A TRUE duplicate — same raw_key AND same effects — still collapses to a single pool entry; the dedup
    fix must not over-preserve. A sibling that shares the raw_key but carries DIFFERENT effects survives
    separately under the "#2" suffix, proving the dedup key is genuinely (raw_key, effects) — neither
    raw_key alone (which would wrongly collapse the distinct sibling) nor effects alone."""
    monkeypatch.setattr(season_manager, "get_active_season", lambda: "SS13")
    synthetic_tree = {
        "nodes": [],
        "core_talents": [
            {"display_name_key": "dup_talent", "name": "Dup Talent", "effects": ["+5% additional damage"]},
            {"display_name_key": "dup_talent", "name": "Dup Talent", "effects": ["+5% additional damage"]},  # true dup
            {"display_name_key": "dup_talent", "name": "Dup Talent", "effects": ["+10% additional damage"]},  # distinct effects
        ],
    }

    def fake_load_season_tree(season, slug, raw=False):
        return synthetic_tree if slug == "synthetic_tree" else None

    monkeypatch.setattr(season_manager, "load_season_tree", fake_load_season_tree)

    pool = _collect_pool(["Synthetic Tree"])
    core = _core_for(pool, "Synthetic Tree")
    assert len(core) == 2   # the true dup collapsed to one; the effect-distinct sibling survived separately
    assert {c["key"] for c in core} == {"Synthetic Tree:dup_talent", "Synthetic Tree:dup_talent#2"}


def test_ss12_god_tree_keeps_plain_key_form_no_suffix(monkeypatch):
    """Every pre-existing tree — every raw_key unique per talent, e.g. SS12's 6-option God of Might — keeps
    the plain "tree:raw_key" key form untouched. The SS12-byte-identical guarantee: this dedup/suffix change
    is additive only for a repeating-raw_key tree like Nether King, never a behavior change for a normal tree."""
    monkeypatch.setattr(season_manager, "get_active_season", lambda: "SS12")
    raw = json.load(open(season_manager._season_dir("SS12") + "/god_of_might.json", encoding="utf-8"))
    raw_cts = raw.get("core_talents", [])
    raw_keys = [ct.get("display_name_key") or ct.get("name") for ct in raw_cts]
    assert len(set(raw_keys)) == len(raw_keys)   # sanity: genuinely all-unique raw_keys in this tree

    pool = _collect_pool(["God of Might"])
    core = _core_for(pool, "God of Might")
    assert len(core) == len(raw_cts)
    keys = {c["key"] for c in core}
    assert keys == {f"God of Might:{rk}" for rk in raw_keys}   # plain form only — never a "#2" suffix
    assert not any("#" in k for k in keys)
