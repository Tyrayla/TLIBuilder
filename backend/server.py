import argparse
import json
import os
import re
import socket
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
import uvicorn

from models.passive_tree import PassiveTree
from models.passive_node import PassiveNode, NodeType
from persistence import save_manager, builds_manager
from persistence import tree_config_manager
from persistence import season_manager
import build_code as _build_code

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'data'))
_TREES_META_PATH = os.path.join(_DATA_ROOT, 'trees_meta.json')
with open(_TREES_META_PATH) as _f:
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
        with open(_PHRASE_OVERRIDES_PATH) as f:
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
        {
            "threshold": slot.threshold,
            "options": [
                {"id": opt.id, "name": opt.name, "effects": opt.effects,
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


class EngineStatsRequest(BaseModel):
    slots:           list[SlotData | None]
    slates:          list[dict] = []
    condition_state: dict[str, float | bool] = {}
    gear:            list[dict] = []
    character:       list[dict] = []
    memory_effects:  list[str] = []
    spirit_effects:  list[str] = []
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

    skills_input = [{"slot": s.slot, "skill_id": s.skill_id, "level": s.level} for s in req.skills]

    # Pre-resolve custom mods and build status list for the frontend
    custom_contributions: list[dict] = []
    custom_mod_statuses: list[dict] = []
    for mod_text in req.custom_mods:
        parsed = _parse_custom_mod_text(mod_text)
        if parsed:
            # Each parsed entry becomes a contribution; all share the same original text
            for entry in parsed:
                custom_contributions.append(entry)
            display_names = [
                _get_stat_display_name(e["stat_key"]) or e["stat_key"] for e in parsed
            ]
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

    # Resolve the main skill's attached supports into stat contributions (additional-damage lines)
    # plus behavioral effects (shotgun falloff / chains-per-jump).
    support_contributions: list[dict] = []
    support_behavior: dict = {}
    if req.attached_supports:
        from engine.support_resolver import resolve_support_contributions, resolve_support_behavior
        support_contributions = resolve_support_contributions(req.attached_supports, skills_by_id)
        support_behavior = resolve_support_behavior(req.attached_supports, skills_by_id)

    # Resolve granted core talents (tree / slate / legendary / belt blend), deduped to count each
    # exactly once, into stat contributions + base-effect override flags. Flags ride in condition_state
    # so the aggregator's blessing/Numbed override loops pick them up. (roadmap #4)
    from engine.core_talent_resolver import resolve_core_talents
    belt_blends_data = season_manager.load_belt_blends(active_season) or {}
    core_contributions, core_flags, core_talent_statuses = resolve_core_talents(
        slots, slates, req.gear, season_trees, belt_blends_data,
        _parse_custom_mod_text, _translate_condition_expr,
    )
    core_condition_state = {**req.condition_state, **{flag: True for flag in core_flags}}
    # Seed player level (for per-level scaling like Brutality) unless the user set it explicitly.
    if req.characterLevel is not None and "level" not in req.condition_state:
        core_condition_state["level"] = float(req.characterLevel)

    # Cardinal rule — never silently drop. Resolve any gear affix/implicit the frontend couldn't
    # (crafted base resistances/life/attributes, etc.), inject it as a contribution on that item, and
    # report every line (resolved or not) so the UI can surface anything still unmodeled.
    gear_resolved: list[dict] = []
    gear_mod_statuses: list[dict] = []
    for gi in req.gear:
        texts = gi.get("unresolved_texts") or []
        if not texts:
            gear_resolved.append(gi)
            continue
        gi = dict(gi)
        contribs = list(gi.get("contributions") or [])
        for t in texts:
            parsed = _parse_custom_mod_text(t)
            if parsed:
                for e in parsed:
                    contribs.append({"stat": e["stat_key"], "display_value": e["amount"], "unit": "",
                                     "item_name": gi.get("item_name") or "Gear", "text": t,
                                     "slot": None, "condition": None})
                names = ", ".join(_get_stat_display_name(e["stat_key"]) or e["stat_key"] for e in parsed)
                gear_mod_statuses.append({"text": t, "resolved": True, "stat_display": names})
            else:
                gear_mod_statuses.append({"text": t, "resolved": False, "stat_display": None})
        gi["contributions"] = contribs
        gear_resolved.append(gi)

    build = BuildInput(
        slots=slots, slates=slates, season=active_season,
        condition_state=core_condition_state,
        gear=gear_resolved, character=req.character,
        memory_effects=req.memory_effects, spirit_effects=req.spirit_effects,
        main_skill=main_skill,
        custom_contributions=custom_contributions,
        attached_support_contributions=support_contributions,
        support_behavior=support_behavior,
        attached_supports=req.attached_supports,
        core_talent_contributions=core_contributions,
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
        "skill_slots": result.skill_slots,
        "consumed_stats": result.consumed_stats,
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
    return {"season": active, "skills": data.get("skills", [])}


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

_GEAR_STOP_WORDS = {"of", "the", "a", "an", "to", "by", "from", "with", "and", "or", "in", "on", "per", "second"}
_GEAR_NORMALIZE_MAP = {
    "regenerates": "regeneration",
    "regenerate":  "regeneration",
    "reduces":     "reduction",
    "reduce":      "reduction",
    "splits":      "split",
}
_GEAR_COND_RE = re.compile(
    r"\s+(?:while\b|when\b|if\b|against\b|recently\b|on\s+hit\b|upon\b|"
    r"for\s+every\b|for\s+each\b)",
    re.I,
)

_EXPRESSION_STAT_OVERRIDES: dict[str, str] = {
    # Flat-count core-talent lines whose in-game wording differs from the stat's gear display name
    # (reached value-stripped via the trailing-count handler in _parse_custom_mod_text).
    "max sentry quantity":  "max_sentry_quantity_flat",
    "min channeled stacks": "min_channeled_stacks_flat",
    "+(#) gear armor":   "armor_gear_flat",
    "+(#) % gear armor": "armor_gear_inc",
    "+(#) gear evasion":   "evasion_gear_flat",
    "+(#) % gear evasion": "evasion_gear_inc",
    # Damage conversion — physical
    "adds (#) % of physical damage as lightning damage": "physical_as_lightning",
    "adds (#) % of physical damage to cold damage":      "physical_as_cold",
    "adds (#) % of physical damage as cold damage":      "physical_as_cold",
    "adds (#) % of physical damage as fire damage":      "physical_as_fire",
    "adds (#) % of physical damage as erosion damage":   "physical_as_erosion",
    # Damage conversion — elemental to erosion
    "adds (#) % of lightning damage as erosion damage":  "lightning_as_erosion",
    "adds (#) % of cold damage as erosion damage":       "cold_as_erosion",
    "adds (#) % of fire damage as erosion damage":       "fire_as_erosion",
    # Damage conversion — adds-as gaps (up-chain: lightning→cold/fire, cold→fire)
    "adds (#) % of lightning damage as cold damage":     "lightning_as_cold",
    "adds (#) % of lightning damage as fire damage":     "lightning_as_fire",
    "adds (#) % of cold damage as fire damage":          "cold_as_fire",
    # Damage conversion — convert (reduces source). "converts (#)% of A damage to B damage".
    "converts (#) % of physical damage to lightning damage": "physical_convert_to_lightning",
    "converts (#) % of physical damage to cold damage":      "physical_convert_to_cold",
    "converts (#) % of physical damage to fire damage":      "physical_convert_to_fire",
    "converts (#) % of physical damage to erosion damage":   "physical_convert_to_erosion",
    "converts (#) % of lightning damage to cold damage":     "lightning_convert_to_cold",
    "converts (#) % of lightning damage to fire damage":     "lightning_convert_to_fire",
    "converts (#) % of lightning damage to erosion damage":  "lightning_convert_to_erosion",
    "converts (#) % of cold damage to fire damage":          "cold_convert_to_fire",
    "converts (#) % of cold damage to erosion damage":       "cold_convert_to_erosion",
    "converts (#) % of fire damage to erosion damage":       "fire_convert_to_erosion",
    # Damage taken conversion
    "converts (#) % of physical damage taken to lightning damage": "physical_taken_as_lightning_inc",
    "converts (#) % of physical damage taken to cold damage":      "physical_taken_as_cold_inc",
    "converts (#) % of physical damage taken to fire damage":      "physical_taken_as_fire_inc",
    "converts (#) % of erosion damage taken to lightning damage":  "erosion_taken_as_lightning_inc",
    "converts (#) % of erosion damage taken to cold damage":       "erosion_taken_as_cold_inc",
    "converts (#) % of erosion damage taken to fire damage":       "erosion_taken_as_fire_inc",
    # Mana/life
    "(#) % of damage is taken from mana before life":    "mana_before_life_inc",
    # Attack / ranged
    "+(#) % ranged damage":                              "ranged_dmg_inc",
    # Skill levels
    "+(#) main skill level":                             "main_skill_level",
    # Channeled
    "min channeled stacks +(#)":                         "min_channeled_stacks_flat",
    # Terra
    "max terra charge stacks +(#)":                      "max_terra_charge_stacks_flat",
    "+(#) % terra charge recovery speed":                "terra_charge_recovery_speed_inc",
    "max terra quantity +(#)":                           "max_terra_quantity_flat",
    # Warcry
    "+(#) max warcry skill charges":                     "max_warcry_skill_charges_flat",
    # Shadow
    "shadow quantity +(#)":                              "max_shadow_quantity_flat",
    # Ignite
    "+(#) ignite limit":                                 "max_ignite_flat",
    # Ailment durations
    "+(#) % ailment duration":                           "ailment_duration_inc",
    "+(#) % ignite duration":                            "ignite_duration_inc",
    # Spirit magi
    "+(#) initial growth for spirit magi":               "spirit_magi_initial_growth_flat",
    # Elixir
    "elixir skills gain (#) charging progress every second":    "elixir_charging_progress_flat",
    "elixir skills gain (#) of charging progress every second": "elixir_charging_progress_flat",
    # Minion
    "minion damage penetrates (#) % elemental resistance": "minion_elemental_pen",
    "+(#) % minion elemental damage":                    "minion_elemental_dmg_inc",
    # Hit/taunt — "on hit" is stripped by _GEAR_COND_RE before dict lookup
    "+(#) % chance for attacks to inflict taunt on enemies": "attack_taunt_on_hit_chance",
    "+(#) % chance for attacks to taunt":                   "attack_taunt_on_hit_chance",
    # Curse
    "-(#)-(#) % curse effect against you":               "curse_effect_against_inc",
    # Damage to life
    "(#) % additional damage applied to life":           "dmg_to_life_additional",
    # Defense additional
    "+(#) % additional armor":                           "armor_additional",
    "+(#) % additional evasion":                         "evasion_additional",
    "+(#) % additional max life":                        "max_life_additional",
    "+(#) % additional armor while moving":              "armor_additional",
    "+(#) % armor effective rate for non-physical damage": "armor_effective_rate_non_physical_inc",
    # Ailment additional
    "+(#) % additional trauma damage":                   "trauma_dmg_additional",
    "+(#) % additional wilt damage":                     "wilt_dmg_additional",
    "+(#) % additional ignite damage":                   "ignite_dmg_additional",
    # Affliction
    "+(#) affliction inflicted per second":              "affliction_per_second_flat",
    # Sentry
    "max sentry quantity +(#)":                          "max_sentry_quantity_flat",
    # Barrage
    "barrage skills +(#) % damage increase per wave":    "barrage_dmg_per_wave_inc",
    # Warcry (text variant with prefix "Warcry is cast immediately")
    "warcry is cast immediately +(#) max warcry skill charges": "max_warcry_skill_charges_flat",
    # Defense
    "+(#) % additional defense gained from shield":      "shield_defense_additional",
    # Tangle (single value)
    "+(#) % tangle damage enhancement":                  "tangle_dmg_inc",
    # Shadow damage
    "+(#) % additional shadow damage":                   "shadow_dmg_additional",
    # Spell burst hit damage (single value)
    "+(#) % additional hit damage for skills cast by spell burst": "spell_burst_hit_dmg_additional",
    # Critical Strike Rating — gear-specific % (scales gear flat only) and main-hand weapon
    "+(#) % attack critical strike rating for this gear":          "attack_crit_rating_gear",
    "+(#) % critical strike rating for the main-hand weapon":      "attack_crit_rating_mh",
    # Flat defense — "maximum X" fuzzy-matches the derived stat key; override to the raw flat input stat
    "+(#) maximum life":             "max_life_flat",
    "+(#) to maximum life":          "max_life_flat",
    "+(#) maximum mana":             "max_mana_flat",
    "+(#) to maximum mana":          "max_mana_flat",
    "+(#) maximum energy shield":    "energy_shield_gear_flat",
    "+(#) to maximum energy shield": "energy_shield_gear_flat",
}

_MULTI_STAT_OVERRIDES: dict[str, list[str]] = {
    "+(#) % attack and cast speed": ["attack_speed_inc", "cast_speed_inc"],
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
        (["max_curse_flat"], ["curse_effect_inc"]),
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

_GEAR_SUFFIX_RE = re.compile(r"\s+(?:(?:for|to)\s+this\s+gear|to\s+the\s+gear)\s*$", re.I)

_gear_candidates: list | None = None


def _gear_normalize(text: str) -> set[str]:
    text = _GEAR_SUFFIX_RE.sub("", text)
    clean = re.sub(r"[^a-z\s]", " ", text.lower())
    return {_GEAR_NORMALIZE_MAP.get(w, w) for w in clean.split()
            if w not in _GEAR_STOP_WORDS and not re.fullmatch(r"\d+", w)}


def _get_gear_candidates() -> list:
    global _gear_candidates
    if _gear_candidates is None:
        from models.stat_meta import STAT_META
        _gear_candidates = []
        for stat, meta in STAT_META.items():
            # Drop pool-qualifier words from the candidate's display words too, so a name like
            # "Additional Minion Damage" matches on {minion, damage} and the pool is decided solely by
            # modifier_type (kept separately) — never by the word "additional" appearing in the name.
            words = _gear_normalize(meta.display_name) - _POOL_QUALIFIER_WORDS
            if words:
                _gear_candidates.append((stat.value, meta.display_name, words, meta.unit, meta.modifier_type))
    return _gear_candidates


# Words that appear in both singular and plural forms in raw affix text.
# All override dict keys use the singular canonical form.
# Add new pairs here as they're discovered from raw game data.
_EXPR_WORD_CANON: dict[str, str] = {
    "splits":    "split",
    "tangle(s)": "tangle",
    "stack(s)":  "stack",
}


def _norm_expr(text: str) -> str:
    """Normalize an affix expression for dict lookup."""
    # Normalize unicode dashes (en dash U+2013, em dash U+2014) to regular hyphen first
    s = text.replace("–", "-").replace("—", "-")
    s = s.replace(",", " ")  # remove commas (e.g., "Life, Mana, and Energy Shield")
    s = re.sub(r"\d+(?:\.\d+)?", "#", s.lower()).strip()
    s = re.sub(r"\(#-#\)", "(#)", s)        # collapse ranged value "(#-#)" → "(#)"
    s = re.sub(r"(?<!\()#(?!\))", "(#)", s) # wrap bare # not already in parens → "(#)"
    s = re.sub(r"\s*%\s*", " % ", s)        # normalize spaces around %
    s = re.sub(r"\s+-\s+", "-", s)          # collapse spaced dashes: "(#) - (#)" → "(#)-(#)"
    s = re.sub(r"\s+", " ", s).strip()
    # normalize plural/singular word variants
    words = s.split(" ")
    s = " ".join(_EXPR_WORD_CANON.get(w, w) for w in words)
    return s


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

# Custom mod text parsing — freeform modifier text → stat contributions
_CUSTOM_RANGE_RE  = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s+(.*)', re.IGNORECASE)
_CUSTOM_SINGLE_RE = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)\s*(%?)\s+(.*)', re.IGNORECASE)
# "Adds N-N <Type> Damage to <Attacks|Spells|Attacks and Spells>" → flat <type>_<dest>_dmg_flat_min/max.
# (The leading word "Adds" means the generic number-first patterns above don't match.)
_CUSTOM_ADDS_RE = re.compile(
    r'^\s*adds\s+([\d.]+)\s*[-–]\s*([\d.]+)\s+(physical|fire|cold|lightning|erosion)\s+damage\s+to\s+'
    r'(attacks and spells|attacks|spells)\b', re.IGNORECASE)
# Modifier verbs that appear in game text but not in stat display names — strip before fuzzy match
_CUSTOM_VERB_RE   = re.compile(r'\b(increased|reduced|more|less)\b', re.IGNORECASE)


def _normalize_for_custom_resolve(text: str) -> str:
    """Strip gaming modifier verbs so the fuzzy matcher aligns with stat display names."""
    return re.sub(r'\s+', ' ', _CUSTOM_VERB_RE.sub('', text)).strip()


def _parse_custom_mod_text(text: str) -> list[dict]:
    """Resolve freeform modifier text to a list of {stat_key, amount, text} dicts.

    Routes through the existing gear stat resolver so all supported modifier text
    forms work, including percentage-based mods, flat adds, and ranges.
    Returns an empty list if the text cannot be resolved.

    Scale is determined by whether the user explicitly typed '%' — not by the stat's
    metadata unit — so that raw flat stats (CSR, flat damage) are not accidentally
    divided by 100.
    """
    t = text.strip()

    # Some core-talent lines prefix the stat with its subsystem before the value ("Spirit Magi +30% …").
    # Drop that leading subsystem label so the value is start-anchored for the matchers below; the stat's
    # display name still carries the subsystem, so resolution is unaffected.
    t = re.sub(r'^\s*Spirit Mag(?:i|us)\s+(?=[+\-]?\d)', '', t, flags=re.I)

    # Leading qualifier/scope word before the value ("Additional -30% X", "Enemies +20% X"): move it after
    # the value so the start-anchored matchers see the number first; the word stays for pool/scope matching.
    t = re.sub(r'^(Additional|Enemies)\s+([+\-]?[\d.]+\s*%?)', r'\2 \1', t, flags=re.I)

    # "You can cast N additional Curses" → Max Curses (a flat count; "additional" here means +N, not the
    # damage pool, so the generic matchers would mishandle it).
    m = re.match(r'(?:you can cast\s+)?([\d.]+)\s+additional\s+curses?\b', t, re.I)
    if m:
        return [{"stat_key": "max_curses_flat", "amount": float(m.group(1)), "text": t}]

    # Outgoing damage-type conversion: "Adds/Converts N% [of] <A> Damage as/to <B> Damage" (the value sits
    # after the verb, so the start-anchored matchers below would miss it). "Adds"/"as" → adds-as key;
    # "Converts"/"to" → convert key. Only valid up the priority chain (phys→light→cold→fire→erosion).
    m = re.match(r'(adds|converts)\s+([\d.]+)\s*%\s*(?:of\s+)?'
                 r'(physical|lightning|cold|fire|erosion)\s+damage\s+(?:as|to)\s+'
                 r'(physical|lightning|cold|fire|erosion)\s+damage', t, re.I)
    if m:
        verb, val, src, dst = m.group(1).lower(), float(m.group(2)), m.group(3).lower(), m.group(4).lower()
        order = ["physical", "lightning", "cold", "fire", "erosion"]
        if order.index(dst) > order.index(src):           # up-chain only
            key = f"{src}_convert_to_{dst}" if verb == "converts" else f"{src}_as_{dst}"
            return [{"stat_key": key, "amount": val / 100.0, "text": t}]
        return []

    # Arcane: "Converts N% of Mana Cost to Life Cost" — active-skill cost paid as life (cost mechanic,
    # tracked; needs skill-cost modeling to do anything).
    m = re.match(r'converts\s+([\d.]+)\s*%\s*of\s+mana\s+cost\s+to\s+life\s+cost', t, re.I)
    if m:
        return [{"stat_key": "mana_cost_to_life_cost", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Ward: "Adds N% of Sealed Mana/Life as Energy Shield" — flat Max ES = coeff × raw sealed pool (needs
    # sealed mana/life modeling).
    m = re.match(r'adds\s+([\d.]+)\s*%\s*of\s+sealed\s+(mana|life)\s+as\s+energy\s+shield', t, re.I)
    if m:
        return [{"stat_key": f"energy_shield_per_sealed_{m.group(2).lower()}", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Joined Force: "Adds N% of the damage of the Off-Hand Weapon to the final damage of the Main-Hand Weapon"
    # — off-hand becomes a stat-stick; N% of its fully-scaled damage adds to main-hand FINAL (needs separate
    # main/off-hand weapon damage modeling).
    m = re.match(r'adds\s+([\d.]+)\s*%\s*of\s+the\s+damage\s+of\s+the\s+off-?hand\s+weapon', t, re.I)
    if m:
        return [{"stat_key": "joined_force_offhand_dmg", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Defensive damage-taken conversion: "Converts N% of <A> Damage taken to <B> Damage" (the "taken" is what
    # distinguishes it from outgoing). Needs the incoming-damage/EHP model to do anything (tracked for now).
    m = re.match(r'converts\s+([\d.]+)\s*%\s*of\s+(physical|lightning|cold|fire|erosion)\s+damage\s+taken\s+to\s+'
                 r'(physical|lightning|cold|fire|erosion)\s+damage', t, re.I)
    if m:
        return [{"stat_key": f"{m.group(2).lower()}_taken_as_{m.group(3).lower()}_inc", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Rebirth: "Converts N% of <Life|Energy Shield> Regain to Restoration Over Time" — needs Regain. The
    # shared-stat splitter separates "Life Regain and Energy Shield Regain", so match each pool segment.
    m = re.match(r'converts\s+([\d.]+)\s*%\s*of\s+(life|energy\s+shield)\s+regain\s+to\s+restoration', t, re.I)
    if m:
        pool = "es" if m.group(2).lower().startswith("energy") else "life"
        return [{"stat_key": f"{pool}_regain_to_restoration", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Co-resonance: share Attack/Cast Speed (inc + additional) onto Sentry Cast Frequency — needs Sentry impl.
    m = re.match(r'(attack|cast)\s+speed\s+bonus\s+and\s+.*additional\s+bonus\s+are\s+also\s+applied\s+to', t, re.I)
    if m:
        which = m.group(1).lower()
        key = "attack_speed_to_attack_sentry_cast_freq" if which == "attack" else "cast_speed_to_spell_sentry_cast_freq"
        return [{"stat_key": key, "amount": 1.0, "text": t}]

    # Play Safe: "N% of the bonuses and additional bonuses to Cast Speed is also applied to Spell Burst Charge
    # Speed" — flag (1.0 = full share); the aggregator propagates cast-speed inc + each additional.
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+bonuses\s+and\s+additional\s+bonuses\s+to\s+cast\s+speed\s+is\s+also\s+applied\s+to\s+spell\s+burst', t, re.I)
    if m:
        return [{"stat_key": "cast_speed_to_spell_burst_charge", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Gale: "N% of the Projectile Speed bonus is also applied to the additional bonus for Projectile Damage"
    # — coefficient on increased projectile speed → additional projectile damage (own factor; aggregator).
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+projectile\s+speed\s+bonus\s+is\s+also\s+applied\s+to\s+the\s+additional\s+bonus\s+for\s+projectile\s+damage', t, re.I)
    if m:
        return [{"stat_key": "proj_speed_to_proj_dmg", "amount": float(m.group(1)) / 100.0, "text": t}]

    # True Flame: "N% of the additional bonus to Damage Over Time taken from Affliction is also applied to your
    # Fire Hit Damage" (lead "When an enemy is Ignited" splits off as the gate). Inert until Affliction modeled.
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+additional\s+bonus\s+to\s+damage\s+over\s+time\s+taken\s+from\s+affliction\s+is\s+also\s+applied\s+to\s+your\s+fire\s+hit\s+damage', t, re.I)
    if m:
        return [{"stat_key": "affliction_dot_to_fire_hit", "amount": float(m.group(1)) / 100.0, "text": t}]

    # United Stand (2nd line): "N% of the Life and Energy Shield Regain Effect of Synthetic Troop Minions is
    # also applied to you" — fraction of minion regain shared to the player. Needs Regain + testing.
    m = re.match(r'([\d.]+)\s*%\s*of\s+the\s+life\s+and\s+energy\s+shield\s+regain\s+effect\s+of\s+synthetic\s+troop\s+minions\s+is\s+also\s+applied\s+to\s+you', t, re.I)
    if m:
        return [{"stat_key": "minion_regain_shared_to_player", "amount": float(m.group(1)) / 100.0, "text": t}]

    # Probabilistic damage ("…N% chance for that cast to deal +M% additional damage") → expected value.
    # Emit one dmg_additional = (N/100)×(M/100) with a SHARED text so a talent's mutually-exclusive tiers
    # pool ADDITIVELY into one factor (offense sums same-identity positives), never multiply.
    m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*chance\b.*?\bdeal\s*\+?(\d+(?:\.\d+)?)\s*%\s*additional\s+damage', t, re.I)
    if m:
        ev = (float(m.group(1)) / 100.0) * (float(m.group(2)) / 100.0)
        return [{"stat_key": "dmg_additional", "amount": ev,
                 "text": "probabilistic additional damage (expected value)"}]

    # "You can apply N additional Tangle(s) to enemies" → flat +N Tangles applied (mirrors the curses form).
    m = re.match(r'(?:you can\s+)?apply\s+([\d.]+)\s+additional\s+tangles?\b', t, re.I)
    if m:
        return [{"stat_key": "extra_tangle_applied_flat", "amount": float(m.group(1)), "text": t}]

    # Trailing flat count: "<Stat Name> +N" (Max Sentry Quantity +1, Min Channeled Stacks +1). Resolve the
    # value-stripped name; accept ONLY a *_flat stat so a stray "+N" can never land in a % pool.
    m = re.match(r'^(.+?)\s+([+\-]\d+(?:\.\d+)?)\s*$', t)
    if m and '%' not in t:
        stat_key, _u = _resolve_gear_stat(m.group(1).strip())
        if stat_key and stat_key.endswith('_flat'):
            return [{"stat_key": stat_key, "amount": float(m.group(2)), "text": t}]

    # "Adds N-N <Type> Damage to Attacks/Spells/Attacks and Spells" → flat added damage min+max.
    m = _CUSTOM_ADDS_RE.match(t)
    if m:
        lo, hi, dtype, dest = float(m.group(1)), float(m.group(2)), m.group(3).lower(), m.group(4).lower()
        dests = ["attack", "spell"] if dest == "attacks and spells" else (["attack"] if dest == "attacks" else ["spell"])
        out: list[dict] = []
        for d in dests:
            out.append({"stat_key": f"{dtype}_{d}_dmg_flat_min", "amount": lo, "text": t})
            out.append({"stat_key": f"{dtype}_{d}_dmg_flat_max", "amount": hi, "text": t})
        return out

    # Range: "50-80 fire attack damage"
    m = _CUSTOM_RANGE_RE.match(t)
    if m:
        val_min = float(m.group(1))
        val_max = float(m.group(2))
        desc = _normalize_for_custom_resolve(m.group(3).strip())
        stat_key, _unit = _resolve_gear_stat(desc)
        if stat_key:
            if stat_key.endswith("_min"):
                base = stat_key[:-4]
                return [
                    {"stat_key": base + "_min", "amount": val_min, "text": t},
                    {"stat_key": base + "_max", "amount": val_max, "text": t},
                ]
            if stat_key.endswith("_max"):
                base = stat_key[:-4]
                return [
                    {"stat_key": base + "_min", "amount": val_min, "text": t},
                    {"stat_key": base + "_max", "amount": val_max, "text": t},
                ]
            avg = (val_min + val_max) / 2.0
            return [{"stat_key": stat_key, "amount": avg, "text": t}]
        return []

    # Single value: "10% additional attack damage" or "500 attack crit rating flat"
    m = _CUSTOM_SINGLE_RE.match(t)
    if m:
        val = float(m.group(1))
        is_pct = bool(m.group(2))
        normalized = _normalize_for_custom_resolve(t)
        stat_key, _unit = _resolve_gear_stat(normalized)
        if stat_key:
            amount = val / 100.0 if is_pct else val
            return [{"stat_key": stat_key, "amount": amount, "text": t}]

    return []


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
    # "against enemies with Max Affliction" → existing enemy_has_max_affliction condition.
    (re.compile(r"with\s+max\s+affliction|enem(?:y|ies)\s+(?:with|has|have)\s+max\s+affliction", re.I), "enemy_has_max_affliction"),
    (re.compile(r"not\s+wielding\s+a\s+wand\s+or\s+tin\s+staff", re.I), {"not": "wielding_wand_or_tin_staff"}),
    (re.compile(r"wielding\s+a\s+wand\s+or\s+tin\s+staff", re.I), "wielding_wand_or_tin_staff"),
    # Attribute comparisons (Tradeoff) — auto-derived from STR vs DEX in the compute loop.
    (re.compile(r"dexterity\s+is\s+no\s+less\s+than\s+strength", re.I), "dexterity_ge_strength"),
    (re.compile(r"strength\s+is\s+no\s+less\s+than\s+dexterity", re.I), "strength_ge_dexterity"),
    # Numeric movement threshold
    (re.compile(r"moved\s+more\s+than\s+(\d+)\s*m\b", re.I), lambda m: {"key": "meters_moved_recently", "op": ">", "value": int(m.group(1))}),
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
            return expr(m) if callable(expr) else expr
    return None


# TLI's "additional" (independent multiplicative) and "increased"/"reduced" (one additive pool) are
# DIFFERENT pools and must never be cross-matched — display names don't encode the qualifier, so the
# fuzzy matcher would otherwise map "additional X" onto an "increased X" stat. Map the qualifier word
# in the text to the stat modifier_type it is allowed to match.
_POOL_QUALIFIERS = {"additional": "additional", "increased": "increased", "reduced": "increased"}
_POOL_QUALIFIER_WORDS = frozenset(_POOL_QUALIFIERS)


def _resolve_gear_stat(raw_text: str) -> tuple[str | None, str]:
    """Return (stat_key, unit) for a gear affix, or (None, '') if unresolved.

    Pool-strict: an "additional" modifier only matches an `additional` stat, and
    "increased"/"reduced" only an `increased` stat. If the text carries a pool qualifier but no
    same-pool stat matches, the affix is left UNRESOLVED rather than silently placed in the wrong pool.
    """
    text = _GEAR_COND_RE.sub("", raw_text)
    norm_expr = _norm_expr(text)
    if norm_expr in _EXPRESSION_STAT_OVERRIDES:
        stat_key = _EXPRESSION_STAT_OVERRIDES[norm_expr]
        unit = "%" if "%" in raw_text else ""
        return stat_key, unit
    query = _gear_normalize(text)
    if not query:
        return None, ""
    # Detect the pool qualifier, then drop it from the query so it neither pollutes the word overlap
    # nor is required to appear in the (qualifier-free) display name.
    want_pool = next((_POOL_QUALIFIERS[w] for w in query if w in _POOL_QUALIFIERS), None)
    query = {w for w in query if w not in _POOL_QUALIFIERS}
    if not query:
        return None, ""
    is_pct = "%" in raw_text
    scores = []
    for stat_val, dn, dn_words, unit, mtype in _get_gear_candidates():
        if want_pool is not None and mtype != want_pool:
            continue   # pool-strict: never cross "additional" with "increased"
        overlap = len(query & dn_words)
        if not overlap:
            continue
        scores.append((overlap / len(query | dn_words), stat_val, dn, unit))
    if not scores:
        return None, ""
    scores.sort(key=lambda x: x[0], reverse=True)
    best_score, best_stat, best_dn, best_unit = scores[0]
    extra = query - _gear_normalize(best_dn)
    if best_score < (0.7 if extra else 0.5):
        return None, ""
    tied = [s for s in scores if s[0] == best_score]
    if len(tied) == 1:
        return best_stat, best_unit
    # Break ties within the matched pool (additional → _additional; else _inc for %, _flat otherwise).
    suffix = "_additional" if want_pool == "additional" else ("_inc" if is_pct else "_flat")
    pref = [s for s in tied if s[1].endswith(suffix)]
    return (pref[0][1], pref[0][3]) if len(pref) == 1 else (None, "")


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


@app.post("/api/map-modifiers")
def map_modifiers(req: MapModifiersRequest):
    """Map raw modifier texts (spirit / memory / talent / slate) to the engine stat key(s) they
    resolve to, so the renderer can flag modifiers whose stat the engine doesn't recognize and
    cross-check the rest against the build's consumed_stats. Deterministic per data version (the
    frontend caches the result). Reuses the exact engine resolvers — no parallel logic.

    Gear/vorax already carry stat_key on the affix object, so they need not be sent; `source:
    'gear'` is still handled (via _resolve_affix) for completeness.
    """
    import re as _re
    from engine.aggregator import resolve_effect_stat_keys
    from tools.node_type_filter_builder import load_filter

    filter_data = load_filter() or {}
    node_recipes = filter_data.get("node_recipes", {})

    def _norm(s: str) -> str:
        return _re.sub(r'\s+', ' ', (s or '').strip()).lower()

    def _node_keys(node_id: str | None, text: str) -> list[str]:
        if not node_id:
            return []
        nt = _norm(text)
        out: list[str] = []
        for r in (node_recipes.get(node_id) or []):
            if r.get("stat") and _norm(r.get("text", "")) == nt:
                out.append(r["stat"])
        return out

    results: dict[str, dict] = {}
    for it in req.items:
        if it.key in results:
            continue
        if it.source in ("spirit", "memory"):
            keys = resolve_effect_stat_keys(it.text, is_memory=(it.source == "memory"))
        elif it.source in ("talent", "slate"):
            keys = _node_keys(it.node_id, it.text)
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
