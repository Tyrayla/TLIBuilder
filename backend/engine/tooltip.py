"""Build a structured, level-aware tooltip spec for any skill/support type.

Single source of truth for tooltip TEXT: this parses the same data the engine consumes
(``description_lines`` + ``progression``) into per-line, per-level display strings, so the
renderer just picks the current level/tier and attaches a status badge per line.

Value-display rule (owner-confirmed, detectable by parentheses alone):
  * bare ``X-Y`` range      -> a damage-add spread, shown as the FULL range at the level.
  * parenthesised ``(a-b)%`` -> roll-variance within a stat (tiered supports only),
    shown as the MIDPOINT (matches what the engine computes).

The backend does NOT resolve badges (Consumed/Inactive/NYI depend on the live build's
consumed/universe sets, a frontend concern); it only emits ``badge_text`` per line for the
frontend text->stat resolver. The gate/support-target line ("Supports X Skills") and
install-restriction meta are kept out of the rendered ``lines`` by design.
"""
from __future__ import annotations
import re

from engine.support_lines import parse_support, _norm, _template
from engine.support_mapper import _level_value, parse_value

# ── classification ─────────────────────────────────────────────────────────────
_STANDARD_TYPES = {"support_skill"}
_TIERED_TYPES = {"magnificent_support_skill", "noble_support_skill", "activation_medium_skill"}
_ACTIVE_TYPES = {"active_skill", "modularization_skill"}
_PASSIVE_TYPES = {"passive_skill"}

# ── text cleaning ──────────────────────────────────────────────────────────────
_SKILLSTONE = re.compile(r"#\s*skillstone[^#]*#", re.I)     # "#skillstone, 1894, affix#" data artifact
_LV_ANNOT = re.compile(r"\(\s*Lv\.?\s*\d+\s*:[^)]*\)")       # "(Lv1:2)" per-level annotations
_INSTALL_RE = re.compile(r"can only be installed", re.I)     # install-restriction meta (not an effect)
_GATE_RE = re.compile(r"^\s*Supports\b", re.I)              # "Supports X Skills." support-target line
_RANGE_NUM = re.compile(r"(\d[\d.,]*)\s*[‐-―–\-]\s*(\d[\d.,]*)")   # "1 - 4", "73-1393"
_LEAD_NUM = re.compile(r"[+\-]?\d[\d.,]*")
_PAREN_PCT = re.compile(r"\(\s*[^)]*?\d[^)]*?\)\s*%")        # "(28-30) %" roll-variance group


def _clean(text: str) -> str:
    return _norm(_LV_ANNOT.sub("", _SKILLSTONE.sub("", text or "")))


def _fmt(n: float) -> str:
    return str(int(n)) if n == int(n) else f"{n:.2f}".rstrip("0").rstrip(".")


def _kind_for(text: str) -> str:
    """A non-scaling line is 'special' if it carries an effect value, else 'flavor' (pure behavioral)."""
    return "special" if re.search(r"\d", text or "") else "flavor"


def _line(kind: str, badge_text: str, text: str = "", values_by_level: dict | None = None) -> dict:
    return {"kind": kind, "badge_text": badge_text, "text": text,
            "values_by_level": values_by_level}


# ── value rendering ────────────────────────────────────────────────────────────
def _render_scaled(base: str, vals: list[float]) -> str:
    """Substitute a scaling line's level value(s) into its base text. A min-max pair shown over an
    ``X - Y`` range in the text -> the FULL range; otherwise the single value replaces the lead number."""
    if not vals:
        return base
    if len(vals) >= 2 and _RANGE_NUM.search(base):
        return _RANGE_NUM.sub(f"{_fmt(vals[0])} - {_fmt(vals[1])}", base, count=1)
    if _LEAD_NUM.search(base):
        return _LEAD_NUM.sub(_fmt(vals[0]), base, count=1)
    return f"{base} ({_fmt(vals[0])})"


