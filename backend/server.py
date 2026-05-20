import argparse
import json
import os
import re
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType
from persistence import save_manager, builds_manager
from persistence import tree_config_manager
from persistence import season_manager

_TREES_META_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trees_meta.json')
with open(_TREES_META_PATH) as _f:
    TREES: dict[str, dict] = json.load(_f)

# Set in __main__ so the lifespan handler can print it after uvicorn is ready
_SERVER_PORT = 8765
_VERBOSE = False


def vlog(*args):
    if _VERBOSE:
        print(*args, flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    vlog(f"[server] lifespan startup — uvicorn bound, now accepting connections")
    print(f"TLI backend running on port {_SERVER_PORT}", flush=True)  # always needed for port detection
    yield
    vlog(f"[server] lifespan shutdown")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tree_from_config(name: str, config: dict) -> PassiveTree:
    tree = PassiveTree(name)
    for n in config["nodes"]:
        tree.add_node(PassiveNode(
            id=n["id"],
            node_type=NodeType(n["node_type"]),
            column=n["column"],
            row=n["row"],
            max_points=n["max_points"],
        ))
    for conn in config["connections"]:
        tree.add_connection(conn["from"], conn["to"])
    return tree


def _tree_from_season_data(name: str, data: dict) -> PassiveTree:
    tree = PassiveTree(name)
    for n in data["nodes"]:
        tree.add_node(PassiveNode(
            id=n["id"],
            node_type=NodeType(n["node_type"]),
            column=n["column"],
            row=n["row"],
            max_points=n["max_points"],
        ))
    for conn in data.get("connections", []):
        tree.add_connection(conn["from"], conn["to"])
    return tree


def _tree_name_to_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


_TITLE_SMALL = {"of", "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "from"}


def _format_core_talent_name(raw_key: str, tree_name: str) -> str:
    """Strip tree slug prefix from a display_name_key, then title-case (respecting small words)."""
    words = tree_name.lower().split()
    candidates = [
        "_".join(words) + "_",          # "god_of_might_"
        (words[-1] if words else "") + "_",  # "might_"
    ]
    stripped = raw_key
    for prefix in candidates:
        if prefix and raw_key.lower().startswith(prefix):
            stripped = raw_key[len(prefix):]
            break
    parts = stripped.split("_")
    return " ".join(
        p.capitalize() if (i == 0 or p not in _TITLE_SMALL) else p
        for i, p in enumerate(parts)
    )


def _build_tree(name: str) -> PassiveTree:
    active = season_manager.get_active_season()
    if active:
        slug = _tree_name_to_slug(name)
        data = season_manager.load_season_tree(active, slug)
        if data:
            return _tree_from_season_data(name, data)
    return PassiveTree(name=name, nodes=[], connections=[])


def _node_prefix(tree: PassiveTree) -> str:
    if not tree.nodes:
        return "node_"
    first_id = next(iter(tree.nodes))
    m = re.match(r"^(.+)_c\d+_r\d+$", first_id)
    return (m.group(1) + "_") if m else "node_"


# ── Trees ──────────────────────────────────────────────────────────────────────

@app.get("/api/trees")
def get_trees():
    return [{"name": name, "color": entry["color"]} for name, entry in TREES.items()]


@app.get("/api/tree/{name}")
def get_tree(name: str):
    if name not in TREES:
        raise HTTPException(status_code=404, detail="Tree not found")
    tree = _build_tree(name)

    effects_by_id: dict[str, list[str]] = {}
    active = season_manager.get_active_season()
    if active:
        slug = _tree_name_to_slug(name)
        season_data = season_manager.load_season_tree(active, slug)
        if season_data:
            for sn in season_data.get("nodes", []):
                effects_by_id[sn["id"]] = sn.get("effects", [])

    nodes = []
    for n in tree.nodes.values():
        nodes.append({
            "id": n.id,
            "column": n.column,
            "row": n.row,
            "max_points": n.max_points,
            "node_type": n.node_type.value,
            "current_points": n.current_points,
            "effects": effects_by_id.get(n.id, []),
        })

    connections = [{"from": id1, "to": id2} for id1, id2 in tree.connections]
    core_talent_slots = [
        {"id": getattr(slot, "id", str(i)), "label": getattr(slot, "label", "")}
        for i, slot in enumerate(tree.core_talent_slots or [])
    ]
    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "core_talent_slots": core_talent_slots,
        "node_prefix": _node_prefix(tree),
    }


# ── Allocation validation ──────────────────────────────────────────────────────

class AllocateRequest(BaseModel):
    tree_name: str
    node_states: dict[str, int]
    node_id: str
    action: str  # "allocate" or "deallocate"


@app.post("/api/validate-allocate")
def validate_allocate(req: AllocateRequest):
    if req.tree_name not in TREES:
        raise HTTPException(status_code=404, detail="Tree not found")
    tree = _build_tree(req.tree_name)
    for node_id, pts in req.node_states.items():
        if node_id in tree.nodes:
            tree.nodes[node_id].current_points = pts

    if req.action == "allocate":
        try:
            tree.allocate(req.node_id)
            return {"allowed": True,
                    "node_states": {nid: n.current_points for nid, n in tree.nodes.items()}}
        except ValueError:
            return {"allowed": False,
                    "node_states": {nid: n.current_points for nid, n in tree.nodes.items()}}
    elif req.action == "deallocate":
        try:
            tree.deallocate(req.node_id)
            return {"allowed": True,
                    "node_states": {nid: n.current_points for nid, n in tree.nodes.items()}}
        except ValueError:
            return {"allowed": False,
                    "node_states": {nid: n.current_points for nid, n in tree.nodes.items()}}
    raise HTTPException(status_code=400, detail="action must be allocate or deallocate")


# ── Tree editing (debug tools) ─────────────────────────────────────────────────

class NodeEditRequest(BaseModel):
    id: str
    column: int
    row: int
    node_type: str
    max_points: int


@app.post("/api/tree/{name}/node")
def upsert_node(name: str, req: NodeEditRequest):
    if name not in TREES:
        raise HTTPException(status_code=404, detail="Tree not found")
    base_tree = _build_tree(name)
    tree_config_manager.upsert_node(name, base_tree, req.model_dump())
    return {"ok": True}


@app.delete("/api/tree/{name}/node/{node_id}")
def remove_node(name: str, node_id: str):
    if name not in TREES:
        raise HTTPException(status_code=404, detail="Tree not found")
    base_tree = _build_tree(name)
    tree_config_manager.remove_node(name, base_tree, node_id)
    return {"ok": True}


class ConnectionRequest(BaseModel):
    src: str
    dst: str


@app.post("/api/tree/{name}/connection")
def toggle_connection(name: str, req: ConnectionRequest):
    if name not in TREES:
        raise HTTPException(status_code=404, detail="Tree not found")
    base_tree = _build_tree(name)
    tree_config_manager.toggle_connection(name, base_tree, req.src, req.dst)
    return {"ok": True}


# ── Modifier pool ──────────────────────────────────────────────────────────────

@app.get("/api/modifier-pool")
def get_modifier_pool():
    from models.node_modifier_pool import NODE_MODIFIER_POOL
    from models.stat_meta import STAT_META
    from tools.node_type_filter_builder import load_filter
    _ALL_TYPES = ["micro", "medium", "legendary_medium"]
    filt = load_filter()
    stats_map: dict = filt["stats"] if filt else {}
    result = []
    for stat, mod in NODE_MODIFIER_POOL.items():
        meta = STAT_META.get(stat)
        node_types = stats_map.get(stat.value, _ALL_TYPES)
        result.append({
            "stat": stat.value,
            "display_name": meta.display_name if meta else stat.value,
            "unit": meta.unit if meta else "",
            "micro_increment": mod.micro_increment,
            "medium_increment": mod.medium_increment,
            "legendary_increment": mod.legendary_increment,
            "node_types": node_types,
        })
    return result


def _collect_pool(tree_names: list[str]) -> dict:
    magic_pool: list[dict] = []
    rare_pool: list[dict] = []
    legendary_pool: list[dict] = []
    core_pool: list[dict] = []
    seen_mods: set[tuple] = set()
    seen_core_names: set[str] = set()

    active = season_manager.get_active_season()
    if not active:
        return {"magic": [], "rare": [], "legendary": [], "core": []}

    for tree_name in tree_names:
        slug = _tree_name_to_slug(tree_name)
        data = season_manager.load_season_tree(active, slug)
        if not data:
            continue
        for node in data.get("nodes", []):
            effects = node.get("effects", [])
            if not effects:
                continue
            mod_key = tuple(sorted(effects))
            if mod_key in seen_mods:
                continue
            seen_mods.add(mod_key)
            entry = {"nodeId": node["id"], "treeName": tree_name, "nodeType": node["node_type"], "effects": effects}
            nt = node["node_type"]
            if nt == "Micro Talent":
                magic_pool.append(entry)
            elif nt == "Medium Talent":
                rare_pool.append(entry)
            elif nt == "Legendary Medium Talent":
                legendary_pool.append(entry)
        for ct in data.get("core_talents", []):
            raw_key = ct.get("display_name_key", "") or ct.get("name", "")
            if not raw_key or raw_key in seen_core_names:
                continue
            seen_core_names.add(raw_key)
            # Prefer an explicit name field (may have apostrophes from source); otherwise auto-format
            display_name = ct.get("name") or _format_core_talent_name(raw_key, tree_name)
            core_pool.append({"key": f"{tree_name}:{raw_key}", "treeName": tree_name, "name": display_name, "effects": ct.get("effects", [])})

    for ct in (season_manager.load_new_god_talents(active) or []):
        name = ct.get("name", "")
        if not name or name in seen_core_names:
            continue
        seen_core_names.add(name)
        core_pool.append({"key": f"new_god:{name}", "treeName": "New God", "name": name, "effects": ct.get("effects", [])})

    return {"magic": magic_pool, "rare": rare_pool, "legendary": legendary_pool, "core": core_pool}


@app.get("/api/slate-pool-all")
def get_slate_pool_all():
    return _collect_pool(list(TREES.keys()))


@app.get("/api/slate-pool/{primary_tree}")
def get_slate_pool(primary_tree: str):
    if primary_tree not in TREES:
        raise HTTPException(status_code=404, detail="Tree not found")
    primary_color = TREES[primary_tree]["color"]
    group = [name for name, info in TREES.items() if info.get("color") == primary_color]
    return _collect_pool(group)


# ── Named builds ───────────────────────────────────────────────────────────────

@app.get("/api/builds")
def get_builds():
    return builds_manager.load()


class SlotData(BaseModel):
    treeName: str
    nodeStates: dict[str, int]


class BuildRequest(BaseModel):
    id: str | None = None
    name: str
    slots: list[SlotData | None]
    slates: list[dict] | None = None


@app.post("/api/builds")
def post_build(req: BuildRequest):
    data = req.model_dump()
    return builds_manager.save_build(data)


@app.delete("/api/builds/{build_id}")
def delete_build(build_id: str):
    if not builds_manager.delete_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")
    return {"ok": True}


# ── Engine ─────────────────────────────────────────────────────────────────────

class SkillConfigRequest(BaseModel):
    name:          str
    skill_type:    str           # "attack" | "spell"
    tags:          list[str]
    damage_types:  list[str]
    base_level:    int
    extra_levels:  int   = 0
    base_dmg_min:  float = 0.0
    base_dmg_max:  float = 0.0
    base_csr:      float = 0.0

class EnemyConfigRequest(BaseModel):
    fire_resistance:       float = 0.0
    cold_resistance:       float = 0.0
    lightning_resistance:  float = 0.0
    erosion_resistance:    float = 0.0
    armor:                 float = 0.0

class EngineComputeRequest(BaseModel):
    slots:   list[SlotData | None]
    slates:  list[dict] = []
    skill:   SkillConfigRequest
    enemy:   EnemyConfigRequest = EnemyConfigRequest()

@app.post("/api/engine/compute")
def engine_compute(req: EngineComputeRequest):
    from engine.resolver import compute
    from engine.models import BuildInput, SkillConfig, EnemyConfig
    result = compute(BuildInput(
        slots=[s.model_dump() if s else None for s in req.slots],
        slates=req.slates,
        skill=SkillConfig(**req.skill.model_dump()),
        enemy=EnemyConfig(**req.enemy.model_dump()),
        season=season_manager.get_active_season() or "",
    ))
    from dataclasses import asdict
    return asdict(result)


# ── Legacy single save ─────────────────────────────────────────────────────────

class SaveRequest(BaseModel):
    tree: str
    nodes: dict[str, int]
    core_talents: dict[str, str | None] | None = None


@app.get("/api/save")
def get_save():
    data = save_manager.load()
    return data if data else {}


@app.post("/api/save")
def post_save(req: SaveRequest):
    save_manager.save(req.tree, req.nodes, req.core_talents)
    return {"ok": True}


@app.delete("/api/save")
def delete_save():
    save_manager.clear()
    return {"ok": True}


# ── Dev tools ─────────────────────────────────────────────────────────────────

@app.post("/api/dev/parse-talent-doc")
async def parse_talent_doc(file: UploadFile = File(...)):
    from tools.talent_parser import parse_document
    data = await file.read()
    try:
        result = parse_document(data, file.filename or "upload",
                                known_tree_names=list(TREES.keys()))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


class DiffRequest(BaseModel):
    snapshot_a: dict
    snapshot_b: dict


@app.post("/api/dev/diff-snapshots")
def diff_talent_snapshots(req: DiffRequest):
    from tools.snapshot_diff import diff_snapshots
    return diff_snapshots(req.snapshot_a, req.snapshot_b)


class SaveSnapshotRequest(BaseModel):
    snapshot: dict


@app.post("/api/dev/save-snapshot")
def save_snapshot(req: SaveSnapshotRequest):
    from persistence import snapshot_manager
    snap = req.snapshot
    if "trees" not in snap or "generated_at" not in snap:
        raise HTTPException(status_code=400, detail="Invalid snapshot format")
    snapshot_manager.save(snap)
    return {"ok": True, "source_file": snap.get("source_file", ""), "generated_at": snap.get("generated_at", "")}


@app.get("/api/dev/snapshot-status")
def snapshot_status():
    from persistence import snapshot_manager
    if not snapshot_manager.exists():
        return {"exists": False, "source_file": None, "generated_at": None}
    snap = snapshot_manager.load()
    return {
        "exists": True,
        "source_file": snap.get("source_file"),
        "generated_at": snap.get("generated_at"),
    }


@app.post("/api/dev/rebuild-node-type-filter")
def rebuild_node_type_filter():
    from persistence import snapshot_manager
    from tools.node_type_filter_builder import build_filter, save_filter
    snap = snapshot_manager.load()
    if snap is None:
        raise HTTPException(status_code=400, detail="No canonical snapshot saved. Upload one first.")
    result = build_filter(snap)
    save_filter(result)
    return {
        "_meta": result["_meta"],
        "stats": result["stats"],
        "unresolved": result["unresolved"],
        "matched_texts": result["matched_texts"],
    }


@app.get("/api/dev/node-type-filter/overrides")
def get_node_type_filter_overrides():
    from tools.node_type_filter_builder import load_overrides
    return {"overrides": load_overrides()}


@app.post("/api/dev/node-type-filter/overrides")
def add_node_type_filter_override(data: dict):
    from tools.node_type_filter_builder import add_override
    text = data.get("text", "")
    stat = data.get("stat", "")
    if not text or not stat:
        raise HTTPException(status_code=400, detail="text and stat required")
    key = add_override(text, stat)
    return {"ok": True, "key": key}


@app.delete("/api/dev/node-type-filter/overrides/{key}")
def delete_node_type_filter_override(key: str):
    from tools.node_type_filter_builder import remove_override
    remove_override(key)
    return {"ok": True}


@app.post("/api/dev/export-unmatched")
def export_unmatched():
    from tools.node_type_filter_builder import load_filter
    from tools.export_stat_meta import build_unmatched_review
    import os
    data = load_filter()
    if data is None:
        raise HTTPException(status_code=400, detail="No filter built yet — run a rebuild first.")
    md = build_unmatched_review(data.get("unresolved", []))
    out_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "docs", "stat-unmatched-review.md")
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    unmatched_count = sum(1 for u in data.get("unresolved", []) if u.get("reason") == "unmatched")
    unique_count = len({u["text"] for u in data.get("unresolved", []) if u.get("reason") == "unmatched"})
    return {"ok": True, "total": unmatched_count, "unique": unique_count, "path": out_path}


