"""Rebuild data/seasons/<SEASON>/_skills.json from the crawler output (one JSON per skill).

Imports every skill-catalog type (active / passive / supports / activation medium / modularization), dedups
the recrawl's doubled description lines, and PRESERVES dev-set fields not present in the crawl (dps_eligible).

Usage:
    python -m tools.rebuild_skills [--season SS12] [--crawl <dir>] [--out <path>] [--dry-run]

--dry-run writes to <out>.new and prints a comparison vs the existing file instead of overwriting.
"""
import argparse
import glob
import json
import os
import sys

from tools.skill_importer import import_crawler_skill

# Crawler subdirs that become entries in _skills.json (the skill catalog). Other dirs (gear, spirits,
# memories, talent trees, crafting, …) belong to different data files and are intentionally excluded.
_SKILL_TYPE_DIRS = [
    "active_skill", "passive_skill", "support_skill",
    "noble_support_skill", "magnificent_support_skill",
    "activation_medium_skill", "modularization_skill",
]

# Fields the app curates that the crawler does not emit — carried over from the existing _skills.json by item_id.
_PRESERVE_FIELDS = ["dps_eligible"]


def build_skills(crawl_dir: str, existing_by_id: dict) -> tuple[list[dict], list[str]]:
    """A skill name can appear in several type dirs (a castable Base Skill plus its Empower/Enhanced passive,
    or a Modularization minion variant). They share an item_id, so only one can win. To avoid reclassifying
    skills on a routine reimport, a colliding id keeps the skill_type the EXISTING data assigned (refreshed
    from that type's file); a genuinely-new collision falls back to _SKILL_TYPE_DIRS priority and is logged."""
    # item_id -> {skill_type: imported_dict} across every dir it appears in.
    candidates: dict[str, dict[str, dict]] = {}
    for tdir in _SKILL_TYPE_DIRS:
        for path in sorted(glob.glob(os.path.join(crawl_dir, tdir, "*.json"))):
            data = json.load(open(path, encoding="utf-8"))
            if not data.get("name"):
                continue
            sk = import_crawler_skill(data)
            candidates.setdefault(sk["item_id"], {})[sk.get("skill_type") or tdir] = sk

    _PRIORITY = {t: i for i, t in enumerate(_SKILL_TYPE_DIRS)}
    skills: list[dict] = []
    notes: list[str] = []
    for iid, by_type in candidates.items():
        if len(by_type) > 1:
            prev_type = (existing_by_id.get(iid) or {}).get("skill_type")
            if prev_type in by_type:
                chosen = prev_type
            else:
                chosen = min(by_type, key=lambda t: _PRIORITY.get(t, 99))
                notes.append(f"{iid}: collision {sorted(by_type)} -> {chosen}"
                             + (f" (was {prev_type}, not among files)" if prev_type else " (new)"))
        else:
            chosen = next(iter(by_type))
        sk = by_type[chosen]
        prev = existing_by_id.get(iid) or {}
        for f in _PRESERVE_FIELDS:
            if f in prev:
                sk[f] = prev[f]
        skills.append(sk)
    skills.sort(key=lambda s: s["item_id"])
    return skills, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="SS12")
    ap.add_argument("--crawl", default="C:/Users/tyray/Documents/tlidb-scraper/output/SS12")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # backend/
    out = args.out or os.path.join(repo, "..", "data", "seasons", args.season, "_skills.json")
    out = os.path.abspath(out)

    existing = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {"skills": []}
    existing_by_id = {s["item_id"]: s for s in existing.get("skills", [])}

    skills, notes = build_skills(args.crawl, existing_by_id)
    payload = {"season": args.season, "skill_count": len(skills), "skills": skills}

    new_ids = {s["item_id"] for s in skills}
    old_ids = set(existing_by_id)
    print(f"crawl dir: {args.crawl}")
    print(f"built {len(skills)} skills (was {len(old_ids)})")
    print(f"  added:   {sorted(new_ids - old_ids)}")
    print(f"  removed: {sorted(old_ids - new_ids)}")
    # Type changes vs the existing data (a reimport should normally change nothing here).
    retyped = [(i, existing_by_id[i].get("skill_type"), s.get("skill_type"))
               for s in skills if (i := s["item_id"]) in existing_by_id
               and existing_by_id[i].get("skill_type") != s.get("skill_type")]
    if retyped:
        print(f"  RETYPED ({len(retyped)}):")
        for i, a, b in retyped[:30]:
            print(f"    {i}: {a} -> {b}")
    if notes:
        print(f"  collision notes ({len(notes)}):")
        for c in notes[:30]:
            print(f"    {c}")
    dps_kept = [s["item_id"] for s in skills if "dps_eligible" in s]
    print(f"  dps_eligible preserved on: {dps_kept}")

    target = (out + ".new") if args.dry_run else out
    json.dump(payload, open(target, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"wrote {target}")
    if args.dry_run:
        print("(dry run — existing file untouched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
