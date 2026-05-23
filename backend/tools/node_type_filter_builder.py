"""
Builds node_type_filter.json from a canonical talent snapshot.

Matches snapshot stat texts (e.g. "+9% Attack Damage") to Stat enum values
using Jaccard-like word-overlap scoring against STAT_META display names.

Split rules handle compound modifier texts — these produce multiple
(stat, value) pairs per text instead of one, avoiding combined stats in
stat.py.  Three split patterns are supported:

  1. Speed combos  — "+X% Attack and Cast Speed" → attack_speed_inc +
                     cast_speed_inc (same value for both)
  2. Flat ranges   — "+X-Y Base Ignite Damage" → ignite_dmg_flat_min (X) +
                     ignite_dmg_flat_max (Y)
  3. Multi-clause  — "Adds 2-2 fire damage to attacks and spells, adds 1-3
                     lightning..." → each clause processed independently

Output: data/node_type_filter.json
  stats    — {stat_value: [node_types that carry it]}
  recipes  — {tree: {node_type: [{stat, rank1, values, text}]}}
  node_recipes — {node_id: [{stat, rank1, values, text}]}
  unresolved — [{tree, node_type, text}] for texts with no confident match
"""

from __future__ import annotations
import json
import os
import re
from datetime import datetime

_DATA_ROOT = os.environ.get('TLI_DATA_DIR') or os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
_FILTER_PATH = os.path.normpath(os.path.join(_DATA_ROOT, 'node_type_filter.json'))
_OVERRIDES_PATH = os.path.normpath(os.path.join(_DATA_ROOT, 'node_type_filter_overrides.json'))

_STOP_WORDS = {"of", "the", "a", "an"}

_NUM_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")
_STRIP_NUMS_RE = re.compile(r"[+-]?\d+(?:\.\d+)?%?\s*")
_RANGE_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\b")

# Strips the conditional suffix so Jaccard matches on the stat portion only.
_COND_STRIP_RE = re.compile(
    r"\s+(?:while\b|when\b|if\b|against\b|recently\b|on\s+hit\b|on\s+defeat\b|"
    r"upon\b|for\s+every\b|for\s+each\b|nearby\b|distant\b|in\s+proximity\b|"
    r"in\s+the\s+last\b|per\s+(?!second))",
    re.I,
)
# Strips trailing prepositions/verbs left over after conditional clause removal.
_TRAILING_STRIP_RE = re.compile(r"\s+\b(to|by|from|dealt|against|taken)\s*$", re.I)

# ── Split rules ───────────────────────────────────────────────────────────────

# Speed combos: word-set subset → list of stat values to emit (same value each)
# More-specific entries must come before less-specific ones.
_SPEED_SPLITS: list[tuple[frozenset, list[str]]] = [
    (frozenset({"minion", "attack", "cast", "speed"}),    ["minion_attack_speed_inc", "minion_cast_speed_inc"]),
    (frozenset({"channeled", "attack", "cast", "speed"}), ["channeled_attack_speed_inc", "channeled_cast_speed_inc"]),
    (frozenset({"attack", "cast", "speed"}),              ["attack_speed_inc", "cast_speed_inc"]),
]

# Elemental flat damage: element → skill-context → (min_stat, max_stat)
_ELEMENT_FLAT: dict[str, dict[str, tuple[str, str]]] = {
    "fire":      {"attack": ("fire_attack_dmg_flat_min",      "fire_attack_dmg_flat_max"),
                  "spell":  ("fire_spell_dmg_flat_min",       "fire_spell_dmg_flat_max")},
    "lightning": {"attack": ("lightning_attack_dmg_flat_min", "lightning_attack_dmg_flat_max"),
                  "spell":  ("lightning_spell_dmg_flat_min",  "lightning_spell_dmg_flat_max")},
    "cold":      {"attack": ("cold_attack_dmg_flat_min",      "cold_attack_dmg_flat_max"),
                  "spell":  ("cold_spell_dmg_flat_min",       "cold_spell_dmg_flat_max")},
    "erosion":   {"attack": ("erosion_attack_dmg_flat_min",   "erosion_attack_dmg_flat_max"),
                  "spell":  ("erosion_spell_dmg_flat_min",    "erosion_spell_dmg_flat_max")},
    "physical":  {"attack": ("physical_attack_dmg_flat_min",  "physical_attack_dmg_flat_max"),
                  "spell":  ("physical_spell_dmg_flat_min",   "physical_spell_dmg_flat_max")},
}