@app.post("/api/dev/export-stat-meta")
def export_stat_meta():
    from tools.export_stat_meta import build_csv
    import os
    csv_data = build_csv()
    out_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "docs", "stat-meta-review.csv")
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(csv_data)
    from models.stat_meta import STAT_META
    return {"ok": True, "stat_count": len(STAT_META), "path": out_path}


@app.delete("/api/dev/snapshot")
def clear_snapshot():
    from persistence import snapshot_manager
    import os
    path = snapshot_manager._PATH
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True}


@app.delete("/api/dev/node-type-filter")
def clear_node_type_filter():
    from tools.node_type_filter_builder import _FILTER_PATH
    import os
    if os.path.exists(_FILTER_PATH):
        os.remove(_FILTER_PATH)
    return {"ok": True}


@app.get("/api/dev/snapshot-modifiers/{tree_name}/{node_type}")
def get_snapshot_modifiers(tree_name: str, node_type: str):
    from persistence import snapshot_manager
    snap = snapshot_manager.load()
    if not snap:
        return []
    tree = snap.get("trees", {}).get(tree_name)
    if not tree:
        return []
    seen: set[str] = set()
    texts: list[dict] = []
    for node in tree.get("nodes", []):
        if node.get("node_type") != node_type:
            continue
        for stat in node.get("stats", []):
            text = stat.get("text", "")
            if text and text not in seen:
                seen.add(text)
                texts.append({"text": text})
    return texts


