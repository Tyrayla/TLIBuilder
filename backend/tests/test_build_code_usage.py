"""build_code.py USAGE (behavior only).

Covers the schema-migration/version-handling paths the existing test_build_code.py doesn't reach (the v1->v2
_migrate branch, missing/unknown/future schema versions), unknown top-level key round-tripping, the `gear`
shape edge cases (not-a-list / non-dict list entries), and a realistic LARGE build round-trip derived from a
REAL saved build on disk (payload-fidelity mandate) rather than a hand-rolled fixture.

NOTE: build_code.py's encode/decode/migrate pipeline is normally FROZEN (wire format, prefix, schema version,
compression). On 2026-07-08 the owner granted a narrowly-scoped, one-time exception (via .claude/settings.json)
authorizing exactly three defensive-hardening fixes as VALIDATION STRICTNESS ONLY (no wire-format change):
encode-side gear-shape guard, forward-schema-version rejection, and decode-side gear-shape guard. The tests
below were updated in step with that fix to assert the corrected (fail-loud) behavior instead of documenting
the old bugs. See .wolf/buglog.json (bug-build-code-encode-crashes-on-nonlist-gear) for the fix summary.
"""
from __future__ import annotations

import base64
import json
import zlib

import pytest

from build_code import BuildCodeError, MAX_DECOMPRESSED_BYTES, SCHEMA_VERSION, decode_build, encode_build


def _make_code(payload: dict) -> str:
    """Build a raw tli1_ code from an arbitrary payload dict, bypassing encode_build entirely — the same
    zlib+base64url recipe test_build_code.py's test_oversized_payload_raises uses. Lets us hand-construct
    payloads (e.g. an old v1 shape, or a shape encode_build itself can't currently produce/would crash on)
    and feed them straight to decode_build."""
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    b64 = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return f"tli1_{b64}"


# ── v1 -> v2 migration ─────────────────────────────────────────────────────────

def test_v1_migrate_merges_conditions_and_condition_values_into_condition_state():
    v1_payload = {
        "v": 1,
        "name": "Legacy Build",
        "slots": [None, None, None, None],
        "gear": [],
        "conditions": ["holding_shield", "dual_wielding"],
        "conditionValues": {"tenacity_active": 5, "numbed_stacks": 3.0},
    }
    code = _make_code(v1_payload)
    result = decode_build(code, [])

    assert result["conditionState"] == {
        "holding_shield": True,
        "dual_wielding": True,
        "tenacity_active": 5.0,
        "numbed_stacks": 3.0,
    }
    # old split representation is gone post-migration
    assert "conditions" not in result
    assert "conditionValues" not in result
    # schema marker is always stripped before the build reaches the frontend
    assert "v" not in result


def test_v1_migrate_handles_missing_conditions_and_condition_values():
    """A v1 build that never had any conditions set at all (both keys absent) migrates to an empty
    conditionState rather than raising."""
    v1_payload = {"v": 1, "name": "Bare Legacy Build", "slots": [None, None, None, None], "gear": []}
    code = _make_code(v1_payload)
    result = decode_build(code, [])
    assert result["conditionState"] == {}


# ── Missing / future schema version ────────────────────────────────────────────

def test_missing_v_key_raises():
    """No 'v' key at all -> build.get('v') is None -> _migrate(build, None) -> not isinstance(None, int) ->
    BuildCodeError. This is the CURRENT fail-closed behavior (an unversioned payload is rejected outright
    rather than silently assumed to be v1). Flagging to the lead: this seems like the safer default, but the
    task brief raised the question of whether a silent-default-to-v1 would be preferable — worth a decision
    from whoever owns build_code.py, since it's frozen here."""
    payload = {"name": "No Version At All", "slots": [None, None, None, None], "gear": []}
    code = _make_code(payload)
    with pytest.raises(BuildCodeError):
        decode_build(code, [])


def test_future_version_raises():
    """FIXED 2026-07-08: a version NEWER than SCHEMA_VERSION (e.g. a build saved by some future builder
    release) now raises BuildCodeError with a clear "update the app" message, instead of falling through
    every `if from_version < N` branch untouched and being silently accepted. Previously an older builder
    importing a future-schema code would silently accept fields it doesn't understand rather than erroring,
    which could produce a build that looks fine but is missing data the future schema depended on."""
    payload = {
        "v": SCHEMA_VERSION + 1,
        "name": "From The Future",
        "slots": [None, None, None, None],
        "gear": [],
        "someHypotheticalFutureField": {"nested": True, "list": [1, 2, 3]},
    }
    code = _make_code(payload)
    with pytest.raises(BuildCodeError):
        decode_build(code, [])


