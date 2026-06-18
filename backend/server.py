import argparse
import json
import os
import re
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
import uvicorn

from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType
from persistence import save_manager, builds_manager
from persistence import tree_config_manager
from persistence import season_manager
import build_code as _build_code
from engine.skill_scope import detect_skill_scope
# Authoritative modifier-text → stat parser (moved to the engine layer so support_mapper can share it; see
# engine/mod_parser.py). server keeps using these exact names; they are no longer defined here.
from engine.mod_parser import (
    _parse_custom_mod_text, _parse_custom_mod_text_base, _resolve_gear_stat, _norm_expr,
    _gear_normalize, _get_gear_candidates, _normalize_for_custom_resolve,
    _EXPRESSION_STAT_OVERRIDES, _POOL_QUALIFIERS, _POOL_QUALIFIER_WORDS,
    _GEAR_COND_RE, _GEAR_SUFFIX_RE,
)

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'data'))
_TREES_META_PATH = os.path.join(_DATA_ROOT, 'trees_meta.json')
with open(_TREES_META_PATH, encoding="utf-8") as _f:
    TREES: dict[str, dict] = json.load(_f)

# Set in __main__ so the lifespan handler can print it after uvicorn is ready
_SERVER_PORT = 8765
_VERBOSE = False
# TLI_DEV_MODE=1 is set by Electron in dev; defaults to off (fail-closed).
# To enable dev routes when running server.py standalone: set TLI_DEV_MODE=1.
IS_DEV = os.environ.get("TLI_DEV_MODE", "0") == "1"

_PHRASE_OVERRIDES_PATH = os.path.join(_DATA_ROOT, 'condition_phrase_overrides.json')
_PHRASE_OVERRIDES: dict[str, object] = {}


def _load_phrase_overrides() -> None:
    global _PHRASE_OVERRIDES
    try:
        with open(_PHRASE_OVERRIDES_PATH, encoding="utf-8") as f:
            _PHRASE_OVERRIDES = json.load(f)
    except FileNotFoundError:
        _PHRASE_OVERRIDES = {}


_load_phrase_overrides()


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
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _gate_dev_routes(request: Request, call_next):
    if not IS_DEV and request.url.path.startswith("/api/dev/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return await call_next(request)


# Bundled entity icons (talent-tree node icons, hero-trait icons; pact-spirit etc. added later). Paired
# by basename: a record's `icon_url` ends in "<file>.webp", served here from data/images/icons/<category>/.
# makedirs guards the first-run case before bootstrapDataDir has populated userData. check_dir=False so a
# missing dir never crashes startup.
_ICONS_DIR = os.path.join(_DATA_ROOT, 'images', 'icons')
os.makedirs(_ICONS_DIR, exist_ok=True)
app.mount("/icons", StaticFiles(directory=_ICONS_DIR, check_dir=False), name="icons")


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
    from models.core_talent import CoreTalent, CoreTalentSlot
    tree = PassiveTree(name)
    for n in data["nodes"]:
        tree.add_node(PassiveNode(
            id=n["id"],
            node_type=NodeType(n["node_type"]),
            column=n["column"],
            row=n["row"],
            max_points=n.get("max_rank") or n.get("max_points", 1),
            icon_url=n.get("icon_url"),
        ))
    for conn in data.get("connections", []):
        tree.add_connection(conn["from"], conn["to"])

    raw_cts = data.get("core_talents", [])

    def _make_options(items):
        return [
            CoreTalent(
                id=ct["display_name_key"],
                name=_format_core_talent_name(ct["display_name_key"], name),
                effects=ct.get("effects", []),
                icon_url=ct.get("icon_url"),
            )
            for ct in items
        ]

    if len(raw_cts) == 6:
        # God/Goddess tree: 2 slots of 3 options each
        tree.add_core_talent_slot(CoreTalentSlot(threshold=12, options=_make_options(raw_cts[0:3])))
        tree.add_core_talent_slot(CoreTalentSlot(threshold=24, options=_make_options(raw_cts[3:6])))
    elif len(raw_cts) == 4:
        # Subtree: 1 slot of 4 options
        tree.add_core_talent_slot(CoreTalentSlot(threshold=24, options=_make_options(raw_cts[0:4])))

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

def _core_effect_status(effect: str) -> dict:
    """Static resolution status for one core-talent effect line (no build context), for UI badges.
    kind: 'stat' (maps to stat keys) | 'override' (re-bases a base effect) | 'deferred' | 'unresolved'.
    `resolved` is True only when EVERY part resolves; `stat_keys` aggregates the resolved keys. Compound
    lines ("+A and +B") are split into segments so the badge reflects all parts, not just the first."""
    from engine.core_talent_resolver import (
        _classify_effect, _split_condition, _split_compound, _expand_shared_stats,
        _strip_max_div, _BASE_EFFECT_RE)
    text = _strip_max_div(effect)
    cls0 = _classify_effect(effect, _parse_custom_mod_text, _translate_condition_expr)
    if cls0["kind"] == "automax":
        return {"resolved": True, "kind": "automax", "stat_keys": []}
    if cls0["kind"] == "set_value":
        # A forced final override always applies when resolved — empty stat_keys so the UI's
        # "resolved-but-unconsumed → Inactive" check skips it (it's not a pooled stat).
        return {"resolved": bool(cls0.get("stat_key")), "kind": "set_value", "stat_keys": []}
    if _BASE_EFFECT_RE.search(text):
        return {"resolved": cls0["kind"] in ("stat", "override"), "kind": cls0["kind"], "stat_keys": []}
    stat_clause, cond_clause = _split_condition(text)
    segments = _split_compound(stat_clause)
    subs = ([s + (" " + cond_clause if cond_clause else "") for s in segments]
            if len(segments) > 1 else [effect])
    subs = [x for sub in subs for x in _expand_shared_stats(sub)]
    stat_keys: list[str] = []
    all_ok = True
    for sub in subs:
        cls = _classify_effect(sub, _parse_custom_mod_text, _translate_condition_expr)
        if cls["kind"] == "stat":
            stat_keys += [c["stat_key"] for c in cls.get("contribs", [])]
        elif cls["kind"] != "override":
            all_ok = False
    return {"resolved": all_ok, "kind": "stat" if all_ok else "unresolved", "stat_keys": stat_keys}


@app.get("/api/trees")
def get_trees():
    return [{"name": name, "color": entry["color"]} for name, entry in TREES.items()]


@app.get("/api/tree-search")
def tree_search(q: str = ""):
    """Cross-tree node search for the overview screen. Returns trees whose nodes match ALL query words
    (matched against each node's effect text, regular nodes + core talents), with a per-tree match count.
    Mirrors the in-tree search so the overview highlights which trees contain what you're looking for."""
    words = [w for w in q.strip().lower().split() if w]
    if not words:
        return []
    active = season_manager.get_active_season()
    if not active:
        return []
    results = []
    for name in TREES:
        data = season_manager.load_season_tree(active, _tree_name_to_slug(name))
        if not data:
            continue
        count = 0
        for n in data.get("nodes", []):
            hay = " ".join(n.get("effects", [])).lower()
            if all(w in hay for w in words):
                count += 1
        for ct in data.get("core_talents", []):
            hay = " ".join(ct.get("effects", [])).lower()
            if all(w in hay for w in words):
                count += 1
        if count:
            results.append({"name": name, "match_count": count})
    return results


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
            "icon_url": n.icon_url,
        })

    connections = [{"from": id1, "to": id2} for id1, id2 in tree.connections]
    core_talent_slots = [
        {
            "threshold": slot.threshold,
            "options": [
                {"id": opt.id, "name": opt.name, "effects": opt.effects, "icon_url": opt.icon_url,
                 # Per-line resolution status (static — independent of selection), so badges show on any
                 # tree: "stat"/"override" resolve, "deferred"/"unresolved" badge as Unrecognized (NYI).
                 "effect_status": [_core_effect_status(e) for e in opt.effects]}
                for opt in slot.options
            ],
            "selected_id": slot.selected_id,
        }
        for slot in (tree.core_talent_slots or [])
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
    coreTalentSelections: dict[str, str] | None = None


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra='allow')

    id: str | None = None
    name: str
    slots: list[SlotData | None]
    slates: list[dict] | None = None
    conditions: list[str] | None = None
    conditionValues: dict | None = None
    gear: list[dict] | None = None
    skills: list[dict] | None = None
    characterLevel: int | None = None
    hasPrism: bool | None = None


@app.post("/api/builds")
def post_build(req: BuildRequest):
    data = req.model_dump()
    return builds_manager.save_build(data)


@app.delete("/api/builds/{build_id}")
def delete_build(build_id: str):
    if not builds_manager.delete_build(build_id):
        raise HTTPException(status_code=404, detail="Build not found")
    return {"ok": True}


class BuildCodeEncodeRequest(BaseModel):
    build: dict


class BuildCodeDecodeRequest(BaseModel):
    code: str


@app.post("/api/build-code/encode")
def encode_build_code(req: BuildCodeEncodeRequest):
    try:
        code = _build_code.encode_build(req.build)
        return {"code": code}
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to encode build.")


@app.post("/api/build-code/decode")
def decode_build_code(req: BuildCodeDecodeRequest):
    active = season_manager.get_active_season()
    gear_data = season_manager.load_legendary_gear(active) if active else None
    gear_items = gear_data.get("items", []) if gear_data else []
    try:
        build = _build_code.decode_build(req.code, gear_items)
        return {"build": build}
    except _build_code.BuildCodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
    slots:      list[SlotData | None]
    slates:     list[dict] = []
    skill:      SkillConfigRequest
    enemy:      EnemyConfigRequest = EnemyConfigRequest()
    conditions: list[str] = []

@app.post("/api/engine/compute")
def engine_compute(req: EngineComputeRequest):
    # DEPRECATED: legacy path (engine.pipeline). No renderer caller; /api/engine/stats (offense.py)
    # is the source of truth. Known-divergent additional pooling — see docs/ADDITIONAL_DAMAGE_POOLING.md.
    from engine.resolver import compute
    from engine.models import BuildInput, SkillConfig, EnemyConfig
    result = compute(BuildInput(
        slots=[s.model_dump() if s else None for s in req.slots],
        slates=req.slates,
        skill=SkillConfig(**req.skill.model_dump()),
        enemy=EnemyConfig(**req.enemy.model_dump()),
        season=season_manager.get_active_season() or "",
        conditions=req.conditions,
    ))
    from dataclasses import asdict
    return asdict(result)


class SkillEngineInput(BaseModel):
    skill_id: str
    level:    int = 1


class SkillSlotInput(BaseModel):
    slot:     int   # 1–5 active, 6–9 passive
    skill_id: str
    level:    int = 1
    enabled:  bool = True   # disabled skills (and their supports + sourced buffs/debuffs) drop out of the calc


class EngineStatsRequest(BaseModel):
    slots:           list[SlotData | None]
    slates:          list[dict] = []
    condition_state: dict[str, float | bool] = {}
    gear:            list[dict] = []
    character:       list[dict] = []
    # Each item is either a bare effect string (legacy) or {text, source} where `source` is the hero-memory /
    # pact-spirit display name surfaced in the stat-breakdown "Source Name" column.
    memory_effects:  list[str | dict] = []
    spirit_effects:  list[str | dict] = []
    main_skill:      SkillEngineInput | None = None   # kept for backward compat
    skills:          list[SkillSlotInput] = []         # all equipped skills with slot info
    custom_mods:     list[str] = []
    attached_supports: list[dict] = []                 # main skill's supports: {item_id, skill_type, rank, level}
    characterLevel:  int | None = None                 # player level — seeds the `level` condition (per-level scaling, e.g. Brutality)