@app.get("/api/dev/stat-recipes/{tree_name}/{node_type}")
def get_stat_recipes(tree_name: str, node_type: str):
    from tools.node_type_filter_builder import load_filter
    from models.stat_meta import STAT_META
    from models.stat import Stat
    filt = load_filter()
    if not filt:
        return []
    recipes = filt.get("recipes", {}).get(tree_name, {}).get(node_type, [])
    result = []
    for r in recipes:
        try:
            stat_enum = Stat(r["stat"])
            meta = STAT_META.get(stat_enum)
            display_name = meta.display_name if meta else r["stat"]
        except ValueError:
            display_name = r["stat"]
        result.append({
            "stat": r["stat"],
            "rank1": r["rank1"],
            "values": r["values"],
            "display_name": display_name,
        })
    return result


# ── Seasons ────────────────────────────────────────────────────────────────────

@app.get("/api/seasons")
def get_seasons():
    names = season_manager.list_seasons()
    active = season_manager.get_active_season()
    result = []
    for name in names:
        summary = season_manager.get_season_summary(name)
        summary["is_active"] = (name == active)
        result.append(summary)
    return result


@app.get("/api/active-season")
def get_active_season():
    return {"name": season_manager.get_active_season()}


class SetActiveSeasonRequest(BaseModel):
    name: str | None = None


