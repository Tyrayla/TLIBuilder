"""Import the TLI Help Database (a tree of markdown articles) into data/help_db.json.

The Help DB is authored as one .md file per topic under a folder hierarchy. This packages every article
into a single JSON catalog the app serves like any other reference data (desktop endpoint + web CDN static
file). The markdown body is preserved verbatim (rendered client-side); this tool does NO markdown→HTML.

The .md tree is the human-authored source of truth; data/help_db.json is a generated artifact — re-run this
after the Help DB changes.

Source dir: $TLI_HELP_DB_DIR, else the default local path below.
Usage:  python backend/tools/import_help_db.py
"""
import json
import os
import re

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.dirname(_BACKEND)
_OUT = os.path.join(_REPO, "data", "help_db.json")
_DEFAULT_SRC = r"C:\Users\tyray\Claude\Projects\TLI Help Database"
_SRC = os.environ.get("TLI_HELP_DB_DIR") or _DEFAULT_SRC

_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.M)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main() -> None:
    if not os.path.isdir(_SRC):
        raise SystemExit(f"Help DB source not found: {_SRC} (set TLI_HELP_DB_DIR)")
    entries = []
    seen_ids: dict[str, int] = {}
    for root, _dirs, files in os.walk(_SRC):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8") as f:
                body = f.read()
            m = _H1_RE.search(body)
            title = (m.group(1).strip() if m else os.path.splitext(fn)[0].strip())
            rel = os.path.relpath(os.path.dirname(path), _SRC)
            breadcrumb = "" if rel == "." else " / ".join(rel.split(os.sep))
            sid = _slug(title) or _slug(os.path.splitext(fn)[0])
            if sid in seen_ids:               # disambiguate duplicate titles (e.g. "Others")
                seen_ids[sid] += 1
                sid = f"{sid}-{seen_ids[sid]}"
            else:
                seen_ids[sid] = 1
            entries.append({
                "id": sid,
                "title": title,
                "breadcrumb": breadcrumb,
                "markdown": body.strip(),
            })
    entries.sort(key=lambda e: (e["breadcrumb"].lower(), e["title"].lower()))
    with open(_OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"entry_count": len(entries), "entries": entries}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"Imported {len(entries)} Help DB articles -> {os.path.relpath(_OUT, _REPO)} "
          f"({os.path.getsize(_OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
