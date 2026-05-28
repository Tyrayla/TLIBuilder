from __future__ import annotations
import math
import re
from engine.models import BuildInput, BuildSource, SourceEntry
from models.stat_meta import STAT_META

# Build a lookup: (display_name_lower, is_percent) → stat key string
# Used to match hero memory modifier strings against known stats.
def _build_memory_lookup() -> dict[tuple[str, bool], str]:
    lookup: dict[tuple[str, bool], str] = {}
    for stat_enum, meta in STAT_META.items():
        is_pct = meta.unit == "%"
        key = (meta.display_name.lower(), is_pct)
        # Don't overwrite — first match wins (flat preferred for non-pct)
        if key not in lookup:
            lookup[key] = stat_enum.value
    return lookup

_MEMORY_STAT_LOOKUP: dict[tuple[str, bool], str] = _build_memory_lookup()
_MEMORY_EFFECT_RE = re.compile(r'^\+(\d+(?:\.\d+)?)\s*(%?)\s+(.+)$')

# Alias lookup: game display text differs from stat_meta display_name
_MEMORY_ALIAS_LOOKUP: dict[tuple[str, bool], str] = {
    ("critical strike damage for combo finishers", True): "combo_finisher_crit_dmg_inc",
}

# Multi-stat lookup: one modifier phrase → multiple stat keys (same value applied to each)
_MEMORY_MULTI_LOOKUP: dict[tuple[str, bool], list[str]] = {
    ("attack and cast speed", True):
        ["attack_speed_inc", "cast_speed_inc"],
    ("minion attack and cast speed", True):
        ["minion_attack_speed_inc", "minion_cast_speed_inc"],
    ("additional attack and cast speed for combo starters", True):
        ["combo_starter_attack_speed_additional", "combo_starter_cast_speed_additional"],
}


_ELEMENTAL_TYPES = {"fire", "cold", "lightning", "erosion"}

_NODE_TYPE_LABELS = {
    "micro": "Micro",
    "medium": "Medium",
    "legendary_medium": "Legendary",
}

_SLATE_KIND_LABELS = {
    "pedigree":                       "Pedigree",
    "fallen_starlight":               "Starlight",
    "corner_of_divinity":             "Corner",
    "spark_of_moth_fire":             "Moth",
    "when_sparks_set_prairie_ablaze": "Prairie",
}

_COPY_SLATE_KINDS = frozenset({"spark_of_moth_fire", "when_sparks_set_prairie_ablaze"})
_MOTH_DELTAS: dict[str, tuple[int, int]] = {
    "above": (-1, 0),
    "below": (1, 0),
    "left":  (0, -1),
    "right": (0, 1),
}

def _slate_positions(slate: dict) -> list[tuple[int, int]]:
    # cells are stored as absolute board positions, not relative offsets
    return [tuple(c) for c in slate.get("cells", [])]

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