@app.post("/api/engine/stats")
def engine_stats(req: EngineStatsRequest):
    import re
    from engine.compute import compute
    from engine.models import BuildInput
    from tools.node_type_filter_builder import load_filter

    active_season = season_manager.get_active_season() or ""
    filter_data = load_filter() or {}

    slots = [s.model_dump() if s else None for s in req.slots]
    slates = req.slates

    def _slug(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    needed_slugs: set[str] = set()
    for slot in slots:
        if slot and slot.get("treeName"):
            needed_slugs.add(_slug(slot["treeName"]))
    for slate in slates:
        for sd in slate.get("slots", []):
            node_id = sd.get("selectedNodeId")
            if node_id:
                m = re.match(r"^(.+)_c\d+_r\d+$", node_id)
                if m:
                    needed_slugs.add(m.group(1))

    season_trees: dict[str, dict] = {}
    for slug in needed_slugs:
        tree_data = season_manager.load_season_tree(active_season, slug)
        if tree_data:
            season_trees[slug] = tree_data

    from engine.models import SkillRef

    main_skill = None
    skill_data = None
    skills_by_id: dict = {}

    # Load skills cache if any skill info is needed
    needs_skills = bool(req.main_skill or req.skills or req.attached_supports)
    if needs_skills:
        skills_by_id = _get_skills_data(active_season)

    if req.main_skill:
        main_skill = SkillRef(skill_id=req.main_skill.skill_id, level=req.main_skill.level)
        skill_data = skills_by_id.get(req.main_skill.skill_id)

    skills_input = [{"slot": s.slot, "skill_id": s.skill_id, "level": s.level, "enabled": s.enabled}
                    for s in req.skills]
    # Host-enable gate: a disabled active/passive skill removes that slot's supports too. With no `skills`
    # payload (today's common case) every support stays enabled → byte-identical.
    _disabled_slots = {s.slot for s in req.skills if not s.enabled}

    # Pre-resolve custom mods and build status list for the frontend. Mirror the gear path: split off a
    # leading/trailing condition ("vs Low Life enemies", "if Ignited", "when only 1 enemy nearby") so the
    # stat clause resolves and the gate rides on each contribution's `condition` (gated in the aggregator).
    # An untranslatable gate makes the mod UNRESOLVED (honest NYI), never applied always-on.
    from engine.core_talent_resolver import _split_condition
    custom_contributions: list[dict] = []
    custom_mod_statuses: list[dict] = []
    for mod_text in req.custom_mods:
        stat_part, cond_part = _split_condition(mod_text)
        parsed = _parse_custom_mod_text(stat_part)
        cond_expr = None
        if parsed and cond_part is not None:
            cond_expr = _translate_condition_expr(mod_text) or _translate_condition_expr(cond_part)
            if cond_expr is None:
                parsed = []
        if parsed:
            # Each parsed entry becomes a contribution; all share the same original text + gate.
            for entry in parsed:
                if cond_expr is not None:
                    entry["condition"] = cond_expr
                custom_contributions.append(entry)
            display_names = [_qualified_stat_display(e["stat_key"]) for e in parsed]
            custom_mod_statuses.append({
                "text": mod_text,
                "resolved": True,
                "stat_display": ", ".join(display_names),
            })
        else:
            custom_mod_statuses.append({
                "text": mod_text,
                "resolved": False,
                "stat_display": None,
            })

    # Pre-resolve pact-spirit / hero-memory effects through the unified resolver + build status lists so
    # nothing is silently dropped (cardinal rule), mirroring the custom-mod block above.
    def _resolve_effect_list(effects: list[str | dict], is_memory: bool) -> tuple[list[dict], list[dict]]:
        contribs: list[dict] = []
        statuses: list[dict] = []
        for item in effects:
            # Accept both the legacy bare-string shape and {text, source} (source = spirit/memory name).
            if isinstance(item, dict):
                eff = item.get("text", "")
                source = item.get("source")
            else:
                eff, source = item, None
            parsed = _resolve_effect_modifiers(eff, is_memory=is_memory)
            if parsed:
                if source:
                    parsed = [{**p, "source": source} for p in parsed]
                contribs.extend(parsed)
                names = ", ".join(_get_stat_display_name(e["stat_key"]) or e["stat_key"] for e in parsed)
                statuses.append({"text": eff, "resolved": True, "stat_display": names})
            else:
                statuses.append({"text": eff, "resolved": False, "stat_display": None})
        return contribs, statuses

    spirit_contributions, spirit_mod_statuses = _resolve_effect_list(req.spirit_effects, is_memory=False)
    memory_contributions, memory_mod_statuses = _resolve_effect_list(req.memory_effects, is_memory=True)

    # Resolve the main skill's attached supports into stat contributions (additional-damage lines)
    # plus behavioral effects (shotgun falloff / chains-per-jump).
    support_contributions: list[dict] = []
    support_behavior: dict = {}
    # Enabled filter: drop individually-disabled supports and any support whose host skill slot is off.
    # Default enabled=True and absent slot → kept, so today's payloads resolve the identical set.
    enabled_supports = [s for s in req.attached_supports
                        if s.get("enabled", True) and s.get("slot", 1) not in _disabled_slots]
    if enabled_supports:
        from engine.support_resolver import resolve_support_contributions, resolve_support_behavior
        support_contributions = resolve_support_contributions(enabled_supports, skills_by_id, _translate_condition_expr)
        support_behavior = resolve_support_behavior(enabled_supports, skills_by_id)

    # Resolve granted core talents (tree / slate / legendary / belt blend), deduped to count each
    # exactly once, into stat contributions + base-effect override flags. Flags ride in condition_state
    # so the aggregator's blessing/Numbed override loops pick them up. (roadmap #4)
    from engine.core_talent_resolver import resolve_core_talents
    belt_blends_data = season_manager.load_belt_blends(active_season) or {}
    core_contributions, core_flags, core_talent_statuses = resolve_core_talents(
        slots, slates, req.gear, season_trees, belt_blends_data,
        _parse_custom_mod_text, _translate_condition_expr,
    )
    # Resolve allocated talent-tree NODES + SLATE slots through the SAME unified resolver (replaces the
    # filter-builder recipes). Amounts pre-scaled by points; conditionals gated in the aggregator.
    from engine.node_resolver import resolve_nodes
    from engine.consumable_universe import consumable_universe
    node_contributions, _node_statuses = resolve_nodes(
        slots, slates, season_trees, _parse_custom_mod_text, _translate_condition_expr,
    )
    core_condition_state = {**req.condition_state, **{flag: True for flag in core_flags}}
    # Seed player level (for per-level scaling like Brutality) unless the user set it explicitly.
    if req.characterLevel is not None and "level" not in req.condition_state:
        core_condition_state["level"] = float(req.characterLevel)

    # Cardinal rule — never silently drop. Resolve any gear affix/implicit the frontend couldn't
    # (crafted base resistances/life/attributes, etc.), inject it as a contribution on that item, and
    # report every line (resolved or not) so the UI can surface anything still unmodeled.
    from engine.core_talent_resolver import _split_condition
    gear_resolved: list[dict] = []
    gear_mod_statuses: list[dict] = []
    affix_curses: list[dict] = []   # curses inflicted by gear affixes (craft bases / legendaries) → curse resolver
    for gi in req.gear:
        texts = gi.get("unresolved_texts") or []
        if not texts:
            gear_resolved.append(gi)
            continue
        gi = dict(gi)
        contribs = list(gi.get("contributions") or [])
        for t in texts:
            # Curse-applying affix? Record it (counts toward the curse limit; magnitude comes from the curse
            # skill at the affix level) and mark resolved — it has no stat contribution of its own.
            ac = _extract_affix_curse(t)
            if ac:
                affix_curses.append({**ac, "source_label": gi.get("item_name") or "Gear"})
                gear_mod_statuses.append({"text": t, "resolved": True,
                                          "stat_display": f"Inflicts {ac['curse_name']} (Lv {ac['level']})"})
                continue
            # Split off a leading ("If recently moved, +X%") or trailing ("+X% if Ignited") gate so the
            # stat clause resolves; the gate is translated and rides on the contribution's `condition`
            # (gated in the aggregator). A gate we can't translate makes the line UNRESOLVED (honest NYI),
            # never applied always-on — silently dropping the condition would be worse than a red badge.
            stat_part, cond_part = _split_condition(t)
            parsed = _parse_custom_mod_text(stat_part)
            cond_expr = None
            if parsed and cond_part is not None:
                cond_expr = _translate_condition_expr(t) or _translate_condition_expr(cond_part)
                if cond_expr is None:
                    parsed = []
            if parsed:
                for e in parsed:
                    contribs.append({"stat": e["stat_key"], "display_value": e["amount"], "unit": "",
                                     "item_name": gi.get("item_name") or "Gear", "text": t,
                                     "slot": None, "condition": cond_expr, "scope": e.get("scope")})
                names = ", ".join(_get_stat_display_name(e["stat_key"]) or e["stat_key"] for e in parsed)
                gear_mod_statuses.append({"text": t, "resolved": True, "stat_display": names})
            else:
                gear_mod_statuses.append({"text": t, "resolved": False, "stat_display": None})
        gi["contributions"] = contribs
        gear_resolved.append(gi)

    # ── Auras / Focus buffs ──────────────────────────────────────────────────
    # Server only PARSES the buff lines into unscaled contributions (needs the text→stat parser). The engine
    # (engine.utility, inside compute) scales them by the fully-aggregated Aura Effect + builds the summaries.
    from engine.aura_resolver import resolve_auras
    aura_buffs, aura_statuses, aura_stack_conditions, aura_meta = resolve_auras(
        skills_input, skills_by_id, _parse_custom_mod_text, _translate_condition_expr)

    # ── Empower (Euphoria) buffs ─────────────────────────────────────────────
    # Server parses the buff lines into unscaled contributions; the engine (utility.apply_empower_buffs, inside
    # compute) scales them by Empower Skill Effect and builds the summaries.
    from engine.empower_resolver import resolve_empowers
    empower_buffs, empower_statuses, empower_stack_conditions, empower_meta = resolve_empowers(
        skills_input, skills_by_id, _parse_custom_mod_text, _translate_condition_expr)

    # ── Curses ───────────────────────────────────────────────────────────────
    # Gather active curses from slotted curse skills + curse-applying affixes; the engine (curse_resolver, inside
    # compute) scales by Curse Effect, enforces the curse limit, and bakes the enemy damage-taken pools. Any active
    # curse means the enemy IS cursed → auto-set enemy_cursed so "+% damage against Cursed enemies" / Grudge work
    # (the limit conflict only gates the damage-taken amplification, not the enemy being cursed).
    from engine.curse_resolver import resolve_curses
    active_curses, curse_statuses, curse_meta = resolve_curses(skills_input, affix_curses, skills_by_id)
    if active_curses and not core_condition_state.get("enemy_cursed"):
        core_condition_state = {**core_condition_state, "enemy_cursed": True}

    build = BuildInput(
        slots=slots, slates=slates, season=active_season,
        condition_state=core_condition_state,
        gear=gear_resolved, character=req.character,
        spirit_contributions=spirit_contributions, memory_contributions=memory_contributions,
        main_skill=main_skill,
        custom_contributions=custom_contributions,
        attached_support_contributions=support_contributions,
        support_behavior=support_behavior,
        attached_supports=enabled_supports,
        core_talent_contributions=core_contributions,
        node_contributions=node_contributions,
        aura_buffs=aura_buffs,
        aura_meta=aura_meta,
        curses=active_curses,
        curse_meta=curse_meta,
        empower_buffs=empower_buffs,
        empower_meta=empower_meta,
    )
    result = compute(
        build, season_trees, filter_data,
        skill_data=skill_data,
        skills_input=skills_input or None,
        skills_by_id=skills_by_id or None,
    )
    return {
        "stats": result.stat_map,
        "condition_maximums": result.condition_maximums,
        "clamp_report": result.clamp_report,
        "offense": result.offense,
        "defense": result.defense,
        "custom_mod_statuses": custom_mod_statuses,
        "core_talent_statuses": core_talent_statuses,
        "gear_mod_statuses": gear_mod_statuses,
        "spirit_mod_statuses": spirit_mod_statuses,
        "memory_mod_statuses": memory_mod_statuses,
        "skill_slots": result.skill_slots,
        # Per-active-slot offense ({slot: OffenseResult}); headline `offense` is the main slot. Additive —
        # the renderer doesn't consume it yet.
        "slot_offense": result.slot_offense,
        "consumed_stats": result.consumed_stats,
        # Maximal set of stats the engine can EVER read (all skills/tags) — lets the UI tell "Inactive"
        # (modeled, not for your skill) apart from "Unconsumed" (engine never reads it). Cached per process.
        "consumable_universe": sorted(consumable_universe()),
        # Calc-target armor/resist (base + effective after penetration) + active enemy debuffs.
        "target_stats": result.target_stats,
        # Per-blessing summary (stacks/max/effects) for the Blessings panel.
        "blessings": result.blessings,
        # Per-aura summary (granted buff lines + applied Aura Effect + NYI lines) for the Skill panel —
        # computed engine-side (engine.utility) so the Aura Effect total is the true post-aggregation value.
        "auras": result.aura_summaries,
        "aura_statuses": aura_statuses,
        # Per-empower summary (Empower Effect + granted buffs + NYI) for the Skill panel, statuses, and the
        # settable per-empower buff-stack conditions (sliders).
        "empowers": result.empower_summaries,
        "empower_statuses": empower_statuses,
        "empower_stack_conditions": empower_stack_conditions,
        # Per-curse summary (Curse Effect, limit, debuff value + applied flag), per-curse meta (base stats + NYI
        # lines) for the Skill panel, NYI statuses, and the over-limit conflict (drives the resolution dropdown).
        "curses": result.curse_summaries,
        "curse_meta": curse_meta,
        "curse_statuses": curse_statuses,
        "curse_conflict": result.curse_conflict,
        # General build warnings/diagnostics (e.g. a curse that amplifies a damage type the build doesn't deal).
        "warnings": result.warnings,
        # Mana/Life sealing: totals (sealed/unsealed pools, insufficient flags) + per-skill seal breakdowns.
        "reservation": result.reservation,
        # Settable per-aura stack conditions ({key,label,max}) for the stack sliders.
        "aura_stack_conditions": aura_stack_conditions,
    }


# ── Conditions ─────────────────────────────────────────────────────────────────

@app.get("/api/conditions")
def get_conditions():
    from models.conditions import ALL_CONDITIONS, DERIVED_ACTIVE_KEYS
    derived_keys = set(DERIVED_ACTIVE_KEYS.keys())
    result: dict[str, list[dict]] = {}
    for c in ALL_CONDITIONS:
        entry: dict = {
            "key": c.key,
            "label": c.label,
            "value_type": c.value_type,
        }
        if c.value_type == "numeric":
            entry["numeric_min"] = c.numeric_min
            entry["numeric_max"] = c.numeric_max
            entry["unit"] = c.unit
            entry["default_value"] = c.default_value   # was omitted → frontend saw undefined → 0 defaults
        else:
            entry["default_bool"] = c.default_bool
        if c.key in derived_keys:
            entry["is_derived"] = True
        if not c.visible:
            entry["visible"] = False
        result.setdefault(c.category, []).append(entry)
    return result


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
    from tools.node_type_filter_builder import build_filter, build_node_recipes, save_filter
    snap = snapshot_manager.load()
    if snap is None:
        raise HTTPException(status_code=400, detail="No canonical snapshot saved. Upload one first.")
    result = build_filter(snap)

    # Build per-node-id recipes from the active season's tree data
    active = season_manager.get_active_season()
    if active:
        season_trees = season_manager.load_all_season_trees(active)
        result["node_recipes"] = build_node_recipes(season_trees)

    save_filter(result)
    return {
        "_meta": result["_meta"],
        "stats": result["stats"],
        "unresolved": result["unresolved"],
        "matched_texts": result["matched_texts"],
        "node_recipe_count": len(result.get("node_recipes", {})),
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
        os.path.join(os.path.dirname(__file__), "..", "docs", "stat-audit.md")
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    unique_count = len({u["text"] for u in data.get("unresolved", []) if u.get("reason") == "unmatched"})
    return {"ok": True, "unique": unique_count, "path": out_path}


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


class ImportCrawlerTreeRequest(BaseModel):
    season_name: str
    tree_name: str
    crawler_data: dict


@app.post("/api/dev/import-crawler-tree")
def import_crawler_tree_endpoint(req: ImportCrawlerTreeRequest):
    from tools.season_importer import import_crawler_tree, _make_display_name_key

    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")

    tree_name = req.tree_name.strip()

    # New God — routes to _new_god_talents.json, not a regular tree file
    if tree_name == "New God":
        talents = []
        for node in req.crawler_data.get("nodes", []):
            if node.get("type") != "core_talent":
                continue
            raw_name = node.get("name", "")
            if not raw_name:
                continue
            item_id = re.sub(r"[^a-z0-9]+", "_", raw_name.lower()).strip("_")
            talents.append({
                "name": raw_name,
                "item_id": item_id,
                "effects": node.get("effects") or [],
                "icon_url": node.get("icon_url", ""),
                "note": "",
            })
        season_manager.save_new_god_talents(req.season_name, talents)
        return {"ok": True, "tree_name": "New God", "count": len(talents)}

    if tree_name not in TREES:
        raise HTTPException(400, f"Unknown tree '{tree_name}'")

    tree_slug = _tree_name_to_slug(tree_name)
    data = import_crawler_tree(req.crawler_data, tree_name)
    data["season"] = req.season_name
    season_manager.save_season_tree(req.season_name, tree_name, tree_slug, data)

    return {
        "ok": True,
        "tree_name": tree_name,
        "node_count": len(data["nodes"]),
        "core_talent_count": len(data["core_talents"]),
        "connection_count": len(data["connections"]),
    }


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


class ImportCrawlerLegendaryGearRequest(BaseModel):
    season_name: str
    items: list[dict]


@app.post("/api/dev/import-crawler-legendary-gear")
def import_crawler_legendary_gear_endpoint(req: ImportCrawlerLegendaryGearRequest):
    from tools.legendary_gear_importer import import_crawler_items
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    items = import_crawler_items(req.items)
    season_manager.save_legendary_gear(req.season_name, {
        "season": req.season_name,
        "item_count": len(items),
        "items": items,
    })
    return {"ok": True, "count": len(items)}


# ── Skills ─────────────────────────────────────────────────────────────────────

class ImportSkillsRequest(BaseModel):
    season_name: str
    file_data: dict


class ImportCrawlerSkillsRequest(BaseModel):
    season_name: str
    items: list[dict]


@app.post("/api/dev/import-crawler-skills")
def import_crawler_skills_endpoint(req: ImportCrawlerSkillsRequest):
    from tools.skill_importer import import_crawler_skills, merge_skills
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    items = import_crawler_skills(req.items)
    existing = season_manager.load_skills(req.season_name) or {"skills": []}
    merged = merge_skills(existing.get("skills", []), items)
    season_manager.save_skills(req.season_name, {
        "season": req.season_name,
        "skill_count": len(merged),
        "skills": merged,
    })
    return {"ok": True, "added": len(items), "total": len(merged)}


@app.post("/api/dev/import-skills")
def import_skills(req: ImportSkillsRequest):
    from tools.skill_importer import parse_skill_file, merge_skills

    if not req.season_name.strip():
        raise HTTPException(status_code=400, detail="season_name must not be empty")

    try:
        incoming = parse_skill_file(req.file_data)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Load existing skills for this season and merge
    existing_data = season_manager.load_skills(req.season_name) or {"skills": []}
    merged = merge_skills(existing_data.get("skills", []), incoming)

    stored = {
        "season": req.season_name,
        "skill_count": len(merged),
        "skills": merged,
    }
    season_manager.save_skills(req.season_name, stored)
    return {"ok": True, "added": len(incoming), "total": len(merged)}


@app.get("/api/skills")
def get_skills():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "skills": []}
    data = season_manager.load_skills(active)
    if not data:
        return {"season": active, "skills": []}
    from engine.tooltip import build_tooltip
    # Which skills CAN contribute to the build's total DPS. Dev-set: an explicit `dps_eligible` in the skill
    # record wins; otherwise default by type (active / modularization deal hit damage; passives/supports/etc
    # do not). The user then toggles inclusion per equipped skill (countInDps).
    _DPS_TYPES = {"active_skill", "modularization_skill"}
    skills = []
    for s in data.get("skills", []):
        out = dict(s)   # enrich a copy; never mutate the loaded store
        out["dps_eligible"] = bool(s["dps_eligible"]) if "dps_eligible" in s else (s.get("skill_type") in _DPS_TYPES)
        # Buff-passive flag: an Aura/Focus-tagged passive grants player buffs (aura_resolver) — lets the UI
        # label it and show its granted effects.
        out["is_aura"] = s.get("skill_type") == "passive_skill" and any(
            t in (s.get("skill_tags") or []) for t in ("Aura", "Focus"))
        try:
            out["tooltip"] = build_tooltip(s)
        except Exception:
            # Never silently drop / 500: fall back to the raw description as flavor lines.
            out["tooltip"] = {
                "gate_text": None, "level_kind": "level",
                "default_level": s.get("max_level") or 1, "available_levels": [s.get("max_level") or 1],
                "lines": [{"kind": "flavor", "badge_text": d, "text": d, "values_by_level": None}
                          for d in (s.get("description_lines") or [])],
            }
        skills.append(out)
    return {"season": active, "skills": skills}


@app.delete("/api/dev/skills")
def clear_skills():
    active = season_manager.get_active_season()
    if active:
        season_manager.delete_skills(active)
    return {"ok": True}


# ── Hero Traits ────────────────────────────────────────────────────────────────

class ImportHeroTraitRequest(BaseModel):
    season_name: str
    file_data: dict


class ImportCrawlerHeroTraitsRequest(BaseModel):
    season_name: str
    items: list[dict]


@app.post("/api/dev/import-crawler-hero-traits")
def import_crawler_hero_traits_endpoint(req: ImportCrawlerHeroTraitsRequest):
    from tools.hero_trait_importer import import_crawler_hero_traits, merge_hero_traits
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    items = import_crawler_hero_traits(req.items)
    existing = season_manager.load_hero_traits(req.season_name) or {"traits": []}
    merged: list[dict] = existing.get("traits", [])
    for item in items:
        merged = merge_hero_traits(merged, item)
    heroes = len({t["hero"] for t in merged if t.get("hero")})
    season_manager.save_hero_traits(req.season_name, {
        "season": req.season_name,
        "hero_count": heroes,
        "trait_count": len(merged),
        "traits": merged,
    })
    return {"ok": True, "added": len(items), "total": len(merged), "heroes": heroes}


@app.post("/api/dev/import-hero-traits")
def import_hero_traits(req: ImportHeroTraitRequest):
    from tools.hero_trait_importer import parse_hero_trait_file, merge_hero_traits

    if not req.season_name.strip():
        raise HTTPException(status_code=400, detail="season_name must not be empty")

    try:
        incoming = parse_hero_trait_file(req.file_data)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing_data = season_manager.load_hero_traits(req.season_name) or {"traits": []}
    merged = merge_hero_traits(existing_data.get("traits", []), incoming)

    # Derive unique hero count from merged traits
    heroes = len({t["hero"] for t in merged if t.get("hero")})

    stored = {
        "season": req.season_name,
        "hero_count": heroes,
        "trait_count": len(merged),
        "traits": merged,
    }
    season_manager.save_hero_traits(req.season_name, stored)
    return {"ok": True, "hero": incoming.get("hero", ""), "total": len(merged), "heroes": heroes}


@app.get("/api/hero-traits")
def get_hero_traits():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "traits": []}
    data = season_manager.load_hero_traits(active)
    if not data:
        return {"season": active, "traits": []}
    return {"season": active, "traits": data.get("traits", [])}


