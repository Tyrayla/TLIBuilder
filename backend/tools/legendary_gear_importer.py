import re

_COND_RE = re.compile(
    r"\s+(?:while\b|when\b|if\b|against\b|recently\b|on\s+hit\b|upon\b|"
    r"for\s+every\b|for\s+each\b|per\s+(?!second))",
    re.I,
)
_NUMERIC_RE = re.compile(
    r'([+-]?)\((\d+(?:\.\d+)?)[–\-](\d+(?:\.\d+)?)\)'
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


def _parse_variant(variant: dict) -> dict:
    implicits = [parse_affix_text(t, None) for t in (variant.get("implicits") or [])]
    explicits = [
        parse_affix_text(e["text"], e.get("modifier_id"))
        for e in (variant.get("explicits") or [])
    ]
    return {"implicits": implicits, "explicits": explicits}


def import_crawler_item(item_data: dict) -> dict:
    item_id = re.sub(r"[^a-z0-9]+", "_", item_data["name"].lower()).strip("_")

    variants: dict[str, dict] = {}
    for v in (item_data.get("variants") or []):
        variants[v.get("rarity_state", "base")] = _parse_variant(v)

    random_affixes: dict[str, list] = {}
    for ra in (item_data.get("random_affixes") or []):
        state = ra.get("rarity_state", "base")
        options = [parse_affix_text(o["text"], o.get("modifier_id")) for o in (ra.get("options") or [])]
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


def import_crawler_items(items_data: list[dict]) -> list[dict]:
    return [import_crawler_item(item) for item in items_data if item.get("name")]
