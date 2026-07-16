"""Shared helper: read a hero trait's per-tier numeric values straight from the season catalog
(`_hero_traits.json`, via `persistence.season_manager.load_hero_traits_indexed`) instead of a hardcoded
Python literal — so a season rebalance is picked up by re-importing data, never by hand-editing a literal
or branching on `season == "..."` (2026-07-16, licorice_note / unsullied_blade / high_court_chariot SS12→SS13
drift fix; see `.wolf/buglog.json`).

Catalog shape: a trait's `advanced_traits[i]["effects"][0]` (a plain string in the normalized runtime view)
often holds SEVERAL `( a / b / c / d / e )` per-tier groups in one string (a cooldown, a ratio, a cap, ...),
so a value is located by ANCHORING on a short marker substring taken VERBATIM from the catalog text that
immediately precedes the target group — never by a bare positional index, since the group order isn't a
stable contract and duplicate-shaped groups exist in the same string (e.g. Licorice Note's Pungent Stimulant
Salt repeats the same ratio group for its Empower and Curse clauses).

Only wired up for the specific per-tier values each trait module was actually confirmed to source from here
(see each module's own comments) — NOT every literal in every hero-trait module. Converting the rest is
future work if the owner wants it; this pass is scoped to the confirmed SS12->SS13 drift.
"""
from __future__ import annotations

import logging
import re

from persistence import season_manager

log = logging.getLogger(__name__)

_NUM_RE = re.compile(r'[+-]?\d+(?:\.\d+)?')


def advanced_trait_text(season: str, trait_id: str, pick_name: str) -> str | None:
    """The raw effect text for one advanced-pick node (`advanced_traits[i].name == pick_name`) of `trait_id`
    in `season`'s catalog, or None if the season/trait/pick isn't present (season not imported, or a pick
    renamed/removed — the audit confirmed every name literal these modules gate on still matches SS13
    byte-for-byte, so in practice this is only None for an unsupported/unimported season). `season` falsy
    (None/"") -> None immediately (e.g. a hero_traits module's `apply()` unit-tested with `build_input=None`
    — the module reads `getattr(build_input, "season", None)`, so this is the None/no-build-input case, not
    an error)."""
    if not season:
        return None
    t = season_manager.load_hero_traits_indexed(season).get(trait_id)
    if not t:
        return None
    for at in t.get("advanced_traits") or []:
        if at.get("name") == pick_name:
            effs = at.get("effects") or []
            return effs[0] if effs else None
    return None


def tier_values(text: str, marker: str = "", *, index: int = 0, allow_scalar: bool = False) -> list[float]:
    """The 5 per-tier numbers (level 1-5), UNSCALED (still the catalog's raw percent/unit, not yet /100),
    from the `index`-th `( a / b / c / d / e )` slash-group found at/after the first occurrence of `marker`
    in `text`. `marker=""` searches from the start of `text` (only safe when the target is unambiguously the
    first group of its kind in the string — documented at each call site).

    Handles the catalog's inconsistent sign formatting (some tiers carry a leading '+', some don't, some are
    negative or decimal, e.g. "( -0.67 / -0.8 / -1 / -1 / -1.2 )%") via a signed-number regex, not string
    splitting on '/' + manual sign stripping.

    If `allow_scalar` is set and no well-formed 5-value group is found at that position, falls back to a
    single scalar number immediately after `marker`, broadcasting it to all 5 tiers. This is for the ONE
    known real shape-change in scope: High Court Chariot's "Unbreakable Stand" cap was a flat scalar
    ("up to +100%") in SS12 and became a per-tier list ("up to ( +50/+60/+70/+80/+90 )%") in SS13 — this lets
    ONE code path resolve correctly under both catalog shapes without an `if season ==` branch.
    """
    pos = 0
    if marker:
        pos = text.find(marker)
        if pos < 0:
            raise ValueError(f"marker {marker!r} not found in: {text!r}")
        pos += len(marker)
    window = text[pos:]
    groups = list(re.finditer(r'\(([^)]*)\)', window))
    if index < len(groups):
        raw = groups[index].group(1)
        nums = [float(x) for x in _NUM_RE.findall(raw)]
        if len(nums) == 5:
            return nums
        if not allow_scalar:
            raise ValueError(
                f"expected 5 per-tier values (marker={marker!r}, index={index}), got {nums} from {raw!r}")
    if allow_scalar:
        m = _NUM_RE.search(window)
        if m:
            return [float(m.group())] * 5
    raise ValueError(f"no per-tier group/scalar found (marker={marker!r}, index={index}) in: {text!r}")


def pick_tier_values(season: str, trait_id: str, pick_name: str, marker: str = "", *, index: int = 0,
                      allow_scalar: bool = False, pct: bool = True, fallback: list[float]) -> list[float]:
    """The season-catalog-driven replacement for a hardcoded per-tier literal: looks up `pick_name`'s effect
    text for `trait_id` in `season`, extracts the tier group anchored at `marker`, and (by default, `pct`)
    divides by 100 to match the engine's fraction convention. Falls back to `fallback` (the historical
    literal, kept in the calling module purely as this last-known-good value — NOT as the primary source)
    ONLY when the season's catalog doesn't have this trait/pick at all; every currently-imported season does,
    so this should never fire in practice. A malformed/missing group once the pick IS found raises (a loud
    failure beats silently reporting a stale or wrong number).

    The fallback is SILENT only when `season` itself is falsy (not supplied — the expected/documented case
    for a unit test calling a hero_traits module directly with `build_input=None`, per
    `advanced_trait_text`'s own docstring). When a REAL season was supplied and the catalog still couldn't
    resolve `trait_id`/`pick_name` (season not imported, or — the real drift risk this whole module exists to
    catch — an advanced pick renamed/removed in a newer season), that is surfaced via `log.warning` rather
    than silently serving the stale literal with no signal (2026-07-16 architecture follow-up; see
    `.wolf/buglog.json`)."""
    text = advanced_trait_text(season, trait_id, pick_name)
    if text is None:
        if season:
            log.warning(
                "hero_traits._catalog.pick_tier_values: season %r has no catalog match for trait_id=%r "
                "pick_name=%r (marker=%r) — falling back to the last-known-good literal %r. This is expected "
                "only for an unimported season; if %r is a currently-imported season, the advanced pick may "
                "have been renamed/removed and this module's literal fallback is now stale.",
                season, trait_id, pick_name, marker, fallback, season)
        return list(fallback)
    vals = tier_values(text, marker, index=index, allow_scalar=allow_scalar)
    return [v / 100.0 for v in vals] if pct else vals
