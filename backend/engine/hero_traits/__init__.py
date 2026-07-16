"""Per-hero-trait effect/mechanic modules + a small dispatch registry.

One module per trait that needs bespoke modeling (computed stacks, capped stat-to-stat scaling, uptime).
The registry keys on `trait_id` so the engine dispatches generically with no per-trait hardcoding. See
README.md for the hook convention.
"""
import inspect

from engine.hero_traits import lightning_shadow as _ls
from engine.hero_traits import high_court_chariot as _hcc
from engine.hero_traits import wind_stalker as _ws
from engine.hero_traits import sing_with_the_tide as _swt
from engine.hero_traits import unsullied_blade as _ub
from engine.hero_traits import licorice_note as _ln

_MODULES = (_ls, _hcc, _ws, _swt, _ub, _ln)

_APPLY = {m.TRAIT_ID: m.apply for m in _MODULES if hasattr(m, "apply")}
_STASH = {m.TRAIT_ID: m.stash for m in _MODULES if hasattr(m, "stash")}
_STATUS = {m.TRAIT_ID: m.status_lines for m in _MODULES if hasattr(m, "status_lines")}
_VIRTUAL = {m.TRAIT_ID: m.virtual_supports for m in _MODULES if hasattr(m, "virtual_supports")}

# The three universal, build-independent inputs every status_lines() accepts (see engine.coverage.trait_coverage's
# probe). `slot_levels`/`advanced_picks` describe a property of the TRAIT itself. `season` (2026-07-16 architecture
# fix) is a *global environment* fact — which season's catalog to read season-sourced display numbers from (e.g.
# a cap that drifted SS12->SS13) — NOT an interaction with another equipped entity the way `main_skill_tags` /
# `attached_supports` are. Unlike those, `season` never gates whether a line/branch EXISTS (no module branches
# `if season == ...` — only the NUMBER inside an already-unconditional "working" line differs), so the probe can
# supply the real active season concretely (see trait_coverage's call) without leaving anything unseen; it is
# therefore excluded from `build_gated_status_params` the same as `slot_levels`/`advanced_picks`.
_STATUS_BASE_PARAMS = {"slot_levels", "advanced_picks", "season"}


def build_gated_status_params(trait_id: str | None) -> list[str]:
    """Named parameters (beyond `slot_levels`/`advanced_picks`/`season`) that this trait's `status_lines`
    accepts — e.g. `main_skill_tags`, `attached_supports`, `skills_input`, `skills_by_id`, `prepared_skill`.
    Those describe an interaction with ANOTHER equipped entity (the main skill, other slots), which is a
    build-specific fact `engine.coverage.trait_coverage`'s single-argument probe leaves at its default
    (None/[]) — so a module that BRANCHES on one of them (a warning/nyi line gated behind `is not None`,
    membership, etc.) may have a line the probe can never see, and 'full' would overclaim it.

    Detected structurally from the function signature (`inspect.signature`), not a hand-maintained
    per-trait list, so a newly-added gated branch on any FUTURE trait module is caught automatically the
    moment it declares the extra parameter — no coverage.py edit required. `[]` means the module only
    takes the three universal inputs, so the probe already saw everything it possibly could."""
    fn = _STATUS.get(trait_id)
    if not fn:
        return []
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return []
    return sorted(
        name for name, p in params.items()
        if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and name not in _STATUS_BASE_PARAMS
    )


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
