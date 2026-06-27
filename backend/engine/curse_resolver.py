"""Resolve curse skills + curse-applying affixes into enemy damage-taken debuffs.

Curses are applied to the enemy from two sources, both naming a specific curse + level: (a) slotted curse skills
(`active_skill` with the "Curse" tag); (b) gear affixes ("Triggers Lv. N <Curse> Curse…", "Nearby enemies … cursed
by Lv. N <Curse>"). Each curse's "+X% additional <type> Damage taken" line is read from the curse skill's
`detailed_description` (Lv20 anchor) and interpolated from the `simple_description` (Lv1 anchor) to the applied level
— the SAME approach as aura_resolver.

`resolve_curses` (server-side) gathers + dedups the curses; `apply_curses` (engine-side, inside the compute loop —
parallels utility.apply_aura_buffs) scales each by Curse Effect and bakes it into the per-final-type `*_curse_taken`
/ `hit_curse_taken` pools that offense's enemy-vulnerability stage consumes (so curses are conversion-correct).

Scope: damage-taken amplification only. Vulnerability→Physical, Scorch→Fire, Biting Cold→Cold, Electrocute→Lightning,
Corruption→Erosion, Timid→all Hit. Entangled Pain (DoT — no DoT engine), Dazzled (movement/Blind), Ominous (Ill Omen),
and ailment-chance lines are surfaced NYI, never dropped.
"""
from __future__ import annotations
import re
from collections import defaultdict

from engine.aggregator import _emit
from engine.models import SourceEntry

_ELEM_TYPES = ("physical", "fire", "cold", "lightning", "erosion")
_TYPE_TO_STAT = {t: f"{t}_curse_taken" for t in _ELEM_TYPES}
_TYPE_TO_STAT["hit"] = "hit_curse_taken"

# "+39 % additional Fire Damage taken …" / "Cursed enemies +39 % additional Cold Damage taken" / "Hit Damage taken".
_TAKEN_RE = re.compile(
    r"([\d.]+)\s*%\s*additional\s+(physical|fire|cold|lightning|erosion|hit)\s+damage\s+taken", re.I)
# Lv1 simple anchor: "Cursed enemies take 20% additional Fire Damage" (no "taken").
_TAKEN_SIMPLE_RE = re.compile(
    r"([\d.]+)\s*%\s*additional\s+(physical|fire|cold|lightning|erosion|hit)\s+damage", re.I)
_DURATION_RE = re.compile(r"lasts?\s+([\d.]+)\s*s", re.I)


def _sel_key(curse_name: str) -> str:
    """Conflict-resolution condition key for a curse: 'Biting Cold' → 'biting_cold' (key `curse_sel_biting_cold`)."""
    return (curse_name or "").strip().lower().replace(" ", "_")


def _as_lines(v) -> list[str]:
    if not v:
        return []
    return [v] if isinstance(v, str) else list(v)


def _match_taken(lines: list[str], rx: re.Pattern) -> tuple[str | None, float | None]:
    """First (type, fraction) match across `lines` for the curse's damage-taken line."""
    for ln in lines:
        m = rx.search(ln or "")
        if m:
            return m.group(2).lower(), float(m.group(1)) / 100.0
    return None, None


def _parse_magnitude(detailed: list[str], simple: list[str], level: int) -> tuple[str | None, float]:
    """(type, level-interpolated fraction) from the Lv20 detail anchor, scaled from the Lv1 simple anchor."""
    typ, base20 = _match_taken(detailed, _TAKEN_RE)
    if typ is None:
        return None, 0.0
    _t1, base1 = _match_taken(simple, _TAKEN_SIMPLE_RE)
    if base1 is None:
        return typ, base20
    frac = (max(1, level) - 1) / 19.0
    return typ, base1 + (base20 - base1) * frac


