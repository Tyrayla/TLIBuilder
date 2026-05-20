from __future__ import annotations
import re
from engine.models import BuildInput, BuildSource


_ELEMENTAL_TYPES = {"fire", "cold", "lightning", "erosion"}

# node_id format: "{tree_slug}_c{col}_r{row}"
_NODE_ID_RE = re.compile(r"^(.+)_c\d+_r\d+$")


def _tree_slug_from_node_id(node_id: str) -> str | None:
    m = _NODE_ID_RE.match(node_id)
    return m.group(1) if m else None


def _apply_node_recipes(
    source: BuildSource,
    tree_name: str,
    node_id: str,
    current_points: int,
    max_points: int,
    node_type: str,
    recipes_by_tree: dict,
) -> None:
    """Look up recipes for tree+node_type and add stat values at the correct rank."""
    tree_recipes = recipes_by_tree.get(tree_name, {})
    type_recipes = tree_recipes.get(node_type, [])
    if not type_recipes:
        return

    rank_index = max(0, min(current_points - 1, len(type_recipes[0].get("values", [1])) - 1))

    for recipe in type_recipes:
        values = recipe.get("values", [])
        if not values:
            continue
        idx = min(rank_index, len(values) - 1)
        source.add(recipe["stat"], values[idx])


def aggregate(build: BuildInput, season_trees: dict[str, dict], filter_data: dict) -> BuildSource:
    """
    Collect all stat contributions from talent nodes and slates into a BuildSource.

    season_trees: {tree_slug: season_tree_dict} — pre-loaded season tree data
    filter_data:  the node_type_filter.json dict with a "recipes" key
    """
    source = BuildSource()
    recipes_by_tree = filter_data.get("recipes", {})

    # ── Talent tree nodes ──────────────────────────────────────────────────────
    for slot in build.slots:
        if not slot:
            continue

        tree_name: str = slot.get("treeName", "")
        node_states: dict[str, int] = slot.get("nodeStates", {})
        if not tree_name or not node_states:
            continue

        tree_slug = re.sub(r"[^a-z0-9]+", "_", tree_name.lower()).strip("_")
        season_tree = season_trees.get(tree_slug, {})
        nodes_by_id = {n["id"]: n for n in season_tree.get("nodes", [])}

        for node_id, current_points in node_states.items():
            if current_points <= 0:
                continue

            node = nodes_by_id.get(node_id)
            if not node:
                continue

            node_type = node.get("node_type", "")
            max_points = node.get("max_points", 1)
            _apply_node_recipes(
                source, tree_name, node_id, current_points, max_points, node_type, recipes_by_tree
            )

    # ── Slate slots ────────────────────────────────────────────────────────────
    # Each CreatorSlot can reference a talent node via selectedNodeId.
    # We treat it as a rank-1 (single point) application of that node's recipes.
    for slate in build.slates:
        for slot in slate.get("slots", []):
            node_id = slot.get("selectedNodeId")
            if not node_id:
                continue

            slug = _tree_slug_from_node_id(node_id)
            if not slug:
                continue

            # Resolve tree name from slug via season_trees keys
            season_tree = season_trees.get(slug, {})
            if not season_tree:
                continue

            tree_name = season_tree.get("tree_name", slug)
            nodes_by_id = {n["id"]: n for n in season_tree.get("nodes", [])}
            node = nodes_by_id.get(node_id)
            if not node:
                continue

            node_type = node.get("node_type", "")
            _apply_node_recipes(
                source, tree_name, node_id, 1, 1, node_type, recipes_by_tree
            )

    return source
