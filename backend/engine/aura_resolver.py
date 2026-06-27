"""Resolve equipped aura / Focus passive skills into player stat contributions.

Auras (`passive_skill` + "Aura" tag) and Focus skills grant their buff to the player. Buff values come from the
skill's `simple_description` (Lv1) and `detailed_description` (Lv20) anchor lines, parsed through the SAME unified
text→stat pipeline talent/gear use (`parse_mod` = server's `_parse_custom_mod_text`), matched by stat key across
the two anchors and **linearly interpolated** to the equipped level (extrapolated past Lv20 like other skills),
then scaled by **Aura Effect**. Output matches the `node_contributions` shape, so the aggregator folds it into
`BuildSource` (tagged source_type "aura").

Stacking buffs ("N% <stat> per stack … Stacks up to M") become a per-aura **settable numeric condition**
(`<skill_id>_stacks`, max M): the per-stack contribution rides a `{"op":"per","key":…}` gate so the aggregator
multiplies it by the user-set stack count. Buff lines the parser can't resolve are surfaced as NYI — never
silently dropped.
"""
from __future__ import annotations
import re

from models.stat import Stat as _Stat

_VALID_STATS = {s.value for s in _Stat}

_INTRO_RE = re.compile(r"gain the following buff|activates? the aura|activates focus|gains a buff", re.I)
_AURA_EFFECT_KEYS = {"aura_effect_inc", "aura_effect_additional"}
# "2.5 % additional Aura Effect per stack" / "5/2% additional Aura Effect per stack of the buff". The phrase
# excludes '%' so a preceding unrelated "+19 %" can't be grabbed — the value must sit right before the phrase.
_PER_STACK_RE = re.compile(r"([\d.]+(?:\s*/\s*\d+)?)\s*%\s*([^%]+?)\s+per stack", re.I)
_MAX_STACK_RE = re.compile(r"stacks?\s+up\s+to\s*(\d+)\s*time", re.I)


def _num(s: str) -> float:
    s = s.strip()
    if "/" in s:
        a, b = s.split("/", 1)
        return float(a) / float(b) if float(b) else 0.0
    return float(s)


def _buff_lines(lines, intro_re=_INTRO_RE) -> list[str]:
    """Drop the intro line ("gain the following buff" / "gains Euphoria") + blanks; keep the buff lines.
    `intro_re` is overridable so other buff resolvers (e.g. empower's Euphoria) can reuse this."""
    return [l for l in (lines or []) if l and l.strip() and not intro_re.search(l)]


def _per_stack_pairs(text: str) -> dict:
    """{ stat_phrase(lower) : per_stack_value_fraction } parsed from 'N% X per stack' in this anchor's joined text."""
    out: dict = {}
    for m in _PER_STACK_RE.finditer(text):
        out[m.group(2).strip()] = _num(m.group(1)) / 100.0   # keep original case for parse_mod
    return out


def _canon_key(stat: str, scope):
    """Canonicalize a scoped generic damage mod to its type/category-specific stat (e.g. dmg_additional + scope
    'spell' → spell_dmg_additional) so the Lv1 and Lv20 anchors of the SAME modifier — which often phrase it
    differently ("additional damage for Spell Skills" vs "additional Spell Damage") — match instead of
    double-emitting. Only collapses when the typed stat actually exists."""
    if scope and stat in ("dmg_additional", "dmg_inc"):
        typed = f"{scope}_{stat}"
        if typed in _VALID_STATS:
            return (typed, None)
    return (stat, scope)


def _parsed_map(lines, parse_mod) -> tuple[dict, list[str]]:
    """{ (stat_key, scope): (amount, source_text) } from non-stacking lines, plus unresolved effect-looking lines."""
    out: dict = {}
    unresolved: list[str] = []
    for line in lines:
        if "per stack" in line.lower() or _MAX_STACK_RE.search(line) or re.search(r"^\s*\d+\s*(s|time)", line):
            continue   # stacking lines handled separately; bare durations/counts aren't stats
        res = parse_mod(line) or []
        if res:
            for e in res:
                out[_canon_key(e["stat_key"], e.get("scope"))] = (float(e["amount"]), line)
        elif re.search(r"\d", line) and len(line.strip()) > 3:
            unresolved.append(line.strip())
    return out, unresolved


