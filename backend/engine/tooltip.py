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
# Elixir tonic lines the engine models (recovery stage): restoration amounts + charging-progress / charge cadence.
_ELIXIR_MODELED_RE = re.compile(
    r"restores?\s+\d|charging\s+progress|gains?\s+\d+\s*charge|restoration\s+effect|affected\s+by[^.]*elixir", re.I)
_UNIVERSAL = "additional damage for the supported skill"     # rank line — resolved generically, keep its badge
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


# Buff trigger/duration clauses describe WHEN/how long a granted buff applies — they're mechanics, not
# stat modifiers, so they get no coverage badge (the buff's actual stat line, "Buffs grant +X% …", does).
_BUFF_FLAVOR_RE = re.compile(r"gains? a buff|the buff lasts|^buffs? last", re.I)


def _line(kind: str, badge_text: str, text: str = "", values_by_level: dict | None = None,
          coverage: str | None = None) -> dict:
    return {"kind": kind, "badge_text": badge_text, "text": text,
            "values_by_level": values_by_level, "coverage": coverage}


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
            # Buff trigger/duration clauses are flavor (no badge_text → no coverage badge).
            badge = "" if _BUFF_FLAVOR_RE.search(base) else base
            out.append(_line(_kind_for(base), badge, text=base))
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
    # aren't part of the per-tier roll clauses. Split each description_line INDIVIDUALLY (they're already
    # clause-separated) — joining them first glued a period-less line (e.g. Chilling Spike's "+4 large Icy
    # Blade Projectiles…") onto the next "(-N…)" line, which then deduped away.
    desc_clauses: list[str] = []
    _kept_t: list[str] = []
    for _ln in (skill_data.get("description_lines") or []):
        for _part in re.split(r"\\n|\n", _ln):     # some lines glue clauses with a (literal or real) newline
            for _c in _split_clauses(_part):
                _t = _template(_c)
                # Skip repeats AND superset/subset combined lines (the crawler sometimes emits a line that
                # concatenates two others) — keep the shorter, drop the one that contains/equals it.
                if not _t or any(_t == k or _t in k or k in _t for k in _kept_t):
                    continue
                _kept_t.append(_t)
                desc_clauses.append(_c)
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


# A short value-only entry the crawler split off from its label (e.g. "1.5", "5", "65%"). Used to re-join
# "Base Attack Frequency:" + "1.5" -> one line.
_VALUE_LINE_RE = re.compile(r"^[+\-]?\d[\d.,]*\s*%?$")
# Sentence boundary only — gentle split for the already-clause-level detailed_description (avoids the aggressive
# "for this/the supported skill" fragmentation that _CLAUSE_SPLIT applies to run-on strings).
_SENTENCE_SPLIT = re.compile(r"(?<=\.)\s+")


def _join_value_labels(entries: list[str]) -> list[str]:
    """Merge a trailing-colon label entry with the following bare-value entry (crawler artifact):
    ["Base Attack Frequency:", "1.5"] -> ["Base Attack Frequency: 1.5"]."""
    out, i = [], 0
    while i < len(entries):
        cur = _norm(entries[i] or "")
        if cur.endswith(":") and i + 1 < len(entries) and _VALUE_LINE_RE.match(_norm(entries[i + 1] or "")):
            out.append(_norm(cur + " " + _norm(entries[i + 1])))
            i += 2
            continue
        if cur:
            out.append(cur)
        i += 1
    return out


def _active_clauses(skill_data: dict, dmg_ref: str) -> list[str]:
    """The non-damage mechanic/special clauses for an active skill, ONE per line. Prefers the crawler's clean
    per-clause `detailed_description`; falls back to `simple_description` -> `description_lines`. The run-on
    per-level `Descript` is intentionally NOT used (it was the source of garbled multi-clause lines). Section
    headers ("Howling Gale:", "Buff:") and any clause that duplicates the damage line are dropped."""
    dd = skill_data.get("detailed_description") or []
    if dd:
        pieces: list[str] = []
        for entry in _join_value_labels(dd):
            e = _clean(entry)
            if not e or e.endswith(":"):          # section header (label with no value) — skip
                continue
            pieces.extend(_SENTENCE_SPLIT.split(e))   # break the occasional multi-sentence entry only
    else:
        src = skill_data.get("simple_description") or skill_data.get("description_lines") or []
        pieces = _split_clauses(" ".join(src))        # run-on summary — needs the aggressive splitter
    out, seen = [], set()
    for piece in pieces:
        c = _norm(piece)
        if not c or _GATE_RE.match(c) or _INSTALL_RE.search(c):
            continue
        if dmg_ref and _is_dup(c, dmg_ref):           # intrinsic damage value — shown by the damage line
            continue
        key = _template(c)
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _lines_active(skill_data: dict) -> list[dict]:
    prog = skill_data.get("progression") or []
    levels = _levels(prog)
    if not levels:
        return _generic_lines(skill_data)
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

    # Mechanic/special clauses — from the clean per-clause detailed_description (NOT the run-on Descript). Skip any
    # clause that duplicates a line already emitted above (e.g. a templated/scaling "Restores N% Max Life" line) so
    # the flat detail copy doesn't show alongside the level-scaled one.
    _emitted = [(ln.get("badge_text") or next(iter((ln.get("values_by_level") or {}).values()), "")) for ln in out]
    for c in _active_clauses(skill_data, next(iter(dmg.values()), "")):
        if any(b and _is_dup(c, b) for b in _emitted):
            continue
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


