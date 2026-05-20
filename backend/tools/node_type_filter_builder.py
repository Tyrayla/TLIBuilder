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
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "node_type_filter.json")
)
_OVERRIDES_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "node_type_filter_overrides.json")
)

_STOP_WORDS = {"of", "the", "a", "an"}

_NUM_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_STRIP_NUMS_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%?\s*")


def _override_key(text: str) -> str:
    """Normalize a modifier text to a stable key by stripping numbers."""
    s = _STRIP_NUMS_RE.sub("", text.lower())
    return re.sub(r"\s+", " ", s).strip()


def load_overrides() -> dict:
    if not os.path.exists(_OVERRIDES_PATH):
        return {}
    with open(_OVERRIDES_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_overrides(overrides: dict) -> None:
    os.makedirs(os.path.dirname(_OVERRIDES_PATH), exist_ok=True)
    with open(_OVERRIDES_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2, sort_keys=True)


def add_override(text: str, stat_value: str) -> str:
    """Save a manual override. Returns the normalized key used."""
    key = _override_key(text)
    overrides = load_overrides()
    overrides[key] = {"stat": stat_value, "example": text}
    save_overrides(overrides)
    return key


def remove_override(key: str) -> None:
    overrides = load_overrides()
    overrides.pop(key, None)
    save_overrides(overrides)


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


def _build_values(rank1: float, node_type: str) -> list[float]:
    """Micro/medium: 3 ranks (×1, ×2, ×3). Legendary_medium: 1 rank."""
    if node_type == "legendary_medium":
        return [round(rank1, 6)]
    return [round(rank1 * i, 6) for i in range(1, 4)]


def build_filter(snapshot: dict) -> dict:
    """
    Given a TalentSnapshot dict, produce the filter dict with stats, recipes,
    unresolved, and _meta. Does NOT write to disk.

    Scoring: Jaccard (overlap / |union|) against STAT_META display names.
    More-specific (longer) display names win over generic ones automatically.
    Manual overrides in node_type_filter_overrides.json are applied first.
    """
    from models.stat_meta import STAT_META

    # Build candidates from all stats in STAT_META
    candidates: list[tuple] = []  # (stat, display_name, dn_words)
    stat_by_value: dict[str, object] = {}
    for stat, meta in STAT_META.items():
        dn_words = _normalize_words(meta.display_name)
        if dn_words:
            candidates.append((stat, meta.display_name, dn_words))
            stat_by_value[stat.value] = stat

    overrides = load_overrides()

    # Accumulators
    stat_node_types: dict[str, set[str]] = {}
    matched_texts: dict[str, dict[str, str]] = {}
    recipes: dict[str, dict[str, list[dict]]] = {}
    unresolved: list[dict] = []
    matched_count = 0
    ambiguous_count = 0
    unmatched_count = 0

    ALL_NODE_TYPES = ["micro", "medium", "legendary_medium"]

    def _apply_match(stat_val: str, rank1: float, text: str, node_type: str, tree: str):
        nonlocal matched_count
        stat_node_types.setdefault(stat_val, set()).add(node_type)
        matched_texts.setdefault(stat_val, {})[_override_key(text)] = text
        values = _build_values(rank1, node_type)
        tree_recipes = recipes.setdefault(tree, {})
        type_recipes = tree_recipes.setdefault(node_type, [])
        if not any(r["stat"] == stat_val for r in type_recipes):
            type_recipes.append({"stat": stat_val, "rank1": round(rank1, 6), "values": values})
        matched_count += 1

    def _process_stat_text(text: str, node_type: str, tree: str):
        nonlocal ambiguous_count, unmatched_count
        query_words = _normalize_words(text)
        if not query_words:
            unmatched_count += 1
            unresolved.append({"tree": tree, "node_type": node_type, "text": text, "reason": "unmatched"})
            return

        rank1, _ = _parse_value(text)

        # Manual overrides take priority
        key = _override_key(text)
        if key in overrides:
            stat_val = overrides[key]["stat"]
            if stat_val in stat_by_value:
                _apply_match(stat_val, rank1, text, node_type, tree)
                return

        # Jaccard scoring: overlap / |union|
        # Longer, more-specific display names win over generic single-word ones automatically.
        scores: list[tuple[float, object, str]] = []
        for stat, display_name, dn_words in candidates:
            overlap = len(query_words & dn_words)
            if overlap == 0:
                continue
            score = overlap / len(query_words | dn_words)
            scores.append((score, stat, display_name))

        scores.sort(key=lambda x: x[0], reverse=True)

        if scores and scores[0][0] >= 0.5:
            best_score = scores[0][0]
            tied = [s for s in scores if s[0] == best_score]
            if len(tied) == 1:
                _, stat, _ = scores[0]
                _apply_match(stat.value, rank1, text, node_type, tree)
                return

            # Tiebreaker: % in text → prefer _inc; no % → prefer _flat
            is_pct = "%" in text
            preferred = [s for s in tied if s[1].value.endswith("_inc" if is_pct else "_flat")]
            if len(preferred) == 1:
                _, stat, _ = preferred[0]
                _apply_match(stat.value, rank1, text, node_type, tree)
                return

            ambiguous_count += 1
            unresolved.append({
                "tree": tree, "node_type": node_type, "text": text,
                "reason": "ambiguous",
                "tied": [{"stat": s.value, "display_name": dn, "score": round(sc, 3)} for sc, s, dn in tied],
            })
            return

        unmatched_count += 1
        unresolved.append({"tree": tree, "node_type": node_type, "text": text, "reason": "unmatched"})

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

    matched_texts_out = {k: sorted(v.values()) for k, v in matched_texts.items()}

    return {
        "_meta": meta,
        "stats": stats_out,
        "recipes": recipes,
        "unresolved": unresolved,
        "matched_texts": matched_texts_out,
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
