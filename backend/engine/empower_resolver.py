"""Resolve equipped EMPOWER skills into player stat contributions (the "Euphoria" buff).

Empower skills (active_skill + "Empower" tag) cast and grant a temporary buff to the PLAYER — e.g. Bull's Rage
"+27% additional Melee Skill Damage", Aim "Ranged/Beam +35% additional damage". Modeled like auras: values come from
simple_description (Lv1 anchor) + detailed_description (Lv20 source of truth), parsed through the shared text->stat
pipeline (parse_mod), interpolated to the equipped level, then scaled engine-side by EMPOWER SKILL EFFECT
(apply_empower_buffs). Buffs are emitted as the SAME typed/scoped damage stats auras use, so they flow through
offense's conversion-aware pipeline (no special stage).

Scope: player damage/speed/crit buffs. Lines that buff minions/Sentries/Spirit Magi/nearby allies are surfaced NYI
(no minion engine). Simple "N% X per stack ... up to M" lines become a settable <sid>_stacks condition; other
conditional/stacking phrasings ("for every stack of Focus Blessing", "Each buff grants … Stacks up to N") are NYI.
Uptime is assumed 100% (the Euphoria buff is treated as always active while the skill is slotted + enabled). Nothing
is silently dropped — unmodeled lines surface as NYI statuses.
"""
from __future__ import annotations
import re

from engine.aura_resolver import _per_stack_pairs, _canon_key, _PER_STACK_RE, _MAX_STACK_RE

_EMPOWER_EFFECT_KEYS = {"empower_effect_inc", "empower_effect_additional"}
# Strip a leading "… (gains) Euphoria …:" intro so the buff after the colon parses; pure-intro lines become "".
_INTRO_STRIP_RE = re.compile(r"^.*?\beuphoria\b[^:]*:\s*", re.I)
# Lines that buff non-player entities → NYI (no minion/sentry/spirit-magi engine).
_NYI_RE = re.compile(r"minion|sentry|spirit\s*mag|summon|nearby all|to allies|\bcommand\b", re.I)
# A skill whose buff DEACTIVATES when Mana hits 0 (Mana Boil's Euphoria). We don't auto-disable it; we record the
# flag so compute can WARN when Mana is unsustainable (the buff would turn off in play once costs outrun recovery).
_MANA_ZERO_DEACTIVATE_RE = re.compile(r"\bloses?\b[^.\n]*\beffect\b[^.\n]*\bmana\b[^.\n]*\bdrops?\s+to\s+0", re.I)
# Whole-skill gate: the Euphoria RECIPIENT is non-player (e.g. "Sentries grant Euphoria to Nearby allies:",
# "Allies will gain Euphoria …", "Minions … Euphoria"). The recipient sits on the intro line we'd otherwise strip,
# so the buff lines look player-applicable — detect it skill-wide and NYI-gate the whole skill.
_ALLY_EUPHORIA_RE = re.compile(
    r"grants?\s+euphoria\s+to|euphoria\s+to\s+(?:nearby\s+)?all|"
    r"(?:minions?|sentr(?:y|ies)|spirit\s*mag\w*|allies)\b[^.\n]*\beuphoria|"
    r"\beuphoria\b[^.\n]*\b(?:minions?|sentr(?:y|ies)|spirit\s*mag\w*|allies)\b", re.I)


def _ally_targeted(lines) -> bool:
    return any(_ALLY_EUPHORIA_RE.search(l or "") for l in (lines or []))


# "+X% <stat> for (every|each) stack of <Named>" → scale the per-stack value by an EXISTING settable numeric
# condition (e.g. Focus Blessing → focus_blessings). The "up to N" cap is governed by that condition's own max
# (Focus Blessings caps well below 8), so it isn't separately enforced (flagged).
_PER_NAMED_RE = re.compile(r"^(.*?)\s+for (?:every|each) stack of (.+?)(?:\s+you have\b|\s+owned\b|[.,]|$)", re.I)
_NAMED_COND = {"focus blessing": "focus_blessings"}
# Pure noise (no stat): bare durations, life-cost swaps, deactivation conditions, channel movement notes.
# NOTE: "Consumes N% Mana every second" is NOT noise — it routes through parse_mod into a consume stat
# (mana_consumed_pct_max_per_sec) and is emitted as a buff so apply_empower_buffs scales it by Empower Effect
# (Mana Boil: the consume scales with Empower Effect just like the Spell Damage buff).
_NOISE_RE = re.compile(r"^\s*lasts?\s+[\d.]+\s*s|costs?\s+life instead|"
                       r"loses?\b[^.]*\beffect\b[^.]*\bdrops?\s+to\b|"
                       r"movement is not restricted", re.I)
