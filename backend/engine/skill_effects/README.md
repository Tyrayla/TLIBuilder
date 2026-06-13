# engine/skill_effects

One module per skill that needs **bespoke** modeling beyond the generic resolvers — its canvas
(magnificent/noble) support mechanics, intrinsic self-buffs, and skill-specific finalize logic.

## When a skill goes here

Add `engine/skill_effects/<skill_id>.py` when a skill has effects the generic path can't express
correctly — e.g. a support whose specific line the range/condition parser misreads, an intrinsic buff
that scales a stat per stack, or a share/conversion local to that skill.

Keep skill-**agnostic** resolution where it lives today:
- generic support contributions / behavior → `engine/support_resolver.py`
- contribution application + condition gating → `engine/aggregator.py`
- the damage pipeline → `engine/offense.py`

Only the skill-**specific** pieces belong here.

## Conventions (see `berserking_blade.py` as the reference)

- Export the skill id as `SKILL_ID` and a `BB_SUPPORT_IDS`-style frozenset of the support item ids.
- Emit slot-local contributions via `BuildSource.add_slotted(stat, amount, slot, scope, entry)` so they
  fold only into that slot's offense (no cross-contamination between setups).
- A canvas support's specific line that the generic parser misreads must be **guarded out** of
  `support_resolver`'s generic path (see the `BB_SUPPORT_IDS` guard) and handled here instead.
- Per-slot config (rolls, thresholds) is extracted server-side (`extract_config`), threaded onto
  `BuildInput`, and consumed in `compute.py`'s per-slot finalize / offense driver.
- Lazy-import this module from `support_resolver` to avoid the circular import (this module imports
  helpers from `support_resolver`).

## Registry (`__init__.py`)

The engine dispatches generically via the registry — no per-skill hardcoding. Each module may expose:
`GUARD_IDS` (support ids whose specific line skips the generic parser), `CONTRIB_HOOKS` (type-A
support-path contributions), `apply_slot_effects(...)` (type-B per-slot emissions, keyed by `SKILL_ID`),
and `preseed(...)` (type-C loop-time condition seeding). `support_resolver` consults
`GENERIC_GUARD_IDS` + `support_contribution`; `compute` calls `apply_slot_effects` + `preseed`.

## Modules

| Module | Skill | Effects modeled |
|--------|-------|-----------------|
| `berserking_blade.py` | Berserking Blade | Desperation / Sweep / Decimate / Rampage + intrinsic Skill-Area buff |
| `focused_slash.py` | Focused Slash | Duel (generic) / Tranquility / Behead / Fervor |
| `moon_strike.py` | Moon Strike | Rainbow / Lunar Ring (tracked, DPS-neutral); Lunar Eclipse + Wax and Wane **deferred** (mana-sealing / Spell Burst) |
