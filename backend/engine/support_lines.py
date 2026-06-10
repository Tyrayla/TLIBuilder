"""Parse a support skill's `description_lines` into gate + scaling lines + flat remainder.

`description_lines` is a single run-on string `Supports <X> Skills. <body><body…>` with the body
(irregularly) duplicated and no reliable delimiters between modifiers. Generic line-splitting is
unreliable, so we anchor on the one thing that IS reliable:

  * SCALING lines == the `progression[*].values` KEYS. We build a whitespace/number-tolerant regex from
    each key, find + remove its occurrence(s) in the body, and attach the per-tier values. These are the
    rollable damage lines that matter for DPS.
  * The FLAT remainder (everything else, deduped) is exposed as text for the mapper's targeted pattern
    matchers (P2) and for the spec to display — nothing is hidden.

Reused by the spec generator (now) and the support resolver (P2+).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re

_GATE_RE = re.compile(r"^\s*(Supports\s+[^.]*?\.)\s*", re.I)
_LV_RE = re.compile(r"\(\s*Lv\s*\d+\s*:[^)]*\)")
_NUM = r"[+\-]?\s*\d[\d.,]*"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _template(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[0-9]+(?:[.,][0-9]+)?", "#", s or "")).strip().lower()


def _template_to_regex(template: str) -> re.Pattern:
    """Glue-tolerant regex from a number-stripped template. The scraper inconsistently glues words
    (progression key `additionalIgniteDamage` vs body `additional Ignite Damage`), so we strip the
    template's whitespace and allow optional whitespace between EVERY character; '#' → a number."""
    pieces = []
    for ch in re.sub(r"\s+", "", template):
        pieces.append(_NUM if ch == "#" else (ch if ch.isalnum() else re.escape(ch)))
    return re.compile(r"\s*".join(pieces), re.I)


@dataclass
class SupportLine:
    text: str
    template: str
    scaling: bool
    tier_values: dict[int, str] = field(default_factory=dict)   # level → raw value string (scaling only)


@dataclass
class ParsedSupport:
    gate_text: str
    gate: str                       # "spell-only" | "attack-only" | "any skill"
    lines: list[SupportLine] = field(default_factory=list)   # scaling lines first, then flat


def _gate_category(gate_text: str, skill_tags: list[str]) -> str:
    g = (gate_text or "").lower()
    has_spell, has_attack = "spell" in g, "attack" in g
    if not gate_text:
        t = {x.lower() for x in (skill_tags or [])}
        has_spell, has_attack = "spell" in t, "attack" in t
    if has_spell and not has_attack:
        return "spell-only"
    if has_attack and not has_spell:
        return "attack-only"
    return "any skill"


def _progression_keys(skill_data: dict) -> dict[str, dict[int, str]]:
    out: dict[str, dict[int, str]] = {}
    for entry in skill_data.get("progression") or []:
        lvl = entry.get("level")
        for key, val in (entry.get("values") or {}).items():
            if key == "Descript":
                continue
            out.setdefault(_template(key), {})[lvl] = str(val)
    return out


_FLAT_SPLIT = re.compile(
    r"(?<=\.)\s+|\s+(?=[+\-]\d)"
    r"|\s+(?=Inflicts\b)|\s+(?=Buffs?\b)|\s+(?=When\b)|\s+(?=While\b)|\s+(?=Stacks?\b)"
    r"|\s+(?=The\s+supported\s+skill\b)|\s+(?=Supported\s+skills?\b)|\s+(?=Always\b)"
    r"|\s+(?=Triggers\b)|\s+(?=Automatically\b)|\s+(?=Prepares\b)|\s+(?=Gains\b)"
    r"|\s+(?=Auto)|\s+(?=Adds\b)|\s+(?=Transfers\b)"
)


def _dedup_flat(text: str) -> list[SupportLine]:
    """Collapse the doubled flat remainder into deduped flat SupportLines: split on sentence (.␠),
    signed-number starts, and clause-start keywords, dropping duplicate/empty fragments (first-wins)."""
    seen, out = set(), []
    for f in _FLAT_SPLIT.split(text):
        f = _norm(f)
        key = _template(f)
        if f and key and key not in seen:
            seen.add(key)
            out.append(SupportLine(text=f, template=key, scaling=False))
    return out


def parse_support(skill_data: dict) -> ParsedSupport:
    raw = _norm(" ".join(skill_data.get("description_lines") or []))
    m = _GATE_RE.match(raw)
    gate_text = m.group(1).strip() if m else ""
    body = raw[m.end():] if m else raw

    prog = _progression_keys(skill_data)
    scaling: list[SupportLine] = []
    for tmpl, tiers in prog.items():
        rx = _template_to_regex(tmpl)
        mt = rx.search(body)
        if mt:
            scaling.append(SupportLine(text=_norm(mt.group(0)), template=tmpl, scaling=True, tier_values=tiers))
            body = rx.sub(" ", body)               # remove ALL occurrences (the doubling)

    body = _LV_RE.sub(" ", body)
    return ParsedSupport(gate_text=gate_text, gate=_gate_category(gate_text, skill_data.get("skill_tags")),
                         lines=scaling + _dedup_flat(body))
