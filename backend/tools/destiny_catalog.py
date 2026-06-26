"""Pact Fates / Kismets catalog.

Pure transform from the imported `_destiny.json` (items as `{name, icon_url, implicit[], detail[]}` — see
`import_destiny`) into installable fate items: kind (from the name), the node tier it replaces (from `detail`), and
the effect clause (from `implicit`). Run at serve time by `GET /api/destiny`. Mirrors
`tools/prism_catalog.categorize_prism_catalog`.

Kinds: micro_fate (micro node), medium_fate / kismet / dual_kismet (medium node), undetermined (the expansion item).
Dual Kismets only grant their effect when 2 of the same are installed in the build (handled in the UI/engine).
"""
from __future__ import annotations
import re

# Node tier comes from the detail line "Install to replace a Micro/Medium Talent Node".
_TIER_RE = re.compile(r"replace a (Micro|Medium) Talent Node", re.I)
# Dual Kismet effect is the clause AFTER this intro.
_DUAL_INTRO_RE = re.compile(r"^Activates the following effects when there are 2 of this Kismet[^:]*:\s*", re.I)


def _kind(name: str) -> str:
    n = name or ""
    if n.startswith("Micro Fate:"):
        return "micro_fate"
    if n.startswith("Medium Fate:"):
        return "medium_fate"
    if n.startswith("Dual Kismet:"):
        return "dual_kismet"
    if n.startswith("Kismet:"):
        return "kismet"
    if n.startswith("Undetermined Fate"):
        return "undetermined"
    return "kismet"


def _short_name(name: str) -> str:
    return name.split(":", 1)[1].strip() if ":" in name else (name or "").strip()


def categorize_destiny(catalog: dict) -> dict:
    items_out: list[dict] = []
    for it in catalog.get("items", []) or []:
        name = it.get("name", "") or ""
        icon = it.get("icon_url", "") or ""
        kind = _kind(name)
        if kind == "undetermined":
            items_out.append({"name": name, "short_name": "Undetermined Fate", "kind": kind,
                              "node_tier": "", "effect_text": "", "icon_url": icon})
            continue
        # node tier from the detail lines; fall back to name-based (micro fate → micro, else medium).
        tier = ""
        for d in (it.get("detail") or []):
            m = _TIER_RE.search(d)
            if m:
                tier = m.group(1).lower()
                break
        if not tier:
            tier = "micro" if kind == "micro_fate" else "medium"
        # effect from the clean implicit lines.
        body = " ".join(s.strip() for s in (it.get("implicit") or []) if s.strip()).strip()
        if kind == "dual_kismet":
            body = _DUAL_INTRO_RE.sub("", body).strip()
        items_out.append({"name": name, "short_name": _short_name(name), "kind": kind,
                          "node_tier": tier, "effect_text": body, "icon_url": icon})

    return {
        "items": items_out,
        # Pools by the node tier they install on (micro nodes ← Micro Fates; medium nodes ← Medium Fates + Kismets).
        "micro": [i for i in items_out if i["node_tier"] == "micro"],
        "medium": [i for i in items_out if i["node_tier"] == "medium"],
        "undetermined": next((i for i in items_out if i["kind"] == "undetermined"), None),
    }