# Ailment flat damage: keyword → (min_stat, max_stat)
_AILMENT_FLAT: dict[str, tuple[str, str]] = {
    "ignite":  ("ignite_dmg_flat_min",  "ignite_dmg_flat_max"),
    "wilt":    ("wilt_dmg_flat_min",    "wilt_dmg_flat_max"),
    "ailment": ("ailment_dmg_flat_min", "ailment_dmg_flat_max"),
}


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


def _parse_range(text: str) -> tuple[float, float] | None:
    """Extract (min, max) from a 'X-Y' range in text, or None if absent."""
    m = _RANGE_RE.search(text)
    return (float(m.group(1)), float(m.group(2))) if m else None


def _build_values(rank1: float, node_type: str) -> list[float]:
    """Micro/medium: 3 ranks (×1, ×2, ×3). Legendary_medium: 1 rank."""
    if node_type == "legendary_medium":
        return [round(rank1, 6)]
    return [round(rank1 * i, 6) for i in range(1, 4)]


# ── Conditional guard ────────────────────────────────────────────────────────

_COND_PHRASES = (
    "while ", " when ", " if ", "against ", "recently",
    "on hit", "on defeat", "upon ",
    "for every", "for each",
    "nearby", "distant", "in proximity", "in the last",
)


def _is_conditional(text: str) -> bool:
    """
    Return True if the modifier text contains conditional language.
    Exception: 'per second' is allowed (regen stats); all other 'per X' are conditional.
    """
    lower = text.lower()
    if "per " in lower and "per second" not in lower:
        return True
    return any(p in lower for p in _COND_PHRASES)


def _strip_conditional(text: str) -> str:
    """Return the stat-value portion of a conditional text (before the conditional clause).
    Used to improve Jaccard matching by removing words that describe the condition."""
    m = _COND_STRIP_RE.search(text)
    result = text[:m.start()].strip() if m and m.start() > 0 else text
    # Strip trailing prepositions/verbs iteratively (e.g. "damage dealt to" → "damage")
    while True:
        m2 = _TRAILING_STRIP_RE.search(result)
        if m2:
            result = result[:m2.start()].strip()
        else:
            break
    return result


# ── Condition key detection ───────────────────────────────────────────────────
# Maps text patterns to condition keys defined in models/conditions.py.
# More-specific patterns must come before overlapping ones.