# ── Gear affix stat resolver ───────────────────────────────────────────────────


_MULTI_STAT_OVERRIDES: dict[str, list[str]] = {
    "+(#) % attack and cast speed": ["attack_speed_inc", "cast_speed_inc"],
    "+(#) % minion attack and cast speed": ["minion_attack_speed_inc", "minion_cast_speed_inc"],
    "+(#) % additional attack and cast speed for combo starters":
        ["combo_starter_attack_speed_additional", "combo_starter_cast_speed_additional"],
    "+(#) % max life max mana and max energy shield": ["max_life_inc", "max_mana_inc", "max_energy_shield_inc"],
    "+(#) % elemental and erosion resistance penetration": ["elemental_pen", "erosion_pen"],
    # Block chance
    "+(#) % attack and spell block chance": ["attack_block_chance_inc", "spell_block_chance_inc"],
    # Max elemental resistance (fire+cold+lightning, not erosion)
    "+(#) % max elemental resistance": ["fire_resistance_max_inc", "cold_resistance_max_inc", "lightning_resistance_max_inc"],
    # Single value → multiple stats
    "+(#) attack and spell critical strike rating": ["attack_crit_rating_flat", "spell_crit_rating_flat"],
    "+(#) % minion attack and cast speed": ["minion_attack_speed_inc", "minion_cast_speed_inc"],
    "+(#) % minion movement speed attack speed and cast speed": ["minion_movement_speed_inc", "minion_attack_speed_inc", "minion_cast_speed_inc"],
    # Elemental + erosion pen for minions
    "+(#) % elemental and erosion resistance penetration for minions": ["minion_elemental_pen"],
    # Resistance combos (dual-element)
    "+(#) % fire and cold resistance":          ["fire_resistance", "cold_resistance"],
    "+(#) % cold and lightning resistance":     ["cold_resistance", "lightning_resistance"],
    "+(#) % cold and erosion resistance":       ["cold_resistance", "erosion_resistance"],
    "+(#) % fire and lightning resistance":     ["fire_resistance", "lightning_resistance"],
    "+(#) % fire and erosion resistance":       ["fire_resistance", "erosion_resistance"],
    "+(#) % lightning and erosion resistance":  ["lightning_resistance", "erosion_resistance"],
    "+(#) % max fire and lightning resistance":  ["fire_resistance_max_inc", "lightning_resistance_max_inc"],
    # Attribute combos
    "+(#) dexterity and intelligence":           ["dexterity_flat", "intelligence_flat"],
    "+(#) strength and intelligence":            ["strength_flat", "intelligence_flat"],
    "+(#) strength and dexterity":               ["strength_flat", "dexterity_flat"],
    # Defense combos
    "+(#) armor and evasion":                    ["armor_flat", "evasion_flat"],
    # Life / Mana combos
    "+(#) % max life and max mana":              ["max_life_inc", "max_mana_inc"],
    "+(#) % additional max life max mana and max energy shield": ["max_life_additional", "max_mana_additional", "max_energy_shield_additional"],
}