def resolve_auras(auras, skills_by_id, parse_mod, translate_cond):
    """auras: list of {skill_id, level, slot, enabled} for equipped passive buff skills.

    Emits UNSCALED buff contributions (base value interpolated to the equipped level) flagged `is_aura_effect`.
    The ENGINE (compute) scales the non-Aura-Effect ones by the fully-aggregated Aura Effect after the source is
    built — so gear/talent/custom/support Aura Effect (and the aura's own) all count. Per-stack buffs ride a
    `{op:per, key:<skill>_stacks}` gate. Returns (contributions, statuses, summaries, stack_conditions)."""
    buffs: list[dict] = []
    statuses: list[dict] = []
    stack_conditions: list[dict] = []
    meta: dict[str, dict] = {}

    def _emit(sid, name, stat, base, scope, cond, per_stack, phrase):
        buffs.append({
            "skill_id": sid, "name": name, "stat_key": stat, "base_amount": base, "scope": scope,
            "condition_expr": cond, "is_aura_effect": stat in _AURA_EFFECT_KEYS, "per_stack": per_stack,
            "phrase": phrase, "text": f"{phrase} |aura|{sid}",
        })

    for a in auras or []:
        sid = a.get("skill_id")
        skill = skills_by_id.get(sid) or {}
        tags = skill.get("skill_tags") or []
        if not any(t in tags for t in ("Aura", "Focus")):
            continue   # only buff-passives by TAG (skips the active-variant pollution in passive_skill)
        # DISABLED auras are still resolved (so the Skill panel shows their stats marked "Disabled") but their
        # buffs are NOT folded into the engine — apply_aura_buffs skips emission when meta.enabled is False.
        enabled = bool(a.get("enabled", True))

        level = int(a.get("level") or 1)
        simple = _buff_lines(skill.get("simple_description"))
        detailed = _buff_lines(skill.get("detailed_description"))
        # DETAIL (Lv20) is the SINGLE SOURCE OF TRUTH for which modifiers exist + their Lv20 value. SIMPLE
        # (Lv1) is consulted ONLY to anchor linear per-level scaling — never to add a modifier the detail list
        # lacks. The simple list splits inconsistently (lost scopes, compound lines), so trusting it adds
        # phantom/duplicate stats (e.g. Spell Amplification emitting both spell_dmg_additional AND a scoped
        # dmg_additional). When the simple anchor is missing/ambiguous we use the detail value flat.
        lv20, un20 = _parsed_map(detailed, parse_mod)
        lv1, _un1 = _parsed_map(simple, parse_mod)
        lv1_by_stat: dict = {}
        for (st, _sc), (amt, _t) in lv1.items():
            lv1_by_stat.setdefault(st, []).append(amt)
        name = skill.get("name", sid)
        frac = (level - 1) / 19.0

        review: list[str] = []

        def _lv1_anchor(stat, scope):
            """(Lv1 value, match) for linear scaling. 'exact' = same (stat, scope) in simple. 'fuzzy' = the
            lone same-base-stat value (simple dropped a scope word, e.g. "Critical Strike Rating" vs detail
            "… for Melee Skills"). 'none' = no Lv1 anchor. Only 'exact' is trusted silently; the rest are
            raised for manual review (the value is still applied so nothing is dropped)."""
            if (stat, scope) in lv1:
                return lv1[(stat, scope)][0], "exact"
            cands = lv1_by_stat.get(stat)
            if cands and len(cands) == 1:
                return cands[0], "fuzzy"
            return None, "none"

        # ── Flat / non-stacking buffs: emit the DETAIL set, interpolate from the Lv1 anchor when found ──
        for key in lv20:
            stat, scope = key
            base20 = lv20[key][0]
            base1, match = _lv1_anchor(stat, scope)
            base = base20 if base1 is None else base1 + (base20 - base1) * frac
            _emit(sid, name, stat, base, scope, None, False, lv20[key][1])
            if match != "exact":
                why = ("no Lv1 anchor — using flat Lv20 value" if match == "none"
                       else "Lv1 anchor matched by stat only (scope differs) — scaling approximate")
                review.append(f"{lv20[key][1]} ({why})")

        # ── Stacking buffs → per-aura settable condition (DETAIL-driven; simple = Lv1 anchor) ──────
        ps20 = _per_stack_pairs(" ".join(detailed))
        ps1 = _per_stack_pairs(" ".join(simple))
        max_stacks = 0
        for m in _MAX_STACK_RE.finditer(" ".join(detailed + simple)):
            max_stacks = max(max_stacks, int(m.group(1)))
        cond_key = f"{sid}_stacks" if (ps20 and max_stacks) else None
        if ps20:
            for phrase in ps20:
                b20 = ps20[phrase]
                b1 = ps1.get(phrase, b20)
                per_stack = b1 + (b20 - b1) * frac
                res = parse_mod(f"{per_stack * 100:g}% {phrase}") or []
                if not res:
                    statuses.append({"skill_id": sid, "text": f"{phrase} per stack", "resolved": False, "kind": "nyi"})
                    continue
                if phrase not in ps1:
                    review.append(f"{phrase} per stack (no Lv1 anchor — using flat Lv20 value)")
                gate = {"op": "per", "key": cond_key, "divisor": 1} if cond_key else None
                for e in res:
                    _emit(sid, name, e["stat_key"], float(e["amount"]), e.get("scope"), gate, True, f"{phrase} (per stack)")
            if cond_key:
                stack_conditions.append({"key": cond_key, "label": f"{name} - Buff Stacks", "max": max_stacks})

        nyi = sorted(set(un20))   # only DETAIL lines we couldn't resolve are genuine NYI; simple noise ignored
        for u in nyi:
            statuses.append({"skill_id": sid, "text": u, "resolved": False, "kind": "nyi"})
        review = sorted(set(review))
        for r in review:
            statuses.append({"skill_id": sid, "text": r, "resolved": True, "kind": "review"})
        meta[sid] = {"name": name, "level": level, "nyi": nyi, "review": review, "slot": a.get("slot"),
                     "enabled": enabled, "stack_condition": cond_key, "max_stacks": max_stacks or None}

    return buffs, statuses, stack_conditions, meta