_CONDITION_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sealed mana and life",                        re.I), "sealed_mana_and_life"),
    (re.compile(r"holding a shield|when.*shield|while.*shield", re.I), "holding_shield"),
    (re.compile(r"two.handed weapon",                           re.I), "holding_two_handed"),
    (re.compile(r"one.handed weapon",                           re.I), "holding_one_handed"),
    (re.compile(r"dual.wield|while\s+dual\b",                   re.I), "dual_wielding"),
    (re.compile(r"tenacity blessing",                           re.I), "tenacity_active"),
    (re.compile(r"focus blessing",                              re.I), "focus_active"),
    (re.compile(r"agility blessing",                            re.I), "agility_active"),
    (re.compile(r"while blur|blur.*active",                     re.I), "blur_active"),
    (re.compile(r"\bfervor\b",                                  re.I), "fervor_active"),
    (re.compile(r"\belixir\b",                                  re.I), "elixir_active"),
    (re.compile(r"standing still",                              re.I), "standing_still"),
    (re.compile(r"when moving",                                 re.I), "moving"),
    (re.compile(r"in proximity|nearby",                         re.I), "enemy_nearby"),
    (re.compile(r"\bdistant\b",                                 re.I), "enemy_distant"),
    (re.compile(r"full mana",                                   re.I), "at_full_mana"),
    (re.compile(r"low mana",                                    re.I), "at_low_mana"),
    (re.compile(r"\bfrostbitten\b|\bfrozen\b",                  re.I), "enemy_frozen"),
    (re.compile(r"\bcursed\b",                                  re.I), "enemy_cursed"),
    (re.compile(r"\blow life\b",                                re.I), "enemy_low_life"),
    (re.compile(r"\bblinded\b",                                 re.I), "enemy_blinded"),
    (re.compile(r"\bignited\b",                                 re.I), "enemy_ignited"),
    (re.compile(r"affected by ailments",                        re.I), "enemy_has_ailment"),
    (re.compile(r"max affliction",                              re.I), "enemy_has_max_affliction"),
    (re.compile(r"defeated.*recently|recently.*defeated",       re.I), "recently_defeated"),
    (re.compile(r"regained in the last|have regained",          re.I), "recently_regained"),
    (re.compile(r"taken damage recently",                       re.I), "recently_taken_damage"),
    (re.compile(r"blocked recently",                            re.I), "recently_blocked"),
    (re.compile(r"critical strike recently",                    re.I), "recently_crit"),
    (re.compile(r"warcry.*last",                                re.I), "recently_warcry"),
    (re.compile(r"triggered life regain|life regain in the last", re.I), "recently_life_regain"),
    (re.compile(r"shield regain in the last",                   re.I), "recently_shield_regain"),
    (re.compile(r"lost life recently",                          re.I), "recently_lost_life"),
    (re.compile(r"synthetic troop.*cast recently",              re.I), "recently_synth_cast"),
    (re.compile(r"mobility skill",                              re.I), "recently_used_mobility"),
    (re.compile(r"sentry.*not used",                            re.I), "sentry_not_used_recently"),
    (re.compile(r"main skill.*not used",                        re.I), "main_skill_not_used_recently"),
    (re.compile(r"channeled stacks.*not.*cap|stacks have not reached cap", re.I), "channeled_not_capped"),
    (re.compile(r"\bon hit\b",                                  re.I), "on_hit"),
]


def _detect_condition(text: str) -> str | None:
    """Return a condition key for the conditional text, or None if not recognised."""
    for pattern, key in _CONDITION_MAP:
        if pattern.search(text):
            return key
    return None


# ── Split helpers ─────────────────────────────────────────────────────────────

def _split_one(text: str) -> list[tuple[str, float]] | None:
    """
    Try to split a single modifier clause into (stat_val, value) pairs.

    Returns None  — no split pattern recognised; fall through to Jaccard.
    Returns []    — split pattern matched but produced no known stats.
    Returns [...] — one or more (stat_val, value) pairs resolved.
    """
    words = set(re.findall(r"[a-z]+", text.lower()))

    # Speed combinations — more-specific entries first
    for required, stats in _SPEED_SPLITS:
        if required.issubset(words):
            val, _ = _parse_value(text)
            return [(s, val) for s in stats]

    # Flat damage ranges  (X-Y pattern)
    rng = _parse_range(text)
    if rng is not None:
        vmin, vmax = rng
        # Ailment types take priority over elemental
        for keyword, (mn, mx) in _AILMENT_FLAT.items():
            if keyword in words:
                return [(mn, vmin), (mx, vmax)]
        # Elemental types
        for element, contexts in _ELEMENT_FLAT.items():
            if element in words:
                has_attack = bool(words & {"attack", "attacks"})
                has_spell  = bool(words & {"spell",  "spells"})
                if not has_attack and not has_spell:
                    has_attack = has_spell = True   # no context → both
                out: list[tuple[str, float]] = []
                if has_attack:
                    mn, mx = contexts["attack"]
                    out += [(mn, vmin), (mx, vmax)]
                if has_spell:
                    mn, mx = contexts["spell"]
                    out += [(mn, vmin), (mx, vmax)]
                return out
        return []   # range present but no matching element/ailment

    return None     # no split pattern detected


