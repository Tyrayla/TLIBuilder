"""Resolve enabled ELIXIR skills into player stat contributions (the "Elixir Effect" buff).

Elixir skills (active_skill + "elixir" tag) are slotted in active skill slots and enabled via the skill enabler.
Each grants a temporary buff to the PLAYER, scaled engine-side by ELIXIR SKILL EFFECT (apply_elixir_buffs).
Tyra-confirmed model: assume FULL UPTIME while enabled — real cooldown/charge-based uptime is a later pass, but
we TRACK the timing now (cooldown, duration, additional duration, charges, charge/sec) for the Skill panel.

Modeled like auras/empowers: buff values parse from the detailed_description through the shared text->stat
pipeline (parse_mod), emitted as the SAME typed/scoped stats so they flow through offense's conversion-aware
pipeline. The (LvN:…) restoration lines are a separate NYI subsystem; the dew/distillate buffs are level-flat.
Nothing is silently dropped — unmapped lines surface as NYI.

Secondary handling here:
  - "Has Blur" (Putrid Toad) → meta.has_blur (server auto-sets blur_active); the Blur-gated lines (+Defense,
    -Cursed Effect) apply gated on blur_active.
  - Flag stats (lucky_<type>, es_uninterruptible, es_bypass_pct) are emitted no_scale (Elixir Effect must not
    multiply a flag/threshold).
  - The 3 elixir support gems (Hyper Metabolism / Medicinal Buildup / Emergency Aid) fold charge/sec + max-charge
    into the per-elixir timing meta.
"""
from __future__ import annotations
import re

from engine.aura_resolver import _canon_key

_ELIXIR_EFFECT_KEYS = {"elixir_effect_inc", "elixir_effect_additional"}
# Flag/threshold stats whose value must NOT be scaled by Elixir Effect (a flag of 1, or a fixed % bypass).
_NO_SCALE_KEYS = frozenset({
    "lucky_physical", "lucky_fire", "lucky_cold", "lucky_lightning", "lucky_erosion",
    "es_uninterruptible", "es_bypass_pct",
})

# Intro line ("Casts this skill and gains an Elixir Effect:" / "… gains restoration:") — drop.
_INTRO_RE = re.compile(r"^casts?\s+this\s+skill\s+and\s+gains\b.*:\s*$", re.I)
# Pure timing / boilerplate / sub-header noise (captured separately or informational).
_NOISE_RE = re.compile(
    r"^lasts?\s+for\s+[\d.]+\s*s\b"
    r"|^defeating\s+enemies\b"
    r"|^while\s+blur\s+is\s+active\s*,?\s*$"
    r"|^this skill's restoration effect", re.I)
# Lines belonging to NYI subsystems (restoration tonics, Saltpeter minion/true-damage, Ignite→Scorch).
_NYI_RE = re.compile(
    r"\brestor(?:es|ation)\b|\bminions?\b|\btrue\s+damage\b|replaced\s+with\s+scorch"
    r"|transferred\s+to\s+a\s+random", re.I)
# Restoration tonic lines → structured restoration entries fed to the recovery stage (NOT NYI). A line is
# "Restores <body> within/in N s" and the body may carry MULTIPLE pool parts (Compound Tonic: "39% Max Life and
# 47 Mana") — every part is captured so nothing is silently dropped.
_RESTORE_RE = re.compile(
    r"restores?\s+([\d.]+)\s*(%?)\s*(?:max\s+)?(life|mana)\b.*?(?:within|in)\s+([\d.]+)\s*s", re.I)
_RESTORE_LINE_RE = re.compile(r"restores?\b(.*?)(?:within|in)\s+([\d.]+)\s*s", re.I)
_RESTORE_PART_RE = re.compile(r"([\d.]+)\s*(%?)\s*(?:max\s+)?(life|mana)\b", re.I)
# Per-level anchors on a restoration line, e.g. "(Lv1:41) (Lv21:61) (Lv41:71)" — the % value scales with the
# elixir's level (the base text number is only the Lv1 value). Interpolated to the equipped level.
_LV_ANCHOR_RE = re.compile(r"\(\s*lv\.?\s*(\d+)\s*:\s*([\d.]+)\s*\)", re.I)