# Trailing duration/qualifier clauses that break the stat parser ("+15% additional Spell Damage while the skill
# lasts" / "… for 6 s"). Stripped before parse_mod; the stat clause is what matters.
_SUFFIX_RE = re.compile(r"\s+(?:while (?:the|this) skill lasts|for\s+[\d.]+\s*s(?:econds?)?)\b.*$", re.I)


def _prep(lines) -> tuple[list[str], list[str]]:
    """(modelable lines, NYI lines) after stripping intros, trailing duration clauses, and noise; minion/ally
    lines split out as NYI."""
    keep, nyi = [], []
    for raw in lines or []:
        s = _INTRO_STRIP_RE.sub("", raw or "").strip()
        s = _SUFFIX_RE.sub("", s).strip(" .")
        if not s or _NOISE_RE.search(s):
            continue
        (nyi if _NYI_RE.search(s) else keep).append(s)
    return keep, nyi


def _flat_map(lines, parse_mod) -> tuple[dict, list[str]]:
    """{(stat,scope): (amount, text)} for flat (non-per-stack) buff lines, plus unresolved-looking NYI lines.
    A "stacks up to N" line WITHOUT a parseable "per stack" value is surfaced NYI (not silently dropped)."""
    out, unresolved = {}, []
    for line in lines:
        if _PER_STACK_RE.search(line):
            continue                                  # per-stack handled separately
        if _MAX_STACK_RE.search(line):
            unresolved.append(line)                   # conditional stacking we don't model yet
            continue
        res = parse_mod(line) or []
        if res:
            for e in res:
                out[_canon_key(e["stat_key"], e.get("scope"))] = (float(e["amount"]), line)
        elif re.search(r"\d", line) and len(line) > 3:
            unresolved.append(line)
    return out, unresolved