def _try_split(text: str) -> list[tuple[str, float]] | None:
    """
    Decompose text into (stat_val, value) pairs, or None if no split applies.

    Multi-clause texts (', adds …' or '. adds …') are clause-split first;
    each clause is processed by _split_one independently.

    Return semantics mirror _split_one:
      None  — no split attempted; caller should fall through to Jaccard.
      []    — split was attempted but produced nothing (treat as unmatched).
      [...] — resolved pairs.
    """
    lower = text.lower()
    if re.search(r"(?:,|\.)\s*adds\s+", lower):
        # Multi-clause: splitting is always the intent
        parts = re.split(r"(?:,|\.)\s*(?=adds\s+)", text, flags=re.IGNORECASE)
        results: list[tuple[str, float]] = []
        for part in parts:
            r = _split_one(part.strip())
            if r:
                results.extend(r)
        return results  # may be [] if no clause resolved

    return _split_one(text)   # None | [] | [...]


# ── Jaccard matcher ───────────────────────────────────────────────────────────

def _jaccard_match(
    text: str,
    candidates: list,
    overrides: dict,
) -> tuple[str, float] | None:
    """
    Pure Jaccard matcher returning (stat_value_string, rank1) or None.
    Applies overrides first, then scored matching with tiebreaker.
    """
    query_words = _normalize_words(text)
    if not query_words:
        return None

    rank1, _ = _parse_value(text)
    key = _override_key(text)

    if key in overrides:
        stat_val = overrides[key]["stat"]
        if any(s.value == stat_val for s, _, _ in candidates):
            return stat_val, rank1

    scores: list[tuple[float, object, str]] = []
    for stat, display_name, dn_words in candidates:
        overlap = len(query_words & dn_words)
        if overlap == 0:
            continue
        score = overlap / len(query_words | dn_words)
        scores.append((score, stat, display_name))

    if not scores:
        return None

    scores.sort(key=lambda x: x[0], reverse=True)
    best_score, best_stat, best_dn = scores[0]

    extra_words = query_words - _normalize_words(best_dn)
    threshold = 0.7 if extra_words else 0.5

    if best_score < threshold:
        return None

    tied = [s for s in scores if s[0] == best_score]
    if len(tied) == 1:
        return best_stat.value, rank1

    # Tiebreaker: % in text → prefer _inc; no % → prefer _flat
    is_pct = "%" in text
    preferred = [s for s in tied if s[1].value.endswith("_inc" if is_pct else "_flat")]
    if len(preferred) == 1:
        return preferred[0][1].value, rank1

    return None  # ambiguous


# ── Public filter-building API ────────────────────────────────────────────────

def _match_effect(text: str, candidates: list, overrides: dict) -> list[tuple[str, float]]:
    """
    Match a single modifier text to one or more (stat_val, rank1) pairs.

    Resolution order:
      1. Override map (exact key match)
      2. Split rules (_try_split)
      3. Jaccard scorer
    """
    # Overrides bypass everything (applied inside _jaccard_match too, but
    # checking here avoids running the split on text that is already resolved).
    key = _override_key(text)
    if key in overrides:
        stat_val = overrides[key]["stat"]
        if any(s.value == stat_val for s, _, _ in candidates):
            rank1, _ = _parse_value(text)
            return [(stat_val, rank1)]

    if _is_conditional(text):
        return []

    split = _try_split(text)
    if split is not None:
        return split    # may be [] — caller treats as unmatched

    result = _jaccard_match(text, candidates, overrides)
    return [result] if result else []


