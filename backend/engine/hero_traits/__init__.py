"""Per-hero-trait effect/mechanic modules + a small dispatch registry.

One module per trait that needs bespoke modeling (computed stacks, capped stat-to-stat scaling, uptime).
The registry keys on `trait_id` so the engine dispatches generically with no per-trait hardcoding. See
README.md for the hook convention.
"""
from engine.hero_traits import lightning_shadow as _ls
from engine.hero_traits import high_court_chariot as _hcc
from engine.hero_traits import wind_stalker as _ws
from engine.hero_traits import sing_with_the_tide as _swt

_MODULES = (_ls, _hcc, _ws, _swt)

_APPLY = {m.TRAIT_ID: m.apply for m in _MODULES if hasattr(m, "apply")}
_STASH = {m.TRAIT_ID: m.stash for m in _MODULES if hasattr(m, "stash")}
_STATUS = {m.TRAIT_ID: m.status_lines for m in _MODULES if hasattr(m, "status_lines")}
_VIRTUAL = {m.TRAIT_ID: m.virtual_supports for m in _MODULES if hasattr(m, "virtual_supports")}


def has_module(trait_id: str | None) -> bool:
    """True if a bespoke module owns this trait (server then skips the generic trait_effects resolver)."""
    return trait_id in _APPLY


def apply(trait_id: str, **kw) -> dict:
    """Loop-top: returns {'contributions': [...], 'numbed_stacks': float|None}. {} when no module."""
    fn = _APPLY.get(trait_id)
    return (fn(**kw) or {}) if fn else {}


def stash(trait_id: str, **kw) -> None:
    """Loop-bottom: capture converged scalars the next pass's apply() needs."""
    fn = _STASH.get(trait_id)
    if fn:
        fn(**kw)


def status_lines(trait_id: str, **kw) -> list[dict]:
    """Per-line working/NYI statuses for the never-silently-drop surface. [] when no module."""
    fn = _STATUS.get(trait_id)
    return (fn(**kw) or []) if fn else []


def virtual_supports(trait_id: str, **kw) -> list[dict]:
    """Free supports a trait grants to the main skill (no UI slot) — folded into support resolution by the caller.
    Each is a normal support dict {item_id, slot, level, …}. [] when no module / none granted."""
    fn = _VIRTUAL.get(trait_id)
    return (fn(**kw) or []) if fn else []
