---
name: add-hero-trait
description: Add a Torchlight Infinite hero trait to the TLI Builder DPS engine as a bespoke module — apply/stash/status_lines, registry wiring, per-node disable gating, plus any new stats/conditions and a test. Use when modeling a new hero trait (every node/line), e.g. another Rosa/Erika/Gemma trait. Scaffold + checklist; approval-gated.
---

# add-hero-trait

Scaffolds a bespoke hero-trait module + the exact wiring checklist. **Approval-gated** — map every line and
propose the exact code + per-tier values, then wait for the owner's OK before writing. Read
`docs/ENGINE_AUTHORING.md` (Add a hero trait, gotchas) first. Reference: `backend/engine/hero_traits/
high_court_chariot.py` and `lightning_shadow.py` (+ their `README.md`).

## 1. Gather the trait data (verbatim)
- Find the trait in `data/seasons/SS12/_hero_traits.json` (by `trait_id` / variant name). Quote **every** line:
  base L1-5, the base-L5 extra (Artificial Moon equivalent), and each advanced pick (unlock 45/60/75,
  pick-one-from-two) with its per-tier numbers.
- For EACH line decide handling: a modelled contribution (which stat + how it scales), a user-set condition, or
  **informational** (spatial/regen/utility → `status_lines`). Per the never-silently-drop rule, nothing is omitted.
- List uncertainties to confirm with the owner (formulas, pooling increased-vs-additional, interactions,
  per-tier values, what's a buff vs an always-on). **Surface these — do not guess.**

## 2. New pools/inputs
- Any new stat the trait emits/reads that doesn't exist → run **`/add-stat`** (approval-gated).
- Any new scenario input (toggle / resource / per-X) → run **`/add-condition`** (default ON/OFF as appropriate;
  hero-trait-gated with `trait_id`).

## 3. Propose the module (do not write yet)
Fill `templates/module.py` (in this skill folder) with the real `TRAIT_ID`, tier constants, gated sections, and
`status_lines`. Key patterns it encodes:
- `apply()` emits `_contrib(stat_key, amount, text, source)` items; gate EVERY tier on `_enabled(slot_levels, idx)`
  (a disabled node is a negative slot level — right-click disable). Use `_tier()` (abs-safe) for the tier index.
- `stash()` captures converged scalars for next pass (block ratio, movement speed, …) when a line scales on an
  aggregated value; the loop converges over ~3 passes. Omit if unused.
- `status_lines()` returns one row per line (`working` | `informational`).
- Return `{"contributions":[...], "numbed_stacks": float|None}` (the override is only for ailment-uptime traits).
Show the owner the filled module + the per-line mapping table for sign-off.

## 4. Apply (after approval)
- [ ] Create `backend/engine/hero_traits/<trait_id>.py` from the approved module.
- [ ] Register in `backend/engine/hero_traits/__init__.py`: `from engine.hero_traits import <id> as _<alias>`
      and add `_<alias>` to `_MODULES`. (Server routes via `has_module` — no server edit needed.)
- [ ] Apply any approved `/add-stat` / `/add-condition` changes.
- [ ] Create `backend/tests/test_<trait_id>.py` from `templates/test.py` — assert each line's DELTA vs
      `trait_id=None`, pick scaling, node-disable (negative slot level drops that tier), and `trait_id=None` clean.

## 5. Verify
Run `/engine-verify` (the new trait test + full suite + consumable-universe + goldens). New always-read
stats/conditions → additive golden re-capture. Do not commit. Then offer in-app/RECOUNT validation to the owner.
