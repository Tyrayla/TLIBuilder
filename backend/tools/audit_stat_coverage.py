"""
Stat coverage audit for craft base types, legendary gear, and hero memories.

Usage (from backend/):
    py -3.12 -m tools.audit_stat_coverage

Outputs:
    docs/stat-audit-craft.md
    docs/stat-audit-gear.md
    docs/stat-audit-memory.md
"""
from __future__ import annotations
import os
import re
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from persistence import season_manager

# ── Number → # normalizer (shared pattern grouper) ───────────────────────────
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_RANGE_DASH_RE = re.compile(r"(\d+)\s*[–—-]\s*(\d+)")

def _to_pattern(text: str) -> str:
    """Replace all numbers with # to produce a grouping key."""
    s = text.replace("–", "-").replace("—", "-")  # normalize unicode dashes
    s = _RANGE_DASH_RE.sub(r"(#)", s)   # collapse e.g. "5-14" → "(#)"
    s = _NUM_RE.sub("#", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ── Resolution helpers ────────────────────────────────────────────────────────

def _resolve_craft_affix(raw_text: str) -> bool:
    """Return True if the craft affix resolves to at least one stat key."""
    from server import (
        _GEAR_COND_RE, _GEAR_SUFFIX_RE, _norm_expr,
        _RANGE_MULTI_STAT_OVERRIDES, _DUAL_MULTI_STAT_OVERRIDES,
        _MULTI_STAT_OVERRIDES, _EXPRESSION_STAT_OVERRIDES,
        _resolve_gear_stat,
    )
    text = _GEAR_COND_RE.sub("", raw_text)
    text = _GEAR_SUFFIX_RE.sub("", text)
    ne = _norm_expr(text)

    if ne in _RANGE_MULTI_STAT_OVERRIDES:
        return True
    if ne in _DUAL_MULTI_STAT_OVERRIDES:
        return True
    if ne in _MULTI_STAT_OVERRIDES:
        return True
    if ne in _EXPRESSION_STAT_OVERRIDES:
        return True
    stat_key, _ = _resolve_gear_stat(raw_text)
    return stat_key is not None


# Hero memory resolution: same regex + display_name lookup used by aggregator
_MEM_EFFECT_RE = re.compile(r"^\+(\d+(?:\.\d+)?)\s*(%?)\s+(.+)$")
_MEM_RANGE_RE  = re.compile(
    r"^\+?\(?(\d+(?:[.,]\d+)?)\s*[–—-]\s*(\d+(?:[.,]\d+)?)\)?\s*(%?)\s+(.+)$"
)


def _resolve_memory_modifier(modifier: str) -> bool:
    """Return True if the modifier string resolves via the memory stat lookup."""
    from engine.aggregator import (
        _MEMORY_STAT_LOOKUP, _MEMORY_ALIAS_LOOKUP, _MEMORY_MULTI_LOOKUP
    )
    text = re.sub(r"\s+", " ", modifier.strip())

    def _try_part(part: str) -> bool:
        def _get_stat_name_pct(m_obj, stat_group, pct_group) -> tuple[str, bool]:
            return m_obj.group(stat_group).strip().lower(), bool(m_obj.group(pct_group))

        for pattern, s_group, p_group in [
            (_MEM_EFFECT_RE, 3, 2), (_MEM_RANGE_RE, 4, 3)
        ]:
            m = pattern.match(part)
            if m:
                stat_name, is_pct = _get_stat_name_pct(m, s_group, p_group)
                if _MEMORY_STAT_LOOKUP.get((stat_name, is_pct)) is not None:
                    return True
                if _MEMORY_ALIAS_LOOKUP.get((stat_name, is_pct)) is not None:
                    return True
                if _MEMORY_MULTI_LOOKUP.get((stat_name, is_pct)) is not None:
                    return True
        return False

    # Try single-stat match first
    if _try_part(text):
        return True

    # Try splitting dual-stat modifiers: "+V1 [%] Stat1 +V2 [%] Stat2"
    # Use (?=\+[\d(]) to handle both "+N %" and "+(N-M) %" forms
    parts = re.split(r' (?=\+[\d(])', text, maxsplit=1)
    if len(parts) == 2:
        return _try_part(parts[0]) and _try_part(parts[1])

    return False


# ── Markdown builder ──────────────────────────────────────────────────────────

def _build_audit_table(
    patterns: Counter,
    total_affixes: int,
    resolved_affixes: int,
    title: str,
    source_desc: str,
) -> str:
    lines: list[str] = []
    today = datetime.now().strftime("%Y-%m-%d")
    pct = round(100.0 * resolved_affixes / total_affixes) if total_affixes else 0

    lines.append(f"# Stat Audit — {title} (Unresolved)")
    lines.append("")
    lines.append(f"> Generated {today}.")
    lines.append(f"> {source_desc}")
    lines.append(f"> Coverage: **{resolved_affixes}/{total_affixes} ({pct}%) affixes resolved**")
    lines.append(">")
    lines.append("> **How to fill in the Answer column:**")
    lines.append("> - `YES` → add new stat key (use Suggested Key or write your own in Notes)")
    lines.append("> - `NO` → out of scope, skip entirely")
    lines.append("> - `MULTI` → maps to multiple existing stats (add to MULTI_STAT_OVERRIDES)")
    lines.append("> - `OVERRIDE` → maps to an existing single stat (add to EXPRESSION_STAT_OVERRIDES)")
    lines.append("> - `SKIP` → conditional/situational, defer for now")
    lines.append("")
    lines.append(f"Total unresolved patterns: **{len(patterns)}**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("| # | Pattern | Count | Suggested Key | Answer | Notes |")
    lines.append("|---|---------|-------|---------------|--------|-------|")

    for i, (pattern, count) in enumerate(patterns.most_common(), 1):
        safe = pattern.replace("|", "\\|")
        lines.append(f"| {i} | `{safe}` | {count} | | | |")

    lines.append("")
    return "\n".join(lines)


# ── Per-source auditors ───────────────────────────────────────────────────────

def audit_craft(season: str) -> str:
    data = season_manager.load_craft_base_types(season)
    if not data:
        return "# Stat Audit — Craft Affixes (Unresolved)\n\n> No data found for active season.\n"

    total = resolved = 0
    unresolved_patterns: Counter = Counter()

    for bt in data.get("base_types", []):
        for affix in bt.get("affixes", []):
            if affix.get("affix_kind") in ("special", "placeholder"):
                continue
            raw = affix.get("raw_text", "")
            if not raw:
                continue
            total += 1
            if _resolve_craft_affix(raw):
                resolved += 1
            else:
                unresolved_patterns[_to_pattern(raw)] += 1

    return _build_audit_table(
        unresolved_patterns, total, resolved,
        "Craft Affixes",
        "Affix texts from craft base types that have no matching stat lookup.",
    )


def audit_legendary(season: str) -> str:
    data = season_manager.load_legendary_gear(season)
    if not data:
        return "# Stat Audit — Legendary Gear (Unresolved)\n\n> No data found for active season.\n"

    total = resolved = 0
    unresolved_patterns: Counter = Counter()

    def _check(affix: dict) -> None:
        nonlocal total, resolved
        if affix.get("affix_kind") in ("special", "placeholder", "tagged"):
            return
        raw = affix.get("raw_text", "")
        if not raw:
            return
        total += 1
        if _resolve_craft_affix(raw):
            resolved += 1
        else:
            unresolved_patterns[_to_pattern(raw)] += 1

    for item in data.get("items", []):
        for variant in item.get("variants", {}).values():
            for a in variant.get("implicits", []):
                _check(a)
            for a in variant.get("explicits", []):
                _check(a)
        for pool in item.get("random_affixes", {}).values():
            for entry in pool:
                for opt in entry.get("options", []):
                    _check(opt)
        for a in item.get("affixes", []):  # legacy flat format
            _check(a)

    return _build_audit_table(
        unresolved_patterns, total, resolved,
        "Legendary Gear",
        "Affix texts from legendary gear items that have no matching stat lookup.",
    )


def audit_memories(season: str) -> str:
    data = season_manager.load_hero_memories(season)
    if not data:
        return "# Stat Audit — Hero Memories (Unresolved)\n\n> No data found for active season.\n"

    total = resolved = 0
    unresolved_patterns: Counter = Counter()

    all_affixes = data.get("fixed_affixes", []) + data.get("random_affixes", [])
    for affix in all_affixes:
        modifier = affix.get("modifier", "")
        if not modifier:
            continue
        # Skip pure text modifiers (no leading + or digit)
        if not re.match(r"^[+\-(]?\d", modifier):
            continue
        total += 1
        if _resolve_memory_modifier(modifier):
            resolved += 1
        else:
            unresolved_patterns[_to_pattern(modifier)] += 1

    return _build_audit_table(
        unresolved_patterns, total, resolved,
        "Hero Memories",
        "Modifier texts from hero memories that have no matching stat lookup.",
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def run_audit() -> dict:
    season = season_manager.get_active_season()
    if not season:
        print("ERROR: No active season set.")
        sys.exit(1)

    print(f"Running audit for season: {season}")
    docs_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "docs")
    )
    os.makedirs(docs_dir, exist_ok=True)

    results = {}
    for name, fn, filename in [
        ("craft",    audit_craft,    "stat-audit-craft.md"),
        ("gear",     audit_legendary, "stat-audit-gear.md"),
        ("memories", audit_memories,  "stat-audit-memory.md"),
    ]:
        print(f"  Auditing {name}…", end=" ", flush=True)
        md = fn(season)
        path = os.path.join(docs_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        # Extract coverage line
        for line in md.splitlines():
            if "Coverage:" in line:
                print(line.strip().lstrip(">").strip())
                break
        else:
            print("done")
        results[name] = path

    return results


if __name__ == "__main__":
    run_audit()