@app.post("/api/active-season")
def set_active_season(req: SetActiveSeasonRequest):
    season_manager.set_active_season(req.name)
    return {"ok": True}


@app.delete("/api/seasons/{season_name}")
def delete_season(season_name: str):
    season_manager.delete_season(season_name)
    return {"ok": True}


class ImportSeasonRequest(BaseModel):
    season_name: str
    nodes: list[dict]


@app.post("/api/dev/import-season")
def import_season(req: ImportSeasonRequest):
    from tools.season_importer import build_slug_map, import_nodes
    if not req.season_name.strip():
        raise HTTPException(status_code=400, detail="season_name must not be empty")
    slug_map = build_slug_map()
    tree_data = import_nodes(req.nodes, slug_map)
    trees_imported: list[str] = []
    skipped: list[str] = []
    for slug, data in tree_data.items():
        if slug not in slug_map:
            skipped.append(slug)
            continue
        tree_name = slug_map[slug]
        canonical_slug = tree_name.lower().replace(" ", "_")
        data["season"] = req.season_name
        season_manager.save_season_tree(req.season_name, tree_name, canonical_slug, data)
        trees_imported.append(tree_name)
    return {"ok": True, "trees_imported": sorted(trees_imported), "skipped": sorted(skipped)}


class ImportNewGodTalentsRequest(BaseModel):
    season_name: str
    items: list[dict]


