import json
import os
from typing import Any, Optional
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import HTMLResponse

from persistence import season_manager

router = APIRouter(prefix="/api/dev/inspect", tags=["dev-inspect"])
_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inspect.html")


# ── Data adapters ─────────────────────────────────────────────────────────────

def _extract_standard(data: dict) -> tuple[list[dict], str]:
    return data.get("items", []), "name"


def _extract_craft_base_types(data: dict) -> tuple[list[dict], str]:
    result = []
    for slot in data.get("slots", []):
        slot_id = slot.get("item_id", "unknown")
        for base_item in slot.get("base_items", []):
            result.append({"_slot_id": slot_id, **base_item})
    return result, "name"


_LOADERS: dict[str, tuple] = {
    "_legendary_gear": (season_manager.load_legendary_gear, _extract_standard),
    "_skills": (season_manager.load_skills, _extract_standard),
    "_hero_traits": (season_manager.load_hero_traits, _extract_standard),
    "_pact_spirits": (season_manager.load_pact_spirits, _extract_standard),
    "_craft_base_types": (season_manager.load_craft_base_types, _extract_craft_base_types),
}


def _load_and_extract(season: str, file: str) -> tuple[list[dict], str]:
    if file in _LOADERS:
        loader_fn, extract_fn = _LOADERS[file]
        data = loader_fn(season)
    else:
        path = os.path.join(season_manager._season_dir(season), f"{file}.json")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"File not found: {file!r}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        extract_fn = _extract_standard
    if data is None:
        raise HTTPException(status_code=404, detail=f"File not found for season {season!r}")
    return extract_fn(data)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _active_season() -> str:
    s = season_manager.get_active_season()
    if not s:
        raise HTTPException(status_code=404, detail="No active season")
    return s


def _get_nested(obj: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def _path_present(obj: dict, path: str) -> bool:
    val = _get_nested(obj, path)
    return val is not None and val != {} and val != [] and val != ""


def _iter_mods(item: dict):
    for variant in item.get("variants", {}).values():
        for arr in (variant.get("implicits", []), variant.get("explicits", [])):
            yield from arr


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)
def inspect_page():
    with open(_HTML_PATH, encoding="utf-8") as f:
        return f.read()


@router.get("/files")
def list_files():
    season = _active_season()
    season_dir = season_manager._season_dir(season)
    files = sorted(
        fname[:-5]
        for fname in os.listdir(season_dir)
        if fname.startswith("_") and fname.endswith(".json") and not fname.endswith("_index.json")
    )
    return {"season": season, "files": files}


@router.get("/{file}/fields")
def get_fields(file: str):
    season = _active_season()
    entries, name_field = _load_and_extract(season, file)
    fields: set[str] = set()
    for entry in entries[:500]:
        fields.update(k for k in entry.keys() if not k.startswith("_"))
    return {"name_field": name_field, "fields": sorted(fields)}


@router.get("/{file}/variants")
def get_variants(file: str):
    season = _active_season()
    entries, _ = _load_and_extract(season, file)
    variants: set[str] = set()
    for entry in entries:
        variants.update(entry.get("variants", {}).keys())
    return {"variants": sorted(variants)}


@router.get("/{file}/entry")
def get_entry(file: str, name: str = Query(...)):
    season = _active_season()
    entries, name_field = _load_and_extract(season, file)
    name_lower = name.lower()
    for entry in entries:
        if (entry.get(name_field) or "").lower() == name_lower:
            return entry
    raise HTTPException(status_code=404, detail=f"Entry not found: {name!r}")


@router.get("/{file}/entries")
def query_entries(
    file: str,
    name: Optional[str] = Query(default=None),
    has: Optional[str] = Query(default=None),
    missing: Optional[str] = Query(default=None),
    where: Optional[str] = Query(default=None),
    mod_text: Optional[str] = Query(default=None),
    mod_has_condition: Optional[bool] = Query(default=None),
    limit: int = Query(default=25, ge=1, le=500),
):
    season = _active_season()
    entries, name_field = _load_and_extract(season, file)
    results = []
    total_scanned = 0
    name_lower = name.lower() if name else None
    mod_text_lower = mod_text.lower() if mod_text else None
    for entry in entries:
        total_scanned += 1
        if name_lower and name_lower not in (entry.get(name_field) or "").lower():
            continue
        if has and not _path_present(entry, has):
            continue
        if missing and _path_present(entry, missing):
            continue
        if where:
            path_key, _, val = where.partition(":")
            if str(_get_nested(entry, path_key) or "") != val:
                continue
        if mod_text_lower:
            if not any(
                mod_text_lower in (m.get("raw_text") or "").lower()
                or mod_text_lower in (m.get("expression") or "").lower()
                for m in _iter_mods(entry)
            ):
                continue
        if mod_has_condition is not None:
            has_cond = any(m.get("condition") is not None for m in _iter_mods(entry))
            if has_cond != mod_has_condition:
                continue
        results.append(entry)
        if len(results) >= limit:
            break
    return {
        "total_scanned": total_scanned,
        "count": len(results),
        "limit_reached": len(results) >= limit,
        "items": results,
    }