# Two-value affixes: first (#) → group[0] stats, second (#) → group[1] stats
# Multi-group affixes with mixed units (% and flat in same affix)
_MIXED_STAT_OVERRIDES: dict[str, list[dict]] = {
    "+(#) % gear physical damage adds (#)-(#) physical damage to the gear": [
        {"value_index": 0, "stat_keys": ["physical_dmg_gear_inc"], "unit": "%"},
        {"value_index": 1, "stat_keys": ["physical_dmg_gear_flat_min"], "unit": ""},
        {"value_index": 2, "stat_keys": ["physical_dmg_gear_flat_max"], "unit": ""},
    ],
    "adds (#)-(#) elemental damage to the gear -(#) % gear physical damage": [
        {"value_index": 0, "stat_keys": ["elemental_dmg_gear_flat_min"], "unit": ""},
        {"value_index": 1, "stat_keys": ["elemental_dmg_gear_flat_max"], "unit": ""},
        {"value_index": 2, "stat_keys": ["physical_dmg_gear_inc"], "unit": "%"},
    ],
}

_DUAL_MULTI_STAT_OVERRIDES: dict[str, tuple[list[str], list[str]]] = {
    "+(#) % attack and cast speed +(#) % minion attack and cast speed":
        (["attack_speed_inc", "cast_speed_inc"],
         ["minion_attack_speed_inc", "minion_cast_speed_inc"]),
    "+(#) % cast speed +(#) % minion cast speed":
        (["cast_speed_inc"], ["minion_cast_speed_inc"]),
    "+(#) % additional attack and cast speed for combo starters +(#) % critical strike damage for combo finishers":
        (["combo_starter_attack_speed_additional", "combo_starter_cast_speed_additional"],
         ["combo_finisher_crit_dmg_inc"]),
    "+(#) max spell burst +(#) % additional hit damage for skills cast by spell burst":
        (["max_spell_burst_flat"], ["spell_burst_hit_dmg_additional"]),
    "+(#) % spell burst charge speed +(#) % chance to immediately gain (#) stack of spell burst charge when using a skill. interval: (#)s":
        (["spell_burst_charge_speed_inc"], ["spell_burst_chance_gain_stacks_flat"]),
    "max terra charge stacks +(#) +(#) % terra charge recovery speed":
        (["max_terra_charge_stacks_flat"], ["terra_charge_recovery_speed_inc"]),
    "max terra quantity +(#) +(#) % additional damage":
        (["max_terra_quantity_flat"], ["dmg_additional"]),
    "+(#) jumps +(#) % additional damage":
        (["extra_jumps_flat"], ["dmg_additional"]),
    "+(#) jumps +(#) % additional damage for every jump (multiplies)":
        (["extra_jumps_flat"], ["jump_dmg_for_every_additional"]),
    "you can cast (#) additional curses +(#) % curse effect":
        (["max_curses_flat"], ["curse_effect_inc"]),
    "+(#) % max mana +(#) skill cost":
        (["max_mana_inc"], ["skill_cost_flat"]),
    "+(#) % evasion +(#) max life":
        (["evasion_inc"], ["max_life_flat"]),
    "+(#) % armor +(#) max life":
        (["armor_inc"], ["max_life_flat"]),
    "shadow quantity +(#) -(#) % additional shadow damage":
        (["max_shadow_quantity_flat"], ["shadow_dmg_additional"]),
    "+(#) % knockback distance +(#) % additional damage":
        (["knockback_distance_inc"], ["dmg_additional"]),
    "+(#) to max summonable synthetic troops +(#) % additional minion damage":
        (["max_synth_troops_flat"], ["minion_dmg_additional"]),
    "+(#) to max tenacity blessing stacks +(#) % additional damage":
        (["max_tenacity_blessing_stacks_flat"], ["dmg_additional"]),
    "+(#) to max agility blessing stacks +(#) % additional damage":
        (["max_agility_blessing_stacks_flat"], ["dmg_additional"]),
    "+(#) to max focus blessing stacks +(#) % additional damage":
        (["max_focus_blessing_stacks_flat"], ["dmg_additional"]),
    "+(#) to max tenacity blessing stacks +(#) % additional minion damage":
        (["max_tenacity_blessing_stacks_flat"], ["minion_dmg_additional"]),
    "+(#) to max agility blessing stacks +(#) % additional minion damage":
        (["max_agility_blessing_stacks_flat"], ["minion_dmg_additional"]),
    "+(#) to max focus blessing stacks +(#) % additional minion damage":
        (["max_focus_blessing_stacks_flat"], ["minion_dmg_additional"]),
    "+(#) % elemental resistance +(#) % erosion resistance":
        (["elemental_resistance"], ["erosion_resistance"]),
    "+(#) % elemental resistance +(#) % chance to avoid elemental ailment":
        (["elemental_resistance"], ["elemental_ailment_avoid_chance"]),
    "+(#) combo points gained from combo starters +(#) % additional damage":
        (["combo_starters_combo_points_flat"], ["dmg_additional"]),
    "+(#) parabolic projectile split quantity +(#) % additional projectile damage":
        (["parabolic_projectile_splits_flat"], ["projectile_dmg_additional"]),
    "-(#) % additional cast speed +(#) % additional spell damage":
        (["cast_speed_additional"], ["spell_dmg_additional"]),
    "+(#) ignite limit +(#) % additional ignite damage":
        (["max_ignite_flat"], ["ignite_dmg_additional"]),
    "+(#) beams +(#) % additional damage":
        (["beam_dmg_additional"], ["dmg_additional"]),
    "you can apply (#) additional tangle to enemies +(#) % tangle damage enhancement":
        (["max_tangle_quantity_flat"], ["tangle_dmg_inc"]),
    "+(#) % gear attack speed (-(#)-(#) % additional attack damage":
        (["attack_speed_gear"], ["attack_dmg_additional"]),
    "+(#) % elemental and erosion resistance penetration +(#) % elemental and erosion resistance penetration for minions":
        (["elemental_pen", "erosion_pen"], ["minion_elemental_pen"]),
    # Pen (different text format): elemental+erosion pen → minion elemental pen
    "+(#) % elemental and erosion resistance penetration minion damage penetrates (#) % elemental resistance":
        (["elemental_pen", "erosion_pen"], ["minion_elemental_pen"]),
    # Profane: erosion dmg → minion erosion dmg
    "has profane . minions have profane +(#) % erosion damage +(#) % minion erosion damage":
        (["erosion_dmg_additional"], ["minion_erosion_dmg_inc"]),
}

# Range affixes where min and max each fan out to multiple stats
_RANGE_MULTI_STAT_OVERRIDES: dict[str, dict] = {
    "adds (#)-(#) physical damage to attacks and spells":
        {"min_keys": ["physical_attack_dmg_flat_min", "physical_spell_dmg_flat_min"],
         "max_keys": ["physical_attack_dmg_flat_max", "physical_spell_dmg_flat_max"]},
    "adds (#)-(#) fire damage to attacks and spells":
        {"min_keys": ["fire_attack_dmg_flat_min", "fire_spell_dmg_flat_min"],
         "max_keys": ["fire_attack_dmg_flat_max", "fire_spell_dmg_flat_max"]},
    "adds (#)-(#) cold damage to attacks and spells":
        {"min_keys": ["cold_attack_dmg_flat_min", "cold_spell_dmg_flat_min"],
         "max_keys": ["cold_attack_dmg_flat_max", "cold_spell_dmg_flat_max"]},
    "adds (#)-(#) lightning damage to attacks and spells":
        {"min_keys": ["lightning_attack_dmg_flat_min", "lightning_spell_dmg_flat_min"],
         "max_keys": ["lightning_attack_dmg_flat_max", "lightning_spell_dmg_flat_max"]},
    "adds (#)-(#) erosion damage to attacks and spells":
        {"min_keys": ["erosion_attack_dmg_flat_min", "erosion_spell_dmg_flat_min"],
         "max_keys": ["erosion_attack_dmg_flat_max", "erosion_spell_dmg_flat_max"]},
    "adds (#)-(#) physical damage to minions":
        {"min_keys": ["minion_physical_dmg_flat_min"], "max_keys": ["minion_physical_dmg_flat_max"]},
    "adds (#)-(#) fire damage to minions":
        {"min_keys": ["minion_fire_dmg_flat_min"], "max_keys": ["minion_fire_dmg_flat_max"]},
    "adds (#)-(#) cold damage to minions":
        {"min_keys": ["minion_cold_dmg_flat_min"], "max_keys": ["minion_cold_dmg_flat_max"]},
    "adds (#)-(#) lightning damage to minions":
        {"min_keys": ["minion_lightning_dmg_flat_min"], "max_keys": ["minion_lightning_dmg_flat_max"]},
    "adds (#)-(#) erosion damage to minions":
        {"min_keys": ["minion_erosion_dmg_flat_min"], "max_keys": ["minion_erosion_dmg_flat_max"]},
    "adds (#)-(#) base trauma damage":
        {"min_keys": ["trauma_base_dmg_flat_min"], "max_keys": ["trauma_base_dmg_flat_max"]},
    "adds (#)-(#) base wilt damage":
        {"min_keys": ["wilt_base_dmg_flat_min"], "max_keys": ["wilt_base_dmg_flat_max"]},
    "adds (#)-(#) base ignite damage":
        {"min_keys": ["ignite_base_dmg_flat_min"], "max_keys": ["ignite_base_dmg_flat_max"]},
    "adds (#)-(#) base ailment damage":
        {"min_keys": ["ailment_dmg_flat_min"], "max_keys": ["ailment_dmg_flat_max"]},
    # Attacks only (no spells)
    "adds (#)-(#) physical damage to attacks":
        {"min_keys": ["physical_attack_dmg_flat_min"], "max_keys": ["physical_attack_dmg_flat_max"]},
    "adds (#)-(#) fire damage to attacks":
        {"min_keys": ["fire_attack_dmg_flat_min"], "max_keys": ["fire_attack_dmg_flat_max"]},
    "adds (#)-(#) cold damage to attacks":
        {"min_keys": ["cold_attack_dmg_flat_min"], "max_keys": ["cold_attack_dmg_flat_max"]},
    "adds (#)-(#) lightning damage to attacks":
        {"min_keys": ["lightning_attack_dmg_flat_min"], "max_keys": ["lightning_attack_dmg_flat_max"]},
    "adds (#)-(#) erosion damage to attacks":
        {"min_keys": ["erosion_attack_dmg_flat_min"], "max_keys": ["erosion_attack_dmg_flat_max"]},
    # Spells only (no attacks)
    "adds (#)-(#) physical damage to spells":
        {"min_keys": ["physical_spell_dmg_flat_min"], "max_keys": ["physical_spell_dmg_flat_max"]},
    "adds (#)-(#) fire damage to spells":
        {"min_keys": ["fire_spell_dmg_flat_min"], "max_keys": ["fire_spell_dmg_flat_max"]},
    "adds (#)-(#) cold damage to spells":
        {"min_keys": ["cold_spell_dmg_flat_min"], "max_keys": ["cold_spell_dmg_flat_max"]},
    "adds (#)-(#) lightning damage to spells":
        {"min_keys": ["lightning_spell_dmg_flat_min"], "max_keys": ["lightning_spell_dmg_flat_max"]},
    "adds (#)-(#) erosion damage to spells":
        {"min_keys": ["erosion_spell_dmg_flat_min"], "max_keys": ["erosion_spell_dmg_flat_max"]},
    # Gear flat damage (after suffix strip, "to the gear" is removed)
    "adds (#)-(#) physical damage":
        {"min_keys": ["physical_dmg_gear_flat_min"], "max_keys": ["physical_dmg_gear_flat_max"]},
    "adds (#)-(#) fire damage":
        {"min_keys": ["fire_dmg_gear_flat_min"], "max_keys": ["fire_dmg_gear_flat_max"]},
    "adds (#)-(#) cold damage":
        {"min_keys": ["cold_dmg_gear_flat_min"], "max_keys": ["cold_dmg_gear_flat_max"]},
    "adds (#)-(#) lightning damage":
        {"min_keys": ["lightning_dmg_gear_flat_min"], "max_keys": ["lightning_dmg_gear_flat_max"]},
    "adds (#)-(#) erosion damage":
        {"min_keys": ["erosion_dmg_gear_flat_min"], "max_keys": ["erosion_dmg_gear_flat_max"]},
}