def _render_midpoint(text: str) -> tuple[str, bool]:
    """Replace the first ``(a-b)%`` roll-variance group with its signed midpoint. Returns
    (rendered_text, matched)."""
    m = _PAREN_PCT.search(text)
    if not m:
        return text, False
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", m.group(0))]
    if not nums:
        return text, False
    mid = sum(nums) / len(nums)
    if "(-" in m.group(0) or "(−" in m.group(0):
        mid = -mid
    return text[:m.start()] + f"{_fmt(mid)} %" + text[m.end():], True


# ── simple-vs-detailed dedup ───────────────────────────────────────────────────
_STOP = {"the", "for", "and", "this", "skill", "that", "with", "when", "deals", "deal",
         "of", "to", "a", "is", "its", "in", "on", "it", "was", "if", "an", "by",
         "additional", "supported"}   # generic modifier words — too common to imply same effect


def _sig_tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if w not in _STOP and len(w) > 2}


def _is_dup(a: str, b: str) -> bool:
    """Two clauses describe the same effect: equal/subset templates, or high significant-token overlap."""
    ta, tb = _template(a), _template(b)
    if ta and tb and (ta == tb or ta in tb or tb in ta):
        return True
    sa, sb = _sig_tokens(a), _sig_tokens(b)
    if not sa or not sb:
        return False
    return len(sa & sb) / min(len(sa), len(sb)) >= 0.6


def _merge_detail(authoritative: list[str], extra: list[str]) -> list[str]:
    """Keep all authoritative (progression-derived) clauses; append only the extra (description_lines)
    clauses that don't duplicate one — so per-level/detailed copies win over the simple summary."""
    out = list(authoritative)
    for c in extra:
        if not any(_is_dup(c, k) for k in out):
            out.append(c)
    return out


# ── clause splitting ───────────────────────────────────────────────────────────
# Tiered run-ons glue several clauses with no reliable delimiter. Split after a clause's
# "for the supported/this skill" suffix or a sentence period, and before a leading +/-number
# (optionally parenthesised) NOT preceded by "skill" (which marks a "The supported skill +X" prefix),
# and before sentence-starting keywords.
_CLAUSE_SPLIT = re.compile(
    r"(?<=for the supported skill)\s+|(?<=for this skill)\s+|(?<=\.)\s+"
    r"|(?<!skill)\s+(?=[+\-]\(?\s*\d)"
    r"|\s+(?=When\b)|\s+(?=While\b)|\s+(?=Always\b)|\s+(?=Inflicts\b)|\s+(?=Gains\b)"
    r"|\s+(?=Supported skills?\b)"
)


def _split_clauses(text: str) -> list[str]:
    out, seen = [], set()
    for piece in _CLAUSE_SPLIT.split(_clean(text)):
        c = _norm(piece)
        if not c or _GATE_RE.match(c) or _INSTALL_RE.search(c):
            continue
        key = _template(c)
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out


# ── per-type builders ──────────────────────────────────────────────────────────
def _levels(progression: list) -> list[int]:
    return sorted({e.get("level") for e in (progression or []) if isinstance(e.get("level"), int)})


def _strip_name_prefix(text: str, name: str) -> str:
    """Drop a leading 'SkillName:' label the progression Descript prepends."""
    if name and text.lower().startswith(name.lower() + ":"):
        return _norm(text[len(name) + 1:])
    return text


# Special progression keys carrying skill damage/flavor/effectiveness/tier text (handled per-type);
# any OTHER key is a support-style {template: value} scaling line.
_SPECIAL_KEYS = {"damage", "Descript", "Effectiveness of added damage", "name"}