def _skill_by_name(skills_by_id: dict, name: str) -> dict:
    if not name:
        return {}
    key = name.strip().lower()
    direct = skills_by_id.get(key) or skills_by_id.get(key.replace(" ", "_"))
    if direct:
        return direct
    for s in skills_by_id.values():
        if (s.get("name") or "").strip().lower() == key:
            return s
    return {}


def resolve_curses(skills_input, affix_curses, skills_by_id):
    """Gather active curses from slotted curse skills + affix records, dedup by curse name (highest level wins),
    parse each one's damage-taken magnitude. Returns (active_curses, statuses, meta).

    active_curses item: {curse_name, skill_id, stat_key|None, base_amount, level, source_label, modeled, enabled,
                         base_stats:{mana_cost,cast_speed,cooldown,duration}}.
    A modeled=False curse (Entangled Pain/Dazzled/Ominous) still counts toward the limit but bakes no damage.
    """
    raw: list[dict] = []
    for s in skills_input or []:
        sid = s.get("skill_id")
        skill = skills_by_id.get(sid) or {}
        tags = skill.get("skill_tags") or []
        if "Curse" not in tags or skill.get("skill_type") != "active_skill":
            continue
        # DISABLED curses are still resolved (Skill panel shows them marked "Disabled") but don't count toward the
        # limit or bake any debuff — apply_curses filters on `enabled`.
        raw.append({"name": skill.get("name", sid), "skill_id": sid, "level": int(s.get("level") or 1),
                    "skill": skill, "source_label": f"{skill.get('name', sid)} (slot {s.get('slot')})",
                    "enabled": bool(s.get("enabled", True))})
    for a in affix_curses or []:
        name = a.get("curse_name")
        skill = _skill_by_name(skills_by_id, name)
        raw.append({"name": name, "skill_id": skill.get("item_id") or (name or "").strip().lower().replace(" ", "_"),
                    "level": int(a.get("level") or 1), "skill": skill,
                    "source_label": a.get("source_label") or "Gear", "enabled": True})

    # Dedup by curse name — keep only the highest-level instance (same curse doesn't stack; highest level applies).
    best: dict[str, dict] = {}
    for r in raw:
        key = (r["name"] or "").strip().lower()
        if not key:
            continue
        # Prefer an ENABLED instance, then the highest level (a disabled copy must never shadow an enabled one).
        if key not in best or (r.get("enabled", True), r["level"]) > (best[key].get("enabled", True), best[key]["level"]):
            best[key] = r

    active: list[dict] = []
    statuses: list[dict] = []
    meta: dict[str, dict] = {}
    for r in best.values():
        skill, level, name, sid = r["skill"], r["level"], r["name"], r["skill_id"]
        detailed = _as_lines(skill.get("detailed_description"))
        simple = _as_lines(skill.get("simple_description"))
        typ, base = _parse_magnitude(detailed, simple, level)
        stat_key = _TYPE_TO_STAT.get(typ) if typ else None
        modeled = stat_key is not None

        nyi: list[str] = []
        if not modeled:
            nyi.append(f"{name}: damage-taken effect not yet modeled (DoT / utility curse)")
        for ln in detailed:
            low = (ln or "").lower()
            if "chance to" in low or "blind" in low or "movement speed" in low or "ill omen" in low:
                nyi.append(ln.strip())
        dur_m = _DURATION_RE.search(" ".join(detailed))
        duration = float(dur_m.group(1)) if dur_m else None

        active.append({
            "curse_name": name, "skill_id": sid, "stat_key": stat_key, "base_amount": base, "level": level,
            "source_label": r["source_label"], "modeled": modeled, "enabled": r.get("enabled", True),
        })
        for t in sorted(set(nyi)):
            statuses.append({"skill_id": sid, "text": t, "resolved": False, "kind": "nyi"})
        meta[sid] = {
            "curse_name": name, "level": level, "type": typ, "base_amount": base, "modeled": modeled,
            "source_label": r["source_label"], "nyi": sorted(set(nyi)),
            "base_stats": {
                "mana_cost": skill.get("mana_cost"), "cast_speed": skill.get("cast_speed"),
                "cooldown": skill.get("cooldown"), "duration": duration,
            },
        }
    return active, statuses, meta


