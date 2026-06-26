"""Ethereal-Prism catalog categorizer.

Pure transform from the raw imported catalog (items + base_affixes + random_affixes — see
`import_ethereal_prism`) into a UI-ready crafting catalog: every item resolved to its implicit + allowed
rarities, and the random-affix pool split into the three craftable slots (area size / middle tier / advanced).
Run at serve time by `GET /api/ethereal-prism`; no game-data is hardcoded — everything is derived from the text.
"""
from __future__ import annotations
import re
from collections import defaultdict

_AREA_RE = re.compile(r"Effect Area expands to\s+(\d+)\s*x\s*(\d+)", re.I)
_OVERALLOC_RE = re.compile(
    r"Points can be allocated to all\s+(Micro|Medium|Legendary Medium)\s+Talent.*?(\d+)\s+additional time", re.I)
_MIDDLE_TIER_RE = re.compile(r"All\s+(Micro|Medium|Legendary Medium)\s+Talent within the area", re.I)
_DNR_MARK = "no longer replace the original talent"
_DNR_NAME_RE = re.compile(r"current Talent Panel:\s*(.+)\s*$")
_REPLACE_PREFIX = "Replaces the Core Talent"
_ADD_PREFIX = "Adds an additional effect to the Core Talent"
_AMPLIFY_MARK = "to the effects of Random Affixes"
_DNR_PENALTIES = ("-15 to All Stats", "-5 % Elemental Resistance", "-8 % Defense")

_TIER_KEY = {"micro": "micro", "medium": "medium", "legendary medium": "legendary"}

# Sign glued to the digits (NOT a separate '\s*') so '+6 %' and '10.5 %' normalise to the same skeleton — the
# catalog writes the base value with a leading '+' but the Phantasmagoria-scaled value without one.
_NUM_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")


def _skeleton(s: str) -> str:
    """Strip all numbers → group affixes that are the same stat at different magnitudes."""
    return _NUM_RE.sub("#", s)


def _first_num(s: str):
    m = _NUM_RE.search(s)
    return float(m.group()) if m else None


