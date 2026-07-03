"""Per-skill effect/mechanic modules + a small dispatch registry.

One module per skill that needs bespoke modeling beyond the generic resolvers — its canvas
(magnificent/noble) support mechanics, intrinsic self-buffs, and skill-specific finalize logic. Keep
generic, skill-agnostic resolution in support_resolver / aggregator / offense; put only the
skill-specific pieces here. See README.md for the convention.

Each module may expose:
  - GUARD_IDS: frozenset      support ids whose SPECIFIC progression line must skip the generic resolver
  - CONTRIB_HOOKS: dict        {item_id: fn(sup, data) -> contribution dict | None}  (type-A, support path)
  - apply_slot_effects(...)    type-B: per-slot slot-local emissions (keyed by SKILL_ID)
  - preseed(...)               type-C: loop-time condition seeding before aggregation (keyed by SKILL_ID)

The registry below aggregates these so the engine dispatches generically (no per-skill hardcoding).
"""
from engine.skill_effects import berserking_blade as _bb, focused_slash as _fs, moon_strike as _ms
from engine.skill_effects import howling_gale as _hg, icebound_beam as _ib, chromatic_shot as _cs
from engine.skill_effects import groundshaker as _gs, activation_medium as _am, split_shot as _ss

_MODULES = (_bb, _fs, _ms, _hg, _ib, _cs, _gs, _am, _ss)

# Support ids handled bespoke/deferred — their specific line is skipped by the generic resolver (the
# universal +20% rank line still applies).
GENERIC_GUARD_IDS = frozenset().union(*(getattr(m, "GUARD_IDS", frozenset()) for m in _MODULES))

_CONTRIB_HOOKS: dict = {}
for _m in _MODULES:
    _CONTRIB_HOOKS.update(getattr(_m, "CONTRIB_HOOKS", {}))

_SLOT_HANDLERS = {m.SKILL_ID: m.apply_slot_effects
                  for m in _MODULES if hasattr(m, "apply_slot_effects") and hasattr(m, "SKILL_ID")}
# Slot-LEVEL handlers (no SKILL_ID): run for EVERY slot regardless of the active skill — they react to the slot's
# SUPPORTS (e.g. activation mediums), not the skill. Their overrides merge on top of the skill handler's.
_SLOT_LEVEL_HOOKS = [m.apply_slot_effects
                     for m in _MODULES if hasattr(m, "apply_slot_effects") and not hasattr(m, "SKILL_ID")]
_PRESEED = {m.SKILL_ID: m.preseed for m in _MODULES if hasattr(m, "preseed") and hasattr(m, "SKILL_ID")}

# Modeled-line specs across all modules: per bespoke support clause, its phrase→stat-keys + roll range_re.
# Drives the coverage-badge resolver (so bespoke lines show Consumed, not NYI) and the per-line roll slider.
_LINE_SPECS: list = []
for _m in _MODULES:
    _LINE_SPECS.extend(getattr(_m, "LINE_SPECS", []))


def resolve_line_keys(text: str):
    """The engine stat key(s) a bespoke support clause resolves to, for the coverage badge.
      - non-empty list → a stat modifier (badge classifies it against consumed/universe)
      - []             → a RECOGNIZED behavioral line (sets a condition/cap, no stat → no badge)
      - None           → not a bespoke line (caller falls through to the generic resolver)
    Phrase-matched, so it works on both the raw '(lo–hi)%' line and the rendered midpoint."""
    if not text:
        return None
    for spec in _LINE_SPECS:
        if spec["phrase"].search(text):
            return list(spec["keys"])
    return None