_BLESSING_COND_RE = re.compile(
    r"(focus|tenacity|agility)\s+bless", re.I)
_THRESHOLD_RE = re.compile(
    r"at\s+least\s+(\d+)"
    r"|>=?\s*(\d+)"
    r"|at\s+most\s+(\d+)"
    r"|<=?\s*(\d+)"
    r"|more\s+than\s+(\d+)"
    r"|fewer\s+than\s+(\d+)|less\s+than\s+(\d+)",
    re.I,
)
_WEAPON_PHYS_DMG_RE = re.compile(r"^([\d.]+)\s*-\s*([\d.]+)\s+Physical Damage$")
_WEAPON_ATK_SPD_RE  = re.compile(r"^([\d.]+)\s+Attack Speed$")
_WEAPON_CSR_RE      = re.compile(r"^([\d.]+)\s+Critical Strike Rating$")





# Curse-applying affixes name a specific curse + level: "Triggers Lv. 20 Scorch Curse upon inflicting damage" /
# "Nearby enemies within 15 m are cursed by Lv. 20 Ominous". These don't map to a stat — they ADD a curse to the
# build (counts toward the limit; magnitude comes from that curse skill's line at the level), so they're collected
# into affix_curses and handed to the curse resolver.
_CURSE_NAMES = {n.lower(): n for n in (
    "Vulnerability", "Scorch", "Biting Cold", "Electrocute", "Corruption", "Timid",
    "Entangled Pain", "Dazzled", "Ominous")}
_AFFIX_CURSE_LV_RE = re.compile(r'(?:triggers|cursed by)\s+lv\.?\s*\(?\s*(?:[\d.]+\s*[-–]\s*)?([\d.]+)', re.I)


def _extract_affix_curse(text: str) -> dict | None:
    """{curse_name, level} if `text` inflicts a named curse (else None). Uses the high end of any level range."""
    low = (text or "").lower()
    if "curse" not in low and "cursed by" not in low:
        return None
    m = _AFFIX_CURSE_LV_RE.search(text or "")
    if not m:
        return None
    level = int(float(m.group(1)))
    tail = (text or "")[m.end():].lower()
    for ln, proper in sorted(_CURSE_NAMES.items(), key=lambda kv: -len(kv[0])):
        if ln in tail:
            return {"curse_name": proper, "level": level}
    return None




# Leading "+N [%] <stat>" form used by pact-spirit / hero-memory effect strings (ported from the old
# aggregator _MEMORY_EFFECT_RE so the unified resolver below extracts the value for the multi-stat path).
_EFFECT_VALUE_RE = re.compile(r'^\+(\d+(?:\.\d+)?)\s*(%?)\s+(.+)$')

# On-hit STACKING resistance penetration (Dreamweaver, cloudgatherer, idling-weasel): "+N% <type> Resistance
# Penetration when hitting / every time you hit an enemy with Elemental Damage …, stacking up to M times".
# Modeled as a PER-STACK {type}_pen scaled by the shared `elemental_hit_pen_stacks` condition (defaults to its
# max so it sits at full uptime during sustained DPS; user-adjustable). The condition's max caps the stacks.
_STACKING_PEN_RE = re.compile(
    r'\+?\s*([\d.]+)\s*%\s*(elemental|fire|cold|lightning|erosion)\s+resistance\s+penetration\b'
    r'.*?\bstack(?:s|ing)?\s+up\s+to\s+\d+\s+times', re.I | re.DOTALL)


def _resolve_stacking_pen(text: str) -> list[dict] | None:
    """Return a per-stack {type}_pen contribution scaled by elemental_hit_pen_stacks, or None if `text`
    isn't an on-hit stacking resistance-pen line."""
    m = _STACKING_PEN_RE.search(text)
    if not m:
        return None
    typ = m.group(2).lower()
    stat = "elemental_pen" if typ == "elemental" else f"{typ}_pen"
    return [{
        "stat_key": stat,
        "amount": float(m.group(1)) / 100.0,   # per-stack; aggregator multiplies by the stack count
        "text": text.strip(),
        "scope": None,
        "condition": {"key": "elemental_hit_pen_stacks", "op": "per", "divisor": 1},
    }]


def _resolve_effect_modifiers(text: str, *, is_memory: bool) -> list[dict]:
    """Resolve a pact-spirit / hero-memory effect string into contributions [{stat_key, amount, text, scope}]
    — the SAME shape as custom_contributions. This is the unified, pool-strict replacement for the old
    _MEMORY_STAT_LOOKUP path: it shares _parse_custom_mod_text (and the gear override tables) so spirit/memory
    can no longer drift from gear/custom resolution.

    Order mirrors the old resolver where it matters: peel a skill-type scope off the WHOLE effect, split off a
    leading/trailing condition clause and GATE on it (a conditional effect must apply only when its condition
    holds, never always-on; an untranslatable gate leaves the whole effect UNRESOLVED rather than applied —
    mirrors the gear loop), then split a dual-stat phrase "+A% X +B% Y" (the real data has these on BOTH
    memories and spirits — not splitting a spirit dual silently dropped a part, so the split is unconditional
    now; single-stat effects have no split point and are untouched). For each part, try the shared
    _MULTI_STAT_OVERRIDES first (one phrase → several stats; the fuzzy single resolver could wrongly
    partial-match these), then fall back to the pool-strict _parse_custom_mod_text (which itself consults
    _EXPRESSION_STAT_OVERRIDES, e.g. the combo-finisher alias and the penetration wording). Every result carries
    the peeled scope, the translated condition, and the ORIGINAL full text so the additional pool's
    affix-identity keeps scoped mods as distinct multiplicative factors. `is_memory` is accepted for caller
    symmetry; resolution is now identical for spirits and memories (one shared path, no drift)."""
    from engine.core_talent_resolver import _split_condition
    original = re.sub(r'\s+', ' ', (text or '').strip())
    # On-hit stacking resistance pen is its own mechanic (per-stack pen × elemental_hit_pen_stacks), not a
    # gated stat — handle it before the condition splitter would treat its "when hitting…" clause as a gate.
    stacking = _resolve_stacking_pen(original)
    if stacking is not None:
        return [{**d, "text": original} for d in stacking]
    residual, scope = detect_skill_scope(original)
    stat_clause, cond_part = _split_condition(residual)
    cond_expr = None
    if cond_part is not None:
        # A gate we can't translate must NOT be applied always-on — leave the whole effect unresolved (NYI).
        cond_expr = _translate_condition_expr(residual) or _translate_condition_expr(cond_part)
        if cond_expr is None:
            return []
    out: list[dict] = []
    for part in re.split(r' (?=\+\d)', stat_clause, maxsplit=1):
        ne = _norm_expr(part)
        multi = _MULTI_STAT_OVERRIDES.get(ne)
        m = _EFFECT_VALUE_RE.match(part)
        if multi and m:
            amount = float(m.group(1)) / 100.0 if m.group(2) else float(m.group(1))
            for sk in multi:
                out.append({"stat_key": sk, "amount": amount, "text": original, "scope": scope, "condition": cond_expr})
            continue
        # Pool-strict single resolver (scope already peeled from `part`; it re-peels harmlessly/idempotently).
        for d in _parse_custom_mod_text(part):
            out.append({**d, "text": original, "scope": scope, "condition": cond_expr})
    return out


def resolve_effect_stat_keys(effect: str, *, is_memory: bool) -> list[str]:
    """The stat key(s) a pact-spirit / hero-memory effect resolves to — for the /api/map-modifiers badge
    endpoint. Thin view over _resolve_effect_modifiers so badges and the engine share ONE resolver and can't
    drift. Empty list = unrecognized (red NYI badge). (Replaces the retired engine.aggregator version.)"""
    return [d["stat_key"] for d in _resolve_effect_modifiers(effect, is_memory=is_memory)]




def _get_stat_display_name(stat_key: str) -> str | None:
    """Return the human-readable display name for a stat key, or None if unknown."""
    from models.stat import Stat
    from models.stat_meta import STAT_META
    try:
        stat = Stat(stat_key)
        meta = STAT_META.get(stat)
        return meta.display_name if meta else None
    except ValueError:
        return None


def _qualified_stat_display(stat_key: str) -> str:
    """Display name qualified by which POOL the stat key targets, so the same base stat's flat / increased /
    additional pools read distinctly (e.g. Dexterity vs "Dexterity (increased)" vs "Dexterity (additional)").
    Skips the qualifier when the display name already carries it. Flat = the bare base name."""
    base = _get_stat_display_name(stat_key) or stat_key
    low = base.lower()
    if stat_key.endswith("_additional") and "additional" not in low:
        return f"{base} (additional)"
    if stat_key.endswith("_more") and "more" not in low:
        return f"{base} (more)"
    if stat_key.endswith("_inc") and "increased" not in low:
        return f"{base} (increased)"
    return base


_BLESSING_KEY_MAP = {
    "focus": "focus_stacks",
    "tenacity": "tenacity_stacks",
    "agility": "agility_stacks",
}


