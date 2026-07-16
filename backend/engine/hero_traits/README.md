# engine/hero_traits

One module per hero trait that needs bespoke engine modeling beyond the generic effect resolver — its
computed stacks, stat-to-stat scaling with caps, uptime/ramp, and cross-quantity coupling. Mirrors
`engine/skill_effects/`: keep generic, trait-agnostic resolution in the mod parser / aggregator; put only
the trait-specific pieces here.

A hero trait is a single global entity (not per-slot), so its hooks fire once per aggregation pass.

Each module exposes:
- `TRAIT_ID: str` — the `trait_id` it handles (matches `_hero_traits.json`).
- `apply(*, build_input, condition_state, ls_state, uptime_mode, slot_levels, advanced_picks) -> dict`
  Runs at the TOP of each fixed-point pass. Returns
  `{"contributions": [ {stat_key, amount, text, source, [condition]} ], "numbed_stacks": float | None}`.
  The caller folds `contributions` into `build_input.trait_contributions` (so `aggregate` includes them,
  including in stages like the Numbed block) and, when `numbed_stacks` is not None, writes it to
  `condition_state` as an engine-owned (manual) value. Reads the previous pass's converged scalars from
  `ls_state`; first pass sees an empty `ls_state` and converges over a few passes (like auras).
- `stash(*, source, ls_state, inflict_aps) -> None`
  Runs at the BOTTOM of each pass. Captures the converged scalars the next pass's `apply` needs (e.g.
  movement-speed total, ailment-duration) plus the inflicting skill's APS (computed by the caller via
  `engine.offense.compute_skill_rates` for the slot that actually inflicts — never main-slot-by-index).
- `status_lines(*, slot_levels, advanced_picks, season) -> list[dict]`
  One `{text, source, status}` per trait line so every line is surfaced (working / informational-NYI),
  satisfying the never-silently-drop rule. `season` (2026-07-16) is the third universal, build-independent
  input — a global environment fact (which season's catalog to read a season-sourced display number from,
  e.g. a cap that drifted between seasons), not an interaction with another equipped entity. A module that
  doesn't need it ignores it via `**_`; one that formats a season-catalog value into its text (via
  `engine.hero_traits._catalog`) takes it as an explicit `season=None` keyword param and reads it directly —
  never a global `persistence.season_manager.get_active_season()` read inside the function body, which is
  invisible to `engine.coverage.trait_coverage`'s structural `build_gated_status_params` detector. All three
  universal params are excluded from that detector (`hero_traits._STATUS_BASE_PARAMS`); any OTHER named
  parameter a module's `status_lines` declares (`main_skill_tags`, `attached_supports`, ...) is a real
  build-specific dependency that downgrades `trait_coverage` to `'partial'` — see `coverage.py`.

The registry in `__init__.py` dispatches by `trait_id` (no per-trait hardcoding in callers).

## Uptime modes
Modules honor `uptime_mode` (`"max"` default | `"real"`). In `max` mode a mechanic returns its assume-max
value (e.g. Numbed = user/cap) — identical to legacy behavior. Only `real` mode runs the ramp math
(`engine.uptime`). A mechanic with no `real` implementation must keep its `max` value regardless of mode.
