"""
Imports crawler tree JSON into the season-stored tree format.
"""

import re

from engine.modifier_lines import slim

# "(Max Divinity Effect: N)" — identity/display-bearing suffix marking a once-per-Divinity-Slate cap.
# It STAYS in the stored text; we also parse N structurally so the engine can enforce the cap from a
# field instead of regex-matching English at aggregation time.
_MAX_DIV_N_RE = re.compile(r"\(Max Divinity Effect:\s*(\d+)[^)]*\)\s*$", re.I)
_HERO_TRAIT_SOURCE_RE = re.compile(r"\s*Source:\s*Hero Trait\s*-\s*(.+?)\s*$", re.I)
_TRAIT_SOURCE_METADATA = {
    "prophecy of revelation": {"trait_id": "wisdom_of_the_gods", "unlock_level": 60},
}


def _effect_line(e) -> dict:
    """Slim stored modifier line for a tree/core effect, with the structured Max-Divinity cap."""
    out = slim(e)
    m = _MAX_DIV_N_RE.search(out["text"])
    if m:
        out["max_divinity_effect"] = int(m.group(1))
    return out


def _trait_variant(node: dict) -> dict | None:
    """Return a complete replacement talent variant when a crawler row is hero-trait sourced."""
    source_name = None
    effects = []
    for effect in (node.get("effects") or []):
        text = effect.get("text", "") if isinstance(effect, dict) else str(effect or "")
        match = _HERO_TRAIT_SOURCE_RE.search(text)
        if match:
            source_name = match.group(1).strip()
            text = text[:match.start()].rstrip()
        # Re-minting is not possible at this boundary. Do not carry identity UUIDs across changed wording.
        effects.append(_effect_line(text) if not match else slim(text))
    if not source_name:
        return None
    metadata = _TRAIT_SOURCE_METADATA.get(source_name.casefold())
    if not metadata:
        # Preserve unsupported sourced variants in the data; the engine leaves them inactive until mapped.
        metadata = {"trait_id": None, "unlock_level": None}
    return {
        **metadata,
        "advanced_selection": source_name,
        "effects": effects,
    }


# ── Crawler format importer ────────────────────────────────────────────────────

_CRAWLER_TYPE_MAP = {
    "micro_talent":            "Micro Talent",
    "medium_talent":           "Medium Talent",
    "legendary_medium_talent": "Legendary Medium Talent",
}
_NETHER_KING_POOL_TYPES = {
    "micro_talent", "medium_talent", "legendary_medium_talent", "ultimate_talent",
}


def _make_display_name_key(tree_name: str, talent_name: str) -> str:
    tree_slug = tree_name.lower().replace(" ", "_")
    talent_slug = re.sub(r"[^a-z0-9]+", "_", talent_name.lower()).strip("_")
    return f"{tree_slug}_{talent_slug}"


def import_crawler_tree(crawler_data: dict, tree_name: str, existing_data: dict | None = None) -> dict:
    tree_slug = tree_name.lower().replace(" ", "_")
    raw_nodes = crawler_data.get("nodes", [])

    # Build talent_id → node_id map for prerequisite resolution
    tid_to_node_id: dict[str, str] = {}
    for node in raw_nodes:
        tid = node.get("talent_id", "")
        col, row = node.get("column"), node.get("row")
        if tid and col is not None and row is not None:
            tid_to_node_id[tid] = f"{tree_slug}_c{col - 1}_r{row - 1}"

    regular_nodes_by_pos: dict[tuple[int, int], dict] = {}
    core_talents: list[dict] = []
    edge_set: set[frozenset] = set()

    glossary_dict = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (crawler_data.get("glossary") or [])
        if g.get("term_id")
    }
    if existing_data:
        # A page-level markup change can make hover extraction return no terms. Keep known definitions and
        # overlay any newly crawled definitions so an incomplete crawl cannot erase glossary coverage.
        glossary_dict = {**(existing_data.get("glossary") or {}), **glossary_dict}

    for node in raw_nodes:
        ntype = node.get("type", "")
        col, row = node.get("column"), node.get("row")

        # Nether King's Divinity page is a flat slate-option pool, not a positioned tree. Older crawls
        # labeled these rows core_talent; SS14 labels them by pool rarity and leaves coordinates empty.
        # Keep them in core_talents because _collect_pool exposes this source as the Nether King core pool.
        if (tree_name.casefold() == "nether king" and col is None and row is None
                and ntype in _NETHER_KING_POOL_TYPES):
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

        pos = (col - 1, row - 1)
        node_id = f"{tree_slug}_c{pos[0]}_r{pos[1]}"
        variant = _trait_variant(node)
        existing = regular_nodes_by_pos.get(pos)
        if variant:
            if existing is None:
                # A source row may appear before its base row. Keep a placeholder and fill its base fields
                # when that row arrives; never turn the replacement into an always-active node.
                existing = {
                    "id": node_id,
                    "uuid": node.get("uuid"),
                    "column": pos[0],
                    "row": pos[1],
                    "node_type": mapped_type,
                    "max_rank": node.get("max_rank") or 1,
                    "effects": [],
                    "pts_required": node.get("pts_required"),
                    "icon_url": node.get("icon_url", ""),
                    "trait_variants": [],
                    "_variant_only": True,
                }
                regular_nodes_by_pos[pos] = existing
            existing.setdefault("trait_variants", []).append(variant)
            continue

        if existing and not existing.pop("_variant_only", False):
            raise ValueError(f"Multiple non-trait talent rows occupy {tree_name} position {pos}")
        base_node = {
            "id": node_id,
            "uuid": node.get("uuid"),
            "column": pos[0],
            "row": pos[1],
            "node_type": mapped_type,
            "max_rank": node.get("max_rank") or 1,
            "effects": [_effect_line(e) for e in (node.get("effects") or [])],
            "pts_required": node.get("pts_required"),
            "icon_url": node.get("icon_url", ""),
        }
        if existing:
            base_node["trait_variants"] = existing.get("trait_variants", [])
        regular_nodes_by_pos[pos] = base_node

        for prereq_tid in (node.get("prerequisites") or []):
            prereq_id = tid_to_node_id.get(prereq_tid)
            if prereq_id:
                edge_set.add(frozenset({prereq_id, node_id}))

    regular_nodes = sorted(regular_nodes_by_pos.values(), key=lambda n: (n["column"], n["row"]))
    for n in regular_nodes:
        n.pop("_variant_only", None)

    connections = []
    for edge in edge_set:
        ids = sorted(edge)
        if len(ids) == 2:
            connections.append({"from": ids[0], "to": ids[1]})
    connections.sort(key=lambda c: (c["from"], c["to"]))

    # Some TLIDB tree pages no longer expose the connection SVG, so the crawler emits empty prerequisite
    # lists. Retain known topology in that case, but filter stale edges against the newly imported node IDs.
    if not connections and existing_data:
        node_ids = {n["id"] for n in regular_nodes}
        preserved = set()
        for edge in existing_data.get("connections") or []:
            start, end = edge.get("from"), edge.get("to")
            if start in node_ids and end in node_ids and start != end:
                preserved.add((min(start, end), max(start, end)))
        connections = [{"from": start, "to": end} for start, end in sorted(preserved)]

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