def build_filter(snapshot: dict) -> dict:
    """
    Given a TalentSnapshot dict, produce the filter dict with stats, recipes,
    unresolved, and _meta. Does NOT write to disk.
    """
    from models.stat_meta import STAT_META

    candidates: list[tuple] = []
    stat_by_value: dict[str, object] = {}
    for stat, meta in STAT_META.items():
        dn_words = _normalize_words(meta.display_name)
        if dn_words:
            candidates.append((stat, meta.display_name, dn_words))
            stat_by_value[stat.value] = stat

    overrides = load_overrides()

    stat_node_types: dict[str, set[str]] = {}
    matched_texts: dict[str, dict[str, str]] = {}
    recipes: dict[str, dict[str, list[dict]]] = {}
    unresolved: list[dict] = []
    matched_count = 0
    ambiguous_count = 0
    unmatched_count = 0
    conditional_count = 0

    staged: list[dict] = []

    ALL_NODE_TYPES = ["micro", "medium", "legendary_medium"]

    def _apply_match(stat_val: str, rank1: float, text: str, node_type: str, tree: str,
                     condition: str | None = None):
        nonlocal matched_count
        values = _build_values(rank1, node_type)
        tree_recipes = recipes.setdefault(tree, {})
        type_recipes = tree_recipes.setdefault(node_type, [])

        if condition:
            # Conditional recipe: keyed by (stat, condition) — doesn't affect matched_texts/stats
            if not any(r["stat"] == stat_val and r.get("condition") == condition for r in type_recipes):
                type_recipes.append({
                    "stat": stat_val, "rank1": round(rank1, 6),
                    "values": values, "text": text, "condition": condition,
                })
        else:
            # Regular recipe: deduplicate by stat only
            stat_node_types.setdefault(stat_val, set()).add(node_type)
            matched_texts.setdefault(stat_val, {})[_override_key(text)] = text
            if not any(r["stat"] == stat_val and not r.get("condition") for r in type_recipes):
                type_recipes.append({"stat": stat_val, "rank1": round(rank1, 6), "values": values, "text": text})
            matched_count += 1

    def _process_stat_text(text: str, node_type: str, tree: str):
        nonlocal ambiguous_count, unmatched_count, conditional_count

        rank1, _ = _parse_value(text)

        # Override — direct apply, bypass staging
        key = _override_key(text)
        if key in overrides:
            stat_val = overrides[key]["stat"]
            if stat_val in stat_by_value:
                _apply_match(stat_val, rank1, text, node_type, tree)
                return

        # Conditional texts: try to extract a conditional recipe, then mark unresolved for audit
        if _is_conditional(text):
            cond_key = _detect_condition(text)
            if cond_key:
                stripped = _strip_conditional(text)
                # Try split first (handles "X% Attack and Cast Speed when Y" combos)
                split = _try_split(stripped)
                if split:
                    for stat_val, sv in split:
                        _apply_match(stat_val, sv, text, node_type, tree, condition=cond_key)
                    return
                result = _jaccard_match(stripped, candidates, overrides)
                if result:
                    _apply_match(result[0], result[1], text, node_type, tree, condition=cond_key)
                    return
            conditional_count += 1
            unresolved.append({"tree": tree, "node_type": node_type, "text": text, "reason": "conditional"})
            return

        # Split rules — direct apply, bypass staging and collision check
        split = _try_split(text)
        if split is not None:
            if split:
                for stat_val, sv in split:
                    _apply_match(stat_val, sv, text, node_type, tree)
            else:
                unmatched_count += 1
                unresolved.append({"tree": tree, "node_type": node_type, "text": text, "reason": "unmatched"})
            return

        # Jaccard matching with staging + multi-text collision check
        query_words = _normalize_words(text)
        if not query_words:
            unmatched_count += 1
            unresolved.append({"tree": tree, "node_type": node_type, "text": text, "reason": "unmatched"})
            return

        scores: list[tuple[float, object, str]] = []
        for stat, display_name, dn_words in candidates:
            overlap = len(query_words & dn_words)
            if overlap == 0:
                continue
            score = overlap / len(query_words | dn_words)
            scores.append((score, stat, display_name))

        scores.sort(key=lambda x: x[0], reverse=True)

        if scores:
            best_score, best_stat, best_dn = scores[0]
            extra_words = query_words - _normalize_words(best_dn)
            threshold = 0.7 if extra_words else 0.5

            if best_score >= threshold:
                tied = [s for s in scores if s[0] == best_score]
                if len(tied) == 1:
                    staged.append({"stat_val": best_stat.value, "rank1": rank1, "text": text, "node_type": node_type, "tree": tree})
                    return

                is_pct = "%" in text
                preferred = [s for s in tied if s[1].value.endswith("_inc" if is_pct else "_flat")]
                if len(preferred) == 1:
                    _, stat, _ = preferred[0]
                    staged.append({"stat_val": stat.value, "rank1": rank1, "text": text, "node_type": node_type, "tree": tree})
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

    # Multi-text collision check for staged Jaccard results
    by_stat: dict[str, list[dict]] = {}
    for m in staged:
        by_stat.setdefault(m["stat_val"], []).append(m)

    for _, matches in by_stat.items():
        distinct_keys = {_override_key(m["text"]) for m in matches}
        if len(distinct_keys) > 1:
            for m in matches:
                unmatched_count += 1
                unresolved.append({"tree": m["tree"], "node_type": m["node_type"], "text": m["text"], "reason": "multi_text"})
        else:
            for m in matches:
                _apply_match(m["stat_val"], m["rank1"], m["text"], m["node_type"], m["tree"])

    stats_out = {k: sorted(v) for k, v in stat_node_types.items()}

    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot_source": snapshot.get("source_file", ""),
        "matched": matched_count,
        "ambiguous": ambiguous_count,
        "unmatched": unmatched_count,
        "conditional": conditional_count,
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


