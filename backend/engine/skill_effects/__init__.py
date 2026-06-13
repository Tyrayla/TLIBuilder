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

_MODULES = (_bb, _fs, _ms)

# Support ids handled bespoke/deferred — their specific line is skipped by the generic resolver (the
# universal +20% rank line still applies).
GENERIC_GUARD_IDS = frozenset().union(*(getattr(m, "GUARD_IDS", frozenset()) for m in _MODULES))

_CONTRIB_HOOKS: dict = {}
for _m in _MODULES:
    _CONTRIB_HOOKS.update(getattr(_m, "CONTRIB_HOOKS", {}))

_SLOT_HANDLERS = {m.SKILL_ID: m.apply_slot_effects for m in _MODULES if hasattr(m, "apply_slot_effects")}
_PRESEED = {m.SKILL_ID: m.preseed for m in _MODULES if hasattr(m, "preseed")}


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
