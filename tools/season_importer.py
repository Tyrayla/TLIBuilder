"""
Imports the game-data JSON format into a season-stored tree format.

JSON node fields used:
  global_node_id  — arbitrary old ID (e.g. "alchemist_031")
  tree            — tree slug (e.g. "alchemist")
  node_category   — "micro" | "medium" | "legendary_medium" | "core_talent"
  col             — 1-indexed column (col - 1 = internal column index)
  row             — 1-indexed row    (row - 1 = internal row index)
  max_stacks      — max_points for the node
  connections     — list of old IDs this node connects to
  prerequisites   — list of old IDs that must be allocated before this one
  effects         — list of raw modifier text strings
"""

import re


_NODE_CATEGORY_MAP = {
    "micro": "Micro Talent",
    "medium": "Medium Talent",
    "legendary_medium": "Legendary Medium Talent",
}


def make_node_id(tree_slug: str, col: int, row: int) -> str:
    """Both col and row are 1-indexed from the JSON."""
    return f"{tree_slug}_c{col - 1}_r{row - 1}"


def build_slug_map() -> dict[str, str]:
    """
    Returns a mapping of all known slug forms to a tree display name.

    Includes two aliases per tree:
      - full snake_case display name ("god_of_might" → "God of Might")
      - short node-prefix slug derived from season data ("might" → "God of Might")
    """
    import json
    import os
    from persistence import season_manager

    meta_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'trees_meta.json')
    with open(meta_path) as f:
        trees_meta: dict[str, dict] = json.load(f)

    active = season_manager.get_active_season()
    slug_map: dict[str, str] = {}

    for tree_name in trees_meta:
        full_slug = tree_name.lower().replace(" ", "_")
        slug_map[full_slug] = tree_name

        if active:
            data = season_manager.load_season_tree(active, full_slug)
            if data and data.get("nodes"):
                first_id = data["nodes"][0]["id"]
                m = re.match(r"^(.+)_c\d+_r\d+$", first_id)
                if m:
                    slug_map[m.group(1)] = tree_name

    return slug_map


def import_nodes(raw_nodes: list[dict], slug_map: dict[str, str]) -> dict[str, dict]:
    """
    Takes a flat list of raw node objects (from one or more JSON files) and
    returns a dict keyed by tree_slug with the processed season tree data.

    Output format per tree:
    {
      "tree_name": "Alchemist",
      "nodes": [{"id": ..., "column": ..., "row": ..., "node_type": ..., "max_points": ..., "effects": [...]}],
      "connections": [{"from": ..., "to": ...}],
      "core_talents": [{"display_name_key": ..., "effects": [...]}]
    }
    """
    # Phase 1: build old-ID → new col/row ID mapping
    id_map: dict[str, str] = {}
    for node in raw_nodes:
        old_id = node.get("global_node_id")
        category = node.get("node_category", "")
        col = node.get("col")
        row = node.get("row")
        tree_slug = node.get("tree", "")
        if category == "core_talent" or col is None or row is None:
            continue
        new_id = make_node_id(tree_slug, col, row)
        if old_id:
            id_map[old_id] = new_id

    # Phase 2: group nodes by tree slug
    by_slug: dict[str, dict] = {}

    def _get_tree_data(slug: str) -> dict:
        if slug not in by_slug:
            by_slug[slug] = {
                "tree_name": slug_map.get(slug, slug),
                "nodes": [],
                "connections": [],  # will store as set of frozensets, convert later
                "_edge_set": set(),
                "core_talents": [],
            }
        return by_slug[slug]

    for node in raw_nodes:
        slug = node.get("tree", "")
        category = node.get("node_category", "")
        col = node.get("col")
        row = node.get("row")
        old_id = node.get("global_node_id", "")
        effects = node.get("effects") or []
        max_stacks = node.get("max_stacks") or 1

        if category == "core_talent" or col is None or row is None:
            # Store as core talent raw data; capture name if present (may include apostrophes)
            td = _get_tree_data(slug)
            entry: dict = {
                "display_name_key": node.get("display_name_key", old_id),
                "effects": effects,
            }
            raw_name = node.get("name")
            if raw_name:
                entry["name"] = raw_name
            td["core_talents"].append(entry)
            continue

        node_type = _NODE_CATEGORY_MAP.get(category)
        if not node_type:
            continue  # unknown category — skip

        new_id = id_map.get(old_id)
        if not new_id:
            continue

        td = _get_tree_data(slug)
        td["nodes"].append({
            "id": new_id,
            "column": col - 1,
            "row": row - 1,
            "node_type": node_type,
            "max_points": max_stacks,
            "effects": effects,
        })

        # Collect edges: connections (this → other) + prerequisites (other → this)
        edge_set: set = td["_edge_set"]
        for other_old in (node.get("connections") or []):
            other_new = id_map.get(other_old)
            if other_new:
                edge_set.add(frozenset({new_id, other_new}))
        for prereq_old in (node.get("prerequisites") or []):
            prereq_new = id_map.get(prereq_old)
            if prereq_new:
                edge_set.add(frozenset({prereq_new, new_id}))

    # Phase 3: convert edge sets to sorted connection pairs and clean up
    result: dict[str, dict] = {}
    for slug, td in by_slug.items():
        connections = []
        for edge in td["_edge_set"]:
            ids = sorted(edge)
            if len(ids) == 2:
                connections.append({"from": ids[0], "to": ids[1]})
        td["connections"] = sorted(connections, key=lambda c: (c["from"], c["to"]))
        del td["_edge_set"]
        result[slug] = td

    return result


def extract_nodes_from_file(data: object) -> list[dict]:
    """
    Handles multiple JSON shapes:
      - Object with top-level "nodes" array: {"tree": "x", "nodes": [...]}
      - Raw array of node objects: [{"global_node_id": ...}, ...]
      - Array of tree objects each with "nodes": [{"tree":"x","nodes":[...]}, ...]
    """
    if isinstance(data, list):
        nodes: list[dict] = []
        for item in data:
            if isinstance(item, dict):
                if "global_node_id" in item:
                    nodes.append(item)
                elif "nodes" in item and isinstance(item["nodes"], list):
                    nodes.extend(item["nodes"])
        return nodes
    if isinstance(data, dict):
        if "nodes" in data and isinstance(data["nodes"], list):
            return data["nodes"]
    return []
