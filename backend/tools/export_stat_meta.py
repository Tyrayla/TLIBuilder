"""
Export tools for external review.

Commands (from backend/):
    py -3.12 -m tools.export_stat_meta           → docs/stat-meta-review.csv
    py -3.12 -m tools.export_stat_meta --unmatched → docs/stat-unmatched-review.md
"""

from __future__ import annotations
import argparse
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.stat_meta import STAT_META
from models.stat import Stat

_CATEGORY_ORDER = [
    "Attributes", "Generic", "Damage", "Ailments", "Status Effects",
    "Critical Strike", "Melee", "Projectile", "Area",
    "Life", "Mana", "Energy Shield", "Barrier", "Defense",
    "Buffs", "Spirit Magi", "Gear", "Damage Taken", "Utility", "Minion",
]

_MODIFIER_LABELS = {
    "increased":        "% increased",
    "added_flat":       "flat",
    "more":             "% more (mult)",
    "base_stat":        "base stat",
    "conversion":       "conversion %",
    "penetration":      "penetration %",
    "chance":           "chance %",
    "additive_percent": "additive %",
    "level":            "level",
    "duration":         "duration",
    "quantity":         "quantity",
    "override":         "override",
}


def _sources(source_types: tuple) -> str:
    s = set(source_types)
    has_talent = "talent_node" in s
    has_gear = "legendary_gear" in s or "normal_gear" in s
    if has_talent and has_gear:
        return "talent + gear"
    if has_talent:
        return "talent"
    if has_gear:
        return "gear"
    return ""


def build_csv() -> str:
    # Sort entries: category order first, then alphabetically by stat value within each category
    category_rank = {c: i for i, c in enumerate(_CATEGORY_ORDER)}

    rows = sorted(
        STAT_META.items(),
        key=lambda kv: (
            category_rank.get(kv[1].category, len(_CATEGORY_ORDER)),
            kv[0].value,
        ),
    )

    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["category", "stat", "display_name", "modifier_type", "unit", "tags", "sources", "notes"])

    for stat, meta in rows:
        writer.writerow([
            meta.category,
            stat.value,
            meta.display_name,
            _MODIFIER_LABELS.get(meta.modifier_type, meta.modifier_type),
            meta.unit or "",
            ", ".join(meta.tags) if meta.tags else "",
            _sources(meta.source_types),
            "",  # blank notes column for reviewers
        ])

    return buf.getvalue()


# ── Unmatched audit ────────────────────────────────────────────────────────────

# Texts matching any of these patterns are flagged as conditionals (defer for now).
_CONDITIONAL_MARKERS = ["when ", "if ", " while ", "recently", "against ", "on hit", "on kill", "upon "]

# Keyword groups for categorising unmatched texts. First match wins.
_THEME_GROUPS: list[tuple[str, list[str]]] = [
    ("Minion",            ["minion", "synthetic troop", "synth"]),
    ("Spirit Magus",      ["spirit magus", "spirit magi"]),
    ("Ailments",          ["ailment", "ignite", "wilt", "tangle", "trauma", "frostbite",
                           "affliction", "deterioration", "numbed", "slow", "blind",
                           "paralysis", "damaging ailment"]),
    ("Critical Strike",   ["critical strike", "critical"]),
    ("Projectile",        ["projectile"]),
    ("Sentry",            ["sentry"]),
    ("Damage",            ["damage", " dmg"]),
    ("Life",              ["life", "regain", "injury buffer"]),
    ("Defense",           ["armor", "evasion", "defense", "shield", "block", "barrier"]),
    ("Mana & Energy",     ["mana", "energy shield", "sealed mana", "skill cost"]),
    ("Speed & Cooldown",  ["speed", "cooldown"]),
    ("Buffs & Mechanics", ["fervor", "blur", "warcry", "elixir", "aura", "curse", "mark",
                           "reaping", "multistrike", "barrage", "knockback",
                           "crowd control", "ill omen", "demolisher", "spell burst"]),
    ("Utility",           ["skill area", "skill effect duration", "skill level",
                           "extra jump", "movement"]),
]


def _classify_text(text: str) -> tuple[str, bool]:
    """Return (theme, is_conditional) for a modifier text."""
    lo = text.lower()
    is_cond = any(m in lo for m in _CONDITIONAL_MARKERS)
    for theme, keywords in _THEME_GROUPS:
        if any(kw in lo for kw in keywords):
            return theme, is_cond
    return "Other", is_cond


