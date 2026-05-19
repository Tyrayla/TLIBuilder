import argparse
import re
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from trees.registry import TREES
from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType
from persistence import save_manager, node_stats_manager, builds_manager
from persistence import tree_config_manager
from persistence import season_manager

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


def _build_tree(name: str) -> PassiveTree:
    active = season_manager.get_active_season()
    if active:
        slug = _tree_name_to_slug(name)
        data = season_manager.load_season_tree(active, slug)
        if data:
            return _tree_from_season_data(name, data)
    config = tree_config_manager.load(name)
    if config is not None:
        return _tree_from_config(name, config)
    return TREES[name]["builder"]()


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

    # Join node stats from node_stats.json
    from models.stat import Stat
    from models.stat_meta import STAT_META
    all_stats = node_stats_manager.load()
    tree_stats = all_stats.get(name, {})

    # Load season effects if a season is active
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
        raw_stats = tree_stats.get(n.id, [])
        enhanced_stats = []
        for s in raw_stats:
            try:
                stat_enum = Stat(s["stat"])
                meta = STAT_META.get(stat_enum)
                enhanced_stats.append({
                    "stat": s["stat"],
                    "display_name": meta.display_name if meta else s["stat"],
                    "unit": meta.unit if meta else "",
                    "values": s["values"],
                })
            except (ValueError, KeyError):
                pass
        nodes.append({
            "id": n.id,
            "column": n.column,
            "row": n.row,
            "max_points": n.max_points,
            "node_type": n.node_type.value,
            "current_points": n.current_points,
            "stats": enhanced_stats,
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
    base_tree = TREES[name]["builder"]()
    tree_config_manager.upsert_node(name, base_tree, req.model_dump())
    return {"ok": True}


@app.delete("/api/tree/{name}/node/{node_id}")
def remove_node(name: str, node_id: str):
    if name not in TREES:
        raise HTTPException(status_code=404, detail="Tree not found")
    base_tree = TREES[name]["builder"]()
    tree_config_manager.remove_node(name, base_tree, node_id)
    return {"ok": True}


class ConnectionRequest(BaseModel):
    src: str
    dst: str


@app.post("/api/tree/{name}/connection")
def toggle_connection(name: str, req: ConnectionRequest):
    if name not in TREES:
        raise HTTPException(status_code=404, detail="Tree not found")
    base_tree = TREES[name]["builder"]()
    tree_config_manager.toggle_connection(name, base_tree, req.src, req.dst)
    return {"ok": True}


# ── Modifier pool ──────────────────────────────────────────────────────────────

@app.get("/api/modifier-pool")
def get_modifier_pool():
    from data.node_modifier_pool import NODE_MODIFIER_POOL
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


@app.post("/api/builds")
def post_build(req: BuildRequest):
    data = req.model_dump()
    return builds_manager.save_build(data)


@app.delete("/api/builds/{build_id}")
def delete_build(build_id: str):
    if not builds_manager.delete_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")
    return {"ok": True}


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


# ── Node stats ─────────────────────────────────────────────────────────────────

@app.get("/api/node-stats")
def get_node_stats():
    return node_stats_manager.load()


@app.get("/api/node-stats/{tree_name}/{node_id}")
def get_node_stats_for_node(tree_name: str, node_id: str):
    all_stats = node_stats_manager.load()
    return all_stats.get(tree_name, {}).get(node_id, [])


class NodeStatsRequest(BaseModel):
    stats: list[dict]


@app.post("/api/node-stats/{tree_name}/{node_id}")
def post_node_stats(tree_name: str, node_id: str, req: NodeStatsRequest):
    from models.passive_node import NodeStat
    from models.stat import Stat
    ns_list = [NodeStat(stat=Stat(s["stat"]), values=s["values"]) for s in req.stats]
    node_stats_manager.save_node(tree_name, node_id, ns_list)
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
    }


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


@app.get("/api/node-modifiers/{tree_name}/{node_id}")
def get_node_modifiers(tree_name: str, node_id: str):
    from persistence import node_modifiers_manager
    all_mods = node_modifiers_manager.load()
    mods = all_mods.get(tree_name, {}).get(node_id)
    if mods is not None:
        return mods
    # Fall back to season effects (raw text, no numeric values yet)
    active = season_manager.get_active_season()
    if active:
        slug = _tree_name_to_slug(tree_name)
        data = season_manager.load_season_tree(active, slug)
        if data:
            node = next((n for n in data.get("nodes", []) if n["id"] == node_id), None)
            if node:
                return [{"text": e, "values": []} for e in node.get("effects", [])]
    return []


class NodeModifiersRequest(BaseModel):
    modifiers: list[dict]


@app.post("/api/node-modifiers/{tree_name}/{node_id}")
def post_node_modifiers(tree_name: str, node_id: str, req: NodeModifiersRequest):
    from persistence import node_modifiers_manager
    node_modifiers_manager.save_node(tree_name, node_id, req.modifiers)
    return {"ok": True}


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