def _unglue(s: str) -> str:
    """Separate a digit glued to a letter (scraper artifact, e.g. 'up to2Machine' -> 'up to 2 Machine')."""
    return _norm(re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", s))


def _templated_lines(by_lvl: dict, levels: list[int]) -> list[dict]:
    """Scaling lines from support-style ``{template: value}`` progression keys (some actives/passives use
    this shape with no damage/Descript key, e.g. Blink, summon caps). The key text is the display base."""
    out, keys = [], []
    for lvl in levels:
        for k in (by_lvl.get(lvl) or {}):
            if k not in _SPECIAL_KEYS and k not in keys:
                keys.append(k)
    for k in keys:
        base = _unglue(_clean(k))
        vbl = {lvl: _render_scaled(base, parse_value(v))
               for lvl in levels if (v := (by_lvl.get(lvl) or {}).get(k)) is not None}
        if vbl:
            out.append(_line("scaling", base, values_by_level=vbl))
    return out


def _lines_standard_support(skill_data: dict) -> list[dict]:
    parsed = parse_support(skill_data)
    out: list[dict] = []
    for ln in parsed.lines:
        base = _clean(ln.text)
        if not base or _INSTALL_RE.search(base):
            continue
        if ln.scaling and ln.tier_values:
            vbl = {lvl: _render_scaled(base, _level_value(ln, lvl)) for lvl in sorted(ln.tier_values)}
            out.append(_line("scaling", base, values_by_level=vbl))
        else:
            out.append(_line(_kind_for(base), base, text=base))
    return out


def _lines_tiered(skill_data: dict) -> list[dict]:
    prog = skill_data.get("progression") or []
    stype = skill_data.get("skill_type")
    tiers = _levels(prog)
    if stype == "activation_medium_skill":
        tiers = [t for t in tiers if t != 3]          # negative penalty tier — not selectable in game
    if not tiers:
        return _generic_lines(skill_data)
    by_tier = {e.get("level"): (e.get("values") or {}).get("name") or "" for e in prog}
    tier_clauses = {t: _split_clauses(by_tier.get(t, "")) for t in tiers}

    base_t = 1 if 1 in tiers else tiers[0]
    base_list = tier_clauses.get(base_t, [])

    # Fixed lines from description_lines (e.g. the universal "+20% additional damage" rank line) that
    # aren't part of the per-tier roll clauses.
    desc_clauses = _split_clauses(" ".join(skill_data.get("description_lines") or []))
    fixed = [c for c in desc_clauses if not any(_is_dup(c, b) for b in base_list)]

    out: list[dict] = [_line(_kind_for(c), c, text=c) for c in fixed]
    for idx, clause in enumerate(base_list):
        if _PAREN_PCT.search(clause):
            vbl = {}
            for t in tiers:
                cl = tier_clauses.get(t, [])
                vbl[t] = _render_midpoint(cl[idx] if idx < len(cl) else clause)[0]
            out.append(_line("scaling", _render_midpoint(clause)[0], values_by_level=vbl))
        else:
            out.append(_line(_kind_for(clause), clause, text=clause))
    return out


def _lines_active(skill_data: dict) -> list[dict]:
    prog = skill_data.get("progression") or []
    levels = _levels(prog)
    if not levels:
        return _generic_lines(skill_data)
    name = skill_data.get("name") or ""
    by_lvl = {e.get("level"): (e.get("values") or {}) for e in prog}
    out: list[dict] = []

    # Primary damage scaling line (already a full per-level "Deals X-Y ..." string).
    dmg = {lvl: _clean(by_lvl[lvl].get("damage") or "") for lvl in levels}
    dmg = {lvl: v for lvl, v in dmg.items() if v}
    if dmg:
        out.append(_line("scaling", "", values_by_level=dmg))   # intrinsic core damage — not a modifier, no badge

    # Effectiveness of added damage (when present / non-empty).
    eff = {lvl: _clean(by_lvl[lvl].get("Effectiveness of added damage") or "") for lvl in levels}
    eff = {lvl: f"Effectiveness of added damage: {v}" for lvl, v in eff.items() if v}
    if eff:
        out.append(_line("scaling", "", values_by_level=eff))   # intrinsic — no badge

    out.extend(_templated_lines(by_lvl, levels))   # support-style {template: value} keys (Blink, summons)

    # Special clauses: authoritative = Descript (minus its damage clause), extra = description_lines.
    rep = base = levels[-1] if levels[-1] in by_lvl else levels[0]
    descript = _strip_name_prefix(_clean(by_lvl[rep].get("Descript") or ""), name)
    auth = [c for c in _split_clauses(descript) if not _is_dup(c, next(iter(dmg.values()), ""))] if dmg else _split_clauses(descript)
    extra = _split_clauses(" ".join(skill_data.get("description_lines") or []))
    if dmg:
        extra = [c for c in extra if not _is_dup(c, next(iter(dmg.values())))]
    for c in _merge_detail(auth, extra):
        out.append(_line(_kind_for(c), c, text=c))
    return out


def _lines_passive(skill_data: dict) -> list[dict]:
    prog = skill_data.get("progression") or []
    levels = _levels(prog)
    name = skill_data.get("name") or ""
    out: list[dict] = []
    if levels:
        by_lvl = {e.get("level"): (e.get("values") or {}) for e in prog}
        # Pair the per-level Descript clauses by template across levels -> per-level scaling lines.
        rep = levels[-1] if levels[-1] in by_lvl else levels[0]
        rep_clauses = _split_clauses(_strip_name_prefix(_clean(by_lvl[rep].get("Descript") or ""), name))
        for idx, clause in enumerate(rep_clauses):
            vbl = {}
            for lvl in levels:
                cls = _split_clauses(_strip_name_prefix(_clean(by_lvl[lvl].get("Descript") or ""), name))
                vbl[lvl] = cls[idx] if idx < len(cls) else clause
            scaling = len({v for v in vbl.values()}) > 1 and bool(re.search(r"\d", clause))
            # Intrinsic "% of Base Damage" lines are the skill's core, not a modifier → suppress the badge.
            badge = "" if "base damage" in clause.lower() else clause
            out.append(_line("scaling" if scaling else _kind_for(clause), badge,
                             text=clause, values_by_level=vbl if scaling else None))
        out.extend(_templated_lines(by_lvl, levels))   # support-style {template: value} keys
        extra = _split_clauses(" ".join(skill_data.get("description_lines") or []))
        for c in extra:
            if not any(_is_dup(c, rc) for rc in rep_clauses):
                out.append(_line(_kind_for(c), c, text=c))
        return out
    return _generic_lines(skill_data)


def _generic_lines(skill_data: dict) -> list[dict]:
    """Fallback: split description_lines into shown clauses (no per-level data available)."""
    return [_line(_kind_for(c), c, text=c)
            for c in _split_clauses(" ".join(skill_data.get("description_lines") or []))]


# ── public entry ───────────────────────────────────────────────────────────────
def build_tooltip(skill_data: dict) -> dict:
    """Return a serialised TooltipSpec for a single skill/support."""
    stype = skill_data.get("skill_type") or ""
    prog = skill_data.get("progression") or []
    gate = parse_support(skill_data).gate_text if stype in _STANDARD_TYPES or stype in _TIERED_TYPES else None

    if stype in _STANDARD_TYPES:
        lines, kind, default = _lines_standard_support(skill_data), "level", 20
    elif stype in _TIERED_TYPES:
        lines, kind, default = _lines_tiered(skill_data), "tier", 1
    elif stype in _ACTIVE_TYPES:
        lines, kind = _lines_active(skill_data), "level"
        default = skill_data.get("max_level") or (max(_levels(prog)) if _levels(prog) else 1)
    elif stype in _PASSIVE_TYPES:
        lines, kind = _lines_passive(skill_data), "level"
        default = skill_data.get("max_level") or (max(_levels(prog)) if _levels(prog) else 1)
    else:
        lines, kind, default = _generic_lines(skill_data), "level", skill_data.get("max_level") or 1

    # Available levels = union of every scaling line's levels (else the default).
    avail = sorted({lvl for ln in lines if ln["values_by_level"] for lvl in ln["values_by_level"]})
    if stype in _TIERED_TYPES:
        tiers = _levels(prog)
        if stype == "activation_medium_skill":
            tiers = [t for t in tiers if t != 3]
        avail = tiers or avail
    if not avail:
        avail = [default]
    if default not in avail:
        default = max((l for l in avail if l <= default), default=avail[0]) if kind == "level" \
            else (1 if 1 in avail else avail[0])

    return {"gate_text": gate, "level_kind": kind, "default_level": default,
            "available_levels": avail, "lines": lines}