def _level_anchors(raw_line: str) -> list[tuple[int, float]]:
    return sorted({(int(m.group(1)), float(m.group(2))) for m in _LV_ANCHOR_RE.finditer(raw_line or "")})


def _interp_level_anchors(anchors: list[tuple[int, float]], level: int) -> float | None:
    """Piecewise-linear value at `level` from (lvl, value) anchors; extrapolates past the last segment (matches
    how auras/supports extend scaling beyond their last anchor)."""
    if not anchors:
        return None
    if level <= anchors[0][0]:
        if len(anchors) >= 2 and level < anchors[0][0]:
            (l0, v0), (l1, v1) = anchors[0], anchors[1]
            return v0 + (v1 - v0) * (level - l0) / (l1 - l0)
        return anchors[0][1]
    for (l0, v0), (l1, v1) in zip(anchors, anchors[1:]):
        if l0 <= level <= l1:
            return v0 + (v1 - v0) * (level - l0) / (l1 - l0)
    (l0, v0), (l1, v1) = anchors[-2], anchors[-1]
    return v1 + (v1 - v0) * (level - l1) / (l1 - l0)
# "At 15 Charging Progress, gains 1 Charge" → the charging needed per charge (drives the charge-limited recast).
_CHARGE_THRESHOLD_RE = re.compile(r"at\s+([\d.]+)\s+charging\s+progress\s*,?\s*gains?\s+\d*\s*charge", re.I)
_BLUR_RE = re.compile(r"\bhas\s+blur\b", re.I)
# Trailing "while Blur is active" qualifier — strip before parse_mod (the gate is applied via condition_expr).
_BLUR_SUFFIX_RE = re.compile(r"\s+while\s+blur\s+is\s+active\b.*$", re.I)
# Strip any (LvN:…) per-level annotation defensively.
_LV_ANNOT_RE = re.compile(r"\s*\(lv\d+:[^)]*\)", re.I)

# Ingredient lines carry trailing condition/spatial/duration/minion clauses the stat parser can't take. Under the
# full-uptime model we assume the condition is satisfied and parse the core stat (e.g. Razor Leaf's "+X% additional
# damage when you land a Critical Strike" → +X% additional damage). Unmapped remainders still surface NYI.
_INGREDIENT_CUT_RE = re.compile(
    r"\s+(?:when|while|within|for every|every|upon|after)\b.*$"
    r"|\.\s*(?:stacks up to|lasts for|interval).*$"
    r"|\s*\(not affected by.*$", re.I)
_INGREDIENT_DROP_RE = re.compile(r"\s+for you and your minions?\b", re.I)
# Pixie Tear (Special Ingredient): two effects the generic parser can't take —
#   (a) "X% of excess Life restoration is also applied to Energy Shield restoration" → excess_restoration_to_es_pct
#   (b) "For every 400 Max Energy Shield, +X% additional damage … up to +Y%" → dmg_additional_per_400_es (+ cap)
# Both are "not affected by the effects of Elixir Skills" → no_scale.
_PIXIE_ES_RESTORE_RE = re.compile(
    r"([\d.]+)\s*%\s*of\s+excess\s+life\s+restoration\s+is\s+also\s+applied\s+to\s+energy\s+shield", re.I)
_PIXIE_PER_400_ES_RE = re.compile(
    r"every\s+400\s+max\s+energy\s+shield\s*,?\s*\+?([\d.]+)\s*%\s*additional\s+damage.*?up\s+to\s*\+?([\d.]+)\s*%", re.I)