def resolve_empowers(skills_input, skills_by_id, parse_mod, translate_cond=None):
    """skills_input: [{skill_id, level, slot, enabled}]. Returns (buffs, statuses, stack_conditions, meta) — same
    shape as resolve_auras. Buffs are UNSCALED; apply_empower_buffs scales them by Empower Effect in the engine."""
    buffs, statuses, stack_conditions, meta = [], [], [], {}

    def _emit(sid, name, stat, base, scope, cond, per_stack, phrase):
        buffs.append({
            "skill_id": sid, "name": name, "stat_key": stat, "base_amount": base, "scope": scope,
            "condition_expr": cond, "is_empower_effect": stat in _EMPOWER_EFFECT_KEYS, "per_stack": per_stack,
            "phrase": phrase, "text": f"{phrase} |empower|{sid}",
        })

    for a in skills_input or []:
        sid = a.get("skill_id")
        skill = skills_by_id.get(sid) or {}
        tags = skill.get("skill_tags") or []
        if "Empower" not in tags or skill.get("skill_type") != "active_skill":
            continue
        # DISABLED empowers are still resolved (Skill panel shows their stats marked "Disabled") but their buffs are
        # NOT folded into the engine — apply_empower_buffs skips emission when meta.enabled is False.
        enabled = bool(a.get("enabled", True))

        level = int(a.get("level") or 1)
        name = skill.get("name", sid)
        raw_detailed = skill.get("detailed_description") or []
        raw_simple = skill.get("simple_description") or []
        # Does this empower's buff turn off at 0 Mana (Mana Boil)? Recorded for the compute-side warning.
        deactivates_at_zero_mana = any(_MANA_ZERO_DEACTIVATE_RE.search(l or "")
                                       for l in list(raw_detailed) + list(raw_simple))

        # Skill-wide gate: if the Euphoria goes to minions/sentries/allies (not the player), NYI the whole skill.
        if _ally_targeted(list(raw_detailed) + list(raw_simple)):
            detail_lines = [l.strip() for l in raw_detailed if l and l.strip()]
            for u in detail_lines:
                statuses.append({"skill_id": sid, "text": u, "resolved": False, "kind": "nyi"})
            meta[sid] = {"name": name, "level": level, "nyi": detail_lines, "review": [], "slot": a.get("slot"),
                         "enabled": enabled, "stack_condition": None, "max_stacks": None,
                         "deactivates_at_zero_mana": deactivates_at_zero_mana}
            continue

        detailed, nyi_d = _prep(raw_detailed)
        simple, _nyi_s = _prep(raw_simple)

        lv20, un20 = _flat_map(detailed, parse_mod)
        lv1, _un1 = _flat_map(simple, parse_mod)
        lv1_by_stat: dict = {}
        for (st, _sc), (amt, _t) in lv1.items():
            lv1_by_stat.setdefault(st, []).append(amt)
        frac = (level - 1) / 19.0
        review: list[str] = []

        def _lv1_anchor(stat, scope):
            if (stat, scope) in lv1:
                return lv1[(stat, scope)][0], "exact"
            cands = lv1_by_stat.get(stat)
            if cands and len(cands) == 1:
                return cands[0], "fuzzy"
            return None, "none"

        # ── Flat buffs (interpolated from the Lv1 anchor when present) ──
        for key in lv20:
            stat, scope = key
            base20 = lv20[key][0]
            base1, match = _lv1_anchor(stat, scope)
            base = base20 if base1 is None else base1 + (base20 - base1) * frac
            _emit(sid, name, stat, base, scope, None, False, lv20[key][1])
            if match != "exact":
                review.append(f"{lv20[key][1]} ({'no Lv1 anchor — flat Lv20' if match == 'none' else 'Lv1 scope differs — approx'})")

        # ── Simple "N% X per stack … up to M" → settable <sid>_stacks condition ──
        ps20 = _per_stack_pairs(" ".join(detailed))
        ps1 = _per_stack_pairs(" ".join(simple))
        max_stacks = 0
        for m in _MAX_STACK_RE.finditer(" ".join(detailed + simple)):
            max_stacks = max(max_stacks, int(m.group(1)))
        cond_key = f"{sid}_stacks" if (ps20 and max_stacks) else None
        for phrase in ps20:
            b20 = ps20[phrase]
            b1 = ps1.get(phrase, b20)
            per_stack = b1 + (b20 - b1) * frac
            res = parse_mod(f"{per_stack * 100:g}% {phrase}") or []
            if not res:
                statuses.append({"skill_id": sid, "text": f"{phrase} per stack", "resolved": False, "kind": "nyi"})
                continue
            gate = {"op": "per", "key": cond_key, "divisor": 1} if cond_key else None
            for e in res:
                _emit(sid, name, e["stat_key"], float(e["amount"]), e.get("scope"), gate, True, f"{phrase} (per stack)")
        if cond_key:
            stack_conditions.append({"key": cond_key, "label": f"{name} - Buff Stacks", "max": max_stacks})

        # ── "N% X for every stack of <Named>" → gate the per-stack value on the EXISTING numeric condition ──
        # (e.g. Secret Origin Unleash: +3% Cast Speed per Focus Blessing → gated on focus_blessings). These lines
        # carry a "Stacks up to N", so _flat_map routed them to un20 (NYI); pull the known ones back out.
        for line in list(un20):
            m = _PER_NAMED_RE.search(line)
            if not m:
                continue
            named_key = _NAMED_COND.get(m.group(2).strip().lower())
            if not named_key:
                continue
            res = parse_mod(m.group(1).strip()) or []
            if not res:
                continue
            gate = {"op": "per", "key": named_key, "divisor": 1}
            for e in res:
                _emit(sid, name, e["stat_key"], float(e["amount"]), e.get("scope"), gate, True,
                      f"{m.group(1).strip()} (per {m.group(2).strip()})")
            un20.remove(line)

        nyi = sorted(set(un20) | set(nyi_d))
        for u in nyi:
            statuses.append({"skill_id": sid, "text": u, "resolved": False, "kind": "nyi"})
        review = sorted(set(review))
        for r in review:
            statuses.append({"skill_id": sid, "text": r, "resolved": True, "kind": "review"})
        meta[sid] = {"name": name, "level": level, "nyi": nyi, "review": review, "slot": a.get("slot"),
                     "enabled": enabled, "stack_condition": cond_key, "max_stacks": max_stacks or None,
                     "deactivates_at_zero_mana": deactivates_at_zero_mana}

    return buffs, statuses, stack_conditions, meta
