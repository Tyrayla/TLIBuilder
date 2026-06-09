"""Audit "additional"-damage affix identities for typos / near-duplicate wordings.

Per-affix pooling (engine.affix_identity) keys on normalized affix text, so two wordings of the
SAME mechanical affix that normalize DIFFERENTLY would wrongly multiply instead of add (and a typo
that makes two distinct affixes collide would wrongly merge). This is an ADVISORY report — it does
not fail. Run it after a data import and eyeball the near-duplicate clusters.

Usage:  py -3.12 tools/audit_affix_identities.py [season]   (default season: active)
"""
from __future__ import annotations
import json
import os
import re
import sys
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.affix_identity import affix_identity  # noqa: E402

_DATA = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
_ADD_RE = re.compile(r"additional\b.*\bdamage\b", re.I)
_HAS_NUM_RE = re.compile(r"\d")
_SIM_THRESHOLD = 0.95  # SequenceMatcher ratio above which two distinct identities look suspicious


def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _collect(season: str) -> dict[str, set[str]]:
    """identity -> set of raw affix texts, across talents + season data."""
    files = [os.path.join(_DATA, "node_type_filter.json")]
    sdir = os.path.join(_DATA, "seasons", season)
    if os.path.isdir(sdir):
        files += [os.path.join(sdir, f) for f in os.listdir(sdir) if f.endswith(".json")]

    ident: dict[str, set[str]] = {}
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        for s in _walk_strings(data):
            # Skip `expression` template strings (contain the '#' placeholder) — they don't flow as
            # runtime affix text and would only add template-vs-rolled noise.
            if "#" in s:
                continue
            if _ADD_RE.search(s) and _HAS_NUM_RE.search(s) and "taken" not in s.lower():
                ident.setdefault(affix_identity(s), set()).add(s.strip())
    return ident


def main() -> None:
    season = sys.argv[1] if len(sys.argv) > 1 else None
    if season is None:
        try:
            from persistence import season_manager
            season = season_manager.get_active_season() or "SS12"
        except Exception:
            season = "SS12"

    ident = _collect(season)
    keys = sorted(ident)
    print(f"# Affix-identity audit (season {season}) — {len(keys)} distinct additional-damage identities\n")

    print("## Suspicious near-duplicate identities (review: same affix worded differently / typo?)")
    flagged = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            if abs(len(a) - len(b)) > 12:
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio >= _SIM_THRESHOLD:
                flagged += 1
                print(f"\n  ~{ratio:.2f}  {a!r}\n         {b!r}")
                print(f"         e.g. {sorted(ident[a])[0]!r}")
                print(f"         e.g. {sorted(ident[b])[0]!r}")
    if not flagged:
        print("  (none)")
    print(f"\n{flagged} near-duplicate pair(s) flagged. Distinct identities collapse multi-source "
          "duplicates automatically (good).")


if __name__ == "__main__":
    main()