def _eval_condition(
    expr,
    active_booleans: frozenset[str],
    numeric_vals: dict[str, float],
) -> bool | float:
    """Evaluate a condition expression.

    Returns True/False for boolean/comparison ops.
    Returns a float multiplier for 'per' scaling ops (0.0 means skip contribution).
    """
    if expr is None:
        return True
    if isinstance(expr, str):
        return expr in active_booleans
    if "and" in expr:
        return all(_eval_condition(e, active_booleans, numeric_vals) for e in expr["and"])
    if "or" in expr:
        return any(_eval_condition(e, active_booleans, numeric_vals) for e in expr["or"])
    if "not" in expr:
        return not _eval_condition(expr["not"], active_booleans, numeric_vals)
    if "op" in expr:
        op = expr["op"]
        if op == "per":
            divisor = float(expr.get("divisor", 1))
            val = numeric_vals.get(expr["key"], 0.0)
            return float(math.floor(val / divisor)) if divisor > 0 else 0.0
        lhs = numeric_vals.get(expr["key"], 0.0)
        rhs = expr["value"]
        return (lhs >= rhs if op == ">=" else lhs > rhs if op == ">" else
                lhs <= rhs if op == "<=" else lhs < rhs if op == "<" else
                lhs == rhs if op == "==" else False)
    return False


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
    points: int = 1,
    active_booleans: frozenset[str] = frozenset(),
    numeric_vals: dict[str, float] | None = None,
) -> None:
    """Look up recipes for this specific node and add stat values at the correct rank.

    Lookup order:
      1. Per-node-id recipes (node_recipes_by_id[node_id]) — precise, specific to this node
      2. Tree+node_type fallback (recipes_by_tree[tree_name][node_type]) — coarse, for compat
    """
    if numeric_vals is None:
        numeric_vals = {}

    per_node = (node_recipes_by_id or {}).get(node_id)
    if per_node is not None:
        type_recipes = per_node
    elif node_recipes_by_id:
        # Per-node filter exists but this node wasn't matched — no contribution
        return
    else:
        # Old filter without per-node data — fall back to tree-level aggregate
        tree_recipes = recipes_by_tree.get(tree_name, {})
        type_recipes = tree_recipes.get(node_type, [])

    if not type_recipes:
        return

    rank_index = max(0, min(current_points - 1, len(type_recipes[0].get("values", [1])) - 1))
    label = f"{label_prefix}{_node_type_display(node_type)}"

    for recipe in type_recipes:
        if not _eval_condition(recipe.get("condition"), active_booleans, numeric_vals):
            continue

        # Rank-based static values
        values = recipe.get("values", [])
        if values:
            idx = min(rank_index, len(values) - 1)
            entry = SourceEntry(
                stat=recipe["stat"],
                amount=values[idx],
                source_type=source_type,
                label=label,
                text=recipe.get("text", ""),
                points=points,
            )
            source.add_with_source(recipe["stat"], values[idx], entry)

        # Scaling contribution (additive on top of values, separate SourceEntry row)
        if "scaling" in recipe:
            s = recipe["scaling"]
            raw = numeric_vals.get(s["key"], 0.0)
            floor_val = s.get("floor", 0.0)
            eff = max(raw, floor_val) if floor_val is not None else raw
            if "per_n" in s:
                amount = (eff // s["per_n"]) * s["per"]
            else:
                amount = eff * s["per"]
            if s.get("cap") is not None:
                amount = min(amount, s["cap"])
            scale_entry = SourceEntry(
                stat=recipe["stat"],
                amount=amount,
                source_type=source_type,
                label=label,
                text=recipe.get("text", ""),
                points=points,
            )
            source.add_with_source(recipe["stat"], amount, scale_entry)


def aggregate(
    build: BuildInput,
    season_trees: dict[str, dict],
    filter_data: dict,
    active_booleans: frozenset[str] | None = None,
    numeric_vals: dict[str, float] | None = None,
) -> BuildSource:
    """
    Collect all stat contributions from talent nodes and slates into a BuildSource.

    season_trees:    {tree_slug: season_tree_dict} — pre-loaded season tree data
    filter_data:     the node_type_filter.json dict with a "recipes" key
    active_booleans: derived from build.condition_state by the fixed-point engine; if None,
                     derived here for backward-compat single-call usage
    numeric_vals:    numeric condition values (clamped) for scaling/threshold evaluation
    """
    source = BuildSource()

    if active_booleans is None:
        active_booleans = frozenset(
            k for k, v in build.condition_state.items()
            if isinstance(v, bool) and v
        )
    if numeric_vals is None:
        numeric_vals = {
            k: float(v) for k, v in build.condition_state.items()
            if not isinstance(v, bool) and isinstance(v, (int, float))
        }

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
                points=current_points,
                active_booleans=active_booleans,
                numeric_vals=numeric_vals,
            )

    # ── Slate slots ────────────────────────────────────────────────────────────
    # Each CreatorSlot can reference a talent node via selectedNodeId.
    # We treat it as a rank-1 (single point) application of that node's recipes.

    # Build a position→slate map for Moth/Prairie adjacency lookups.
    position_to_slate: dict[tuple[int, int], dict] = {}
    for _s in build.slates:
        for _pos in _slate_positions(_s):
            position_to_slate[_pos] = _s

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
            slate_kind = slate.get("kind", "base")
            if slate_kind == "base":
                tree_short = tree_name.split()[-1] if tree_name else tree_name
                slate_label_prefix = f"Slate · {tree_short} "
            else:
                kind_label = _SLATE_KIND_LABELS.get(slate_kind, slate_kind.replace("_", " ").title())
                slate_label_prefix = f"Slate · {kind_label} "
            _apply_node_recipes(
                source, tree_name, node_id, 1, 1, node_type, recipes_by_tree,
                source_type="slate", label_prefix=slate_label_prefix,
                node_recipes_by_id=node_recipes_by_id,
                active_booleans=active_booleans,
                numeric_vals=numeric_vals,
            )

        # ── Moth/Prairie copy ───────────────────────────────────────────────
        slate_kind = slate.get("kind", "base")
        if slate_kind not in _COPY_SLATE_KINDS:
            continue

        ar, ac = slate.get("anchor", [0, 0])
        if slate_kind == "spark_of_moth_fire":
            moth_dir = slate.get("mothDirection")
            if not moth_dir:
                continue
            dr, dc = _MOTH_DELTAS.get(moth_dir, (0, 0))
            positions_to_check = [(ar + dr, ac + dc)]
        else:  # when_sparks_set_prairie_ablaze — all 4 neighbours
            positions_to_check = [(ar + dr, ac + dc) for dr, dc in _MOTH_DELTAS.values()]

        kind_label = _SLATE_KIND_LABELS.get(slate_kind, slate_kind.replace("_", " ").title())

        for pos in positions_to_check:
            adj = position_to_slate.get(pos)
            if not adj or adj.get("kind", "base") in _COPY_SLATE_KINDS:
                continue  # missing or another copy-slate — skip
            adj_slots = adj.get("slots", [])
            if not adj_slots:
                continue
            # Only the bottom slot is copied (matches frontend getBottomEffects)
            adj_slot = adj_slots[-1]
            node_id = adj_slot.get("selectedNodeId")
            if not node_id:
                continue
            slug = _tree_slug_from_node_id(node_id)
            if not slug:
                continue
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
                source_type="slate", label_prefix=f"Slate · {kind_label} ",
                node_recipes_by_id=node_recipes_by_id,
                active_booleans=active_booleans,
                numeric_vals=numeric_vals,
            )

    # ── Equipped gear affixes ──────────────────────────────────────────────────
    for contrib in (c for item in build.gear for c in item.get("contributions", [])):
        stat = contrib.get("stat")
        if not stat:
            continue
        cond = contrib.get("condition")
        if cond is not None:
            cond_result = _eval_condition(cond, active_booleans, numeric_vals)
            if isinstance(cond_result, float):
                if cond_result == 0.0:
                    continue
                scaled = contrib.get("display_value", 0) * cond_result
                if isinstance(cond, dict) and "cap" in cond:
                    scaled = min(scaled, float(cond["cap"]))
                contrib = {**contrib, "display_value": scaled}
            elif not cond_result:
                continue
        val = contrib.get("display_value", 0)
        unit = contrib.get("unit", "")
        amount = val / 100.0 if unit == "%" else float(val)
        slot_label = (contrib.get("slot") or "item").replace("1", " 1").replace("2", " 2").title()
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="gear",
            label=f"Gear · {slot_label}",
            text=contrib.get("item_name", ""),
            points=1,
        )
        source.add_with_source(stat, amount, entry)

    # ── Character contributions (energy base/gear/level/prism) ─────────────────
    for contrib in build.character:
        stat = contrib.get("stat")
        if not stat:
            continue
        amount = float(contrib.get("amount", 0))
        entry = SourceEntry(
            stat=stat,
            amount=amount,
            source_type="character",
            label=f"Character · {contrib.get('label', '')}",
            text=contrib.get("text", ""),
            points=1,
        )
        source.add_with_source(stat, amount, entry)

    # ── Pact Spirit effects ───────────────────────────────────────────────────
    for effect in build.spirit_effects:
        effect = re.sub(r'\s+', ' ', effect.strip())
        m = _MEMORY_EFFECT_RE.match(effect)
        if not m:
            continue
        raw_val = float(m.group(1))
        is_pct = bool(m.group(2))
        stat_name = m.group(3).strip()
        stat_key = _MEMORY_STAT_LOOKUP.get((stat_name.lower(), is_pct))
        if not stat_key:
            continue
        amount = raw_val / 100.0 if is_pct else raw_val
        entry = SourceEntry(
            stat=stat_key,
            amount=amount,
            source_type="pact_spirit",
            label="Pact Spirit",
            text=effect,
            points=1,
        )
        source.add_with_source(stat_key, amount, entry)

    # ── Hero Memory effects ────────────────────────────────────────────────────
    for effect in build.memory_effects:
        effect = re.sub(r'\s+', ' ', effect.strip())
        # Split dual-stat modifiers like "+18 % Attack Speed +12 % Minion Speed"
        parts = re.split(r' (?=\+\d)', effect, maxsplit=1)
        for part in parts:
            m = _MEMORY_EFFECT_RE.match(part)
            if not m:
                continue
            raw_val = float(m.group(1))
            is_pct = bool(m.group(2))
            stat_name = m.group(3).strip()
            stat_name_lower = stat_name.lower()
            amount = raw_val / 100.0 if is_pct else raw_val
            # Try single-stat lookup (display_name)
            stat_key = _MEMORY_STAT_LOOKUP.get((stat_name_lower, is_pct))
            if not stat_key:
                stat_key = _MEMORY_ALIAS_LOOKUP.get((stat_name_lower, is_pct))
            if stat_key:
                entry = SourceEntry(
                    stat=stat_key,
                    amount=amount,
                    source_type="hero_memory",
                    label="Hero Memory",
                    text=effect,
                    points=1,
                )
                source.add_with_source(stat_key, amount, entry)
                continue
            # Try multi-stat lookup
            stat_keys = _MEMORY_MULTI_LOOKUP.get((stat_name_lower, is_pct))
            if stat_keys:
                for sk in stat_keys:
                    entry = SourceEntry(
                        stat=sk,
                        amount=amount,
                        source_type="hero_memory",
                        label="Hero Memory",
                        text=effect,
                        points=1,
                    )
                    source.add_with_source(sk, amount, entry)

    return source
