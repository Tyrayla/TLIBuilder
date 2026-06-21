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
from engine.skill_effects import howling_gale as _hg, icebound_beam as _ib

_MODULES = (_bb, _fs, _ms, _hg, _ib)

# Support ids handled bespoke/deferred — their specific line is skipped by the generic resolver (the
# universal +20% rank line still applies).
GENERIC_GUARD_IDS = frozenset().union(*(getattr(m, "GUARD_IDS", frozenset()) for m in _MODULES))

_CONTRIB_HOOKS: dict = {}
for _m in _MODULES:
    _CONTRIB_HOOKS.update(getattr(_m, "CONTRIB_HOOKS", {}))

_SLOT_HANDLERS = {m.SKILL_ID: m.apply_slot_effects for m in _MODULES if hasattr(m, "apply_slot_effects")}
_PRESEED = {m.SKILL_ID: m.preseed for m in _MODULES if hasattr(m, "preseed")}

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
    Returns [{identity, stat_keys, ranges_by_tier:{tier:{min,max,mid}}}] — only lines with a range_re (a
    user-tunable roll); fixed values (Projectile Speed, Knockback Chance) are omitted. Ranges are signed
    fractions (e.g. 0.22)."""
    from engine.affix_identity import affix_identity
    prog = (data or {}).get("progression") or []
    out: list[dict] = []
    for spec in _LINE_SPECS:
        if item_id not in spec["support_ids"] or spec["range_re"] is None:
            continue
        identity, ranges = None, {}
        for entry in prog:
            line = str((entry.get("values") or {}).get("name", ""))
            m = spec["range_re"].search(line)
            if not m:
                continue
            lo, hi = sorted((float(m.group(1)), float(m.group(2))))
            neg = "(-" in m.group(0) or "(−" in m.group(0)
            sign = -1.0 if neg else 1.0
            lo, hi = sorted((sign * lo / 100.0, sign * hi / 100.0))
            ranges[entry.get("level")] = {"min": lo, "max": hi, "mid": (lo + hi) / 2.0}
            identity = identity or affix_identity(line)
        if ranges and identity:
            out.append({"identity": identity, "stat_keys": list(spec["keys"]), "ranges_by_tier": ranges})
    return out


def support_contribution(sup: dict, data: dict):
    """Type-A: a support-path stat contribution for a guarded support id (e.g. Desperation, Fervor)."""
    fn = _CONTRIB_HOOKS.get(sup.get("item_id"))
    return fn(sup, data) if fn else None


def apply_slot_effects(skill_id: str, **kw) -> dict:
    """Type-B: emit a skill's slot-local effects for one slot. Returns offense overrides (e.g.
    {'remove_mod_tags': {...}}) or {} when the skill has no module."""
    fn = _SLOT_HANDLERS.get(skill_id)
    return (fn(**kw) or {}) if fn else {}


def preseed(skill_id: str, **kw) -> None:
    """Type-C: seed conditions before the fixed-point aggregation (e.g. Decimate's enemy_low_life)."""
    fn = _PRESEED.get(skill_id)
    if fn:
        fn(**kw)
