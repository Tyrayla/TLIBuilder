import dataclasses
import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from persistence import season_manager

router = APIRouter(prefix="/api/dev/conditions", tags=["dev-conditions"])

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_CONDITIONS_PATH = os.path.join(_DATA_ROOT, 'conditions.json')
_OVERRIDES_PATH = os.path.join(_DATA_ROOT, 'condition_phrase_overrides.json')

_SOURCE_FILES = {
    "legendary": "_legendary_gear",
    "grafts":    "_grafts",
    "craft":     "_craft_base_types",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_conditions() -> dict:
    if os.path.exists(_CONDITIONS_PATH):
        with open(_CONDITIONS_PATH) as f:
            return json.load(f)
    return {"conditions": [], "derived_keys": {}}


def _write_conditions(data: dict) -> None:
    with open(_CONDITIONS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    # reload in-memory module state
    from models import conditions as _cmod
    _cmod.reload()


def _read_overrides() -> dict:
    if os.path.exists(_OVERRIDES_PATH):
        with open(_OVERRIDES_PATH) as f:
            return json.load(f)
    return {}


def _write_overrides(data: dict) -> None:
    with open(_OVERRIDES_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # reload server module's phrase override cache
    import server as _srv
    _srv._load_phrase_overrides()


def _collect_condition_strings(active: str) -> dict[str, dict]:
    """Return {condition_text: {sources: [...], affix_count: N}} across all sources."""
    found: dict[str, dict] = {}

    def _walk(obj: Any, source_label: str) -> None:
        if isinstance(obj, dict):
            cond = obj.get("condition")
            if cond and isinstance(cond, str):
                if cond not in found:
                    found[cond] = {"sources": [], "affix_count": 0}
                entry = found[cond]
                if source_label not in entry["sources"]:
                    entry["sources"].append(source_label)
                entry["affix_count"] += 1
            for v in obj.values():
                _walk(v, source_label)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, source_label)

    loaders = {
        "legendary": season_manager.load_legendary_gear,
        "grafts":    season_manager.load_grafts,
        "craft":     season_manager.load_craft_base_types,
    }
    for label, loader in loaders.items():
        try:
            data = loader(active)
            if data:
                _walk(data, label)
        except Exception:
            pass

    return found


def _collect_items_for_condition(active: str, condition_text: str) -> list[dict]:
    """Return list of {source, item_name, affix_text} for all affixes matching condition_text."""
    results: list[dict] = []

    def _walk(obj: Any, source_label: str, item_name: str | None = None, affix_text: str | None = None) -> None:
        if isinstance(obj, dict):
            current_name: str | None = obj.get("name") or item_name
            # Carry the most recently seen text field down the tree so that when
            # condition is found on a deep stat dict, we still have the affix text
            # from its nearest ancestor that had one.
            current_text: str | None = obj.get("raw_text") or obj.get("text") or obj.get("display_text") or affix_text
            cond = obj.get("condition")
            if cond == condition_text:
                results.append({
                    "source": source_label,
                    "item_name": current_name or "Unknown",
                    "affix_text": current_text or "",
                })
            for v in obj.values():
                _walk(v, source_label, current_name, current_text)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, source_label, item_name, affix_text)

    loaders = {
        "legendary": season_manager.load_legendary_gear,
        "grafts":    season_manager.load_grafts,
        "craft":     season_manager.load_craft_base_types,
    }
    for label, loader in loaders.items():
        try:
            data = loader(active)
            if data:
                _walk(data, label)
        except Exception:
            pass

    return results


# ── Stat key lookup ───────────────────────────────────────────────────────────

@router.get("/stat-keys")
def get_stat_keys():
    from models.stat import Stat
    return {"keys": sorted(s.value for s in Stat)}


# ── Condition definition endpoints ────────────────────────────────────────────

@router.get("/definitions")
def get_definitions():
    return _read_conditions()


class ConditionIn(BaseModel):
    model_config = {"extra": "allow"}
    key: str
    label: str
    category: str
    value_type: str = "boolean"
    numeric_min: float = 0
    numeric_max: float | None = None
    min_base: float = 0
    min_from_stat: str | None = None
    max_base: float = 0
    max_from_stat: str | None = None
    unit: str = ""
    default_value: float = 0
    default_bool: bool = False
    visible: bool = True
    source: str = "user"


@router.post("/definitions")
def create_definition(body: ConditionIn):
    data = _read_conditions()
    if any(c["key"] == body.key for c in data["conditions"]):
        raise HTTPException(400, f"Condition key '{body.key}' already exists")
    data["conditions"].append(body.model_dump())
    _write_conditions(data)
    return {"ok": True}


@router.put("/definitions/{key}")
def update_definition(key: str, body: ConditionIn):
    data = _read_conditions()
    idx = next((i for i, c in enumerate(data["conditions"]) if c["key"] == key), None)
    if idx is None:
        raise HTTPException(404, f"Condition key '{key}' not found")
    new_key = body.key
    if new_key != key and any(c["key"] == new_key for c in data["conditions"]):
        raise HTTPException(400, f"Condition key '{new_key}' already exists")
    data["conditions"][idx] = body.model_dump()
    _write_conditions(data)
    # Migrate phrase overrides that referenced the old key
    if new_key != key:
        overrides = _read_overrides()
        changed = False
        for text, expr in list(overrides.items()):
            if isinstance(expr, str) and expr == key:
                overrides[text] = new_key; changed = True
            elif isinstance(expr, dict) and expr.get("key") == key:
                overrides[text] = {**expr, "key": new_key}; changed = True
        if changed:
            _write_overrides(overrides)
    return {"ok": True}


@router.delete("/definitions/{key}")
def delete_definition(key: str):
    data = _read_conditions()
    before = len(data["conditions"])
    data["conditions"] = [c for c in data["conditions"] if c["key"] != key]
    if len(data["conditions"]) == before:
        raise HTTPException(404, f"Condition key '{key}' not found")
    # Also remove from derived_keys if present
    data["derived_keys"] = {k: v for k, v in data.get("derived_keys", {}).items()
                            if k != key and v != key}
    _write_conditions(data)
    return {"ok": True}


@router.get("/derived-keys")
def get_derived_keys():
    return _read_conditions().get("derived_keys", {})


class DerivedKeyIn(BaseModel):
    bool_key: str
    stack_key: str


@router.post("/derived-keys")
def upsert_derived_key(body: DerivedKeyIn):
    data = _read_conditions()
    data.setdefault("derived_keys", {})[body.bool_key] = body.stack_key
    _write_conditions(data)
    return {"ok": True}


@router.delete("/derived-keys/{bool_key}")
def delete_derived_key(bool_key: str):
    data = _read_conditions()
    if bool_key not in data.get("derived_keys", {}):
        raise HTTPException(404, f"Derived key '{bool_key}' not found")
    del data["derived_keys"][bool_key]
    _write_conditions(data)
    return {"ok": True}


# ── Phrase override endpoints ─────────────────────────────────────────────────

@router.get("/sources")
def get_sources():
    from models.conditions import CONDITIONS_BY_KEY
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "entries": []}
    found = _collect_condition_strings(active)
    overrides = _read_overrides()
    entries = []
    for text, meta in sorted(found.items(), key=lambda x: (x[0] in overrides, x[0])):
        entries.append({
            "text": text,
            "sources": meta["sources"],
            "affix_count": meta["affix_count"],
            "expression": overrides.get(text),
            "mapped": text in overrides,
        })
    return {"season": active, "entries": entries}


@router.get("/source-items")
def get_source_items(text: str):
    active = season_manager.get_active_season()
    if not active:
        return {"items": []}
    return {"items": _collect_items_for_condition(active, text)}


@router.get("/overrides")
def get_overrides():
    return _read_overrides()


class OverrideIn(BaseModel):
    condition_text: str
    expression: Any  # dict (numeric threshold) or str (boolean key) or null


@router.post("/overrides")
def save_override(body: OverrideIn):
    overrides = _read_overrides()
    overrides[body.condition_text] = body.expression
    _write_overrides(overrides)
    return {"ok": True}


@router.delete("/overrides")
def delete_override(body: OverrideIn):
    overrides = _read_overrides()
    if body.condition_text not in overrides:
        raise HTTPException(404, "Override not found")
    del overrides[body.condition_text]
    _write_overrides(overrides)
    return {"ok": True}