# Condition-clause patterns → engine condition expressions (for talent/affix gates). Negated forms are
# listed before their positive counterparts so "not low" wins over "low". A value can be a static expr
# or a callable(match)->expr for thresholds. These map onto conditions in data/conditions.json.
_COND_PATTERNS: list[tuple] = [
    # Low-resource gates (self) — negated first
    (re.compile(r"energy\s+shield\s+is\s+not\s+low|not\s+at\s+low\s+energy\s+shield", re.I), {"not": "low_energy_shield"}),
    (re.compile(r"life\s+is\s+not\s+low|not\s+at\s+low\s+life", re.I), {"not": "low_life"}),
    (re.compile(r"\bat\s+low\s+energy\s+shield\b", re.I), "low_energy_shield"),
    (re.compile(r"\bat\s+low\s+life\b", re.I), "low_life"),
    # Elemental "dealt X recently"
    (re.compile(r"dealt\s+fire\s+damage\s+recently", re.I), "dealt_fire_recently"),
    (re.compile(r"dealt\s+cold\s+damage\s+recently", re.I), "dealt_cold_recently"),
    (re.compile(r"dealt\s+lightning\s+damage\s+recently", re.I), "dealt_lightning_recently"),
    # Buffs / recent / state
    # Blur is active. NOTE: "for N s after Blur ends" is a distinct post-Blur window we don't model yet
    # (deferred to full Blur modeling); for now it grants its bonus while Blur is active.
    (re.compile(r"blur\s+is\s+active|after\s+blur\s+ends", re.I), "blur_active"),
    (re.compile(r"having\s+squidnova|have\s+squidnova", re.I), "has_squidnova"),
    (re.compile(r"taken\s+damage\s+in\s+the\s+last|recently\s+taken\s+damage", re.I), "recently_taken_damage"),
    (re.compile(r"used\s+a\s+mobility\s+skill", re.I), "recently_used_mobility"),
    # "Critical Strike or Reaped" → either condition satisfies it.
    (re.compile(r"landed\s+a\s+critical\s+strike\s+or\s+reaped", re.I), {"or": ["recently_crit", "recently_reaped"]}),
    (re.compile(r"landed\s+a\s+critical\s+strike|critical\s+strike\b.*\brecently\b", re.I), "recently_crit"),
    (re.compile(r"performing\s+multistrikes?", re.I), "performing_multistrike"),
    # USE and CAST are distinct in TLI (Help DB) — this gate is on CAST, its own condition.
    (re.compile(r"sentry\s+skill\s+has\s+been\s+cast\s+recently", re.I), "sentry_skill_cast_recently"),
    (re.compile(r"defeat(?:ing|ed)\s+wilted\s+enem", re.I), "defeated_wilted_recently"),
    (re.compile(r"holding\s+a\s+two-?handed\s+weapon", re.I), "holding_two_handed"),
    (re.compile(r"holding\s+a\s+one-?handed\s+weapon", re.I), "holding_one_handed"),
    # "against/from <Status> enemies" → the matching enemy-status condition.
    (re.compile(r"(?:against|from)\s+(paralyzed|numbed|cursed|ignited|frozen|frostbitten|wilted|traumatized|blinded)\s+enem", re.I),
     lambda m: f"enemy_{m.group(1).lower()}"),
    (re.compile(r"enem(?:y|ies)\s+in\s+proximity|in\s+proximity", re.I), "enemy_in_proximity"),
    # "(only) N enemy/enemies nearby" / "at least N enemies nearby" → NUMERIC enemies-nearby count (not the
    # boolean enemy_nearby). Must precede the generic "nearby enem" → enemy_nearby pattern further down.
    (re.compile(r"only\s+(\d+)\s+enem(?:y|ies)\s+(?:are\s+|is\s+)?nearby", re.I),
     lambda m: {"key": "enemies_nearby", "op": "==", "value": int(m.group(1))}),
    (re.compile(r"at\s+least\s+(\d+)\s+enem(?:y|ies)\s+(?:are\s+)?nearby", re.I),
     lambda m: {"key": "enemies_nearby", "op": ">=", "value": int(m.group(1))}),
    # Benign cast-timing clauses that describe WHEN, not a gate — always-on (the chance/EV is the mechanic).
    (re.compile(r"when\s+casting\s+a\s+skill|when\s+you\s+cast|on\s+cast\b", re.I), {"const": True}),
    # Per-"stack owned" scaling → multiply the contribution by the stack count (floor(val/1)).
    (re.compile(r"(?:per|for\s+every|for\s+each)\s+stack(?:\(s\))?\s+of\s+(focus|agility|tenacity)\s+blessing", re.I),
     lambda m: {"key": f"{m.group(1).lower()}_blessings", "op": "per", "divisor": 1}),
    (re.compile(r"per\s+(?:\d+\s+)?stack(?:\(s\))?\s+of\s+fortitude", re.I),
     {"key": "fortitude_stacks", "op": "per", "divisor": 1}),
    # Per-character-level scaling, e.g. Brutality "-1% Elemental Damage for every 3 level(s)" (PLAYER only
    # for now — minion interaction unverified). Divisor = the "every N levels" step.
    (re.compile(r"(?:per|for\s+every|for\s+each)\s+(\d+)\s+level", re.I),
     lambda m: {"key": "level", "op": "per", "divisor": int(m.group(1))}),
    # "for each <countable>" per-scaling — MUST precede the boolean recent/state patterns below, which would
    # otherwise shadow them (e.g. "for each time you have Regained" must scale, not just gate on regained).
    (re.compile(r"for\s+each\s+unique\s+type\s+of\s+weapon", re.I), {"key": "unique_weapon_types", "op": "per", "divisor": 1}),
    (re.compile(r"for\s+each\s+time\s+you\s+have\s+regained", re.I), {"key": "regain_stacks", "op": "per", "divisor": 1}),
    (re.compile(r"for\s+each\s+type\s+of\s+(?:elemental\s+)?ailment", re.I), {"key": "ailment_type_count", "op": "per", "divisor": 1}),
    # "against enemies with Max Affliction" → existing enemy_has_max_affliction condition.
    (re.compile(r"with\s+max\s+affliction|enem(?:y|ies)\s+(?:with|has|have)\s+max\s+affliction", re.I), "enemy_has_max_affliction"),
    (re.compile(r"not\s+wielding\s+a\s+wand\s+or\s+tin\s+staff", re.I), {"not": "wielding_wand_or_tin_staff"}),
    (re.compile(r"wielding\s+a\s+wand\s+or\s+tin\s+staff", re.I), "wielding_wand_or_tin_staff"),
    # Attribute comparisons (Tradeoff) — auto-derived from STR vs DEX in the compute loop.
    (re.compile(r"dexterity\s+is\s+no\s+less\s+than\s+strength", re.I), "dexterity_ge_strength"),
    (re.compile(r"strength\s+is\s+no\s+less\s+than\s+dexterity", re.I), "strength_ge_dexterity"),
    # Numeric movement threshold
    (re.compile(r"moved\s+more\s+than\s+(\d+)\s*m\b", re.I), lambda m: {"key": "meters_moved_recently", "op": ">", "value": int(m.group(1))}),
    # ── Talent-node gates → existing conditions (added for the node-unification coverage pass) ──────────
    (re.compile(r"at\s+full\s+mana", re.I), "at_full_mana"),
    (re.compile(r"at\s+low\s+mana", re.I), "at_low_mana"),
    (re.compile(r"\bwhile\s+dual\s+wielding|\bwhen\s+dual\s+wielding|\bdual\s+wielding", re.I), "dual_wielding"),
    (re.compile(r"\bwhile\s+moving\b|\bwhen\s+moving\b", re.I), "moving"),
    (re.compile(r"while\s+standing\s+still|when\s+standing\s+still", re.I), "standing_still"),
    (re.compile(r"channeled\s+stacks\s+have\s+not\s+reached\s+cap|not\s+reached\s+(?:the\s+)?cap", re.I), "channeled_not_capped"),
    (re.compile(r"holding\s+a\s+shield|when\s+holding\s+a\s+shield|while\s+holding\s+a\s+shield", re.I), "holding_shield"),
    (re.compile(r"to\s+distant\s+enemies|distant\s+enem", re.I), "enemy_distant"),
    (re.compile(r"to\s+nearby\s+enemies|nearby\s+enem", re.I), "enemy_nearby"),
    # Regain / regen "recently" windows
    (re.compile(r"triggered\s+life\s+regain\s+in\s+the\s+last", re.I), "recently_life_regain"),
    (re.compile(r"triggered\s+shield\s+regain\s+in\s+the\s+last", re.I), "recently_shield_regain"),
    (re.compile(r"(?:have\s+)?regained\s+in\s+the\s+last|regained\s+recently", re.I), "recently_regained"),
    # "Sentry Skill is not used in the last N s" / "Main Skill ... not used in the last"
    (re.compile(r"sentry\s+skill\s+is\s+not\s+used\s+in\s+the\s+last", re.I), "sentry_not_used_recently"),
    (re.compile(r"main\s+skill\s+(?:is\s+|has\s+)?not\s+(?:been\s+)?used\s+in\s+the\s+last", re.I), "main_skill_not_used_recently"),
    # "while/when <X> Blessing is active" → has at least one stack of that blessing
    (re.compile(r"(focus|agility|tenacity)\s+blessing\s+is\s+active|(?:while|when)\s+(?:having|has)\s+(focus|agility|tenacity)\s+blessing", re.I),
     lambda m: {"key": f"{(m.group(1) or m.group(2)).lower()}_blessings", "op": ">=", "value": 1}),
    # Enemy-scope gates — Proximity (≤4m), Nearby (≤6m), Distant (>6m) are THREE DISTINCT conditions; never
    # cross-map them. ("in proximity" is handled by the dedicated enemy_in_proximity pattern above.)
    (re.compile(r"(?:to|against)\s+nearby\s+enem|dealt\s+to\s+nearby\s+enem", re.I), "enemy_nearby"),
    (re.compile(r"(?:to|against)\s+distant\s+enem|dealt\s+to\s+distant\s+enem", re.I), "enemy_distant"),
    (re.compile(r"against\s+low\s+life\s+enem|low\s+life\s+enemies", re.I), "enemy_low_life"),
    (re.compile(r"against\s+enemies\s+(?:affected\s+by|with)\s+(?:\w+\s+)?ailments?|enemies\s+(?:that\s+have|with)\s+ailments?", re.I), "enemy_has_ailment"),
    (re.compile(r"used\s+a\s+warcry\s+skill\s+(?:in\s+the\s+last|recently)|warcry\s+.*recently", re.I), "recently_warcry"),
    # Recent self-state windows
    (re.compile(r"blocked\s+recently|have\s+blocked\s+in\s+the\s+last|if\s+you\s+have\s+blocked", re.I), "recently_blocked"),
    (re.compile(r"elixir\s+skill\s+is\s+active|while\s+an?\s+elixir", re.I), "elixir_active"),
    (re.compile(r"defeated\s+an?\s+enemy\s+recently|have\s+defeated\s+an?\s+enemy", re.I), "enemy_defeated_recently"),
    (re.compile(r"(?:while\s+)?having\s+fervor\b|while\s+you\s+have\s+fervor", re.I), "fervor_active"),
    (re.compile(r"both\s+sealed\s+mana\s+and\s+(?:sealed\s+)?life|having\s+both\s+sealed", re.I), "sealed_mana_and_life"),
    (re.compile(r"synthetic\s+troop\s+skill\s+has\s+been\s+(?:cast|used)\s+recently|synthetic\s+troop\s+skill\s+.*recently", re.I), "recently_synth_cast"),
    (re.compile(r"taken\s+damage\s+recently", re.I), "recently_taken_damage"),
    (re.compile(r"lost\s+life\s+recently|have\s+lost\s+life", re.I), "recently_lost_life"),
    # Per-Fervor-Rating scaling: "+X per N Fervor Rating" → ×floor(fervor/N).
    (re.compile(r"per\s+(\d+)\s+fervor\s+rating", re.I), lambda m: {"key": "fervor_rating", "op": "per", "divisor": int(m.group(1))}),
    (re.compile(r"per\s+fervor\s+rating", re.I), {"key": "fervor_rating", "op": "per", "divisor": 1}),
]


def _translate_condition_expr(text: str | None) -> dict | str | None:
    """Map a raw condition text string to an engine expression, or None if unresolvable."""
    if not text:
        return None
    # Exact override wins
    if text in _PHRASE_OVERRIDES:
        return _PHRASE_OVERRIDES[text]
    # Regex fallback: blessing stack thresholds
    bm = _BLESSING_COND_RE.search(text)
    if bm:
        key = _BLESSING_KEY_MAP[bm.group(1).lower()]
        tm = _THRESHOLD_RE.search(text)
        if tm:
            ge, ge2, le, le2, gt, lt, lt2 = tm.groups()
            if ge:   return {"key": key, "op": ">=", "value": int(ge)}
            if ge2:  return {"key": key, "op": ">=", "value": int(ge2)}
            if le:   return {"key": key, "op": "<=", "value": int(le)}
            if le2:  return {"key": key, "op": "<=", "value": int(le2)}
            if gt:   return {"key": key, "op": ">",  "value": int(gt)}
            if lt:   return {"key": key, "op": "<",  "value": int(lt)}
            if lt2:  return {"key": key, "op": "<",  "value": int(lt2)}
    # Pattern table: low-resource / dealt-recently / buff / weapon / movement gates
    for pat, expr in _COND_PATTERNS:
        m = pat.search(text)
        if m:
            e = expr(m) if callable(expr) else expr
            # "for each X while Y": a per-scaling can ALSO carry a boolean gate. Scan the text OUTSIDE the
            # per-match for a non-per gate and combine, so both survive (e.g. per weapon-type AND dual-wield).
            if isinstance(e, dict) and e.get("op") == "per":
                rest = (text[:m.start()] + " " + text[m.end():])
                for p2, x2 in _COND_PATTERNS:
                    m2 = p2.search(rest)
                    if not m2:
                        continue
                    g = x2(m2) if callable(x2) else x2
                    if g != e and not (isinstance(g, dict) and g.get("op") == "per"):
                        return {"and": [e, g]}
            return e
    return None