def build_node_recipes(season_trees: dict[str, dict]) -> dict[str, list[dict]]:
    """
    Build per-node-id stat recipes directly from season tree data.
    Each node's effects are matched independently via _match_effect,
    which applies split rules before falling back to Jaccard.
    """
    from models.stat_meta import STAT_META

    candidates: list[tuple] = []
    for stat, meta in STAT_META.items():
        dn_words = _normalize_words(meta.display_name)
        if dn_words:
            candidates.append((stat, meta.display_name, dn_words))

    overrides = load_overrides()
    node_recipes: dict[str, list[dict]] = {}

    for tree_data in season_trees.values():
        for node in tree_data.get("nodes", []):
            node_id = node.get("id", "")
            if not node_id:
                continue
            raw_node_type = node.get("node_type", "")
            node_type = raw_node_type.lower().replace(" talent", "").strip().replace(" ", "_")
            if node_type not in ("micro", "medium", "legendary_medium"):
                continue
            effects = node.get("effects", [])

            recipes_for_node: list[dict] = []
            seen_stats: set[str] = set()
            seen_cond_pairs: set[tuple[str, str]] = set()
            for effect_text in effects:
                if _is_conditional(effect_text):
                    cond_key = _detect_condition(effect_text)
                    if cond_key:
                        result = _jaccard_match(effect_text, candidates, overrides)
                        if result:
                            stat_val, rank1 = result
                            pair = (stat_val, cond_key)
                            if pair not in seen_cond_pairs:
                                seen_cond_pairs.add(pair)
                                values = _build_values(rank1, node_type)
                                recipes_for_node.append({
                                    "stat": stat_val,
                                    "rank1": round(rank1, 6),
                                    "values": values,
                                    "text": effect_text,
                                    "condition": cond_key,
                                })
                    continue
                matches = _match_effect(effect_text, candidates, overrides)
                for stat_val, rank1 in matches:
                    if stat_val in seen_stats:
                        continue
                    seen_stats.add(stat_val)
                    values = _build_values(rank1, node_type)
                    recipes_for_node.append({
                        "stat": stat_val,
                        "rank1": round(rank1, 6),
                        "values": values,
                        "text": effect_text,
                    })

            if recipes_for_node:
                node_recipes[node_id] = recipes_for_node

    return node_recipes
