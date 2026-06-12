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
  statuses       list[dict]  {node_id, text, resolved, kind}  — one per effect segment, for UI badges
"""
from __future__ import annotations
import re

from engine.core_talent_resolver import (
    _strip_max_div, _split_condition, _split_compound, _expand_shared_stats,
    _classify_effect, _MAX_DIV_RE, _BASE_EFFECT_RE,
)

_NODE_ID_RE = re.compile(r"^(.+)_c\d+_r\d+$")

# Slate copy mechanics (mirrors engine.aggregator): Moth copies one neighbour's bottom slot; Prairie all four.
_COPY_SLATE_KINDS = frozenset({"spark_of_moth_fire", "when_sparks_set_prairie_ablaze"})
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
                key = re.sub(r"\s+", " ", _strip_max_div(eff).lower()).strip()
                if key in seen_maxdiv:
                    statuses.append({"node_id": node_id, "text": eff, "resolved": True, "kind": "deduped"})
                    continue
                seen_maxdiv.add(key)
            kept.append(eff)
        c, s = _resolve_node(node_id, kept, 1, label, "slate", parse_mod, translate_cond)
        contribs.extend(c)
        statuses.extend(s)

    position_to_slate: dict[tuple, dict] = {}
    for sl in slates or []:
        for pos in _slate_positions(sl):
            position_to_slate[pos] = sl

    for slate in slates or []:
        for slot in slate.get("slots", []) or []:
            nid = slot.get("selectedNodeId")
            if nid:
                _resolve_slate_node(nid, f"Slate · {nid}")

        # Moth/Prairie: copy the bottom slot of adjacent (non-copy) slates.
        if slate.get("kind", "base") not in _COPY_SLATE_KINDS:
            continue
        ar, ac = slate.get("anchor", [0, 0])
        if slate.get("kind") == "spark_of_moth_fire":
            d = _MOTH_DELTAS.get(slate.get("mothDirection"), None)
            checks = [(ar + d[0], ac + d[1])] if d else []
        else:
            checks = [(ar + dr, ac + dc) for dr, dc in _MOTH_DELTAS.values()]
        for pos in checks:
            adj = position_to_slate.get(pos)
            if not adj or adj.get("kind", "base") in _COPY_SLATE_KINDS:
                continue
            adj_slots = adj.get("slots", []) or []
            if not adj_slots:
                continue
            nid = adj_slots[-1].get("selectedNodeId")   # only the bottom slot is copied
            if nid:
                _resolve_slate_node(nid, f"Slate · Copy · {nid}")

    return contribs, statuses