# ── Unknown/extra top-level keys round-trip ────────────────────────────────────

def test_unknown_top_level_keys_roundtrip_unchanged():
    build = {
        "name": "Has Extra Fields",
        "slots": [None, None, None, None],
        "gear": [],
        "someFutureFeature": {"a": 1, "b": [1, 2, 3]},
        "anotherUnknownKey": "just some string",
    }
    code = encode_build(build)
    result = decode_build(code, [])
    assert result["someFutureFeature"] == {"a": 1, "b": [1, 2, 3]}
    assert result["anotherUnknownKey"] == "just some string"


# ── `gear` shape edge cases ─────────────────────────────────────────────────────
#
# FIXED 2026-07-08: decode_build now raises BuildCodeError for any gear value that isn't a list, or a list
# containing a non-dict entry — matching encode_build's new symmetric guard (below). Previously decode_build
# silently left a non-list gear value as-is and silently dropped non-dict list entries, while encode_build
# had no equivalent guard at all and crashed with an opaque TypeError/AttributeError on the same shapes.

def test_decode_gear_null_raises():
    """A gear value of None is "present but not a list" — decode_build now fails loudly rather than passing
    it through untouched."""
    code = _make_code({"v": SCHEMA_VERSION, "name": "Null Gear", "gear": None})
    with pytest.raises(BuildCodeError):
        decode_build(code, [])


def test_decode_gear_dict_raises():
    code = _make_code({"v": SCHEMA_VERSION, "name": "Dict Gear", "gear": {"not": "a list"}})
    with pytest.raises(BuildCodeError):
        decode_build(code, [])


def test_decode_gear_list_with_non_dict_entry_raises():
    """A gear list with a stray non-dict entry (string/None/int) now raises instead of silently dropping
    it — a real data-corruption bug should surface to the user, not be hidden."""
    code = _make_code({
        "v": SCHEMA_VERSION, "name": "Mixed Gear List",
        "gear": [
            {"item_id": "int_helmet", "slot": "helmet", "is_crafted": True, "affixes": []},
            "a bogus string entry",
            None,
            42,
            {"item_id": "unknown_item_xyz", "slot": "ring"},
        ],
    })
    with pytest.raises(BuildCodeError):
        decode_build(code, [])


def test_encode_gear_none_encodes_fine():
    """FIXED 2026-07-08 — encode_build now treats gear=None the same as gear absent: no error, and the
    'gear' key is dropped from the payload entirely so it round-trips identically to an absent-gear build."""
    code = encode_build({"name": "Null Gear", "gear": None})
    result = decode_build(code, [])
    assert "gear" not in result
    assert result["name"] == "Null Gear"


def test_encode_gear_absent_encodes_fine():
    code = encode_build({"name": "No Gear Key At All"})
    result = decode_build(code, [])
    assert "gear" not in result


def test_encode_raises_on_dict_gear():
    """A non-list, non-None gear value (e.g. a dict) now raises BuildCodeError instead of crashing with an
    opaque AttributeError deep inside _strip_gear_item."""
    with pytest.raises(BuildCodeError):
        encode_build({"name": "Dict Gear", "gear": {"weird": 1}})


def test_encode_raises_on_non_dict_gear_list_entry():
    """A gear LIST that itself contains a non-dict entry now raises BuildCodeError instead of crashing —
    real gear is never silently dropped."""
    with pytest.raises(BuildCodeError):
        encode_build({"name": "Bogus Entry", "gear": [{"item_id": "a", "slot": "helmet"}, "bogus"]})


# ── Large realistic build round-trip (payload-fidelity mandate) ────────────────
#
# `data/builds/` is gitignored (only `.gitkeep` is tracked), so a fresh clone / clean CI runner has NO real
# builds on disk. Two tests below split the concern so the size-cap assertion ALWAYS runs on every machine:
#
#   1. test_large_synthetic_build_round_trips_under_size_cap — self-contained, no filesystem dependency,
#      always executes the size-cap round-trip against an in-test-constructed large build (full passive
#      trees across 4 tree slots, several crafted/vorax gear items with real affix shapes, skills with
#      multiple supports each). This is the one that must never be skipped.
#   2. test_large_real_build_round_trips_under_size_cap — payload-fidelity bonus coverage against an actual
#      saved build under data/builds/ when one exists locally; pytest.skip's (not fails) when the directory
#      is empty, since that's just an environment fact, not a code defect.


