---
name: add-support
description: Model a support gem in the TLI Builder DPS engine. Most supports need NO code (the generic support_resolver parses their lines) — this skill checks that first, then scaffolds a bespoke skill_effects module only for special/conditional supports. Use when a support's damage isn't resolving, or it has a bespoke mechanic. Scaffold + checklist; approval-gated.
---

# add-support

Decides generic-vs-bespoke and scaffolds the bespoke path only when needed. **Approval-gated** — confirm the
approach + exact code with the owner before writing. Read `docs/ENGINE_AUTHORING.md` (Add a support gem). Live
reference: `backend/engine/skill_effects/berserking_blade.py` (+ `skill_effects/README.md`).

## 1. Generic-path check FIRST (most supports need no code)
- `backend/engine/support_resolver.py` already parses each attached support's progression line into
  `dmg_additional`-style contributions. Attach the support to a skill in a `mock_build.make_request(...,
  attached_supports=[...])` run and check whether its contribution shows up correctly.
- If it resolves correctly → **no code needed.** Stop (just confirm with a test/golden if desired).
- Go bespoke ONLY if: the generic parser mis-reads the line, or the support is conditional / form-scoped /
  preseeds an enemy state / has a non-damage mechanic (barrier, shotgun, chains).

## 2. Bespoke (only if step 1 says so) — propose, don't write yet
Create `backend/engine/skill_effects/<skill_id>.py` exposing the hooks it needs:
- `SKILL_ID = "<skill_id>"`.
- `GUARD_IDS = frozenset({...})` — support ids whose specific progression line must SKIP the generic parser.
- `CONTRIB_HOOKS = {"<support_id>": fn(sup, data) -> contribution|None}` — type-A support-path contribution
  (e.g. a per-life-lost `dmg_additional` with a `condition: {"key":..., "op":"per", "divisor":N, "cap":...}`).
- `apply_slot_effects(*, source, slot, ...) -> dict` — type-B slot-local emits (use `source.add_slotted(...)` so it
  folds only into that slot's offense); may return offense overrides (e.g. `remove_mod_tags`).
- `preseed(*, slot, condition_state, ...) -> None` — type-C seed an enemy/build condition before aggregation
  (MUST work per-slot, including off the main slot — test that).
Additional pools multiply per distinct source; form-scoped lines gate on the form's `proc_stat_key`. Show the
owner the exact module + which lines are guarded for sign-off.

## 3. Apply (after approval)
- [ ] Create `backend/engine/skill_effects/<skill_id>.py`.
- [ ] Register in `backend/engine/skill_effects/__init__.py`: import + add to `_MODULES`.
- [ ] New stat for a non-damage mechanic → run `/add-stat` (it may be emitted-but-NYI until its consumer exists —
      that's fine; it surfaces with an NYI badge, never silently dropped).
- [ ] Test (extend `test_support_skill_goldens.py` or a focused `test_<id>.py`): baseline vs with-support delta,
      condition gating, per-slot preseed firing off-slot.

## 4. Verify
Run `/engine-verify` (support golden + full suite). Do not commit.

## 5. Verification entry (anti-drift)
If the support has a bespoke mechanic (not the generic path), run `/add-verification` so it gets a Verification
Database entry (status `unverified` unless tested). Generic-path supports don't need one on their own.