def _ingredient_stat_text(line: str) -> str:
    """Reduce an ingredient effect line to its core stat clause for parsing (full-uptime: conditions assumed met)."""
    return _INGREDIENT_DROP_RE.sub("", _INGREDIENT_CUT_RE.sub("", line)).strip(" .")

# Elixir support gems (item_id) → how they affect timing. Charge/sec and max-charge are display-only today.
_SUPPORT_GEMS = {
    "hyper_metabolism": "charge_per_second",   # "+0.5 Charging Progress every second"
    "medicinal_buildup": "max_charge",         # "+1 Max Charges"
    "emergency_aid": "nyi",                     # charge on Severe Injury (event-based) — surfaced NYI
}


def _num(val) -> float | None:
    """First number in a value like 0.5, '3.0', '0.5 s' → float, else None."""
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"[\d.]+", str(val or ""))
    return float(m.group(0)) if m else None


def _prep(lines, has_blur: bool):
    """(modelable lines, nyi lines) after stripping intro/noise/level-annotations. NYI-subsystem lines split out.
    `has_blur` gates the kept lines on blur_active (full uptime → always on, but surfaced as a gated buff)."""
    keep, nyi = [], []
    for raw in lines or []:
        s = _LV_ANNOT_RE.sub("", raw or "").strip(" .")
        if not s or _INTRO_RE.match(s) or _NOISE_RE.search(s) or _BLUR_RE.search(s):
            continue
        s = _BLUR_SUFFIX_RE.sub("", s).strip(" .")
        if not s:
            continue
        (nyi if _NYI_RE.search(s) else keep).append(s)
    return keep, nyi


