"""build_code.py — compact, shareable build codes.

Pipeline:  build dict  →  strip derived fields  →  compact JSON  →  zlib  →  base64url
Prefix: "tli1_"  (scheme id + wire-format version; bump only if pipeline changes)
"""
from __future__ import annotations

import base64
import json
import zlib

CODE_PREFIX = "tli1"
SCHEMA_VERSION = 1
MAX_DECOMPRESSED_BYTES = 1_000_000  # zip-bomb guard


class BuildCodeError(ValueError):
    """Raised when a build code is malformed, corrupt, or unrecognized."""


# ── Encode ────────────────────────────────────────────────────────────────────

def encode_build(build: dict) -> str:
    """Serialize a build object into a compact shareable code string."""
    payload = _strip_for_share(build)
    payload["v"] = SCHEMA_VERSION
    raw = json.dumps(
        payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    ).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    b64 = base64.urlsafe_b64encode(compressed).decode("ascii").rstrip("=")
    return f"{CODE_PREFIX}_{b64}"


def _strip_for_share(build: dict) -> dict:
    """Return a copy of the build with the id and derived gear fields removed."""
    result = {k: v for k, v in build.items() if k != "id"}
    if "gear" in result:
        result["gear"] = [_strip_gear_item(item) for item in result["gear"]]
    return result


def _strip_gear_item(item: dict) -> dict:
    """Keep only source-of-truth fields for gear items."""
    is_crafted = bool(item.get("is_crafted", False))
    stripped: dict = {
        "item_id": item.get("item_id"),
        "name": item.get("name"),
        "slot": item.get("slot"),
        "base_type": item.get("base_type") or None,
        "is_crafted": is_crafted,
        "customizations": item.get("customizations") or [],
    }
    if is_crafted:
        stripped["affixes"] = item.get("affixes") or []
        if item.get("implicit_count"):
            stripped["implicit_count"] = item["implicit_count"]
    # Drop None / empty list values to keep payload lean
    return {k: v for k, v in stripped.items() if v is not None and v != []}


# ── Decode ────────────────────────────────────────────────────────────────────

def decode_build(code: str, legendary_gear_items: list[dict]) -> dict:
    """Parse a shareable code, rehydrate legendary gear, return a full build dict.

    legendary_gear_items — the full item list from _legendary_gear.json for the
    active season, used to rehydrate stripped gear entries.
    """
    build = _decompress_and_parse(code)

    # Build a quick lookup by item_id for rehydration
    gear_by_id: dict[str, dict] = {
        item["item_id"]: item
        for item in legendary_gear_items
        if isinstance(item, dict) and "item_id" in item
    }

    if "gear" in build and isinstance(build["gear"], list):
        build["gear"] = [
            _rehydrate_gear_item(g, gear_by_id)
            for g in build["gear"]
            if isinstance(g, dict)
        ]

    # Remove the schema version marker before returning to the frontend
    build.pop("v", None)
    return build


def _rehydrate_gear_item(item: dict, gear_by_id: dict[str, dict]) -> dict:
    """Rehydrate a legendary item from game data; pass crafted items through."""
    if item.get("is_crafted"):
        return item

    item_id = item.get("item_id")
    full = gear_by_id.get(item_id) if item_id else None
    if full is None:
        # Unknown item (different game version) — return as-is so the build still loads
        return item

    # Merge: take the full item definition, then override with user choices from the code
    rehydrated = dict(full)
    rehydrated["slot"] = item.get("slot", full.get("slot"))
    rehydrated["customizations"] = item.get("customizations", [])
    if item.get("base_type"):
        rehydrated["base_type"] = item["base_type"]
    return rehydrated


def _decompress_and_parse(code: str) -> dict:
    code = code.strip()
    prefix, sep, b64 = code.partition("_")
    if sep != "_" or prefix != CODE_PREFIX:
        raise BuildCodeError(
            "Unrecognized build code — wrong prefix or version."
        )

    b64 += "=" * (-len(b64) % 4)
    try:
        compressed = base64.urlsafe_b64decode(b64.encode("ascii"))
    except Exception as exc:
        raise BuildCodeError("Build code is not valid base64.") from exc

    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(compressed, MAX_DECOMPRESSED_BYTES)
    except zlib.error as exc:
        raise BuildCodeError("Build code is corrupt.") from exc
    if decompressor.unconsumed_tail:
        raise BuildCodeError("Build code exceeds the maximum allowed size.")

    try:
        build = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise BuildCodeError("Build code does not contain valid JSON.") from exc

    if not isinstance(build, dict):
        raise BuildCodeError("Build code has an unexpected structure.")

    version = build.get("v")
    if version != SCHEMA_VERSION:
        build = _migrate(build, version)

    return build


# ── Migration ─────────────────────────────────────────────────────────────────

def _migrate(build: dict, from_version) -> dict:
    """Upgrade an older build object to the current schema version.

    Add one branch per schema version bump as the format evolves.
    """
    return build
