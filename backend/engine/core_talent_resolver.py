"""Resolve granted Core Talents into engine stat contributions + base-effect override flags.

Core talents (roadmap #4) are granted by four sources — talent-tree slots, slates, legendary gear
affixes (`[Name] <effect>`), and an equipped belt blend. Every core-talent effect is "Max Divinity
Effect: 1": a talent counts EXACTLY ONCE no matter how many sources grant it. This module collects the
granted talents from all four sources, dedups them by normalized name (first wins), and resolves each
unique talent's effect strings into:

  - stat contributions  → {stat_key, amount, text, label, condition_expr|None}, injected by the
    aggregator with source_type="core_talent" (each carries a unique `|core|<name>` text so distinct
    talents' additional-damage lines multiply in offense's per-affix pool);
  - override flags       → core_sacrifice / core_conductive / divine_grace, set when a talent's effect
    "Changes the base effect of <X> to: …" — the aggregator applies the actual re-based magnitude;
  - statuses             → one {name, text, resolved, kind} per effect, for badging in the UI. Nothing
    is ever silently dropped: effects we cannot model yet are captured as resolved:False.

Effect RESOLUTION reuses the server's freeform-mod resolvers, injected as `parse_mod`
(`_parse_custom_mod_text`) and `translate_cond` (`_translate_condition_expr`) so this module stays
free of any server import (and is unit-testable with stubs).

Conditional effects ("+X% … when/while/if …") are applied ONLY when their clause translates to an
engine condition expression; an untranslatable condition is captured (resolved:False) rather than
applied unconditionally, so the engine never over-counts a gated bonus. (Plan v1 scope.)
"""
from __future__ import annotations
import re

# "(Max Divinity Effect: 1)" trailer present on the canonical line of every talent — strip before parse.
_MAX_DIV_RE = re.compile(r"\s*\(Max Divinity Effect:[^)]*\)\s*$", re.I)

# "Changes the base effect of <X> to: <Y>" — the override marker. <X> maps to a flag the aggregator
# reads; the re-based magnitude itself is encoded in the aggregator (not parsed from <Y>).
_BASE_EFFECT_RE = re.compile(r"changes the base effect of\s+(.+?)\s+to\b[: ]", re.I)
_OVERRIDE_TARGETS = {
    "tenacity blessing": "core_sacrifice",   # Sacrifice  — Tenacity becomes offensive
    "numbed": "core_conductive",             # Conductive — Numbed re-based to +11%/stack
    "all blessings": "divine_grace",         # Divine Grace (aromatic belt blend)
}
# Overrides we recognise but DON'T model yet (Mind Focus → Focus: flat Physical = 1% Max Mana). v2.
_DEFERRED_TARGETS = {"focus blessing"}

# Condition-clause keywords. A leading "When …, <stat>" or a trailing "<stat> when/while/if/against …"
# splits the stat clause from the gate so we resolve the bare stat and gate it separately.
_LEAD_COND_RE = re.compile(r"^\s*(when|while|if)\b(.*?),\s*(.+)$", re.I)
# Trailing gate starts: keyword (when/while/if/…/after), an "at Low/Full/Max <resource>" state, or a
# "for N s …" duration window (the gate trigger follows it). First match marks where the gate begins.
_TRAIL_COND_RE = re.compile(
    r"\b(?:when|while|if|against|upon|after)\b|\bfrom\s+\w+\s+enem|\bat\s+(?:low|full|max)\b|\bfor\s+[\d.]+\s*s\b"
    r"|\bper\s+(?:\d+\s+)?stack|\bfor\s+every\b|\bfor\s+each\b"
    r"|\bdealt\s+to\b|\bto\s+(?:nearby|distant)\s+enem|\b(?:to\s+enemies\s+)?in\s+proximity\b"
    r"|\bper\s+(?:(?:\d+(?:\.\d+)?|\([\d.]+\s*[-–]\s*[\d.]+\))\s+)?(?:fervor|command|strength|dexterity|intelligence|growth)\b", re.I)


