"""Resolve allocated talent-tree NODES and SLATE slots into engine stat contributions — through the ONE
unified resolver (server's `_parse_custom_mod_text` + the core-talent classification pipeline), replacing
the precomputed filter-builder recipes.

Each node effect is run through the same pipeline core talents use (`_classify_effect`: strip Max-Divinity →
split condition → split compound → expand shared-magnitude → parse + translate). Per-rank scaling is LINEAR
(recipe `values = [rank1, 2·rank1, 3·rank1]`), so a contribution's amount is the rank-1 value × the points
invested — the server pre-scales it here. Conditional effects carry a `condition_expr` and are GATED in the
aggregator (correct — recipes applied them always-on).

Slate slots resolve the same way at 1 point. "Max Divinity Effect: 1" is a SLATE DEDUP rule: each DISTINCT
effect text carrying that marker contributes ONCE across all slate slots (count-based — removing one of N
identical leaves the rest contributing; the damage + delta recompute from the full set, so this is correct).

Returns (contributions, statuses):
  contributions  list[dict]  {stat_key, amount, text, label, condition_expr|None}  (amount pre-scaled by points)
  statuses       list[dict]  {node_id, text, resolved, kind}  — one per effect segment (internal/tests only)

Badges no longer use these statuses: the UI resolves node/slate text on demand via /api/map-modifiers →
`resolve_effect_text_keys` (the SAME pipeline), then classifies against consumed_stats + consumable_universe.
"""
from __future__ import annotations
import re

from engine.core_talent_resolver import (
    _strip_max_div, _split_condition, _split_compound, _expand_shared_stats,
    _classify_effect, _MAX_DIV_RE, _BASE_EFFECT_RE,
)
from engine.affix_identity import affix_identity

_NODE_ID_RE = re.compile(r"^(.+)_c\d+_r\d+$")

# Slate copy mechanics. Moth/Prairie copy a neighbour's BOTTOM slot (Moth = one chosen direction, Prairie =
# all four). Space Rift/Residence copy a neighbour's MEDIUM-talent slots (Space Rift = one chosen L/R
# direction, incl. Legendary Medium; Residence = all four, Medium only — excludes Micro + Legendary Medium).
_COPY_SLATE_KINDS = frozenset({"spark_of_moth_fire", "when_sparks_set_prairie_ablaze",
                               "space_rift", "residence_of_stars"})
_ONE_DIR_COPY = frozenset({"spark_of_moth_fire", "space_rift"})   # copy from the single mothDirection neighbour
_MEDIUM_COPY = frozenset({"space_rift", "residence_of_stars"})    # copy Medium talents (vs the bottom slot)
_MOTH_DELTAS = {"above": (-1, 0), "below": (1, 0), "left": (0, -1), "right": (0, 1)}


def _slate_positions(slate: dict) -> list[tuple]:
    return [tuple(c) for c in slate.get("cells", []) or []]


def _tree_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def _slug_from_node_id(node_id: str) -> str:
    m = _NODE_ID_RE.match(node_id or "")
    return m.group(1) if m else ""


def _resolve_node(node_id: str, effects, points: int, label: str, source_text_tag: str,
                  parse_mod, translate_cond) -> tuple[list[dict], list[dict]]:
    """Resolve one allocated node's effects at `points`. Mirrors core_talent_resolver._resolve_talent but
    scales each contribution amount by `points` (linear per-rank) and tags pooling identity per node id."""
    contribs: list[dict] = []
    statuses: list[dict] = []
    for eff in effects or []:
        if not (eff or "").strip():
            continue
        text = _strip_max_div(eff)
        # Nodes don't carry core-talent base-effect overrides; if one appears, capture it (don't apply).
        if _BASE_EFFECT_RE.search(text):
            statuses.append({"node_id": node_id, "text": eff, "resolved": False, "kind": "deferred"})
            continue
        stat_clause, cond_clause = _split_condition(text)
        segments = _split_compound(stat_clause)
        subs = ([s + (" " + cond_clause if cond_clause else "") for s in segments]
                if len(segments) > 1 else [eff])
        subs = [x for sub in subs for x in _expand_shared_stats(sub)]
        for sub in subs:
            cls = _classify_effect(sub, parse_mod, translate_cond)
            if cls["kind"] == "stat":
                for c in cls["contribs"]:
                    contribs.append({
                        "stat_key": c["stat_key"],
                        "amount": c["amount"] * points,          # linear per-rank scaling
                        "text": f"{c.get('text', sub)} |{source_text_tag}|{node_id}",
                        "label": label,
                        "condition_expr": cls["condition_expr"],
                    })
                statuses.append({"node_id": node_id, "text": sub, "resolved": True, "kind": "stat"})
            else:
                statuses.append({"node_id": node_id, "text": sub, "resolved": False, "kind": cls["kind"]})
    return contribs, statuses


