"""
Imports game-data skill JSON files into a season-stored _skills.json.

Each source file covers one skill category (e.g. "Activation Medium Skill.txt").
Fields kept per skill:
  item_id           — unique identifier (snake_case)
  name              — display name
  description_lines — list of display text lines
  raw_text          — full concatenated text (useful for search / future parsing)
  skill_tags        — list of tag strings (e.g. ["Attack", "Melee", "Active"])
"""

_KEEP_FIELDS = {"item_id", "name", "description_lines", "raw_text", "skill_tags"}


def clean_skill(raw: dict) -> dict:
    """Strip unwanted fields from a raw skill item."""
    cleaned = {k: v for k, v in raw.items() if k in _KEEP_FIELDS}
    # Ensure required fields are present with safe defaults
    cleaned.setdefault("item_id", "")
    cleaned.setdefault("name", "")
    cleaned.setdefault("description_lines", [])
    cleaned.setdefault("raw_text", "")
    cleaned.setdefault("skill_tags", [])
    return cleaned


def parse_skill_file(data: dict) -> list[dict]:
    """
    Parse a single skill JSON file.
    Expected shape: { "items": [ {...}, ... ], "extract_date": "...", ... }
    Returns a list of cleaned skill dicts.
    """
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("skill file must have an 'items' array")

    skills: list[dict] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        skill = clean_skill(raw)
        if skill["item_id"]:
            skills.append(skill)
    return skills


