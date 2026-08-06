"""
Imports crawler tree JSON into the season-stored tree format.
"""

import re

from engine.modifier_lines import slim

# "(Max Divinity Effect: N)" — identity/display-bearing suffix marking a once-per-Divinity-Slate cap.
# It STAYS in the stored text; we also parse N structurally so the engine can enforce the cap from a
# field instead of regex-matching English at aggregation time.
_MAX_DIV_N_RE = re.compile(r"\(Max Divinity Effect:\s*(\d+)[^)]*\)\s*$", re.I)


def _effect_line(e) -> dict:
    """Slim stored modifier line for a tree/core effect, with the structured Max-Divinity cap."""
    out = slim(e)
    m = _MAX_DIV_N_RE.search(out["text"])
    if m:
        out["max_divinity_effect"] = int(m.group(1))
    return out


# ── Crawler format importer ────────────────────────────────────────────────────

_CRAWLER_TYPE_MAP = {
    "micro_talent":            "Micro Talent",
    "medium_talent":           "Medium Talent",
    "legendary_medium_talent": "Legendary Medium Talent",
}


def _make_display_name_key(tree_name: str, talent_name: str) -> str:
    tree_slug = tree_name.lower().replace(" ", "_")
    talent_slug = re.sub(r"[^a-z0-9]+", "_", talent_name.lower()).strip("_")
    return f"{tree_slug}_{talent_slug}"


def import_crawler_tree(crawler_data: dict, tree_name: str) -> dict:
    tree_slug = tree_name.lower().replace(" ", "_")
    raw_nodes = crawler_data.get("nodes", [])

    # Build talent_id → node_id map for prerequisite resolution
    tid_to_node_id: dict[str, str] = {}
    for node in raw_nodes:
        tid = node.get("talent_id", "")
        col, row = node.get("column"), node.get("row")
        if tid and col is not None and row is not None:
            tid_to_node_id[tid] = f"{tree_slug}_c{col - 1}_r{row - 1}"

    regular_nodes: list[dict] = []
    core_talents: list[dict] = []
    edge_set: set[frozenset] = set()

    glossary_dict = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (crawler_data.get("glossary") or [])
        if g.get("term_id")
    }

    for node in raw_nodes:
        ntype = node.get("type", "")
        col, row = node.get("column"), node.get("row")

        if ntype == "core_talent":
            raw_name = node.get("name", "")
            core_talents.append({
                "display_name_key": _make_display_name_key(tree_name, raw_name),
                "name": raw_name,
                "uuid": node.get("uuid"),
                "effects": [_effect_line(e) for e in (node.get("effects") or [])],
                "pts_required": node.get("pts_required"),
                "icon_url": node.get("icon_url", ""),
            })
            continue

        mapped_type = _CRAWLER_TYPE_MAP.get(ntype)
        if mapped_type is None or col is None or row is None:
            continue

        node_id = f"{tree_slug}_c{col - 1}_r{row - 1}"
        regular_nodes.append({
            "id": node_id,
            "uuid": node.get("uuid"),
            "column": col - 1,
            "row": row - 1,
            "node_type": mapped_type,
            "max_rank": node.get("max_rank") or 1,
            "effects": [_effect_line(e) for e in (node.get("effects") or [])],
            "pts_required": node.get("pts_required"),
            "icon_url": node.get("icon_url", ""),
        })

        for prereq_tid in (node.get("prerequisites") or []):
            prereq_id = tid_to_node_id.get(prereq_tid)
            if prereq_id:
                edge_set.add(frozenset({prereq_id, node_id}))

    regular_nodes.sort(key=lambda n: (n["column"], n["row"]))

    connections = []
    for edge in edge_set:
        ids = sorted(edge)
        if len(ids) == 2:
            connections.append({"from": ids[0], "to": ids[1]})
    connections.sort(key=lambda c: (c["from"], c["to"]))

    return {
        "tree_name": tree_name,
        "uuid": crawler_data.get("uuid"),
        "total_points": crawler_data.get("total_points"),
        "tags": crawler_data.get("tags", []),
        "glossary": glossary_dict,
        "nodes": regular_nodes,
        "connections": connections,
        "core_talents": core_talents,
    }