@app.post("/api/dev/import-new-god-talents")
def import_new_god_talents(req: ImportNewGodTalentsRequest):
    if not req.season_name.strip():
        raise HTTPException(status_code=400, detail="season_name must not be empty")
    talents = [
        {
            "name": item.get("name", ""),
            "item_id": item.get("item_id", ""),
            "effects": item.get("effect_lines", []),
            "note": " ".join(item.get("note_lines", [])),
        }
        for item in req.items
        if item.get("name")
    ]
    season_manager.save_new_god_talents(req.season_name, talents)
    return {"ok": True, "count": len(talents)}


class ImportLegendaryGearRequest(BaseModel):
    season_name: str
    file_data: dict


@app.post("/api/dev/import-legendary-gear")
def import_legendary_gear(req: ImportLegendaryGearRequest):
    if not req.season_name.strip():
        raise HTTPException(status_code=400, detail="season_name must not be empty")
    raw = req.file_data
    items_raw = raw.get("items", [])
    if not isinstance(items_raw, list):
        raise HTTPException(status_code=400, detail="file_data.items must be a list")

    def _clean_affix(affix: dict) -> dict:
        return {k: v for k, v in affix.items() if k != "source_line"}

    items = [
        {
            "item_id": item.get("item_id", ""),
            "name": item.get("name", ""),
            "required_level": item.get("required_level"),
            "affix_count": item.get("affix_count"),
            "affixes": [_clean_affix(a) for a in (item.get("affixes") or [])],
        }
        for item in items_raw
        if isinstance(item, dict) and item.get("item_id")
    ]

    stored = {
        "season": req.season_name,
        "set_name": raw.get("set_name", "Legendary Gear"),
        "extract_date": raw.get("extract_date"),
        "parsed_item_count": raw.get("parsed_item_count", len(items)),
        "items": items,
    }
    season_manager.save_legendary_gear(req.season_name, stored)
    return {"ok": True, "count": len(items), "set_name": stored["set_name"]}