def merge_skills(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """
    Merge incoming skills into existing list, deduplicating by item_id.
    Incoming entries overwrite existing entries with the same item_id.
    """
    by_id: dict[str, dict] = {s["item_id"]: s for s in existing}
    for skill in incoming:
        by_id[skill["item_id"]] = skill
    return list(by_id.values())


# ── Crawler-format importer ────────────────────────────────────────────────

import re as _re

from engine.modifier_lines import line_text, line_texts, slim_checked

# The crawler leaves many values as UNREDUCED fractions ("41/4", "21/2", "6/100", "1/2") in both progression
# values and description text — e.g. Electric Overload's Lv1 "41/4" is 10.25, matching its "10.25 %" base.
# This plagues every data type, so normalize at import: evaluate a TWO-number N/M group to a clean decimal.
# The slash is overloaded: a chain of 3+ numbers ("1/3/6/100") is a per-enemy-tier LIST (Normal/Magic/Rare/
# Boss), NOT a fraction, so we match a whole slash-number group and only convert it when it has exactly two
# numbers — chains are left untouched. Ranges use "," or " - " (never "/"). 6 sig-figs drops trailing zeros
# without scientific notation here (41/4 -> "10.25", 21/2 -> "10.5", 1/3 -> "0.333333").
_FRACTION_RE = _re.compile(r"\b\d+(?:/\d+)+\b")
# A "/"-separated WORD list (Normal/Magic/Rare/Boss, Attack/Spell, Max/Min) signals that "/"-separated NUMBERS
# in the same string are a parallel per-category LIST, not a fraction — even a TWO-element one ("Normal/Magic …
# grants 1/3"). When present we skip the whole string, erring toward leaving a value unreduced (a harmless
# miss) rather than corrupting a list (a wrong conversion). No current string contains both, so this is pure
# future-proofing with zero effect on today's data.
_WORD_SLASH_LIST_RE = _re.compile(r"[A-Za-z]+/[A-Za-z]+")


def normalize_fractions(text: str) -> str:
    """Replace each unreduced two-number N/M fraction token in a string with its decimal value (e.g. '41/4'
    -> '10.25'). Slash chains of 3+ numbers (per-tier lists like '1/3/6/100') and any string carrying a
    parallel word-slash-list (a per-category list signal) are left unchanged."""
    if not isinstance(text, str) or "/" not in text or _WORD_SLASH_LIST_RE.search(text):
        return text
    def _sub(m):
        parts = m.group(0).split("/")
        if len(parts) != 2:
            return m.group(0)          # 3+ chain → a list, not a fraction
        num, den = int(parts[0]), int(parts[1])
        return m.group(0) if den == 0 else f"{num / den:.6g}"
    return _FRACTION_RE.sub(_sub, text)


def _normalize_deep(obj):
    """Recursively apply normalize_fractions to every string in a nested dict/list (e.g. progression values)."""
    if isinstance(obj, str):
        return normalize_fractions(obj)
    if isinstance(obj, list):
        return [_normalize_deep(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _normalize_deep(v) for k, v in obj.items()}
    return obj


# ── Structured duration extraction ────────────────────────────────────────
# The crawler has no structured duration field, so we mine every duration/timing clause from the description text
# into a `durations` list (collect-everything: most are unused today but we don't want to recrawl/redo to add them).
# Each clause is classified by kind so consumers can pick what they need without re-parsing prose:
#   skill        — the skill/buff's own duration ("Lasts 6 s.")
#   entity       — a spawned sub-entity's lifetime ("Sentry lasts 8 s", "Remnant lasts 0.65 s")
#   per_stack    — duration of ONE stack of a stacking buff ("… lasting for 1.2 s, up to 8 stacks"); carries max_stacks
#   interval     — a tick/proc period ("every 0.5 s", "every second")
#   duration_mod — a bonus TO some duration ("+3 s duration for Sentries", "Thundercloud Duration +2.5 s")
#   window       — a damage/restore-over-time window ("Deals X every second for 2 s", "Restores Y within 2 s")
# Bare fragment lines (a lone "1 s" the crawler split out) are NOT captured — we can't tell what they time.
_DN = r"([\d.]+)"
_DUR_SKILL_RE = _re.compile(r"^\s*lasts?\s+(?:for\s+)?" + _DN + r"\s*s\b", _re.I)
_DUR_ENTITY_RE = _re.compile(r"^(.*?\S)\s+lasts?\s+(?:for\s+)?" + _DN + r"\s*s\b", _re.I)
_DUR_MOD_RE = _re.compile(r"\+\s*" + _DN + r"\s*s\b[^.]*?\bduration\b(?:\s+for\s+([A-Za-z][\w ]*?))?(?:[.,]|$)", _re.I)
_DUR_MOD_REV_RE = _re.compile(r"\bduration\b[^.]*?\+\s*" + _DN + r"\s*s\b", _re.I)
_DUR_STACKDUR_RE = _re.compile(r"(?:lasting for|for|lasts?(?:\s+for)?)\s+" + _DN + r"\s*s\b", _re.I)
_DUR_MAXSTACK_RE = _re.compile(r"(?:up to|stacking up to)\s+(\d+)\s*(?:time|stack)", _re.I)
_DUR_INTERVAL_RE = _re.compile(r"every\s+(?:" + _DN + r"\s*s|second)\b|interval:\s*" + _DN, _re.I)
_DUR_WINDOW_RE = _re.compile(r"(?:deals|restores|inflict\w*|gain\w*|reaps)\b[^.]*?\b(?:within|in|for)\s+" + _DN + r"\s*s\b", _re.I)
_DUR_ANY_RE = _re.compile(_DN + r"\s*s\b")
_DUR_STACKHINT_RE = _re.compile(r"stack", _re.I)
_DUR_ARTICLE_RE = _re.compile(r"^(?:the|a|an|each|this|that)\s+", _re.I)
# Leading number of a cooldown string ("10 s" -> 10.0); the crawler now emits cooldown as a structured field.
_COOLDOWN_NUM_RE = _re.compile(r"([\d.]+)")


def _dur_entry(kind: str, seconds, source: str, subject=None, max_stacks=None) -> dict:
    return {"kind": kind, "seconds": float(seconds) if seconds is not None else None,
            "subject": subject, "max_stacks": max_stacks, "source": source}


def extract_durations(lines: list[str]) -> list[dict]:
    """Classify every duration/timing clause across the given description lines into structured entries (see the
    kind taxonomy above). One entry per matched clause, in text order; the `source` line is kept for traceability."""
    out: list[dict] = []
    for raw in lines or []:
        s = line_text(raw).strip()
        if not s or (not _DUR_ANY_RE.search(s) and "duration" not in s.lower()):
            continue
        stacked = bool(_DUR_STACKHINT_RE.search(s))
        m = _DUR_SKILL_RE.match(s)
        if m:
            out.append(_dur_entry("skill", m.group(1), s))
            continue
        m = _DUR_ENTITY_RE.match(s)
        if m and not stacked:
            subj = _DUR_ARTICLE_RE.sub("", m.group(1).strip()).strip()
            if 1 <= len(subj.split()) <= 4:
                out.append(_dur_entry("entity", m.group(2), s, subject=subj))
                continue
        dm = _DUR_MOD_RE.search(s) or _DUR_MOD_REV_RE.search(s)
        if dm:
            subj = (dm.lastindex == 2 and dm.group(2) or "")
            out.append(_dur_entry("duration_mod", dm.group(1), s, subject=(subj.strip() or None)))
            continue
        if stacked:
            md = _DUR_STACKDUR_RE.search(s)
            if md:
                ms = _DUR_MAXSTACK_RE.search(s)
                out.append(_dur_entry("per_stack", md.group(1), s,
                                      max_stacks=int(ms.group(1)) if ms else None))
                continue
        mi = _DUR_INTERVAL_RE.search(s)
        if mi:
            out.append(_dur_entry("interval", mi.group(1) or mi.group(2) or "1", s))
            continue
        mw = _DUR_WINDOW_RE.search(s)
        if mw:
            out.append(_dur_entry("window", mw.group(1), s))
            continue
    return out


def _skill_duration(durations: list[dict]) -> float | None:
    """The skill/buff's own duration (first `skill`-kind entry) — the convenience scalar for simple readers."""
    for d in durations:
        if d["kind"] == "skill":
            return d["seconds"]
    return None


def _as_lines(val) -> list:
    """Normalize a description field to a list of non-empty lines. The recrawl emits lists of
    ModifierLine dicts (older data: plain strings / a single string); empties are dropped by text."""
    if isinstance(val, list):
        return [x for x in val if line_text(x).strip()]
    if (isinstance(val, str) or isinstance(val, dict)) and line_text(val).strip():
        return [val]
    return []


def _dedup_lines(lines: list[dict]) -> list[dict]:
    """Drop duplicate description lines (the recrawl emits each effect line twice for most supports — ~59/60
    support_skill, ~41/60 noble), preserving first-occurrence order. Keyed on collapsed whitespace of the
    line TEXT so trivial spacing differences still dedup. Exact-duplicate description lines are always the
    crawler artifact, never meaningful, so this is safe across all skill types (active descriptions have no
    dupes and are unaffected)."""
    seen: set[str] = set()
    out: list[dict] = []
    for line in lines:
        key = " ".join(line_text(line).split())
        if key and key not in seen:
            seen.add(key)
            out.append(line)
    return out


# A minion ability deals damage as a coefficient of its (shared) minion Base Damage — "Deals X% of Base Damage"
# (the "% weapon Attack Damage" wording seen on some minions is a crawler inconsistency meaning the same thing).
# This is distinct from `effectiveness_of_added_damage` (which scales ADDED flat damage). We mine it so the minion
# engine can multiply the shared per-level Base Damage table by this coefficient.
_BASE_DMG_COEFF_RE = _re.compile(r"([\d.]+)\s*%\s*(?:of\s*)?(?:base damage|weapon attack damage)", _re.I)


def _base_damage_coefficient(progression: list, lines: list[str]):
    """Extract a minion ability's '% of Base Damage' hit coefficient. Prefers per-level values mined from
    `progression`; falls back to the single value in the description lines. Returns {level: pct} (per-level),
    a float (single value), or None when the skill states no base-damage coefficient (e.g. pure buff skills)."""
    per_level: dict[int, float] = {}
    for entry in progression or []:
        lvl = entry.get("level")
        if lvl is None:
            continue
        text = " ".join(str(v) for v in (entry.get("values") or {}).values())
        m = _BASE_DMG_COEFF_RE.search(text)
        if m:
            per_level[int(lvl)] = float(m.group(1))
    if per_level:
        return per_level
    for line in lines or []:
        m = _BASE_DMG_COEFF_RE.search(line_text(line))
        if m:
            return float(m.group(1))
    return None


def import_crawler_skill(data: dict, owner_id: str | None = None) -> dict:
    """Import a single crawler skill file (one JSON file per skill), recursing into nested `minion_skills`.

    The recrawl emits `simple_description` (Lv1) and `detailed_description` (Lv20) as SPLIT LINE LISTS, plus a
    `sealed_mana` reservation amount. We keep both anchor descriptions (for aura/focus per-level interpolation)
    and `sealed_mana`; `description_lines` mirrors the simple (Lv1) lines for back-compat with existing readers.

    A minion owner (a summon/module skill) nests its minion's abilities under `minion_skills`; we preserve that
    tree, tag each child with `owner_id`, and mine each child's Base-Damage coefficient. Children are kept ONLY
    nested (they are not hoisted into the flat top-level skills array), so they never appear in the active-skill
    picker but stay reachable via their owner for the minion DPS engine + panel.
    """
    name = data.get("name", "")
    item_id = _re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    variant = (data.get("variants") or [{}])[0]
    glossary = {
        g["term_id"]: {"name": g.get("name", ""), "description": g.get("description", "")}
        for g in (data.get("glossary") or [])
        if g.get("term_id")
    }
    # Stored line shape: slim {text, uuid, pooling_uuid, modifier_id} dicts. Fraction normalization is a
    # value-only transform, so the minted ids carry onto the normalized text (identity is value-stripped);
    # slim_checked verifies that per line and degrades to uuid-less rather than storing a lying identity.
    simple = _dedup_lines([slim_checked(l, normalize_fractions(line_text(l)))
                           for l in _as_lines(variant.get("simple_description"))])
    detailed = _dedup_lines([slim_checked(l, normalize_fractions(line_text(l)))
                             for l in _as_lines(variant.get("detailed_description"))])
    # Structured combat fields the recrawl now emits directly (cooldown, icon_url) plus two we derive here:
    #   charges  — Help DB: only a skill with a cooldown can hold charges; default 1 (explicit higher counts
    #              aren't reliably stated in the text, so we don't guess — see docs/BACKLOG.md). None = no cooldown.
    #   duration — parsed from the "Lasts N s" line (no structured field exists for it).
    cooldown = variant.get("cooldown")
    charges = 1 if cooldown else None
    durations = extract_durations(detailed or simple)
    duration = _skill_duration(durations)
    out = {
        "item_id": item_id,
        "name": name,
        "uuid": data.get("uuid"),
        "internal_id": data.get("internal_id"),
        "skill_type": data.get("skill_type", ""),
        "skill_tags": variant.get("tags") or [],
        "description_lines": simple,                     # Lv1 lines (back-compat readers use this)
        "simple_description": simple,                    # Lv1 anchor (split lines)
        "detailed_description": detailed,                # Lv20 anchor (split lines)
        "raw_text": " ".join(line_texts(detailed or simple)),
        "max_level": variant.get("max_level"),
        "mana_cost": variant.get("mana_cost"),
        "sealed_mana": variant.get("sealed_mana"),       # reservation amount, e.g. "50%"
        "cast_speed": variant.get("cast_speed"),
        "cooldown": cooldown,                            # e.g. "10 s"; None when the skill has no cooldown
        "charges": charges,                              # base max charges (1 if cooldown, else None)
        "duration": duration,                            # convenience scalar: the skill's own "Lasts N s", or None
        "durations": durations,                          # full structured duration/timing capture (see extract_durations)
        "icon_url": variant.get("icon_url"),             # CDN skill icon (not used yet; stored for future use)
        "effectiveness_of_added_damage": variant.get("effectiveness_of_added_damage"),
        "weapon_restriction": variant.get("weapon_restriction"),
        "main_stat": variant.get("main_stat"),
        "progression": _normalize_deep(data.get("progression") or variant.get("progression") or []),
        "glossary": glossary,
    }
    # Dev-set "can contribute to DPS" override — only persist when explicitly present (else /api/skills
    # derives it from skill_type). Never write null, which would read as "explicitly ineligible".
    if "dps_eligible" in data:
        out["dps_eligible"] = bool(data["dps_eligible"])
    # Minion-ability metadata: owner back-link + the "% of Base Damage" hit coefficient (only for nested abilities).
    if owner_id is not None:
        out["owner_id"] = owner_id
        coeff = _base_damage_coefficient(out["progression"], detailed or simple)
        if coeff is not None:
            out["base_damage_coefficient"] = coeff
    # Preserve nested minion abilities (the summon/module owner's minion_skills tree), recursing the same builder.
    children = data.get("minion_skills") or []
    if children:
        out["minion_skills"] = [import_crawler_skill(c, owner_id=item_id) for c in children if c.get("name")]
    return out


def import_crawler_skills(items_data: list[dict]) -> list[dict]:
    return [import_crawler_skill(item) for item in items_data if item.get("name")]