# Compound lines join several "+N% Stat" mods with "and"/"," — split BEFORE a conjunction that precedes
# a SIGNED NUMBER (a new mod), but never "and" inside a stat name ("Ultimate Damage and Ailment Damage"
# has no number after "and", so it stays one stat).
_COMPOUND_SPLIT_RE = re.compile(r"\s*,?\s*\band\b\s+(?=[+\-]\d)|\s*,\s*(?=[+\-]\d)", re.I)


def _split_compound(stat_clause: str) -> list[str]:
    return [p.strip() for p in _COMPOUND_SPLIT_RE.split(stat_clause) if p and p.strip()]


# Shared-magnitude joins: a single "+N%" applied to TWO stats whose names share an elided head-noun or a
# trailing qualifier, joined by "and" with no second number (so _split_compound can't see them, e.g.
# "+20% Life Regain and Energy Shield Regain for Minions"). Each entry maps the joined stat-name phrase to
# the expanded stat-name phrases; we re-emit the whole line once per expansion (string-replace the joined
# phrase), so the leading magnitude and any trailing condition ride onto each. CURATED, never inferred —
# so a single stat like "Ultimate Damage and Ailment Damage" is never wrongly split.
_SHARED_STAT_JOINS = [
    (re.compile(r"\bLife Regain and Energy Shield Regain\b", re.I),
     ["Life Regain", "Energy Shield Regain"]),
    (re.compile(r"\bMinion Attack Speed and Cast Speed\b", re.I),
     ["Minion Attack Speed", "Minion Cast Speed"]),
    (re.compile(r"\bMinion Attack and Cast Speed\b", re.I),
     ["Minion Attack Speed", "Minion Cast Speed"]),
    (re.compile(r"\bAttack Speed and Cast Speed\b", re.I),
     ["Attack Speed", "Cast Speed"]),
    (re.compile(r"\bAttack and Cast Speed\b", re.I),
     ["Attack Speed", "Cast Speed"]),
    # "Elemental and Erosion Resistance" (and its Penetration variant) = one magnitude, two stats.
    (re.compile(r"\bElemental and Erosion Resistance\b", re.I),
     ["Elemental Resistance", "Erosion Resistance"]),
]


def _expand_shared_stats(effect: str) -> list[str]:
    """Expand a single shared-magnitude join into one full effect string per stat. Returns [effect] if no
    join matches (the common case), so callers can flat-map unconditionally."""
    for pat, parts in _SHARED_STAT_JOINS:
        m = pat.search(effect)
        if m:
            return [effect[:m.start()] + p + effect[m.end():] for p in parts]
    return [effect]


# "Gain on hit" generation lines: "+100% chance to gain N stack(s) of <Blessing>/Fervor on hit". We model
# these as full uptime (the blessing/Fervor sits at MAX) — an approximation pending uptime calc modes. Emits
# an `automax_*` flag the compute loop reads to pin that condition to its derived max.
_GAIN_BLESSING_RE = re.compile(r"gain\s+\d+\s+stack(?:s|\(s\))?\s+of\s+(focus|agility|tenacity)\s+blessing", re.I)
_GAIN_FERVOR_RE   = re.compile(r"gain\s+\d+\s+fervor\s+rating", re.I)


def _gain_on_hit_flag(text: str) -> str | None:
    m = _GAIN_BLESSING_RE.search(text)
    if m:
        return f"automax_{m.group(1).lower()}_blessings"
    if _GAIN_FERVOR_RE.search(text):
        return "automax_fervor"
    return None


# Set-value lines: "<stat> is set to / fixed at N" — a FINAL override (not additive). Only the derived
# stats the engine actually computes can be forced; other targets (Block Ratio, enemy resistances, support
# mana multiplier, Max Spirit Magi count) resolve to a tracked status but aren't applied until modeled.
_SET_VALUE_RE = re.compile(r"^(?:your\s+|the\s+)?(.+?)\s+is\s+(?:set\s+to|fixed\s+at)\s+([+\-]?[\d.]+)", re.I)
_SET_VALUE_TARGETS = {
    "max life": "max_life",
    "max energy shield": "max_energy_shield",
}


