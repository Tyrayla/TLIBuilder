import re
import warnings

from engine.modifier_lines import line_text, line_pooling_uuid

_COND_RE = re.compile(
    r"\s+(?:while\b|when\b|if\b|against\b|recently\b|on\s+hit\b|upon\b|"
    r"for\s+every\b|for\s+each\b|per\s+(?!second))",
    re.I,
)
_NUMERIC_RE = re.compile(
    # Range: (LO–HI) with an optional outer sign and optional inner signs on EACH bound, so negative ranges
    # like "(-50–-40)" parse as one range (min −50, max −40) instead of two separate fixed values.
    r'([+-]?)\(([+-]?\d+(?:\.\d+)?)\s*[–\-]\s*([+-]?\d+(?:\.\d+)?)\)'
    r'|([+-])(\d+(?:\.\d+)?)'
)


def parse_affix_text(text: str, modifier_id: str | None) -> dict:
    if text.startswith('<'):
        return {"raw_text": text, "modifier_id": modifier_id,
                "expression": text, "condition": None,
                "affix_kind": "placeholder", "numeric_values": []}

    m = _COND_RE.search(text)
    condition = text[m.start():].strip() if m else None

    numeric_values = []
    replacements: list[tuple[int, int, str]] = []
    for match in _NUMERIC_RE.finditer(text):
        raw = match.group(0)
        if match.group(2):
            sign = match.group(1) or ""
            nv = {"kind": "range", "sign": sign,
                  "min": float(match.group(2)), "max": float(match.group(3)), "raw": raw}
            repl = sign + "(#)"
        else:
            sign = match.group(4)
            nv = {"kind": "fixed", "sign": sign,
                  "value": float(match.group(5)), "raw": raw}
            repl = sign + "#"
        numeric_values.append(nv)
        replacements.append((match.start(), match.end(), repl))

    expression = text
    for start, end, repl in reversed(replacements):
        expression = expression[:start] + repl + expression[end:]

    return {"raw_text": text, "modifier_id": modifier_id,
            "expression": expression, "condition": condition,
            "affix_kind": "numeric" if numeric_values else "special",
            "numeric_values": numeric_values}


def _parse_affix(line) -> dict:
    """Parse one affix line (scraper ModifierLine dict or legacy plain string) into the stored
    affix dict, carrying the minted identity fields alongside the parse."""
    parsed = parse_affix_text(line_text(line), line.get("modifier_id") if isinstance(line, dict) else None)
    parsed["uuid"] = line.get("uuid") if isinstance(line, dict) else None
    parsed["pooling_uuid"] = line_pooling_uuid(line)
    return parsed


def _dedup_affix_lines(lines: list, item_id: str, variant_state: str, kind: str) -> list:
    """Drop exact-duplicate affix lines within one item variant's implicits/explicits array — the same
    crawl artifact `skill_importer._dedup_lines` guards against for skills, seen here on legendary gear:
    royal_cycle's `corroded` explicits repeats "+1 % Fire Damage per (10-12) Strength" verbatim under two
    different modifier_ids (51411940 and 51411950). Keyed on collapsed-whitespace line TEXT only — never
    modifier_id/uuid, because the artifact mints a fresh id per repeat, so an id-inclusive key would miss
    the exact case this exists to catch.

    Placeholder lines (raw text starting with "<", e.g. "<A Random Attack Sentry or Spell Sentry Affix>")
    are NEVER deduped: an item can legitimately carry several random-affix slots with identical placeholder
    wording (each slot resolves against its own `random_affixes` pool entry by POSITION, not by text), and
    SS12 data confirms this is a real, common shape (10 items have repeated-placeholder variants) — collapsing
    them would silently delete a real random-affix slot.

    Preserves first-occurrence order. Every drop emits a loud `warnings.warn` (project rule: never fail
    silently) naming the item, variant, and dropped text so a real import run can be audited, not just a
    passing test."""
    seen: set[str] = set()
    out: list = []
    for line in lines:
        text = line_text(line).strip()
        if not text or text.startswith("<"):
            out.append(line)
            continue
        key = " ".join(text.split())
        if key in seen:
            warnings.warn(
                f"legendary_gear_importer: dropped duplicate {kind} line on "
                f"item_id={item_id!r} variant={variant_state!r}: {text!r}",
                stacklevel=2,
            )
            continue
        seen.add(key)
        out.append(line)
    return out


def _parse_variant(item_id: str, variant_state: str, variant: dict) -> dict:
    implicits = _dedup_affix_lines(variant.get("implicits") or [], item_id, variant_state, "implicits")
    explicits = _dedup_affix_lines(variant.get("explicits") or [], item_id, variant_state, "explicits")
    return {
        "implicits": [_parse_affix(t) for t in implicits],
        "explicits": [_parse_affix(e) for e in explicits],
    }


def import_crawler_item(item_data: dict) -> dict:
    item_id = re.sub(r"[^a-z0-9]+", "_", item_data["name"].lower()).strip("_")

    variants: dict[str, dict] = {}
    for v in (item_data.get("variants") or []):
        state = v.get("rarity_state", "base")
        variants[state] = _parse_variant(item_id, state, v)

    random_affixes: dict[str, list] = {}
    for ra in (item_data.get("random_affixes") or []):
        state = ra.get("rarity_state", "base")
        options = [_parse_affix(o) for o in (ra.get("options") or [])]
        random_affixes.setdefault(state, []).append(
            {"placeholder": ra["placeholder"], "options": options}
        )

    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (item_data.get("glossary") or [])
        if g.get("term_id")
    }

    return {
        "item_id": item_id,
        "name": item_data["name"],
        "uuid": item_data.get("uuid"),
        "internal_id": item_data.get("internal_id"),
        "base_type": item_data.get("base_type", ""),
        "required_level": item_data.get("required_level"),
        "drop_level": item_data.get("drop_level"),
        "flavor_text": item_data.get("flavor_text"),
        "drop_sources": item_data.get("drop_sources", []),
        "glossary": glossary,
        "variants": variants,
        "random_affixes": random_affixes,
    }


_DIVINITY_SLATE_NAMES = {
    "a corner of divinity", "fallen starlight", "pedigree of gods", "space rift",
    "sparks of moth fire", "residence of stars", "when sparks set the prairie ablaze",
}


def import_crawler_items(items_data: list[dict]) -> list[dict]:
    return [
        import_crawler_item(item) for item in items_data
        if item.get("name") and item["name"].lower() not in _DIVINITY_SLATE_NAMES
    ]