# TLI's "additional" (independent multiplicative) and "increased"/"reduced" (one additive pool) are
# DIFFERENT pools and must never be cross-matched — display names don't encode the qualifier, so the




@app.get("/api/legendary-gear-index")
def get_legendary_gear_index():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "items": []}
    data = season_manager.load_legendary_gear_index(active)
    if not data:
        return {"season": active, "items": []}
    return {"season": active, "items": data.get("items", [])}


def _resolve_affix(affix: dict) -> dict:
    """Resolve a gear affix dict to include stat_key/stat_keys/unit/condition_expr fields."""
    condition_expr = _translate_condition_expr(affix.get("condition"))
    if affix.get("affix_kind") == "placeholder":
        return {**affix, "stat_key": None, "unit": "", "condition_expr": condition_expr}
    if affix.get("affix_kind") == "special":
        raw = affix.get("raw_text", "")
        if _WEAPON_PHYS_DMG_RE.match(raw):
            return {**affix, "stat_key": None, "unit": "", "condition_expr": None,
                    "min_stat_keys": ["physical_dmg_gear_flat_min"],
                    "max_stat_keys": ["physical_dmg_gear_flat_max"]}
        if _WEAPON_ATK_SPD_RE.match(raw):
            return {**affix, "stat_key": "weapon_attack_speed", "unit": "", "condition_expr": None}
        if _WEAPON_CSR_RE.match(raw):
            return {**affix, "stat_key": "weapon_crit_rating_flat", "unit": "", "condition_expr": None}
        return {**affix, "stat_key": None, "unit": "", "condition_expr": None}
    raw_text = affix.get("raw_text", "")
    text = _GEAR_COND_RE.sub("", raw_text)
    text = _GEAR_SUFFIX_RE.sub("", text)
    ne = _norm_expr(text)
    unit = "%" if "%" in raw_text else ""
    # 1. Range-multi: min and max each fan out to multiple stats
    if ne in _RANGE_MULTI_STAT_OVERRIDES:
        rm = _RANGE_MULTI_STAT_OVERRIDES[ne]
        return {**affix, "stat_key": None, "unit": unit, "condition_expr": condition_expr,
                "min_stat_keys": rm["min_keys"], "max_stat_keys": rm["max_keys"]}
    # 2a. Mixed-unit multi-group affixes (per-group unit override)
    if ne in _MIXED_STAT_OVERRIDES:
        return {**affix, "stat_key": None, "unit": unit, "condition_expr": condition_expr,
                "dual_stat_groups": _MIXED_STAT_OVERRIDES[ne]}
    # 2b. Dual-value: two separate (#) values → two groups of stats
    if ne in _DUAL_MULTI_STAT_OVERRIDES:
        g0, g1 = _DUAL_MULTI_STAT_OVERRIDES[ne]
        dual_groups = [{"value_index": 0, "stat_keys": g0},
                       {"value_index": 1, "stat_keys": g1}]
        return {**affix, "stat_key": None, "unit": unit, "condition_expr": condition_expr,
                "dual_stat_groups": dual_groups}
    # 3. Multi-stat: single value → multiple stats
    if ne in _MULTI_STAT_OVERRIDES:
        stat_keys = _MULTI_STAT_OVERRIDES[ne]
        is_range_split = any(k.endswith(("_flat_min", "_flat_max")) for k in stat_keys)
        return {**affix, "stat_key": None, "stat_keys": stat_keys,
                "is_range_split": is_range_split, "unit": unit, "condition_expr": condition_expr}
    # 4. Expression or fuzzy fallback
    stat_key, unit = _resolve_gear_stat(raw_text)
    return {**affix, "stat_key": stat_key, "unit": unit, "condition_expr": condition_expr}


class ResolveModRequest(BaseModel):
    text: str


@app.post("/api/resolve-mod")
def resolve_mod(req: ResolveModRequest):
    """Resolve a single freeform modifier text string to stat contributions.

    Used by the frontend for real-time validation feedback as the user types.
    Returns a list of resolved stat contributions (may be empty if unresolved).
    """
    results = _parse_custom_mod_text(req.text)
    resolved = [
        {
            **r,
            "display_name": _get_stat_display_name(r["stat_key"]) or r["stat_key"],
        }
        for r in results
    ]
    return {"text": req.text, "resolved": resolved}


@app.get("/api/legendary-gear")
def get_legendary_gear():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "items": []}
    data = season_manager.load_legendary_gear(active)
    if not data:
        return {"season": active, "items": []}

    _resolve = _resolve_affix

    # New crawler format: items have "variants" dict
    if data.get("items") and data["items"][0].get("variants"):
        items = []
        for item in data.get("items", []):
            resolved = {k: v for k, v in item.items() if k not in ("variants", "random_affixes")}
            resolved["variants"] = {
                state: {
                    "implicits": [_resolve(a) for a in v.get("implicits", [])],
                    "explicits": [_resolve(a) for a in v.get("explicits", [])],
                }
                for state, v in item.get("variants", {}).items()
            }
            resolved["random_affixes"] = {
                state: [
                    {**entry, "options": [_resolve(o) for o in entry.get("options", [])]}
                    for entry in pool
                ]
                for state, pool in item.get("random_affixes", {}).items()
            }
            items.append(resolved)
        return {"season": active, "items": items}

    # Legacy flat format
    items = data.get("items", [])
    for item in items:
        for affix in item.get("affixes", []):
            resolved = _resolve(affix)
            affix.update({k: resolved[k] for k in ("stat_key", "unit") if k in resolved})
            for extra_key in ("stat_keys", "is_range_split", "min_stat_keys", "max_stat_keys", "dual_stat_groups"):
                if extra_key in resolved:
                    affix[extra_key] = resolved[extra_key]
    return {"season": active, "items": items}


@app.get("/api/divinity-slates")
def get_divinity_slates():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "items": []}
    data = season_manager.load_divinity_slates(active)
    if not data:
        return {"season": active, "items": []}
    return {"season": active, "items": data.get("items", [])}


@app.delete("/api/dev/hero-traits")
def clear_hero_traits():
    active = season_manager.get_active_season()
    if active:
        season_manager.delete_hero_traits(active)
    return {"ok": True}


# ── Pact Spirits ───────────────────────────────────────────────────────────────

class ImportCrawlerPactSpiritsRequest(BaseModel):
    season_name: str
    items: list[dict]


@app.post("/api/dev/import-crawler-pact-spirits")
def import_crawler_pact_spirits_endpoint(req: ImportCrawlerPactSpiritsRequest):
    from tools.pact_spirit_importer import import_crawler_spirits
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    spirits = import_crawler_spirits(req.items)
    season_manager.save_pact_spirits(req.season_name, {
        "season": req.season_name,
        "spirit_count": len(spirits),
        "spirits": spirits,
    })
    return {"ok": True, "count": len(spirits)}


@app.get("/api/pact-spirits")
def get_pact_spirits():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "spirits": []}
    data = season_manager.load_pact_spirits(active)
    if not data:
        return {"season": active, "spirits": []}
    return {"season": active, "spirits": data.get("spirits", [])}


@app.delete("/api/dev/pact-spirits")
def clear_pact_spirits():
    active = season_manager.get_active_season()
    if active:
        season_manager.delete_pact_spirits(active)
    return {"ok": True}


# ── Craft Base Types ───────────────────────────────────────────────────────────

class ImportCrawlerCraftBaseTypesRequest(BaseModel):
    season_name: str
    items: list[dict]


@app.post("/api/dev/import-crawler-craft-base-types")
def import_crawler_craft_base_types_endpoint(req: ImportCrawlerCraftBaseTypesRequest):
    from tools.craft_base_type_importer import import_crawler_craft_base_types
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    base_types = import_crawler_craft_base_types(req.items)
    season_manager.save_craft_base_types(req.season_name, {
        "season": req.season_name,
        "type_count": len(base_types),
        "base_types": base_types,
    })
    # Also save lightweight base-items-only file (no affix pools)
    base_items_only = [
        {"item_id": bt["item_id"], "name": bt["name"], "base_items": bt["base_items"]}
        for bt in base_types
    ]
    season_manager.save_craft_base_items(req.season_name, {
        "season": req.season_name,
        "base_types": base_items_only,
    })
    global _craft_bases_cache
    _craft_bases_cache = None  # invalidate so next request re-resolves
    return {"ok": True, "count": len(base_types)}


_craft_bases_cache: list | None = None
_craft_bases_cache_season: str | None = None

_skills_cache: dict[str, dict] | None = None  # item_id → skill dict
_skills_cache_season: str | None = None


def _get_skills_data(season: str) -> dict[str, dict]:
    global _skills_cache, _skills_cache_season
    if _skills_cache is not None and _skills_cache_season == season:
        return _skills_cache
    raw = season_manager.load_skills(season)
    if not raw:
        _skills_cache = {}
        _skills_cache_season = season
        return _skills_cache
    _skills_cache = {item["item_id"]: item for item in raw.get("skills", []) if "item_id" in item}
    _skills_cache_season = season
    return _skills_cache


def _resolve_craft_base_types(base_types: list) -> list:
    for bt in base_types:
        for affix in bt.get("affixes", []):
            if affix.get("affix_kind") in ("special", "placeholder"):
                continue
            resolved = _resolve_affix(affix)
            affix.update({k: resolved[k] for k in ("stat_key", "unit") if k in resolved})
            for extra_key in ("stat_keys", "is_range_split", "min_stat_keys", "max_stat_keys", "dual_stat_groups"):
                if extra_key in resolved:
                    affix[extra_key] = resolved[extra_key]
        for affix in bt.get("corrosion_base_affixes", []):
            if affix.get("affix_kind") in ("special", "placeholder"):
                continue
            resolved = _resolve_affix(affix)
            affix.update({k: resolved[k] for k in ("stat_key", "unit") if k in resolved})
            for extra_key in ("stat_keys", "is_range_split", "min_stat_keys", "max_stat_keys", "dual_stat_groups"):
                if extra_key in resolved:
                    affix[extra_key] = resolved[extra_key]
    return base_types


@app.get("/api/craft-base-types")
def get_craft_base_types():
    global _craft_bases_cache, _craft_bases_cache_season
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "base_types": []}
    if _craft_bases_cache is not None and _craft_bases_cache_season == active:
        return {"season": active, "base_types": _craft_bases_cache}
    data = season_manager.load_craft_base_types(active)
    if not data:
        return {"season": active, "base_types": []}
    base_types = _resolve_craft_base_types(data.get("base_types", []))
    _craft_bases_cache = base_types
    _craft_bases_cache_season = active
    return {"season": active, "base_types": base_types}


@app.get("/api/craft-base-items")
def get_craft_base_items():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "base_types": []}
    data = season_manager.load_craft_base_items(active)
    if not data:
        return {"season": active, "base_types": []}
    return {"season": active, "base_types": data.get("base_types", [])}


class ResolveGearAffixesRequest(BaseModel):
    texts: list[str]

@app.post("/api/resolve-gear-affixes")
def resolve_gear_affixes(req: ResolveGearAffixesRequest):
    """Batch-resolve raw affix texts to stat fields. Used to refresh stale saved gear."""
    results: dict[str, dict] = {}
    for raw_text in req.texts:
        if not raw_text or raw_text in results:
            continue
        resolved = _resolve_affix({"raw_text": raw_text, "affix_kind": "numeric"})
        entry: dict = {"stat_key": resolved.get("stat_key"), "unit": resolved.get("unit", "")}
        for k in ("stat_keys", "is_range_split", "min_stat_keys", "max_stat_keys", "dual_stat_groups"):
            if k in resolved:
                entry[k] = resolved[k]
        results[raw_text] = entry
    return {"results": results}


class MapModifierItem(BaseModel):
    key: str
    text: str
    source: str                  # "gear" | "spirit" | "memory" | "talent" | "slate"
    node_id: str | None = None


class MapModifiersRequest(BaseModel):
    items: list[MapModifierItem]


