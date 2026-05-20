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


def build_unmatched_review(unresolved: list[dict]) -> str:
    """
    Build a Markdown review document from the unresolved list produced by build_filter().
    Only includes entries with reason == "unmatched". Deduplicates by text and splits
    into % (likely _inc) and flat (likely _flat) sections.
    """
    from datetime import datetime

    unmatched = [u for u in unresolved if u.get("reason") == "unmatched"]
    unique: dict[str, str] = {}
    for u in unmatched:
        t = u["text"]
        if t not in unique:
            unique[t] = t

    pct_texts  = sorted(t for t in unique if "%" in t)
    flat_texts = sorted(t for t in unique if "%" not in t)

    lines: list[str] = []
    lines.append("# Unmatched Stat Texts")
    lines.append("")
    lines.append(f"> Generated {datetime.now().strftime('%Y-%m-%d')} from last filter rebuild.")
    lines.append("> These modifier texts appear in the talent snapshot but have no matching stat.")
    lines.append("> **% texts** likely need an `_inc` stat added to `stat.py` + `stat_meta.py`.")
    lines.append("> **Flat texts** likely need a `_flat` stat.")
    lines.append(f">")
    lines.append(f"> Total: {len(unique)} unique texts ({len(pct_texts)} percent, {len(flat_texts)} flat)")
    lines.append("")

    if pct_texts:
        lines.append(f"## % Modifier Texts — likely `_inc`  ({len(pct_texts)})")
        lines.append("")
        for t in pct_texts:
            lines.append(f"- {t}")
        lines.append("")

    if flat_texts:
        lines.append(f"## Flat Modifier Texts — likely `_flat`  ({len(flat_texts)})")
        lines.append("")
        for t in flat_texts:
            lines.append(f"- {t}")
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
            os.path.join(os.path.dirname(__file__), "..", "..", "docs", "stat-unmatched-review.md")
        )
        md = build_unmatched_review(data.get("unresolved", []))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"Exported unmatched review → {out_path}")
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