def _tag_phantasmagoria_scaled(rows: list[dict]) -> list[dict]:
    """Tag each middle ("area bonus") affix as base or its ×1.75 Phantasmagoria variant. The catalog lists every
    such stat twice — the base value AND that value ×1.75 (Phantasmagoria's +75% pre-applied, e.g. '+6 % Aura
    Effect' AND '10.5 % Aura Effect'). Within a stat skeleton the smallest value is the base; any larger value is
    the scaled variant. BOTH are kept and flagged so the UI can show base mods on every prism except
    Phantasmagoria and the scaled mods only on Phantasmagoria (the +75% is read straight from the value, not
    applied again)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[_skeleton(r["modifier"])].append(r)
    out: list[dict] = []
    for g in groups.values():
        lo = min((v for v in (_first_num(r["modifier"]) for r in g) if v is not None), default=None)
        for r in g:
            v = _first_num(r["modifier"])
            scaled = lo is not None and v is not None and v != lo and lo > 0 and 1.6 <= v / lo <= 2.1
            out.append({**r, "scaled": scaled})
    return out


def _short_name(item_name: str) -> str:
    """'Ethereal Prism: Juggernaut' -> 'Juggernaut'."""
    return item_name.split(":", 1)[1].strip() if ":" in item_name else item_name.strip()


def _replace_target(text: str) -> str:
    """Tail name a 'Replaces … Advanced Talent Panel with <Name>' base affix points at."""
    m = re.search(r"Advanced Talent Panel with\s+(.+?)\s*$", text)
    return m.group(1).strip() if m else ""


def _dedupe(seq):
    seen, out = set(), []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _split_dnr_penalty(modifier: str) -> tuple[str, str]:
    """Return (penalty, short_name) for a do-not-replace affix; penalty = text before 'Mutated'."""
    idx = modifier.find("Mutated")
    penalty = modifier[:idx].strip() if idx >= 0 else ""
    m = _DNR_NAME_RE.search(modifier)
    name = m.group(1).strip() if m else ""
    return penalty, name


def categorize_prism_catalog(catalog: dict) -> dict:
    """Build the enriched crafting catalog (see module docstring)."""
    base = list(catalog.get("base_affixes") or [])
    random_aff = list(catalog.get("random_affixes") or [])

    add_options = _dedupe(b for b in base if b.startswith(_ADD_PREFIX))
    amplify = next((b for b in base if _AMPLIFY_MARK in b), "")
    replace_by_name: dict[str, str] = {}
    for b in base:
        if b.startswith(_REPLACE_PREFIX):
            replace_by_name[_replace_target(b)] = b

    # ── Random-affix pools ───────────────────────────────────────────────────
    area_size, middle, advanced = [], [], []
    do_not_replace: dict[str, list[dict]] = {}
    for r in random_aff:
        mod = r.get("modifier", "")
        typ = r.get("type", "")
        if not mod:
            continue
        if typ == "Prism Gauge - Rare":
            tm = _MIDDLE_TIER_RE.search(mod)
            tier = _TIER_KEY.get(tm.group(1).lower(), "") if tm else ""
            middle.append({"modifier": mod, "tier": tier})
        elif typ == "Prism Gauge - Legendary":
            om = _OVERALLOC_RE.search(mod)
            if om:
                advanced.append({"modifier": mod, "kind": "over_alloc",
                                 "tier": _TIER_KEY.get(om.group(1).lower(), ""), "count": int(om.group(2))})
            elif "ignore prerequisite" in mod.lower():
                advanced.append({"modifier": mod, "kind": "ignore_prereq"})
            else:
                advanced.append({"modifier": mod, "kind": "conditional"})
        else:  # untyped: area size or do-not-replace
            am = _AREA_RE.search(mod)
            if am:
                area_size.append({"modifier": mod, "cols": int(am.group(1)), "rows": int(am.group(2))})
            elif _DNR_MARK in mod:
                penalty, name = _split_dnr_penalty(mod)
                do_not_replace.setdefault(name, []).append({"modifier": mod, "penalty": penalty})

    # dedupe pools by their modifier text
    def _dedupe_by_mod(rows):
        seen, out = set(), []
        for row in rows:
            if row["modifier"] not in seen:
                seen.add(row["modifier"])
                out.append(row)
        return out
    area_size = _dedupe_by_mod(area_size)
    # Phantasmagoria's +75% only scales the middle-row ("area bonus") affixes, so the base/×1.75 pairs live only
    # there — tag them (keep both). The area-size and advanced/legendary slots have no scaled variants.
    middle = _tag_phantasmagoria_scaled(_dedupe_by_mod(middle))
    advanced = _dedupe_by_mod(advanced)
    for k in do_not_replace:
        do_not_replace[k] = _dedupe_by_mod(do_not_replace[k])

    # ── Items: resolve implicit + rarities ───────────────────────────────────
    items_out = []
    for it in (catalog.get("items") or []):
        if it.get("kind") != "ethereal_prism":
            continue
        short = _short_name(it.get("name", ""))
        low = short.lower()
        if low == "haze":
            implicit = {"kind": "add_choice", "options": add_options}
            rarities, default, tint = ["rare"], "rare", False
        elif low == "phantasmagoria":
            implicit = {"kind": "amplify", "text": amplify}
            rarities, default, tint = ["legendary"], "legendary", False
        else:
            implicit = {"kind": "replace", "text": replace_by_name.get(short, "")}
            rarities, default, tint = ["rare", "legendary"], "legendary", True
        # For replace prisms the item glossary holds the replacement Core Talent's description.
        gl = (it.get("glossary") or [{}])[0] if it.get("glossary") else {}
        items_out.append({
            "name": it.get("name", ""),
            "short_name": short,
            "kind": "ethereal_prism",
            "icon_url": it.get("icon_url", ""),
            "tags": it.get("tags") or [],
            "detail": it.get("detail") or [],
            "rarities": rarities,
            "default_rarity": default,
            "tint_when_rare": tint,
            "implicit": implicit,
            "replace_description": gl.get("description", "") if implicit["kind"] == "replace" else "",
        })

    return {
        "items": items_out,
        "area_size": area_size,
        "middle": middle,
        "advanced": advanced,
        "do_not_replace": do_not_replace,
        "penalties": list(_DNR_PENALTIES),
    }