def modeled_rolls(item_id: str, data: dict) -> list[dict]:
    """Per-line roll metadata for a bespoke support (item_id), so the support panel can show a roll slider
    bounded by the tier range and keyed the SAME way the engine reads it (affix_identity of the tier line).
    Returns [{identity, stat_keys, ranges_by_tier:{tier:{min,max,mid}}, unit, scale, label, group, wired}] — only
    lines with a range (a user-tunable roll); fixed values are omitted. Ranges are signed fractions (e.g. 0.22)."""
    # Activation mediums are parsed generically (many rolls per concatenated line) by the AM module.
    if _am.is_activation_medium(item_id):
        return [{"identity": r["identity"], "stat_keys": ([r["stat_key"]] if r.get("stat_key") else []),
                 "ranges_by_tier": r["ranges_by_tier"], "unit": r["unit"], "scale": r["scale"],
                 "label": r["label"], "desc": r.get("desc", r["label"]),
                 "group": r.get("group"), "wired": r.get("wired", False)}
                for r in _am.parse_am_rolls(data)]
    from engine.affix_identity import affix_identity
    prog = (data or {}).get("progression") or []
    out: list[dict] = []
    for spec in _LINE_SPECS:
        if item_id not in spec["support_ids"] or spec["range_re"] is None:
            continue
        # unit/scale: '%' at scale 100 (default) → ranges are signed fractions; a seconds roll uses scale 1
        # ('s'), so its slider shows raw seconds. identity: a fixed synthetic key (activation-medium rolls carry
        # two rolls on one line, so affix-identity can't tell them apart); else the tier line's affix-identity.
        scale = float(spec.get("scale", 100.0)) or 100.0
        fixed_identity = spec.get("identity")

        def _mk_range(m):
            g1, g2 = m.group(1), m.group(2)
            lo_raw, hi_raw = float(g1), float(g2)
            if not (g1.lstrip().startswith(("-", "−")) or g2.lstrip().startswith(("-", "−"))):
                if "(-" in m.group(0) or "(−" in m.group(0):
                    lo_raw, hi_raw = -lo_raw, -hi_raw
            lo, hi = sorted((lo_raw / scale, hi_raw / scale))
            return {"min": lo, "max": hi, "mid": (lo + hi) / 2.0}

        identity, ranges = fixed_identity, {}
        for entry in prog:
            line = str((entry.get("values") or {}).get("name", ""))
            m = spec["range_re"].search(line)
            if not m:
                continue
            ranges[entry.get("level")] = _mk_range(m)
            identity = identity or affix_identity(line)
        # Fallback: the roll lives only in raw_text (e.g. Rhythm's interval appears in raw_text, not every tier's
        # progression line) → key it under tier 1 so the panel still shows the slider.
        if not ranges:
            m = spec["range_re"].search(str((data or {}).get("raw_text", "")))
            if m:
                ranges[1] = _mk_range(m)
        if ranges and identity:
            keys = list(spec["keys"])
            out.append({"identity": identity, "stat_keys": keys,
                        "ranges_by_tier": ranges, "unit": spec.get("unit", "%"), "scale": scale,
                        "label": spec.get("label", "Roll"), "group": spec.get("group"),
                        "wired": bool(keys)})
    return out


def support_contribution(sup: dict, data: dict):
    """Type-A: a support-path stat contribution for a guarded support id (e.g. Desperation, Fervor)."""
    fn = _CONTRIB_HOOKS.get(sup.get("item_id"))
    return fn(sup, data) if fn else None


def is_guarded(item_id: str | None) -> bool:
    """A support whose specific line the generic resolver must skip: a bespoke-module guard id OR any activation
    medium (parsed/wired by the AM module). Used by support_resolver + tooltip."""
    return bool(item_id) and (item_id in GENERIC_GUARD_IDS or _am.is_activation_medium(item_id))


def apply_slot_effects(skill_id: str, **kw) -> dict:
    """Type-B: emit a slot's local effects. Runs the active skill's handler (if any) THEN every slot-level hook
    (which react to the slot's supports, e.g. activation mediums). Overrides are merged; slot-level keys
    (trigger/inject_supports) never collide with skill keys (demolisher_flags/remove_mod_tags)."""
    out: dict = {}
    fn = _SLOT_HANDLERS.get(skill_id)
    if fn:
        out.update(fn(**kw) or {})
    for hook in _SLOT_LEVEL_HOOKS:
        res = hook(**kw) or {}
        for k, v in res.items():
            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                out[k].update(v)
            elif k in out and isinstance(out[k], list) and isinstance(v, list):
                out[k].extend(v)
            else:
                out[k] = v
    return out


def preseed(skill_id: str, **kw) -> None:
    """Type-C: seed conditions before the fixed-point aggregation (e.g. Decimate's enemy_low_life)."""
    fn = _PRESEED.get(skill_id)
    if fn:
        fn(**kw)