class DiffSeasonsRequest(BaseModel):
    season_a: str
    season_b: str


@app.post("/api/dev/diff-seasons")
def diff_seasons(req: DiffSeasonsRequest):
    for name in (req.season_a, req.season_b):
        if name not in season_manager.list_seasons():
            raise HTTPException(status_code=404, detail=f"Season '{name}' not found")

    def _load_all(season: str) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for tree_name in TREES:
            slug = tree_name.lower().replace(" ", "_")
            data = season_manager.load_season_tree(season, slug)
            if data:
                result[tree_name] = data
        return result

    trees_a = _load_all(req.season_a)
    trees_b = _load_all(req.season_b)
    all_trees = sorted(set(trees_a) | set(trees_b))

    summary = {"trees_added": 0, "trees_removed": 0,
               "nodes_added": 0, "nodes_removed": 0, "nodes_changed": 0,
               "connections_added": 0, "connections_removed": 0}
    trees_diff: dict[str, dict] = {}

    for tree_name in all_trees:
        a = trees_a.get(tree_name)
        b = trees_b.get(tree_name)

        if a is None:
            summary["trees_added"] += 1
            nodes_b = b["nodes"]
            summary["nodes_added"] += len(nodes_b)
            trees_diff[tree_name] = {
                "status": "added",
                "nodes_added": nodes_b, "nodes_removed": [], "nodes_changed": [],
                "connections_added": b.get("connections", []), "connections_removed": [],
            }
            continue
        if b is None:
            summary["trees_removed"] += 1
            nodes_a = a["nodes"]
            summary["nodes_removed"] += len(nodes_a)
            trees_diff[tree_name] = {
                "status": "removed",
                "nodes_added": [], "nodes_removed": nodes_a, "nodes_changed": [],
                "connections_added": [], "connections_removed": a.get("connections", []),
            }
            continue

        nodes_a = {n["id"]: n for n in a["nodes"]}
        nodes_b = {n["id"]: n for n in b["nodes"]}
        conns_a = {(c["from"], c["to"]) for c in a.get("connections", [])}
        conns_b = {(c["from"], c["to"]) for c in b.get("connections", [])}

        added = [nodes_b[nid] for nid in nodes_b if nid not in nodes_a]
        removed = [nodes_a[nid] for nid in nodes_a if nid not in nodes_b]
        changed = []
        for nid in nodes_a:
            if nid not in nodes_b:
                continue
            na, nb = nodes_a[nid], nodes_b[nid]
            if na["node_type"] != nb["node_type"] or na["max_points"] != nb["max_points"] or na.get("effects") != nb.get("effects"):
                changed.append({"id": nid, "old": na, "new": nb})

        conns_added = [{"from": f, "to": t} for f, t in conns_b - conns_a]
        conns_removed = [{"from": f, "to": t} for f, t in conns_a - conns_b]

        summary["nodes_added"] += len(added)
        summary["nodes_removed"] += len(removed)
        summary["nodes_changed"] += len(changed)
        summary["connections_added"] += len(conns_added)
        summary["connections_removed"] += len(conns_removed)

        any_change = added or removed or changed or conns_added or conns_removed
        trees_diff[tree_name] = {
            "status": "changed" if any_change else "unchanged",
            "nodes_added": added, "nodes_removed": removed, "nodes_changed": changed,
            "connections_added": conns_added, "connections_removed": conns_removed,
        }

    return {"summary": summary, "trees": trees_diff}


# ── Entry point ────────────────────────────────────────────────────────────────

def find_free_port(preferred: int) -> int:
    try:
        with socket.socket() as s:
            s.bind(('127.0.0.1', preferred))
        return preferred
    except OSError:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--verbose", action="store_true", default=False)
    args = parser.parse_args()
    _VERBOSE = args.verbose
    vlog(f"[server] __main__ start — preferred port: {args.port}")
    _SERVER_PORT = find_free_port(args.port)
    vlog(f"[server] find_free_port selected: {_SERVER_PORT}")
    vlog(f"[server] calling uvicorn.run — lifespan will print ready signal")
    uvicorn.run(app, host="127.0.0.1", port=_SERVER_PORT, log_level="warning")
    vlog(f"[server] uvicorn.run returned (process exiting)")