def build_unmatched_review(unresolved: list[dict]) -> str:
    """
    Build a Markdown stat-audit survey from the unresolved list produced by build_filter().
    Only includes entries with reason == "unmatched". Groups by theme, separates conditionals.
    """
    from datetime import datetime

    # Deduplicate by text
    seen: set[str] = set()
    unique: list[str] = []
    for u in unresolved:
        if u.get("reason") == "unmatched" and u["text"] not in seen:
            seen.add(u["text"])
            unique.append(u["text"])

    # Classify each unique text
    by_theme: dict[str, list[str]] = {}
    conditionals: list[str] = []

    for text in sorted(unique):
        theme, is_cond = _classify_text(text)
        if is_cond:
            conditionals.append(text)
        else:
            by_theme.setdefault(theme, []).append(text)

    # Build output in stat-audit.md format
    lines: list[str] = []
    lines.append("# Stat Audit — Unmatched Modifier Texts")
    lines.append("")
    lines.append(f"> Generated {datetime.now().strftime('%Y-%m-%d')} from last filter rebuild.")
    lines.append("> These modifier texts appear in the talent snapshot but have no matching stat in `stat.py`.")
    lines.append(">")
    lines.append("> **How to fill in:**")
    lines.append("> - **Answer** column: `YES`, `NO`, or `SKIP`")
    lines.append(">   - `YES` → add new stat key to `stat.py` + `stat_meta.py`")
    lines.append(">   - `NO` → intentionally out of scope, skip")
    lines.append(">   - `SKIP` → conditional/situational, defer for now")
    lines.append("> - **Notes** column: write the suggested stat key or any reasoning")
    lines.append(">   - `%` texts → key usually ends in `_inc`")
    lines.append(">   - Flat texts → key usually ends in `_flat`")
    non_cond = sum(len(v) for v in by_theme.values())
    lines.append(f">")
    lines.append(f"> Total: {len(unique)} unique unmatched texts "
                 f"({non_cond} reviewable, {len(conditionals)} conditional)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Emit each theme group
    theme_order = [t for t, _ in _THEME_GROUPS] + ["Other"]
    section_num = 1

    for theme in theme_order:
        texts = by_theme.get(theme)
        if not texts:
            continue
        pct   = [t for t in texts if "%" in t]
        flat  = [t for t in texts if "%" not in t]

        lines.append(f"## {'①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮'[section_num - 1]} {theme}")
        lines.append("")

        if pct:
            lines.append(f"### % Modifier Texts")
            lines.append("")
            lines.append("| Answer | Notes | Modifier text | Suggested key |")
            lines.append("|---|---|---|---|")
            for t in pct:
                lines.append(f"| | | {t} | |")
            lines.append("")

        if flat:
            lines.append(f"### Flat Modifier Texts")
            lines.append("")
            lines.append("| Answer | Notes | Modifier text | Suggested key |")
            lines.append("|---|---|---|---|")
            for t in flat:
                lines.append(f"| | | {t} | |")
            lines.append("")

        lines.append("---")
        lines.append("")
        section_num += 1

    # Conditionals at the end
    if conditionals:
        lines.append(f"## {'①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮'[section_num - 1]} Conditionals (defer)")
        lines.append("")
        lines.append("> These texts contain conditional language (when/if/while/recently/against).")
        lines.append("> Answer `SKIP` for all unless you want to handle them now.")
        lines.append("")
        lines.append("| Answer | Notes | Modifier text |")
        lines.append("|---|---|---|")
        for t in sorted(conditionals):
            lines.append(f"| SKIP | | {t} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Export STAT_META or unmatched review.")
    parser.add_argument("--out", default=None, help="Output file path")
    parser.add_argument("--unmatched", action="store_true", help="Export unmatched review instead of stat CSV")
    args = parser.parse_args()

    if args.unmatched:
        from tools.node_type_filter_builder import load_filter
        data = load_filter()
        if data is None:
            print("ERROR: no node_type_filter.json found — run a rebuild first.")
            sys.exit(1)
        out_path = args.out or os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "docs", "stat-audit.md")
        )
        md = build_unmatched_review(data.get("unresolved", []))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Exported unmatched audit → {out_path}")
    else:
        out_path = args.out or os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "docs", "stat-meta-review.csv")
        )
        csv_data = build_csv()
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(csv_data)
        print(f"Exported {len(STAT_META)} stats → {out_path}")


if __name__ == "__main__":
    main()
