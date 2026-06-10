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
_TRAIL_COND_RE = re.compile(r"\b(when|while|if|against|upon)\b", re.I)


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

    m = _BASE_EFFECT_RE.search(text)
    if m:
        target = _normalize(m.group(1))
        flag = _OVERRIDE_TARGETS.get(target)
        if flag:
            return {"kind": "override", "flag": flag}
        return {"kind": "deferred"}

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
        cls = _classify_effect(eff, parse_mod, translate_cond)
        kind = cls["kind"]
        if kind == "override":
            flags.add(cls["flag"])
            statuses.append({"name": name, "text": eff, "resolved": True, "kind": "override"})
        elif kind == "stat":
            for c in cls["contribs"]:
                contribs.append({
                    "stat_key": c["stat_key"],
                    "amount": c["amount"],
                    "text": f"{c.get('text', eff)} |core|{norm}",
                    "label": label,
                    "condition_expr": cls["condition_expr"],
                })
            statuses.append({"name": name, "text": eff, "resolved": True, "kind": "stat"})
        else:  # deferred | unresolved
            statuses.append({"name": name, "text": eff, "resolved": False, "kind": kind})
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


def _collect(slots, slates, gear, season_trees, belt_blends) -> list[tuple[str, list[str]]]:
    """Gather (name, effects) candidates from all four grant sources, in priority order (tree → slate
    → legendary → belt blend). Dedup happens later — first occurrence wins."""
    out: list[tuple[str, list[str]]] = []
    catalog = _build_catalog(season_trees, belt_blends)

    # 1. Talent-tree slots — coreTalentSelections maps slot → display_name_key.
    for slot in slots or []:
        if not slot:
            continue
        sels = slot.get("coreTalentSelections") or {}
        if not sels:
            continue
        tree = (season_trees or {}).get(_slug(slot.get("treeName", ""))) or {}
        by_key = {ct.get("display_name_key"): ct for ct in tree.get("core_talents", []) or []}
        for talent_id in sels.values():
            ct = by_key.get(talent_id)
            if ct:
                out.append((ct.get("name") or talent_id, ct.get("effects", []) or []))
            else:  # tree not loaded — fall back to the name-keyed catalog
                out.append((talent_id, catalog.get(_normalize(talent_id), [])))

    # 2. Slates — a slot flagged isCore grants the selected core talent (name + effects inline).
    for slate in slates or []:
        for sd in slate.get("slots", []) or []:
            if sd.get("isCore") and sd.get("coreName"):
                out.append((sd["coreName"], sd.get("effects", []) or []))

    # 3 & 4. Gear — legendary `[Name] …` grants (names extracted client-side into granted_talents) and
    # the equipped belt blend (belt item's belt_blend id → blend catalog).
    blend_by_id = {str(b.get("talent_id")): b for b in (belt_blends or {}).get("blends", []) or []}
    for gi in gear or []:
        if not isinstance(gi, dict):
            continue
        for nm in gi.get("granted_talents", []) or []:
            out.append((nm, catalog.get(_normalize(nm), [])))
        bb = gi.get("belt_blend")
        if bb is not None and str(bb) != "":
            blend = blend_by_id.get(str(bb))
            if blend:
                nm = blend.get("talent_name") or f"Belt Blend {bb}"
                out.append((nm, [blend.get("effect_text", "")]))
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
    for name, effects in _collect(slots, slates, gear, season_trees, belt_blends):
        norm = _normalize(name)
        if not norm or norm in seen:
            continue  # Max Divinity Effect: 1 — count each talent exactly once across all sources
        seen.add(norm)
        c, f, s = _resolve_talent(name, effects, parse_mod, translate_cond)
        contribs.extend(c)
        flags |= f
        statuses.extend(s)
    return contribs, flags, statuses