def _synthetic_tree_slot(tree_name: str, prefix: str, n_nodes: int) -> dict:
    """Build a passive-tree slot entry shaped like the real ones in data/builds/ (see e.g. the
    'God of Might' / 'Warrior' / 'Prophet' / 'Steel Vanguard' slots on real saved builds): a treeName,
    a nodeStates dict of `<prefix>_c<col>_r<row>` -> allocation rank, and a coreTalentSelections dict."""
    node_states = {
        f"{prefix}_c{col}_r{row}": ((col + row) % 3) + 1
        for col in range(n_nodes // 4)
        for row in range(4)
    }
    return {
        "treeName": tree_name,
        "nodeStates": node_states,
        "coreTalentSelections": {"0": f"{prefix}_core_choice_a", "1": f"{prefix}_core_choice_b"},
    }


def _synthetic_gear_item(item_id: str, slot: str, *, crafted: bool = False, vorax: bool = False) -> dict:
    """Build a gear item shaped like real saved-build gear entries (see e.g. 'tide_of_the_styx' on a real
    build): item_id/name/slot/base_type plus an affixes list with the real numeric_values/raw_text/
    modifier_id/expression/condition/affix_kind shape encode_build's _strip_gear_item round-trips for
    crafted/vorax items."""
    affixes = [
        {
            "raw_text": f"+{100 + i * 7} Gear Armor",
            "modifier_id": f"5142{i}710",
            "expression": "+# Gear Armor",
            "condition": None,
            "affix_kind": "numeric",
            "numeric_values": [{"kind": "fixed", "sign": "+", "value": 100 + i * 7, "raw": f"+{100 + i * 7}"}],
            "stat_key": "armor_gear_flat",
            "unit": "",
            "condition_expr": None,
        }
        for i in range(8)
    ]
    item = {
        "item_id": item_id,
        "name": item_id.replace("_", " ").title(),
        "slot": slot,
        "base_type": "Old King's Crown" if slot == "helmet" else None,
        "is_crafted": crafted,
        "is_vorax": vorax,
        "customizations": [{"affix_index": i, "chosen_values": {"0": 100 + i}} for i in range(3)],
        "implicit_count": 1,
    }
    if crafted or vorax:
        item["affixes"] = affixes
    return item


def _synthetic_support(item_id: str, index: int) -> dict:
    return {
        "support_index": index,
        "item_id": item_id,
        "name": item_id.replace("_", " ").title(),
        "skill_type": "support_skill",
        "level": 20,
        "skill_tags": ["Support", "Physical"],
        "description_lines": [
            "Supports Attack Skills or Spell Skills.",
            f"+{15 + index} % additional damage for the supported skill (Lv1:{15 + index}) (Lv21:{25 + index}) (Lv41:{35 + index})",
        ],
    }


def _synthetic_skill(slot: int, item_id: str) -> dict:
    return {
        "slot": slot,
        "item_id": item_id,
        "name": item_id.replace("_", " ").title(),
        "level": 20,
        "skill_tags": ["Attack", "Projectile", "Physical", "Ranged"],
        "description_lines": [
            f"Casts {item_id.replace('_', ' ')} and fires projectiles dealing weapon attack damage.",
            "After defeating enemies, gains a stacking damage buff.",
        ],
        "supports": [_synthetic_support(f"{item_id}_support_{i}", i) for i in range(5)],
    }


def _make_large_synthetic_build() -> dict:
    """A self-contained, in-test-constructed build with the same overall shape as a real large saved build
    (full-ish passive trees across all 4 tree slots, several crafted/vorax gear items with real affix
    shapes, and skills with multiple supports each) — no filesystem dependency, so it always exists."""
    tree_slots = [
        _synthetic_tree_slot("God of Might", "god_of_might", 40),
        _synthetic_tree_slot("Warrior", "warrior", 40),
        _synthetic_tree_slot("Prophet", "prophet", 40),
        _synthetic_tree_slot("Steel Vanguard", "steel_vanguard", 40),
    ]
    gear = [
        _synthetic_gear_item("tide_of_the_styx", "helmet"),
        _synthetic_gear_item("omni_elixir_notes", "belt"),
        _synthetic_gear_item("thunder_tempered_lightning_ring", "ring1", crafted=True),
        _synthetic_gear_item("thunder_tempered_lightning_ring", "ring2", crafted=True),
        _synthetic_gear_item("war_ender_s_boomstick", "weapon1", crafted=True),
        _synthetic_gear_item("future_warrior_s_kite_shield", "weapon2", crafted=True),
        _synthetic_gear_item("ranger_s_dirty_boots", "boots", crafted=True),
        _synthetic_gear_item("blade_dancer_s_fingers", "gloves"),
        _synthetic_gear_item("crimson_king", "chest", vorax=True),
        _synthetic_gear_item("heart_of_the_storm", "amulet"),
    ]
    skills = [_synthetic_skill(slot, f"synthetic_skill_{slot}") for slot in range(8)]
    return {
        "name": "Synthetic Large Build (size-cap coverage)",
        "slots": tree_slots,
        "slates": [],
        "slateInventory": [],
        "prisms": [],
        "prismInventory": [],
        "conditionState": {"holding_shield": True, "dual_wielding": True, "numbed_stacks": 3.0},
        "gear": gear,
        "skills": skills,
        "characterLevel": 100,
        "hasPrism": False,
        "traitId": "licorice_note",
        "traitLevel": 1,
        "traitSlotLevels": [1, 1, 5, 1],
        "advancedTraitSelections": ["Elixir of Immortality"],
        "traitSkillSupports": [],
        "heroMemories": [None, None, None],
        "pactSpirits": [None, None, None],
        "fates": {},
        "undetermined": [None, None, None],
        "notes": "Self-contained synthetic build for size-cap round-trip coverage.",
        "customMods": ["4 Charging Progress Per Second", "450% Elixir Effect", "15% Life Regain"],
    }


def test_large_synthetic_build_round_trips_under_size_cap():
    """Self-contained size-cap round-trip — no dependency on data/builds/, so this ALWAYS executes on every
    machine (fresh clone, clean CI runner, or a dev box with real builds on disk alike). Constructs a large
    build in-test (full passive trees, crafted/vorax gear with real affix shapes, skills with supports) and
    confirms the encoded code stays comfortably under the zip-bomb guard while preserving the build's shape."""
    build = _make_large_synthetic_build()

    code = encode_build(dict(build))
    assert code.startswith("tli1_")
    assert len(code) < MAX_DECOMPRESSED_BYTES // 2

    result = decode_build(code, [])
    assert "id" not in result
    assert result["name"] == build["name"]
    assert len(result["gear"]) == len(build["gear"])
    original_slots = sorted(g.get("slot") for g in (build.get("gear") or []))
    result_slots = sorted(g.get("slot") for g in (result.get("gear") or []))
    assert result_slots == original_slots
    assert len(result["slots"]) == len(build["slots"])
    assert [t.get("treeName") for t in result["slots"]] == [t.get("treeName") for t in build["slots"]]
    assert len(result["skills"]) == len(build["skills"])
    assert len(result["skills"][0]["supports"]) == len(build["skills"][0]["supports"])


def test_large_real_build_round_trips_under_size_cap():
    """Payload-fidelity bonus coverage: derived from a REAL saved build on disk (data/builds/) when one
    exists locally, rather than a hand-rolled fixture. Skips (does not fail) on a fresh clone / clean CI
    runner where data/builds/ is empty — that's an environment fact, not a code defect; the size-cap
    assertion itself is always exercised regardless, by
    test_large_synthetic_build_round_trips_under_size_cap above."""
    import persistence.builds_manager as builds_manager
    import persistence.season_manager as season_manager

    all_builds = builds_manager.load()
    if not all_builds:
        pytest.skip("no real saved builds under data/builds/ in this environment (expected on a fresh clone/CI)")
    build = max(all_builds, key=lambda b: len(json.dumps(b)))

    season = season_manager.get_active_season() or "SS12"
    gear_data = season_manager.load_legendary_gear(season)
    gear_items = gear_data.get("items", []) if gear_data else []

    code = encode_build(dict(build))
    assert code.startswith("tli1_")
    # Sanity: a real build compresses to a code far smaller than the decompressed-size cap.
    assert len(code) < MAX_DECOMPRESSED_BYTES // 2

    result = decode_build(code, gear_items)
    assert "id" not in result
    assert result["name"] == build["name"]
    assert len(result["gear"]) == len(build["gear"])
    original_slots = sorted(g.get("slot") for g in (build.get("gear") or []))
    result_slots = sorted(g.get("slot") for g in (result.get("gear") or []))
    assert result_slots == original_slots