def resolve_effect_text_keys(text, parse_mod, translate_cond) -> list[str]:
    """Stat key(s) one node/slate effect LINE resolves to, via the unified pipeline — the exact path
    resolve_nodes uses, so badges never drift from the engine. Build-agnostic (no points/condition gating
    applied); empty list = unrecognized/deferred. Used by /api/map-modifiers for talent/slate badges."""
    contribs, _ = _resolve_node("__map__", [text], 1, "", "node", parse_mod, translate_cond)
    seen, out = set(), []
    for c in contribs:
        k = c["stat_key"]
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def resolve_nodes(slots, slates, season_trees, parse_mod, translate_cond):
    """Resolve all allocated tree nodes (× points) + slate slots (× 1, Max-Divinity-deduped) to contributions."""
    contribs: list[dict] = []
    statuses: list[dict] = []

    # ── Tree nodes ──────────────────────────────────────────────────────────────
    for slot in slots or []:
        if not slot:
            continue
        tree_name = slot.get("treeName", "")
        node_states = slot.get("nodeStates") or {}
        if not tree_name or not node_states:
            continue
        tree = (season_trees or {}).get(_tree_slug(tree_name)) or {}
        nodes_by_id = {n["id"]: n for n in tree.get("nodes", []) or []}
        for node_id, points in node_states.items():
            if not points or points <= 0:
                continue
            node = nodes_by_id.get(node_id)
            if not node:
                continue
            c, s = _resolve_node(node_id, node.get("effects") or [], int(points),
                                 f"{tree_name} · {node_id}", "node", parse_mod, translate_cond)
            contribs.extend(c)
            statuses.extend(s)

    # ── Slate slots (1 point) — with Max-Divinity-Effect-1 dedup ─────────────────
    # Each DISTINCT effect text carrying "(Max Divinity Effect: 1)" contributes once across ALL slate slots
    # (count-based; the damage + delta recompute from the full slate set, so removing one of N is correct).
    seen_maxdiv: set[str] = set()

    def _resolve_slate_node(node_id: str, label: str):
        tree = (season_trees or {}).get(_slug_from_node_id(node_id)) or {}
        node = {n["id"]: n for n in tree.get("nodes", []) or []}.get(node_id)
        if not node:
            return
        kept: list[str] = []
        for eff in node.get("effects") or []:
            if _MAX_DIV_RE.search(eff or ""):
                # Key by VALUE-STRIPPED identity so a "(Max Divinity Effect: 1)" effect counts once across
                # slates even if two slates grant it at different rolled values (the effect is gained once).
                key = affix_identity(_strip_max_div(eff))
                if key in seen_maxdiv:
                    statuses.append({"node_id": node_id, "text": eff, "resolved": True, "kind": "deduped"})
                    continue
                seen_maxdiv.add(key)
            kept.append(eff)
        c, s = _resolve_node(node_id, kept, 1, label, "slate", parse_mod, translate_cond)
        contribs.extend(c)
        statuses.extend(s)

    def _node_type(node_id: str) -> str:
        tree = (season_trees or {}).get(_slug_from_node_id(node_id)) or {}
        node = {n["id"]: n for n in tree.get("nodes", []) or []}.get(node_id)
        return (node or {}).get("node_type", "")

    position_to_slate: dict[tuple, dict] = {}
    for sl in slates or []:
        for pos in _slate_positions(sl):
            position_to_slate[pos] = sl

    for slate in slates or []:
        for slot in slate.get("slots", []) or []:
            nid = slot.get("selectedNodeId")
            if nid:
                _resolve_slate_node(nid, f"Slate · {nid}")

        kind = slate.get("kind", "base")
        if kind not in _COPY_SLATE_KINDS:
            continue
        # Footprint-based copy: look at every cell ADJACENT to any of this slate's own cells (one chosen
        # direction for Moth/Space Rift, all four for Prairie/Residence) and copy each distinct neighbour
        # slate once. Moth/Prairie copy its BOTTOM slot; Space Rift/Residence copy its MEDIUM talents
        # (Space Rift incl. Legendary Medium; Residence Medium only).
        dirs = ([_MOTH_DELTAS.get(slate.get("mothDirection"))] if kind in _ONE_DIR_COPY
                else list(_MOTH_DELTAS.values()))
        dirs = [d for d in dirs if d]
        medium_copy = kind in _MEDIUM_COPY
        medium_only = kind == "residence_of_stars"   # exclude Legendary Medium (and Micro)
        copied_ids: set = set()
        for cr, cc in (tuple(c) for c in slate.get("cells") or []):
            for dr, dc in dirs:
                adj = position_to_slate.get((cr + dr, cc + dc))
                if not adj or adj.get("kind", "base") in _COPY_SLATE_KINDS:
                    continue
                aid = adj.get("id") or id(adj)
                if aid in copied_ids:               # copy each neighbour slate once
                    continue
                copied_ids.add(aid)
                adj_slots = adj.get("slots", []) or []
                if not adj_slots:
                    continue
                if medium_copy:
                    for slot in adj_slots:
                        nid = slot.get("selectedNodeId")
                        if not nid:
                            continue
                        nt = _node_type(nid)
                        if "Medium Talent" not in nt:               # skip Micro Talents
                            continue
                        if medium_only and nt != "Medium Talent":   # Residence: skip Legendary Medium
                            continue
                        _resolve_slate_node(nid, f"Slate · Copy · {nid}")
                else:
                    nid = adj_slots[-1].get("selectedNodeId")       # Moth/Prairie: only the bottom slot
                    if nid:
                        _resolve_slate_node(nid, f"Slate · Copy · {nid}")

    return contribs, statuses
