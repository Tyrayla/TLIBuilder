from __future__ import annotations
import re
from engine.models import BuildInput, BuildSource, SourceEntry


_ELEMENTAL_TYPES = {"fire", "cold", "lightning", "erosion"}

_NODE_TYPE_LABELS = {
    "micro": "Micro",
    "medium": "Medium",
    "legendary_medium": "Legendary",
}

def _node_type_display(node_type: str) -> str:
    return _NODE_TYPE_LABELS.get(node_type, node_type.replace("_", " ").title())

def _normalize_node_type(raw: str) -> str:
    """Normalize season node_type strings to filter recipe keys.

    Season data: "Micro Talent", "Medium Talent", "Legendary Medium Talent"
    Filter keys: "micro", "medium", "legendary_medium"
    """
    s = raw.lower().replace(" talent", "").strip().replace(" ", "_")
    return s

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
    source_type: str = "talent",
    label_prefix: str = "",
    node_recipes_by_id: dict | None = None,
) -> None:
    """Look up recipes for this specific node and add stat values at the correct rank.

    Lookup order:
      1. Per-node-id recipes (node_recipes_by_id[node_id]) — precise, specific to this node
      2. Tree+node_type fallback (recipes_by_tree[tree_name][node_type]) — coarse, for compat
    """
    per_node = (node_recipes_by_id or {}).get(node_id)
    if per_node is not None:
        type_recipes = per_node
    else:
        tree_recipes = recipes_by_tree.get(tree_name, {})
        type_recipes = tree_recipes.get(node_type, [])

    if not type_recipes:
        return

    rank_index = max(0, min(current_points - 1, len(type_recipes[0].get("values", [1])) - 1))
    label = f"{label_prefix}{_node_type_display(node_type)}"

    for recipe in type_recipes:
        values = recipe.get("values", [])
        if not values:
            continue
        idx = min(rank_index, len(values) - 1)
        entry = SourceEntry(
            stat=recipe["stat"],
            amount=values[idx],
            source_type=source_type,
            label=label,
            text=recipe.get("text", ""),
        )
        source.add_with_source(recipe["stat"], values[idx], entry)


def aggregate(build: BuildInput, season_trees: dict[str, dict], filter_data: dict) -> BuildSource:
    """
    Collect all stat contributions from talent nodes and slates into a BuildSource.

    season_trees: {tree_slug: season_tree_dict} — pre-loaded season tree data
    filter_data:  the node_type_filter.json dict with a "recipes" key
    """
    source = BuildSource()
    recipes_by_tree = filter_data.get("recipes", {})
    node_recipes_by_id = filter_data.get("node_recipes", {})

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

            node_type = _normalize_node_type(node.get("node_type", ""))
            max_points = node.get("max_points", 1)
            _apply_node_recipes(
                source, tree_name, node_id, current_points, max_points, node_type, recipes_by_tree,
                source_type="talent", label_prefix=f"{tree_name} ",
                node_recipes_by_id=node_recipes_by_id,
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

            node_type = _normalize_node_type(node.get("node_type", ""))
            _apply_node_recipes(
                source, tree_name, node_id, 1, 1, node_type, recipes_by_tree,
                source_type="slate", label_prefix=f"Slate — {tree_name} ",
                node_recipes_by_id=node_recipes_by_id,
            )

    return source
