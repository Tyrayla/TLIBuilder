"""Importer for Belt Blends (a.k.a. Blending Rituals — the in-game /Belt page).

Scraper output (tlidb-scraper output/<season>/blending_rituals/blending_rituals.json) is a single
object: {entries: [...], glossary: [...]}. Each entry is one blendable belt talent with its crafting
materials. The effect TEXT resolves differently per talent type:
  - Medium Talent  → `effect` is the modifier text inline.
  - Core Talents   → `effect` is "[Name] <text>" (bracketed name + text inline).
  - Aromatic Talent→ `effect` is ONLY the talent name; the real text lives in the glossary by that name
                     (e.g. "Divine Grace" → glossary term 10148).

Scope: ingest + normalize + carry the glossary block (merged into the master glossary by
build_master_glossary.py). Modifier text is parsed into the standard affix shape via parse_affix_text,
but stat-key RESOLUTION is deferred (these talents aren't applied by the engine yet — that's a later
roadmap step, alongside Talent Tree Nodes / Core Talents).
"""
import re
from tools.legendary_gear_importer import parse_affix_text

# "Medium Talent Lv.0" / "Aromatic Talent Lv.0" / "Core Talents Lv.0" → (kind, level)
_TALENT_TYPE_RE = re.compile(r"^(.*?)\s*Lv\.?\s*(\d+)\s*$", re.I)
_KIND_MAP = {
    "medium talent": "medium",
    "aromatic talent": "aromatic",
    "core talents": "core",
    "core talent": "core",
}
# Core talents carry their name in a leading [Bracket]: "[Sacrifice] Changes the base effect ...".
_BRACKET_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.S)


def _normalize_talent_type(raw: str) -> tuple[str, int]:
    m = _TALENT_TYPE_RE.match(raw or "")
    label = (m.group(1) if m else (raw or "")).strip().lower()
    level = int(m.group(2)) if m else 0
    return _KIND_MAP.get(label, label.replace(" ", "_")), level


def import_crawler_belt_blends(data: dict) -> dict:
    entries = data.get("entries") or []
    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (data.get("glossary") or [])
        if g.get("term_id")
    }
    gloss_by_name = {
        (v["name"] or "").strip().lower(): v["description"]
        for v in glossary.values() if v.get("name")
    }

    blends = []
    for e in entries:
        kind, level = _normalize_talent_type(e.get("talent_type", ""))
        raw_effect = (e.get("effect") or "").strip()

        talent_name: str | None = None
        effect_text = raw_effect
        bm = _BRACKET_RE.match(raw_effect)
        if bm:                                   # core: "[Name] <text>"
            talent_name = bm.group(1).strip()
            effect_text = bm.group(2).strip() or raw_effect
        elif kind == "aromatic":                 # aromatic: name only → look up the glossary
            talent_name = raw_effect
            effect_text = gloss_by_name.get(raw_effect.lower(), raw_effect)

        affix = parse_affix_text(effect_text, e.get("modifier_id"))

        materials = []
        for m in (e.get("materials") or []):
            try:
                qty = int(m.get("quantity", 0) or 0)
            except (ValueError, TypeError):
                qty = 0
            materials.append({"name": m.get("name", ""), "quantity": qty})

        blends.append({
            "talent_id": e.get("talent_id"),
            "modifier_id": e.get("modifier_id"),
            "talent_type": kind,
            "talent_level": level,
            "talent_name": talent_name,
            "effect_raw": raw_effect,
            "effect_text": effect_text,
            "affix": affix,
            "materials": materials,
        })

    return {
        "blend_count": len(blends),
        "blends": blends,
        "glossary": glossary,
    }