def _affix_stat_keys(resolved: dict) -> list[str]:
    """Collect every stat key a resolved gear affix maps to (single/multi/range/dual), de-duped."""
    keys: list[str] = []
    if resolved.get("stat_key"):
        keys.append(resolved["stat_key"])
    for k in ("stat_keys", "min_stat_keys", "max_stat_keys"):
        keys.extend(resolved.get(k) or [])
    for g in (resolved.get("dual_stat_groups") or []):
        keys.extend(g.get("stat_keys") or [])
    seen: set[str] = set()
    out: list[str] = []
    for s in keys:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _resolve_skill_line_keys(text: str) -> list[str]:
    """Stat key(s) a structured tooltip line (skill/support, source='skill') resolves to — for badges.
    Tries the support mapper (handles "for the supported skill" damage/capture/conditional lines, with a
    permissive condition set so gated lines still resolve) and falls back to the unified node resolver
    for general skill stat phrasing. Empty list → the badge shows 'Unrecognized (NYI)'."""
    from engine.support_lines import SupportLine, _template
    from engine.support_mapper import map_line, _ADDED_FLAT_RE
    from engine.node_resolver import resolve_effect_text_keys
    # Buff-grant lines ("Buffs grant +X% … to this skill") describe a granted buff the engine applies as a
    # normal supported-skill modifier (e.g. Electric Overload's on-crit +15% Lightning). Normalize the wording
    # so the line resolves like the direct "+X% … for the supported skill" form instead of badging NYI.
    text = re.sub(r'^\s*buffs?\s+grants?\s+', '', text, flags=re.I)
    text = re.sub(r'\bto (?:this|the supported) skill\b', 'for the supported skill', text, flags=re.I)
    # A skill's OWN line uses "for this skill" where the support mapper expects "for the supported skill"
    # (e.g. Chain Lightning "+2 Jumps for this skill"). Normalize so the same stat resolves either way.
    text = re.sub(r'\bfor this skill\b', 'for the supported skill', text, flags=re.I)
    # Strip a "(the) (supported) skill's" possessive that sits between a parser keyword and its operand
    # (e.g. "Converts 50% of the supported skill's Lightning Damage to Cold Damage" → "… of Lightning Damage
    # to Cold Damage"), so conversion/added-flat lines resolve to their stat instead of badging NYI.
    text = re.sub(r"\b(?:the\s+)?(?:supported\s+)?skill['’]s\s+", '', text, flags=re.I)
    tmpl = _template(text)
    # "adds X-Y <type> Damage" added-flat line → per-cat flat stats. Return BOTH cats so the badge
    # matches whichever the supported skill uses (classifyKeys checks .some()).
    m = _ADDED_FLAT_RE.search(tmpl)
    if m and "damage" in tmpl:
        d = m.group(1)
        return [f"{d}_{c}_dmg_flat_{mm}" for c in ("attack", "spell") for mm in ("min", "max")]
    # All gating conditions ON so conditional damage lines (cursed/numbed/fervor/blessing/ignite) resolve.
    permissive = {"enemy_cursed": True, "enemy_numbed": True, "numbed_stacks": 10, "fervor_rating": 100,
                  "focus_blessings": 4, "ignite_stacks": 5, "ailment_type_count": 3,
                  "standing_still": True, "willpower_stacks": 6}
    line = SupportLine(text=text, template=tmpl, scaling=False)
    keys = [c.stat_key for c in map_line(line, 20, None, permissive)]   # cat=None: skip added-flat (handled above)
    if keys:
        return keys
    # Fallback: the unified node resolver maps the stat phrasing itself via stat_meta (which already honors the
    # increased-vs-additional pool and the damage type). It doesn't understand the "for/of the (supported) skill"
    # support-target phrase, so strip it (prefix or suffix) first. This recovers minion/penetration/etc. lines
    # map_line doesn't cover, with NO per-stat table — the parser decides the exact stat from the bare phrasing.
    bare = re.sub(r'^\s*the supported skill\s+', '', text, flags=re.I)
    bare = re.sub(r'\s+(?:for|of)\s+(?:the supported|this) skill\b.*$', '', bare, flags=re.I).strip()
    return resolve_effect_text_keys(bare, _parse_custom_mod_text, _translate_condition_expr)


@app.post("/api/map-modifiers")
def map_modifiers(req: MapModifiersRequest):
    """Map raw modifier texts (spirit / memory / talent / slate) to the engine stat key(s) they
    resolve to, so the renderer can flag modifiers whose stat the engine doesn't recognize and
    cross-check the rest against the build's consumed_stats. Deterministic per data version (the
    frontend caches the result). Reuses the exact engine resolvers — no parallel logic.

    Gear/vorax already carry stat_key on the affix object, so they need not be sent; `source:
    'gear'` is still handled (via _resolve_affix) for completeness.
    """
    from engine.node_resolver import resolve_effect_text_keys

    results: dict[str, dict] = {}
    for it in req.items:
        if it.key in results:
            continue
        if it.source in ("spirit", "memory"):
            keys = resolve_effect_stat_keys(it.text, is_memory=(it.source == "memory"))
        elif it.source in ("talent", "slate"):
            # SAME unified resolver the engine uses (engine.node_resolver) — no more filter-builder recipes,
            # so node badges can't drift from the actual DPS contribution. node_id is irrelevant now.
            keys = resolve_effect_text_keys(it.text, _parse_custom_mod_text, _translate_condition_expr)
        elif it.source == "skill":
            keys = _resolve_skill_line_keys(it.text)
        elif it.source == "gear":
            keys = _affix_stat_keys(_resolve_affix({"raw_text": it.text, "affix_kind": "numeric"}))
        else:
            keys = []
        results[it.key] = {"stat_keys": keys}
    return {"results": results}


@app.delete("/api/dev/craft-base-types")
def clear_craft_base_types():
    global _craft_bases_cache
    _craft_bases_cache = None
    active = season_manager.get_active_season()
    if active:
        season_manager.delete_craft_base_types(active)
    return {"ok": True}


# ── Grafts ─────────────────────────────────────────────────────────────────────

class ImportCrawlerGraftsRequest(BaseModel):
    season_name: str
    items: list[dict]


@app.post("/api/dev/import-crawler-grafts")
def import_crawler_grafts_endpoint(req: ImportCrawlerGraftsRequest):
    from tools.graft_importer import import_crawler_grafts
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    grafts = import_crawler_grafts(req.items)
    season_manager.save_grafts(req.season_name, {
        "season": req.season_name,
        "graft_count": len(grafts),
        "grafts": grafts,
    })
    return {"ok": True, "count": len(grafts)}


def _resolve_grafts(grafts: list) -> list:
    """Attach stat resolution fields to graft affixes (same as legendary/craft) so vorax items
    carry stat_key like other gear and flow through the same modifier-status check."""
    for g in grafts:
        for key in ("base_affixes", "affixes"):
            for affix in g.get(key, []):
                if affix.get("affix_kind") in ("special", "placeholder"):
                    continue
                resolved = _resolve_affix(affix)
                affix.update({k: resolved[k] for k in ("stat_key", "unit") if k in resolved})
                for extra_key in ("stat_keys", "is_range_split", "min_stat_keys", "max_stat_keys", "dual_stat_groups"):
                    if extra_key in resolved:
                        affix[extra_key] = resolved[extra_key]
    return grafts


@app.get("/api/grafts")
def get_grafts():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "grafts": []}
    data = season_manager.load_grafts(active)
    if not data:
        return {"season": active, "grafts": []}
    return {"season": active, "grafts": _resolve_grafts(data.get("grafts", []))}


@app.delete("/api/dev/grafts")
def clear_grafts():
    active = season_manager.get_active_season()
    if active:
        season_manager.delete_grafts(active)
    return {"ok": True}


# ── Belt Blends (Blending Rituals) ───────────────────────────────────────────────

class ImportCrawlerBeltBlendsRequest(BaseModel):
    season_name: str
    data: dict   # the full blending_rituals.json: {entries: [...], glossary: [...]}


@app.post("/api/dev/import-crawler-belt-blends")
def import_crawler_belt_blends_endpoint(req: ImportCrawlerBeltBlendsRequest):
    from tools.belt_blend_importer import import_crawler_belt_blends
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    result = import_crawler_belt_blends(req.data)
    season_manager.save_belt_blends(req.season_name, {"season": req.season_name, **result})
    return {"ok": True, "count": result["blend_count"]}


@app.get("/api/belt-blends")
def get_belt_blends():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "blends": [], "glossary": {}}
    data = season_manager.load_belt_blends(active)
    if not data:
        return {"season": active, "blends": [], "glossary": {}}
    return {"season": active, "blends": data.get("blends", []), "glossary": data.get("glossary", {})}


@app.delete("/api/dev/belt-blends")
def clear_belt_blends():
    active = season_manager.get_active_season()
    if active:
        season_manager.delete_belt_blends(active)
    return {"ok": True}


# ── Singletons ─────────────────────────────────────────────────────────────────

class ImportSingletonRequest(BaseModel):
    season_name: str
    data: dict


@app.post("/api/dev/import-destiny")
def import_destiny_endpoint(req: ImportSingletonRequest):
    from tools.singleton_importer import import_destiny
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    parsed = import_destiny(req.data, req.season_name)
    season_manager.save_destiny(req.season_name, parsed)
    return {"ok": True, "count": parsed["item_count"]}


@app.get("/api/destiny")
def get_destiny():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "items": []}
    data = season_manager.load_destiny(active)
    if not data:
        return {"season": active, "items": []}
    return {"season": active, "items": data.get("items", [])}


@app.post("/api/dev/import-ethereal-prism")
def import_ethereal_prism_endpoint(req: ImportSingletonRequest):
    from tools.singleton_importer import import_ethereal_prism
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    parsed = import_ethereal_prism(req.data, req.season_name)
    season_manager.save_ethereal_prism(req.season_name, parsed)
    return {"ok": True, "count": parsed["modifier_count"]}


@app.get("/api/ethereal-prism")
def get_ethereal_prism():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "modifiers": []}
    data = season_manager.load_ethereal_prism(active)
    if not data:
        return {"season": active, "modifiers": []}
    return {"season": active, "modifiers": data.get("modifiers", [])}


@app.post("/api/dev/import-hero-memories")
def import_hero_memories_endpoint(req: ImportSingletonRequest):
    from tools.singleton_importer import import_hero_memories
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    parsed = import_hero_memories(req.data, req.season_name)
    season_manager.save_hero_memories(req.season_name, parsed)
    return {"ok": True, "count": parsed["affix_count"]}


@app.get("/api/hero-memories")
def get_hero_memories():
    active = season_manager.get_active_season()
    empty = {"season": None, "memory_types": [], "fixed_affixes": [], "random_affixes": [], "base_stats": []}
    if not active:
        return empty
    data = season_manager.load_hero_memories(active)
    if not data:
        return {**empty, "season": active}
    return {
        "season": active,
        "memory_types": data.get("memory_types", []),
        "fixed_affixes": data.get("fixed_affixes", []),
        "random_affixes": data.get("random_affixes", []),
        "base_stats": data.get("base_stats", []),
    }


@app.post("/api/dev/import-memory-revival")
def import_memory_revival_endpoint(req: ImportSingletonRequest):
    from tools.singleton_importer import import_memory_revival
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    parsed = import_memory_revival(req.data, req.season_name)
    season_manager.save_memory_revival(req.season_name, parsed)
    return {"ok": True, "count": parsed["affix_count"]}


@app.get("/api/memory-revival")
def get_memory_revival():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "affixes": []}
    data = season_manager.load_memory_revival(active)
    if not data:
        return {"season": active, "affixes": []}
    return {"season": active, "affixes": data.get("affixes", [])}


@app.post("/api/dev/import-tower-sequence")
def import_tower_sequence_endpoint(req: ImportSingletonRequest):
    from tools.singleton_importer import import_tower_sequence
    if not req.season_name.strip():
        raise HTTPException(400, "season_name must not be empty")
    parsed = import_tower_sequence(req.data, req.season_name)
    season_manager.save_tower_sequence(req.season_name, parsed)
    return {"ok": True, "count": parsed["entry_count"]}


@app.get("/api/tower-sequence")
def get_tower_sequence():
    active = season_manager.get_active_season()
    if not active:
        return {"season": None, "entries": []}
    data = season_manager.load_tower_sequence(active)
    if not data:
        return {"season": active, "entries": []}
    return {"season": active, "entries": data.get("entries", [])}


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


# ── Dev: data inspector ───────────────────────────────────────────────────────

from dev.inspect import router as _inspect_router
app.include_router(_inspect_router)

# ── Dev: condition manager ────────────────────────────────────────────────────

from dev.conditions import router as _conditions_router
app.include_router(_conditions_router)


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
