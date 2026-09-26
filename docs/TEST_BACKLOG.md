# Test backlog

> Last verified against: 5e6ddd4 (2026-09-25).

What test coverage is deferred, and what to do next. The detailed plan with effort estimates is
[`TEST_EXPANSION_PLAN.md`](TEST_EXPANSION_PLAN.md); this page tracks where that plan stands.

## Current state (2026-09-25)

- Backend: about 4,100 collected pytest cases (1,878 test functions, many parametrized), plus the
  golden fixtures (`support_skill_golden`, `scope_golden`) and the consumable-universe scan.
- Renderer: 42 vitest files, 423 tests, all pure logic in a `node` environment.
- E2E: 4 Playwright specs (web and Electron smoke, a web journey, Electron perf).
- CI (`.github/workflows/ci.yml`) runs typecheck, vitest, and pytest.
- Live verification: the `app-harness` skill drives the Electron app and the web build through
  agent-browser on per-worktree dev slots (`scripts/dev-slot.mjs`). Its feature map lists which
  features have been driven on which platform.

### Weak-test audit

On 2026-09-25 every backend and renderer test was scanned for the five shapes the `test-behavior`
skill rejects (no assertion, existence-only, mock-only, self-referential, constant pin). Nine
backend candidates came up and none is a real problem:

- `test_ailment_inflict.py` (3): asserts sit on the same line after `;`, which the scanner missed.
- `test_guards.py` (4): "must not raise" checks, each paired with a sibling test that asserts the
  raise.
- `test_models_stat*.py` (2): structural checks across every row of a registry, which the skill
  keeps on purpose.

The renderer suite had no candidates. The scanner lives at
`.wolf/scratch/weak_tests.py` in the docs-architecture worktree; re-run it after large test
additions.

## Test Expansion Plan status

| Phase | Status |
|---|---|
| 0: un-gate season-independent backend tests | Done (2026-08-27, +757 tests) |
| 1: test infrastructure | Partly done: CI runs typecheck, vitest, pytest. **Not done:** jsdom / Testing Library for component tests, coverage reporting |
| 2: tier-1 renderer interaction tests | Not started (no test renders a component yet) |
| 3: user-journey E2E | Started: 4 specs; the app harness now proves journeys live first, then `testing` turns them into specs |
| 4: tier-2 screens and backfill | Not started |

## Next batches (each needs owner review before it lands)

1. **Phase 1 finish:** add `jsdom` and `@testing-library/react` as dev dependencies and a
   `renderer` vitest project with the jsdom environment. This is a dependency change, so it goes
   through the security lane.
2. **Phase 2, first slice:** interaction tests for the build lifecycle in `App.tsx` (open, save,
   the unsaved-changes modal, discard) and `ImportExportOverlay` round-trips, following the
   `test-behavior` skill.
3. **Phase 3, from the feature map:** turn the harness journey `main-skill-dps` (Chain Lightning
   Lv20 = 566 Full DPS on both targets) into Playwright specs for the web and Electron projects.

## Deferred (carried over)

- **`compute()` full fixed-point loop** (`backend/engine/compute.py`): convergence over
  aggregate → derive → clamp → re-derive, the `computed_stat` condition injection, and the
  clamp report, beyond what the goldens already pin.
- **server.py endpoint integration tests** for `/api/validate-allocate` and `/api/engine/stats`
  with a small test season.
- **Renderer utilities:** `utils/statsPayload.ts` payload shape and `buildGearPayload` (single vs
  dual wield); `utils/affixText.ts` range reconstruction.
- **Damage-delta classification** in `components/tooltip/useDamageDelta.ts`: extract the
  near-zero classification into a pure function and test it once the "consume stats" engine work
  settles.
