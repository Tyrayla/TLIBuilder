import argparse
import re
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from trees.registry import TREES
from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType
from persistence import save_manager, node_stats_manager, builds_manager
from persistence import tree_config_manager

# Set in __main__ so the lifespan handler can print it after uvicorn is ready
_SERVER_PORT = 8765


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[server] lifespan startup — uvicorn bound, now accepting connections", flush=True)
    print(f"TLI backend running on port {_SERVER_PORT}", flush=True)
    yield
    print(f"[server] lifespan shutdown", flush=True)


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


def _build_tree(name: str) -> PassiveTree:
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
    result = []
    for stat, mod in NODE_MODIFIER_POOL.items():
        meta = STAT_META.get(stat)
        result.append({
            "stat": stat.value,
            "display_name": meta.display_name if meta else stat.value,
            "unit": meta.unit if meta else "",
            "micro_increment": mod.micro_increment,
            "medium_increment": mod.medium_increment,
            "legendary_increment": mod.legendary_increment,
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
    args = parser.parse_args()
    print(f"[server] __main__ start — preferred port: {args.port}", flush=True)
    _SERVER_PORT = find_free_port(args.port)
    print(f"[server] find_free_port selected: {_SERVER_PORT}", flush=True)
    print(f"[server] calling uvicorn.run — lifespan will print ready signal", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=_SERVER_PORT, log_level="warning")
    print(f"[server] uvicorn.run returned (process exiting)", flush=True)
