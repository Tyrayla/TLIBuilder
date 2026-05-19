"""
Builds node_type_filter.json from a canonical talent snapshot.

Matches snapshot stat texts (e.g. "+9% Attack Damage") to Stat enum values
using Jaccard-like word-overlap scoring against STAT_META display names.

Output: data/node_type_filter.json
  stats    — {stat_value: [node_types that carry it]}
  recipes  — {tree: {node_type: [{stat, rank1, values}]}}
  unresolved — [{tree, node_type, text}] for texts with no confident match
"""

from __future__ import annotations
import json
import os
import re
from datetime import datetime

_FILTER_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "node_type_filter.json")
)

_STOP_WORDS = {"increased", "additional", "chance", "penetration", "of", "the", "a", "an"}

_NUM_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")


def _normalize_words(text: str) -> set[str]:
    """Lower, strip noise tokens and numbers, return word set."""
    clean = re.sub(r"[^a-z\s]", " ", text.lower())
    words = clean.split()
    return {w for w in words if w not in _STOP_WORDS and not re.fullmatch(r"\d+", w)}


def _parse_value(text: str) -> tuple[float, bool]:
    """
    Return (rank1_value, is_percent).
    E.g. "+18% damage" → (0.18, True)
         "+10 Armor"   → (10.0, False)
         "-4 Skill Cost" → (-4.0, False)
    """
    is_percent = "%" in text
    m = _NUM_RE.search(text)
    if not m:
        return 0.0, is_percent
    raw = float(m.group())
    return (raw / 100.0 if is_percent else raw), is_percent


def _build_values(rank1: float, node_type: str, mod_def) -> list[float]:
    """
    Derive the full values list for a node.
    Micro/medium: 3 ranks (×1, ×2, ×3 of rank1).
    Legendary_medium: 1 rank.
    """
    if node_type == "legendary_medium":
        return [round(rank1, 6)]
    return [round(rank1 * i, 6) for i in range(1, 4)]


def build_filter(snapshot: dict) -> dict:
    """
    Given a TalentSnapshot dict, produce the filter dict with stats, recipes,
    unresolved, and _meta. Does NOT write to disk.
    """
    from data.node_modifier_pool import NODE_MODIFIER_POOL
    from models.stat_meta import STAT_META

    # Build lookup: stat_value → display_name words (only pool entries with meta)
    pool_candidates: list[tuple] = []
    for stat, mod_def in NODE_MODIFIER_POOL.items():
        meta = STAT_META.get(stat)
        if meta:
            pool_candidates.append((stat, meta.display_name, _normalize_words(meta.display_name), mod_def))

    # Accumulators
    stat_node_types: dict[str, set[str]] = {}  # stat_value → set of node_types
    recipes: dict[str, dict[str, list[dict]]] = {}
    unresolved: list[dict] = []
    matched_count = 0
    ambiguous_count = 0
    unmatched_count = 0

    ALL_NODE_TYPES = ["micro", "medium", "legendary_medium"]

    def _process_stat_text(text: str, node_type: str, tree: str):
        nonlocal matched_count, ambiguous_count, unmatched_count
        query_words = _normalize_words(text)
        if not query_words:
            unmatched_count += 1
            unresolved.append({"tree": tree, "node_type": node_type, "text": text})
            return

        rank1, _ = _parse_value(text)

        # Score each candidate by overlap_words / len(display_name_words)
        scores: list[tuple[float, object, object]] = []
        for stat, display_name, dn_words, mod_def in pool_candidates:
            if not dn_words:
                continue
            overlap = len(query_words & dn_words)
            score = overlap / len(dn_words)
            if score > 0:
                scores.append((score, stat, mod_def))

        scores.sort(key=lambda x: x[0], reverse=True)

        # Require exactly one winner with score >= 0.5, and it must be unambiguously better
        if scores and scores[0][0] >= 0.5:
            best_score = scores[0][0]
            # Check for ties
            tied = [s for s in scores if s[0] == best_score]
            if len(tied) == 1:
                _, stat, mod_def = scores[0]
                stat_val = stat.value
                stat_node_types.setdefault(stat_val, set()).add(node_type)
                values = _build_values(rank1, node_type, mod_def)
                tree_recipes = recipes.setdefault(tree, {})
                type_recipes = tree_recipes.setdefault(node_type, [])
                # Avoid duplicate stat in same tree+node_type
                if not any(r["stat"] == stat_val for r in type_recipes):
                    type_recipes.append({"stat": stat_val, "rank1": round(rank1, 6), "values": values})
                matched_count += 1
                return
            else:
                ambiguous_count += 1
        else:
            unmatched_count += 1

        unresolved.append({"tree": tree, "node_type": node_type, "text": text})

    trees: dict = snapshot.get("trees", {})
    for tree_name, tree_data in trees.items():
        for node in tree_data.get("nodes", []):
            nt = node.get("node_type", "")
            if nt not in ALL_NODE_TYPES:
                continue
            for stat_obj in node.get("stats", []):
                _process_stat_text(stat_obj.get("text", ""), nt, tree_name)

        # Core talents — treat as informational; don't add to node filter (no node_type)
        # but do collect unresolved so devs know what exists
        for ct in tree_data.get("core_talents", []):
            for stat_obj in ct.get("stats", []):
                pass  # core talents are not placed on regular nodes

    # New-god talents — also informational
    for ng in snapshot.get("new_god_talents", []):
        for stat_obj in ng.get("stats", []):
            pass

    # Convert sets → sorted lists
    stats_out = {k: sorted(v) for k, v in stat_node_types.items()}

    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot_source": snapshot.get("source_file", ""),
        "matched": matched_count,
        "ambiguous": ambiguous_count,
        "unmatched": unmatched_count,
    }

    return {
        "_meta": meta,
        "stats": stats_out,
        "recipes": recipes,
        "unresolved": unresolved,
    }


def save_filter(filter_data: dict) -> None:
    os.makedirs(os.path.dirname(_FILTER_PATH), exist_ok=True)
    with open(_FILTER_PATH, "w", encoding="utf-8") as f:
        json.dump(filter_data, f, indent=2)


def load_filter() -> dict | None:
    if not os.path.exists(_FILTER_PATH):
        return None
    with open(_FILTER_PATH, encoding="utf-8") as f:
        return json.load(f)