def _normalize(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _strip_max_div(text: str) -> str:
    return _MAX_DIV_RE.sub("", text or "").strip()


def _split_condition(text: str) -> tuple[str, str | None]:
    """Split a freeform effect into (stat_clause, condition_clause | None)."""
    lead = _LEAD_COND_RE.match(text)
    if lead:
        return lead.group(3).strip(), (lead.group(1) + lead.group(2)).strip()
    m = _TRAIL_COND_RE.search(text)
    if m and m.start() > 0:
        return text[:m.start()].strip(), text[m.start():].strip()
    return text, None


def _classify_effect(effect: str, parse_mod, translate_cond) -> dict:
    """Classify one effect string. Returns a dict with `kind`:
      'override'   → {flag}            base-effect re-base we model
      'deferred'   → {}                recognised override we don't model yet (Mind Focus)
      'stat'       → {contribs, condition_expr}
      'unresolved' → {}                captured, not applied (special / untranslatable conditional)
    """
    text = _strip_max_div(effect)

    # "Skills no longer cost Mana" (Frozen Lotus) → a flag the skill-cost model reads to zero the BASE cost
    # (flat additions + multipliers still apply). NOT a final-value override (per stat.py MANA_COST_OVERRIDE note).
    if re.search(r"skills?\s+no\s+longer\s+cost(?:s)?\s+mana", text, re.I):
        return {"kind": "flag", "flag": "skill_no_mana_cost"}

    if re.search(r"doubles?\s+max\s+warcry\s+skill\s+effects", text, re.I):
        return {"kind": "flag", "flag": "formless_warcry_effects"}

    flag = _gain_on_hit_flag(text)
    if flag:
        return {"kind": "automax", "flag": flag}

    sv = _SET_VALUE_RE.search(text)
    if sv:
        return {"kind": "set_value", "stat_key": _SET_VALUE_TARGETS.get(_normalize(sv.group(1))),
                "value": float(sv.group(2))}

    m = _BASE_EFFECT_RE.search(text)
    if m:
        target = _normalize(m.group(1))
        flag = _OVERRIDE_TARGETS.get(target)
        if flag:
            return {"kind": "override", "flag": flag}
        return {"kind": "deferred"}

    # Self-consume lines ("Consumes X% … when you use Attack Skills") carry their cadence + skill-type scope INLINE;
    # the condition split would strip that and the gate is untranslatable → whole line wrongly unresolved. Parse the
    # FULL text first: if it yields consume stats (scope/cadence baked into the stat key), take it as-is (no gate).
    full = parse_mod(text)
    if full and any("_consumed_" in (c.get("stat_key") or "") for c in full):
        return {"kind": "stat", "contribs": full, "condition_expr": None}

    stat_part, cond_part = _split_condition(text)
    contribs = parse_mod(stat_part)
    if not contribs:
        return {"kind": "unresolved"}

    condition_expr = None
    if cond_part is not None:
        # Try the full line first (the phrase-override table is keyed by full effect text), then the
        # isolated clause. If neither maps, we have a gate we can't model → don't apply (capture).
        condition_expr = translate_cond(text) or translate_cond(cond_part)
        if condition_expr is None:
            return {"kind": "unresolved"}

    return {"kind": "stat", "contribs": contribs, "condition_expr": condition_expr}


def _resolve_talent(name: str, effects, parse_mod, translate_cond):
    contribs: list[dict] = []
    flags: set[str] = set()
    statuses: list[dict] = []
    norm = _normalize(name)
    label = f"Core · {name}"
    for eff in effects or []:
        if not (eff or "").strip():
            continue
        text = _strip_max_div(eff)

        # "Gain on hit" blessing/Fervor lines — whole-line; emit an automax flag (full-uptime approximation).
        gflag = _gain_on_hit_flag(text)
        if gflag:
            flags.add(gflag)
            statuses.append({"name": name, "text": eff, "resolved": True, "kind": "automax"})
            continue

        # Set-value override (whole-line). Applied only for derived targets we can force (stat_key set);
        # other targets are tracked-but-unmodeled (resolved:False) — never silently dropped.
        sv = _SET_VALUE_RE.search(text)
        if sv:
            cls = _classify_effect(eff, parse_mod, translate_cond)
            _target = _normalize(sv.group(1))
            if cls.get("stat_key"):
                contribs.append({"set_value": True, "stat_key": cls["stat_key"], "amount": cls["value"],
                                 "text": f"{eff} |core|{norm}", "label": label, "condition_expr": None})
                statuses.append({"name": name, "text": eff, "resolved": True, "kind": "set_value"})
            elif "support" in _target and "mana multiplier" in _target:
                # Off the Beaten Track: forces every attached support's Mana Multiplier to a fixed value
                # (95%). Consumed in engine.utility.apply_reservation as a core flag (no stat to set).
                flags.add("core_support_mana_mult_95")
                statuses.append({"name": name, "text": eff, "resolved": True, "kind": "override"})
            else:
                statuses.append({"name": name, "text": eff, "resolved": False, "kind": "set_value"})
            continue

        # Base-effect overrides are whole-line — don't compound-split them.
        if _BASE_EFFECT_RE.search(text):
            cls = _classify_effect(eff, parse_mod, translate_cond)
            if cls["kind"] == "override":
                flags.add(cls["flag"])
                statuses.append({"name": name, "text": eff, "resolved": True, "kind": "override"})
            else:
                statuses.append({"name": name, "text": eff, "resolved": False, "kind": cls["kind"]})
            continue

        # Compound: split into stat segments that share the trailing condition; classify each so every
        # part is tracked (a resolved segment contributes; an unresolved one is captured, not dropped).
        stat_clause, cond_clause = _split_condition(text)
        segments = _split_compound(stat_clause)
        subs = ([s + (" " + cond_clause if cond_clause else "") for s in segments]
                if len(segments) > 1 else [eff])
        # A shared-magnitude join inside any segment fans out to one sub-effect per stat (usually a no-op).
        subs = [x for sub in subs for x in _expand_shared_stats(sub)]

        for sub in subs:
            cls = _classify_effect(sub, parse_mod, translate_cond)
            if cls["kind"] == "stat":
                for c in cls["contribs"]:
                    contribs.append({
                        "stat_key": c["stat_key"],
                        "amount": c["amount"],
                        "text": f"{c.get('text', sub)} |core|{norm}",
                        "label": label,
                        "condition_expr": cls["condition_expr"],
                    })
                statuses.append({"name": name, "text": sub, "resolved": True, "kind": "stat"})
            elif cls["kind"] == "flag":   # e.g. Frozen Lotus → skill_no_mana_cost (read by engine.skill_cost)
                flags.add(cls["flag"])
                statuses.append({"name": name, "text": sub, "resolved": True, "kind": "flag"})
            else:  # deferred | unresolved
                statuses.append({"name": name, "text": sub, "resolved": False, "kind": cls["kind"]})
    return contribs, flags, statuses


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def _build_catalog(season_trees: dict, belt_blends: dict) -> dict[str, list[str]]:
    """name(normalized) → effect strings, for sources that grant a talent by NAME only (legendary).
    Built from the loaded trees' core_talents and the full belt-blend catalog (55 core blends ≈ the
    common core-talent names). First definition wins."""
    cat: dict[str, list[str]] = {}
    for tree in (season_trees or {}).values():
        for ct in tree.get("core_talents", []) or []:
            nm = _normalize(ct.get("name"))
            if nm:
                cat.setdefault(nm, ct.get("effects", []) or [])
    for b in (belt_blends or {}).get("blends", []) or []:
        nm = _normalize(b.get("talent_name"))
        if nm:
            cat.setdefault(nm, [b.get("effect_text", "")])
    return cat


def _collect(slots, slates, gear, season_trees, belt_blends) -> list[tuple[str, list[str], str | None]]:
    """Gather (name, effects, tree_name) candidates from all four grant sources, in priority order
    (tree → slate → legendary → belt blend). `tree_name` is the granting tree for tree-slot cores (drives
    the source color in the UI); None for slate/legendary/belt-blend cores. Dedup later — first wins."""
    out: list[tuple[str, list[str], str | None]] = []
    catalog = _build_catalog(season_trees, belt_blends)

    # 1. Talent-tree slots — coreTalentSelections maps slot → display_name_key.
    for slot in slots or []:
        if not slot:
            continue
        sels = slot.get("coreTalentSelections") or {}
        if not sels:
            continue
        tree_name = slot.get("treeName", "") or None
        tree = (season_trees or {}).get(_slug(slot.get("treeName", ""))) or {}
        by_key = {ct.get("display_name_key"): ct for ct in tree.get("core_talents", []) or []}
        for talent_id in sels.values():
            ct = by_key.get(talent_id)
            if ct:
                out.append((ct.get("name") or talent_id, ct.get("effects", []) or [], tree_name))
            else:  # tree not loaded — fall back to the name-keyed catalog
                out.append((talent_id, catalog.get(_normalize(talent_id), []), tree_name))

    # 2. Slates — a slot flagged isCore grants the selected core talent (name + effects inline).
    for slate in slates or []:
        for sd in slate.get("slots", []) or []:
            if sd.get("isCore") and sd.get("coreName"):
                out.append((sd["coreName"], sd.get("effects", []) or [], None))

    # 3 & 4. Gear — legendary `[Name] …` grants (names extracted client-side into granted_talents) and
    # the equipped belt blend (belt item's belt_blend id → blend catalog).
    blend_by_id = {str(b.get("talent_id")): b for b in (belt_blends or {}).get("blends", []) or []}
    for gi in gear or []:
        if not isinstance(gi, dict):
            continue
        for nm in gi.get("granted_talents", []) or []:
            out.append((nm, catalog.get(_normalize(nm), []), None))
        bb = gi.get("belt_blend")
        if bb is not None and str(bb) != "":
            blend = blend_by_id.get(str(bb))
            if blend:
                nm = blend.get("talent_name") or f"Belt Blend {bb}"
                out.append((nm, [blend.get("effect_text", "")], None))
    return out


def resolve_core_talents(slots, slates, gear, season_trees, belt_blends, parse_mod, translate_cond):
    """Collect → dedup-by-name → resolve. Returns (contributions, override_flags, statuses).

      contributions  list[dict]  {stat_key, amount, text, label, condition_expr|None}
      override_flags set[str]    {core_sacrifice, core_conductive, divine_grace}
      statuses       list[dict]  {name, text, resolved, kind} — one per effect, for UI badges

    parse_mod(text)      → list[{stat_key, amount, text}]   (server._parse_custom_mod_text)
    translate_cond(text) → engine condition expr | None      (server._translate_condition_expr)
    """
    contribs: list[dict] = []
    flags: set[str] = set()
    statuses: list[dict] = []
    seen: set[str] = set()
    for name, effects, tree_name in _collect(slots, slates, gear, season_trees, belt_blends):
        norm = _normalize(name)
        if not norm or norm in seen:
            continue  # Max Divinity Effect: 1 — count each talent exactly once across all sources
        seen.add(norm)
        c, f, s = _resolve_talent(name, effects, parse_mod, translate_cond)
        for ce in c:
            ce["tree"] = tree_name   # granting tree (None for slate/legendary/belt) → source color in UI
        contribs.extend(c)
        flags |= f
        statuses.extend(s)
    return contribs, flags, statuses
