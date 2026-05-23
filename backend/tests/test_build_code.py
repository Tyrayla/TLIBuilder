"""Round-trip and error-path tests for build_code.py."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import build_code
from build_code import BuildCodeError, encode_build, decode_build


# ── Fixtures ──────────────────────────────────────────────────────────────────

LEGENDARY_ITEM = {
    "item_id": "shield_of_judgment",
    "name": "Shield of Judgment",
    "required_level": 60,
    "base_type": "INT Shield",
    "affixes": [
        {"raw_text": "+200 Max Life", "expression": "+200 Max Life", "affix_kind": "numeric",
         "numeric_values": [{"kind": "fixed", "value": 200}], "stat_key": "max_life_flat", "unit": ""},
    ],
    "is_crafted": False,
    "customizations": [],
    "slot": "weapon2",
}

CRAFTED_ITEM = {
    "item_id": "int_helmet",
    "name": "INT Helmet (Crafted)",
    "required_level": 0,
    "base_type": "INT Helmet",
    "affixes": [
        {"raw_text": "+50 Energy Shield", "expression": "+50 Energy Shield", "affix_kind": "numeric",
         "numeric_values": [{"kind": "fixed", "value": 50}], "stat_key": None, "unit": ""},
    ],
    "is_crafted": True,
    "customizations": [{"affix_index": 0, "chosen_values": {"0": 50}, "chosen_placeholder_key": None}],
    "slot": "helmet",
    "implicit_count": 1,
}

SAMPLE_BUILD = {
    "id": "abc12345",
    "name": "Test Build",
    "characterLevel": 80,
    "hasPrism": False,
    "slots": [
        {"treeName": "Goddess of Hunting",
         "nodeStates": {"goddess_of_hunting_c0_r2": 3},
         "coreTalentSelections": {"0": "goddess_of_hunting_impermanence"}},
        None, None, None,
    ],
    "slates": [],
    "conditions": ["holding_shield"],
    "conditionValues": {"tenacity_active": 5},
    "gear": [LEGENDARY_ITEM, CRAFTED_ITEM],
    "skills": [],
    "traitId": None,
    "traitSlotLevels": [1, 1, 1, 1],
    "advancedTraitSelections": [],
}

GEAR_CATALOG = [LEGENDARY_ITEM]


# ── Round-trip tests ──────────────────────────────────────────────────────────

def test_round_trip_drops_id():
    code = encode_build(SAMPLE_BUILD)
    result = decode_build(code, GEAR_CATALOG)
    assert "id" not in result

def test_round_trip_preserves_name():
    code = encode_build(SAMPLE_BUILD)
    result = decode_build(code, GEAR_CATALOG)
    assert result["name"] == "Test Build"

def test_round_trip_preserves_slots():
    code = encode_build(SAMPLE_BUILD)
    result = decode_build(code, GEAR_CATALOG)
    assert result["slots"][0]["treeName"] == "Goddess of Hunting"
    assert result["slots"][0]["nodeStates"]["goddess_of_hunting_c0_r2"] == 3

def test_round_trip_preserves_conditions():
    code = encode_build(SAMPLE_BUILD)
    result = decode_build(code, GEAR_CATALOG)
    assert "holding_shield" in result["conditions"]
    assert result["conditionValues"]["tenacity_active"] == 5

def test_round_trip_rehydrates_legendary_gear():
    code = encode_build(SAMPLE_BUILD)
    result = decode_build(code, GEAR_CATALOG)
    legendary = next(g for g in result["gear"] if not g.get("is_crafted"))
    # Rehydrated from catalog — should have affixes back
    assert "affixes" in legendary
    assert len(legendary["affixes"]) == 1
    # Slot from code is preserved
    assert legendary["slot"] == "weapon2"

def test_round_trip_preserves_crafted_gear():
    code = encode_build(SAMPLE_BUILD)
    result = decode_build(code, GEAR_CATALOG)
    crafted = next(g for g in result["gear"] if g.get("is_crafted"))
    assert crafted["affixes"][0]["raw_text"] == "+50 Energy Shield"
    assert crafted["customizations"][0]["chosen_values"]["0"] == 50

def test_legendary_gear_strips_affixes_in_code():
    """The encoded code should not contain the full affix array for legendary items."""
    code = encode_build(SAMPLE_BUILD)
    # The affix text should not appear in the raw code (it's stripped before encoding)
    import base64, zlib
    b64 = code.split("_", 1)[1]
    b64 += "=" * (-len(b64) % 4)
    raw = zlib.decompress(base64.urlsafe_b64decode(b64)).decode()
    # "raw_text" for legendary affix should be absent in the stripped payload
    import json
    payload = json.loads(raw)
    legendary_in_code = next(g for g in payload["gear"] if not g.get("is_crafted"))
    assert "affixes" not in legendary_in_code

def test_idempotency():
    code1 = encode_build(SAMPLE_BUILD)
    decoded = decode_build(code1, GEAR_CATALOG)
    code2 = encode_build(decoded)
    # Both codes decompress to the same keys (decoded has no id, so encode is stable)
    assert decode_build(code1, GEAR_CATALOG)["name"] == decode_build(code2, GEAR_CATALOG)["name"]

def test_code_prefix():
    code = encode_build(SAMPLE_BUILD)
    assert code.startswith("tli1_")

def test_schema_version_in_payload():
    code = encode_build(SAMPLE_BUILD)
    import base64, zlib, json
    b64 = code.split("_", 1)[1]
    b64 += "=" * (-len(b64) % 4)
    payload = json.loads(zlib.decompress(base64.urlsafe_b64decode(b64)))
    assert payload["v"] == build_code.SCHEMA_VERSION


# ── Unknown item fallback ─────────────────────────────────────────────────────

def test_unknown_item_id_does_not_crash():
    build = {**SAMPLE_BUILD, "gear": [{"item_id": "unknown_item_xyz", "name": "???", "slot": "helmet",
                                        "is_crafted": False, "customizations": []}]}
    code = encode_build(build)
    result = decode_build(code, GEAR_CATALOG)
    assert result["gear"][0]["item_id"] == "unknown_item_xyz"


# ── Error paths ───────────────────────────────────────────────────────────────

def test_empty_string_raises():
    with pytest.raises(BuildCodeError):
        decode_build("", [])

def test_wrong_prefix_raises():
    with pytest.raises(BuildCodeError):
        decode_build("pob_AAAA", [])

def test_no_underscore_raises():
    with pytest.raises(BuildCodeError):
        decode_build("tli1AAAA", [])

def test_bad_base64_raises():
    with pytest.raises(BuildCodeError):
        decode_build("tli1_!!!notbase64!!!", [])

def test_truncated_data_raises():
    code = encode_build(SAMPLE_BUILD)
    truncated = code[:20]
    with pytest.raises(BuildCodeError):
        decode_build(truncated, [])

def test_oversized_payload_raises():
    """A real zip bomb should be caught."""
    import zlib, base64
    # ~1.1 MB of zeros (over the 1 MB cap)
    raw = b"\x00" * 1_100_000
    compressed = zlib.compress(raw, level=9)
    b64 = base64.urlsafe_b64encode(compressed).decode().rstrip("=")
    code = f"tli1_{b64}"
    with pytest.raises(BuildCodeError):
        decode_build(code, [])