def _curse_effect_factor(source) -> tuple[float, float]:
    """(increased_total, additional_mult) for Curse Effect. Increased sums; additional multiplies PER SOURCE (only
    Defile today — future-proofed; flag to verify the multiplicative rule once a 2nd additional source exists)."""
    inc = source.total("curse_effect_inc")
    groups: dict[str, float] = defaultdict(float)
    for e in source.source_log:
        if e.stat == "curse_effect_additional":
            groups[e.text or e.source_name or e.label or ""] += e.amount
    add_mult = 1.0
    for v in groups.values():
        add_mult *= (1.0 + v)
    return inc, add_mult


def apply_curses(source, active_curses, condition_state):
    """Bake applied curses' damage-taken magnitudes (scaled by Curse Effect) into the `*_curse_taken` pools, and
    return (summaries, conflict). Runs each compute pass after the source is fully aggregated (mirrors
    apply_aura_buffs). Curse limit = 1 + Max Curses, capped by Curse Limit Cap. If active curses exceed the limit
    and the user hasn't resolved the conflict (curse_conflict_selection), NOTHING is baked — the player must pick.
    """
    if not active_curses:
        return [], None

    prev_rec = source._recording
    source._recording = True   # record Curse-Effect reads → consumed_stats (so curse-effect mods badge working)
    try:
        limit = 1 + int(round(source.total("max_curses_flat")))
        cap = source.total("curse_limit_cap_flat")
        if cap and cap > 0:
            limit = min(limit, int(round(cap)))
        limit = max(1, limit)

        enabled = [c for c in active_curses if c.get("enabled", True)]
        n_active = len(enabled)
        # Over-limit conflict resolution: the user picks which curses apply via per-curse boolean conditions
        # `curse_sel_<name>` (set by the Conditionals dropdown; fits condition_state's float|bool typing + persists).
        cs = condition_state or {}

        conflict = None
        applied = enabled
        if n_active > limit:
            chosen = [c for c in enabled if cs.get(f"curse_sel_{_sel_key(c['curse_name'])}")]
            resolved = bool(chosen) and len(chosen) <= limit
            applied = chosen if resolved else []
            conflict = {
                "limit": limit,
                "active": [{"name": c["curse_name"], "source": c["source_label"],
                            "sel_key": f"curse_sel_{_sel_key(c['curse_name'])}"} for c in enabled],
                "resolved": resolved,
            }

        inc, add_mult = _curse_effect_factor(source)
        factor = (1.0 + inc) * add_mult

        for c in applied:
            if not c.get("modeled") or not c.get("stat_key"):
                continue
            amount = c["base_amount"] * factor
            _emit(source, c["stat_key"], amount, None, SourceEntry(
                stat=c["stat_key"], amount=amount, source_type="curse",
                label=c["curse_name"], text=f'{c["curse_name"]} ({c["source_label"]})', points=1,
                source_name=c["curse_name"]), slot=None)

        applied_ids = {id(c) for c in applied}
        summaries = []
        for c in active_curses:
            summaries.append({
                "skill_id": c["skill_id"], "curse_name": c["curse_name"], "level": c["level"],
                "stat_key": c["stat_key"], "modeled": c["modeled"], "source_label": c["source_label"],
                "base_amount": c["base_amount"],
                "scaled_amount": c["base_amount"] * factor if c.get("modeled") else 0.0,
                "curse_effect_inc": inc, "curse_effect_additional": add_mult - 1.0,
                "limit": limit, "n_active": n_active, "enabled": c.get("enabled", True),
                "applied": id(c) in applied_ids and bool(c.get("modeled")),
            })
        return summaries, conflict
    finally:
        source._recording = prev_rec
