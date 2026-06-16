"""Import bundled divinity-slate icons from the crawler output.

Slate kinds/shapes are hard-coded in the renderer (SlateScreen.tsx), so the only thing we import is the
icon art, served from data/images/icons/divinity_slate/ via the /icons mount.

Baseline (base tree) slates come in SIX forms — the six tetrominoes minus the I-piece: O1, L1, L2, T1, Z1, Z2.
L2 and Z2 are horizontal MIRRORS of L1 and Z1, and the renderer produces them by flipping the L1/Z1 art, so we
deliberately KEEP only the four non-mirror forms (saves 2 forms × 6 trees = 12 files). Legendary slate icons
(UI_MI_TalantNG_Gold_*) are imported as-is.

Each icon is trimmed to its opaque bounding box and re-encoded as quality-90 lossy webp (plenty for the small
on-board display) to keep the bundle lean.

Usage:
    python -m tools.divinity_slate_icon_importer [SCRAPER_OUTPUT_ROOT]
    (default root: C:/Users/tyray/Documents/tlidb-scraper/output)
"""
from __future__ import annotations
import json
import os
import sys

from PIL import Image

# Mirror forms the renderer derives by flipping their partner — do NOT bundle their art.
_SKIP_BASE_FORMS = {"L2", "Z2"}
_QUALITY = 90

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "data", "images", "icons", "divinity_slate"))


def _trim_and_save(src_path: str, dst_path: str) -> tuple[int, int]:
    im = Image.open(src_path).convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if bbox:
        im = im.crop(bbox)
    im.save(dst_path, "WEBP", quality=_QUALITY, method=6)
    return im.size


def import_icons(scraper_root: str) -> None:
    json_path = os.path.join(scraper_root, "SS12", "divinity_slate", "divinity_slate.json")
    img_dir = os.path.join(scraper_root, "images", "divinity_slate")
    data = json.load(open(json_path, encoding="utf-8"))
    os.makedirs(_DATA_DIR, exist_ok=True)

    # Collect the icon basenames we want: baseline forms (minus mirrors) + every legendary icon.
    wanted: set[str] = set()
    for section in data.get("sections") or []:
        for item in section.get("items") or []:
            for shape in item.get("shapes") or []:
                if shape.get("shape") in _SKIP_BASE_FORMS:
                    continue
                url = shape.get("icon_url") or ""
                if url:
                    wanted.add(os.path.basename(url))
            # Legendary entries carry a single icon_url, not a shapes list.
            url = item.get("icon_url") or ""
            if url:
                wanted.add(os.path.basename(url))

    copied = skipped = 0
    for name in sorted(wanted):
        src = os.path.join(img_dir, name)
        if not os.path.exists(src):
            print(f"  MISSING source: {name}")
            skipped += 1
            continue
        w, h = _trim_and_save(src, os.path.join(_DATA_DIR, name))
        copied += 1
        print(f"  {name:48s} -> {w}x{h}")
    print(f"Imported {copied} icons ({skipped} missing) into {_DATA_DIR}")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/tyray/Documents/tlidb-scraper/output"
    import_icons(root)