def resolve_elixirs(skills_input, skills_by_id, parse_mod, translate_cond=None, attached_supports=None,
                    ingredient_lines_by_slot=None):
    """skills_input: [{slot, skill_id, level, enabled}]; attached_supports: [{item_id, slot, level, enabled}].
    ingredient_lines_by_slot: {slot: [effect_text]} — Licorice Note Ingredient "additional base effect" lines
    (already tier-expanded + prefix-stripped server-side), folded into that scent-bottle elixir's buffs like its
    own lines. Returns (buffs, statuses, stack_conditions, meta) — same shape as resolve_empowers. Buffs are
    UNSCALED; apply_elixir_buffs scales them by Elixir Effect in the engine."""
    buffs, statuses, stack_conditions, meta = [], [], [], {}
    ingredient_lines_by_slot = ingredient_lines_by_slot or {}

    # Map enabled elixir support gems by host slot → {kind: total_value}.
    supports_by_slot: dict = {}
    for sup in attached_supports or []:
        if not sup.get("enabled", True):
            continue
        kind = _SUPPORT_GEMS.get(sup.get("item_id"))
        if not kind:
            continue
        slot = sup.get("slot", 1)
        data = (skills_by_id or {}).get(sup.get("item_id")) or {}
        # Value from the gem's simple_description (Lv1 anchor — level-scaling of charge timing is approximate).
        val = 0.0
        if kind == "charge_per_second":
            for l in data.get("simple_description") or []:
                m = re.search(r"([\d.]+)\s+charging\s+progress\s+every\s+second", _LV_ANNOT_RE.sub("", l), re.I)
                if m:
                    val = float(m.group(1)); break
        elif kind == "max_charge":
            for l in data.get("simple_description") or []:
                m = re.search(r"\+([\d.]+)\s+max\s+charges?", l, re.I)
                if m:
                    val = float(m.group(1)); break
        gem_name = data.get("name") or sup.get("item_id")
        bucket = supports_by_slot.setdefault(
            slot, {"charge_per_second": 0.0, "max_charge": 0.0, "nyi": [], "sources": []})
        if kind == "nyi":
            bucket["nyi"].append(gem_name)
        else:
            bucket[kind] += val
            # Per-gem source row for the timing breakdowns (name + what it granted).
            bucket["sources"].append({"name": gem_name, "kind": kind, "value": val})

    def _emit(sid, name, stat, base, scope, cond, no_scale, phrase):
        buffs.append({
            "skill_id": sid, "name": name, "stat_key": stat, "base_amount": base, "scope": scope,
            "condition_expr": cond, "is_elixir_effect": stat in _ELIXIR_EFFECT_KEYS, "no_scale": no_scale,
            "per_stack": False, "phrase": phrase, "text": f"{phrase} |elixir|{sid}",
        })

    for a in skills_input or []:
        sid = a.get("skill_id")
        skill = skills_by_id.get(sid) or {}
        tags = [t.lower() for t in (skill.get("skill_tags") or [])]
        if "elixir" not in tags or skill.get("skill_type") != "active_skill":
            continue
        # DISABLED elixirs are still resolved (so the Skill panel shows their stats marked "Disabled") but their
        # buffs are NOT folded into the engine — apply_elixir_buffs skips emission when meta.enabled is False, and
        # the auto-conditions count only enabled elixirs.
        enabled = bool(a.get("enabled", True))

        level = int(a.get("level") or 1)
        slot = a.get("slot")
        name = skill.get("name", sid)
        raw = skill.get("detailed_description") or skill.get("simple_description") or []
        has_blur = any(_BLUR_RE.search(l or "") for l in raw)
        _ct = None
        for _l in raw:
            _m = _CHARGE_THRESHOLD_RE.search(_l or "")
            if _m:
                _ct = float(_m.group(1)); break

        keep, nyi = _prep(raw, has_blur)
        seen: dict = {}
        review: list[str] = []
        for line in keep:
            res = parse_mod(line) or []
            if not res:
                if re.search(r"\d", line) and len(line) > 3:
                    nyi.append(line)
                continue
            for e in res:
                key = _canon_key(e["stat_key"], e.get("scope"))
                if key in seen:
                    continue
                seen[key] = True
                cond = "blur_active" if has_blur else None
                _emit(sid, name, e["stat_key"], float(e["amount"]), e.get("scope"), cond,
                      e["stat_key"] in _NO_SCALE_KEYS, line)

        # ── Restoration tonics: pull "Restores N% Max Life/Mana within Ns" out of NYI into structured entries the
        # recovery stage consumes (scaled by Elixir Effect/Duration in apply_elixir_buffs, then Restoration
        # Effect/Duration in recovery). pct = fraction of max pool; flat = absolute. ──
        # Parse from the RAW description (anchors intact) so the % scales to the equipped level. Every pool part in
        # a "Restores … within N s" line is captured (Compound Tonic = % Life + flat Mana) — none dropped.
        restoration: list[dict] = []
        _handled: set[str] = set()
        for rawline in raw:
            stripped = _LV_ANNOT_RE.sub("", rawline or "").strip(" .")
            lm = _RESTORE_LINE_RE.search(stripped)
            if not lm:
                continue
            body, window = lm.group(1), lm.group(2)
            parts = list(_RESTORE_PART_RE.finditer(body))
            if not parts:
                continue
            anchors = _level_anchors(rawline or "")
            pct_parts = sum(1 for p in parts if p.group(2))
            for p in parts:
                amt, pct, pool = p.group(1), p.group(2), p.group(3)
                # Anchors scale the single % part (the leveled value); literal parts (flat, or a 2nd %) stay as-is.
                lvl_val = _interp_level_anchors(anchors, level) if (pct and pct_parts == 1 and anchors) else None
                value = lvl_val if lvl_val is not None else float(amt)
                restoration.append({
                    "pool": pool.lower(), "mode": "pct" if pct else "flat",
                    "base_amount": (value / 100.0) if pct else value,
                    "base_window": float(window), "slot": slot, "text": stripped, "name": name,
                })
            _handled.add(stripped)
        nyi = [u for u in nyi if u not in _handled]

        # ── Licorice Note Ingredients: fold this scent-bottle elixir's equipped ingredient effects in as buffs ──
        # (already tier-expanded + prefix-stripped server-side). "(not affected by … Elixir Skills)" → no_scale.
        for line in ingredient_lines_by_slot.get(slot, []) or []:
            no_scale = bool(re.search(r"not\s+affected\s+by[^.]*elixir", line, re.I))
            # Pixie Tear: explicit two-part handling (excess→ES restoration + per-400-ES capped damage), both
            # no_scale. Handled here rather than via parse_mod (the generic parser can't take either clause).
            _px_es = _PIXIE_ES_RESTORE_RE.search(line)
            _px_dmg = _PIXIE_PER_400_ES_RE.search(line)
            if _px_es or _px_dmg:
                if _px_es:
                    k = _canon_key("excess_restoration_to_es_pct", None)
                    if k not in seen:
                        seen[k] = True
                        _emit(sid, name, "excess_restoration_to_es_pct", float(_px_es.group(1)) / 100.0,
                              None, None, True, f"{line} (Ingredient)")
                if _px_dmg:
                    if _canon_key("dmg_additional_per_400_es", None) not in seen:
                        seen[_canon_key("dmg_additional_per_400_es", None)] = True
                        _emit(sid, name, "dmg_additional_per_400_es", float(_px_dmg.group(1)) / 100.0,
                              None, None, True, f"{line} (Ingredient)")
                        _emit(sid, name, "dmg_additional_per_400_es_cap", float(_px_dmg.group(2)) / 100.0,
                              None, None, True, f"{line} (Ingredient cap)")
                continue
            # "when you land a Critical Strike" → crit-weighted additional damage (offense weights by crit chance).
            is_crit = bool(re.search(r"critical\s+strike", line, re.I))
            # "Stacks up to N times" → assume max stacks under full uptime (Scattered Spore = ×2).
            sm = re.search(r"stacks?\s+up\s+to\s+(\d+)", line, re.I)
            stacks = int(sm.group(1)) if sm else 1
            res = parse_mod(_ingredient_stat_text(line)) or []
            if not res:
                if re.search(r"\d", line) and len(line) > 3:
                    nyi.append(f"{line} (Ingredient)")
                continue
            for e in res:
                stat_key = e["stat_key"]
                if is_crit and stat_key == "dmg_additional":   # route to the crit-weighted pool
                    stat_key = "dmg_additional_on_crit"
                key = _canon_key(stat_key, e.get("scope"))
                if key in seen:
                    continue
                seen[key] = True
                _emit(sid, name, stat_key, float(e["amount"]) * stacks, e.get("scope"), None,
                      no_scale or stat_key in _NO_SCALE_KEYS, f"{line} (Ingredient)")

        nyi = sorted(set(nyi))
        for u in nyi:
            statuses.append({"skill_id": sid, "text": u, "resolved": False, "kind": "nyi"})

        sup = supports_by_slot.get(slot, {})
        for u in sup.get("nyi", []):
            statuses.append({"skill_id": sid, "text": f"{u} (charge on Severe Injury — event-based)",
                             "resolved": False, "kind": "nyi"})

        meta[sid] = {
            "name": name, "level": level, "slot": slot, "nyi": nyi, "review": review,
            "has_blur": has_blur, "enabled": enabled, "stack_condition": None, "max_stacks": None,
            "restoration": restoration,
            "timing": {
                "cooldown": _num(skill.get("cooldown")),
                "base_duration": _num(skill.get("duration")),
                "charges": _num(skill.get("charges")),
                "charge_threshold": _ct,
                "support_charge_per_second": sup.get("charge_per_second", 0.0),
                "support_max_charge": sup.get("max_charge", 0.0),
                "support_sources": sup.get("sources", []),
            },
        }

    return buffs, statuses, stack_conditions, meta