_BUFF_INTRO_RE = re.compile(r"gain the following buff|activates? the aura|activates focus|gains a buff", re.I)


def _lines_aura(skill_data: dict) -> list[dict]:
    """Aura / Focus buff skills. The buff text is the part after "… gain the following buff:". Show the intro
    as flavor (no badge) and each buff CLAUSE as its own badged line, so a modeled buff ("additional Lightning
    Damage") badges as working instead of the whole blob reading NYI. Uses the DETAILED (Lv20) description —
    the authoritative source the engine resolves from — falling back to the simple/legacy description."""
    src = (skill_data.get("detailed_description")
           or skill_data.get("simple_description")
           or skill_data.get("description_lines") or [])
    out: list[dict] = []
    buff: list[str] = []
    for raw in src:
        c = _clean(raw)
        if not c:
            continue
        if _BUFF_INTRO_RE.search(c):
            out.append(_line("flavor", "", text=c))   # intro flavor — never badged
        else:
            buff.append(c)
    # Join the buff lines before splitting: the crawler splits a single buff mid-sentence ("Gains" / "1
    # stack(s)…"), so per-line clauses fragment. Joining + clause-splitting reassembles whole modifiers.
    for clause in _split_clauses(" ".join(buff)):
        out.append(_line(_kind_for(clause), clause, text=clause))
    return out or _generic_lines(skill_data)


_GENERIC_FLAVOR_RE = re.compile(r"gains?\s+euphoria|^\s*casts?\b|^\s*lasts?\s+[\d.]+\s*s", re.I)


def _generic_lines(skill_data: dict) -> list[dict]:
    """Fallback when there's no per-level progression. Prefer the DETAILED description — its lines are already
    split per-modifier and curated for accuracy — rendering each as its own clause (so e.g. empower skills split
    properly instead of showing the simple one-line blob). Falls back to description_lines (joined + clause-split)
    when there's no detailed list."""
    detailed = [_clean(l) for l in (skill_data.get("detailed_description") or []) if _clean(l)]
    if detailed:
        out: list[dict] = []
        for c in detailed:
            if _GENERIC_FLAVOR_RE.search(c):
                out.append(_line("flavor", "", text=c))   # intro / "Lasts N s" — flavor, no badge
            else:
                out.append(_line(_kind_for(c), c, text=c))
        return out
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
        tags = skill_data.get("skill_tags") or []
        lines = _lines_aura(skill_data) if any(t in tags for t in ("Aura", "Focus")) else _lines_passive(skill_data)
        kind = "level"
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

    # Bespoke canvas supports (Howling Gale / Berserking Blade / …): their specific lines are modeled in
    # engine.skill_effects, not the generic mapper. (1) Resolve each line's badge there so stat clauses show
    # Consumed; SUPPRESS the badge on behavioral/flavor clauses ("Stacks up to 10", "Doubles the cap") that
    # carry no stat modifier — they'd otherwise badge NYI. (2) Emit `modeled_rolls` so the panel can show a
    # per-line roll slider for tunable lines. Non-bespoke skills are untouched (genuine gaps still badge NYI).
    from engine import skill_effects
    item_id = skill_data.get("item_id")
    modeled = []
    if item_id in skill_effects.GENERIC_GUARD_IDS:
        for ln in lines:
            bt = ln.get("badge_text") or ""
            if not bt or _UNIVERSAL in bt.lower():
                continue
            if not skill_effects.resolve_line_keys(bt):   # None or [] → not a stat clause → no badge
                ln["badge_text"] = ""
        modeled = skill_effects.modeled_rolls(item_id, skill_data)

    # Modeled active skills: positively mark their intrinsic mechanic lines as 'modeled' (green) so they don't
    # badge NYI. Only lines the engine TRULY models (per classify_intrinsic_line) go green; everything else is
    # left as-is, so genuinely-unimplemented mechanics honestly stay NYI. Clears badge_text on greened lines so
    # they don't ALSO run the keys path.
    from engine.skill_resolver import _REGISTRY, resolve_skill, classify_intrinsic_line
    if item_id in _REGISTRY:
        resolved = resolve_skill(skill_data)
        for ln in lines:
            bt = ln.get("badge_text") or ""
            if bt and classify_intrinsic_line(bt, resolved) == "modeled":
                ln["coverage"] = "modeled"
                ln["badge_text"] = ""

    # Elixir restoration tonics: the restoration + charging-progress lines ARE modeled (recovery stage parses the
    # "Restores N% Max Life within N s" amount + level-scaling, and the charge threshold drives the recast cadence),
    # so mark them green instead of leaving them to badge NYI.
    tags = skill_data.get("skill_tags") or []
    if "Elixir" in tags or "elixir" in tags:
        for ln in lines:
            base = ln.get("badge_text") or next(iter((ln.get("values_by_level") or {}).values()), "") or ln.get("text") or ""
            if _ELIXIR_MODELED_RE.search(base):
                ln["coverage"] = "modeled"
                ln["badge_text"] = ""

    return {"gate_text": gate, "level_kind": kind, "default_level": default,
            "available_levels": avail, "lines": lines, "modeled_rolls": modeled}
