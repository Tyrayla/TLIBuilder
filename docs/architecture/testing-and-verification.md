# Testing and verification
> Last verified against: 5e6ddd4 (2026-09-25).

## Overview

TLIBuilder checks correctness at several levels. Backend pytest suites exercise engine and server behavior. Vitest checks renderer logic. Playwright drives the web build and the Electron desktop app. Golden fixtures preserve selected engine results when unrelated work must not change them.

The Verification Database answers a different question. It records the evidence and status of a modeled behavior, including work that is still unverified. A passing test says that the current code produces its expected result. It does not by itself confirm that the result matches observed behavior.

For planned coverage work, see [Test expansion plan](../TEST_EXPANSION_PLAN.md).

## Key Concepts

- **Backend tests.** `backend/tests/` contains pytest suites. Tests normally call public engine entry points such as `server.engine_stats()` through `EngineStatsRequest`, as shown by `tests.mock_build.make_request()` and the golden suites.
- **Golden fixture.** A committed JSON snapshot of a selected engine response. It catches an unexpected change in a stable response shape or value.
- **Consumable universe.** `engine.consumable_universe.consumable_universe()` produces the set of stat keys the engine can read. The renderer uses the result with `computedStats.consumable_universe` in `ModifierBadge.tsx` to classify modifier status.
- **Renderer logic test.** A Vitest test under `src/renderer/src/__tests__/`. `vitest.config.ts` runs these tests in the Node environment and excludes `e2e/`.
- **End-to-end test.** A Playwright test under `e2e/` that starts a built target and observes it through the browser or Electron.
- **Verification entry.** A JSON record under `data/verification/`. Its status and sources describe the evidence for a modeled behavior. Generated Markdown copies live in `docs/verification/`.

## How It Works

Backend pytest tests cover individual resolvers, engine stages, server behavior, and cross-module regressions in `backend/tests/`. The test suite is the first place to add a focused executable regression check. The `tdd` skill requires a bug reproduction to fail before its fix, and the `test-behavior` skill requires the test to call the code as a user does and assert an observable literal result.

Two suites use golden fixtures to protect broader engine behavior:

- `backend/tests/test_support_skill_goldens.py` derives its cases from `engine.skill_resolver._REGISTRY`. `test_support_skill_golden()` builds an app-shaped request, calls `server.engine_stats()`, and compares a canonical response slice with `backend/tests/fixtures/support_skill_golden/<skill>.json`.
- `backend/tests/test_skill_scope_nochange.py` runs fixed requests without scoped modifiers. `test_no_change_vs_golden()` compares their canonical results with `backend/tests/fixtures/scope_golden/<name>.json` so the scoped-modifier work stays an identity operation for those inputs.

Both tests capture a missing fixture once and skip that case. After a fixture exists, they fail on a changed result. Do not edit a golden by hand to silence that failure. Project rules require an additive-only golden diff: add new keys without changing existing values, unless the change intentionally changes behavior and the change states that reason. Re-capture generated results rather than hand-merging them. The `blast-radius` skill calls out golden capture as useful evidence for changes to shared engine plumbing.

The consumable-universe scan guards a UI-facing engine contract. `consumable_universe()` in `backend/engine/consumable_universe.py` runs synthetic offense, defense, derivation, and incoming-damage paths, then collects `BuildSource.consumed_stats`. `backend/tests/test_consumable_universe.py::test_all_live_engine_stat_reads_are_in_universe()` also scans live engine files for literal `source.total()`, `source.get()`, and `source.sum()` reads. It fails when an engine-read stat is absent from that universe.

Vitest covers renderer logic in `src/renderer/src/__tests__/`. `npm run test` invokes `vitest run`, while `vitest.config.ts` keeps these tests separate from Playwright specs. These tests are useful for state, payload, parsing, and helper behavior that does not require a running app.

Playwright covers the two shipped targets through `e2e/playwright.config.ts`. Its `web` project runs `e2e/web/**/*.spec.ts` against `dist-web`. Its `electron` project runs `e2e/electron/**/*.spec.ts` through Playwright's Electron launcher. `e2e/fixtures/web.ts` boots and waits for the browser-side compute worker. `e2e/fixtures/electron.ts` creates isolated temporary user-data and data directories, launches the desktop app on `E2E_PYTHON_PORT`, and waits for the preload API and backend response. The fixtures prevent tests from using saved builds or a live development backend.

For attended checks outside the test suites, the `app-harness` skill assigns each worktree a development slot through `scripts/dev-slot.mjs`. Its `slot:info`, `dev:slot`, and `web:slot` workflow gives Electron and the web server separate ports and scratch data. The skill then uses agent-browser to drive both targets and capture evidence. Use that path when a claim needs live UI proof or Electron and web parity evidence.

The Verification Database is not a test runner. `backend/server.py::_load_verification_entries()` reads `data/verification/*.json`, validates the entry fields, and turns unreadable or invalid files into visible failed entries. `get_verification_db()` exposes the entries and filter facets at `/api/verification-db`. `backend/tools/gen_verification_docs.py::main()` renders the same JSON source into `docs/verification/README.md` and one Markdown page per entry. Edit the JSON source, then regenerate the Markdown. Do not hand-edit generated verification pages.

## Where Things Live

| Path | Role |
| --- | --- |
| `backend/tests/` | Pytest suites for backend, engine, and server behavior. |
| `backend/tests/test_support_skill_goldens.py` | Registry-driven support-skill golden comparison. |
| `backend/tests/fixtures/support_skill_golden/` | Per-modeled-skill golden JSON. |
| `backend/tests/test_skill_scope_nochange.py` | Scope feature no-change golden comparison. |
| `backend/tests/fixtures/scope_golden/` | Scope no-change golden JSON. |
| `backend/tests/test_consumable_universe.py` | Synthetic-universe and live-read scan. |
| `src/renderer/src/__tests__/` and `vitest.config.ts` | Renderer logic tests and their runner configuration. |
| `e2e/playwright.config.ts` and `e2e/fixtures/` | Playwright projects plus web and Electron setup. |
| `scripts/dev-slot.mjs` | Slot allocator path documented by the app-harness workflow. |
| `data/verification/` | Source records for verification status and evidence. |
| `backend/tools/gen_verification_docs.py` | Generator for `docs/verification/`. |

## Gotchas

- A green golden test only says that the current output matches the fixture. It does not confirm the fixture against a recorded source.
- A Verification Database entry can be unverified or pending. That status is useful information, not a test failure.
- Do not let a new engine read bypass the consumable-universe scan. The result affects the modifier status shown by the renderer.
- Do not use a normal development server for concurrent live checks. Use the app-harness slot workflow so one worktree does not take another worktree's ports or saved data.
- Playwright serializes its projects with one worker in `e2e/playwright.config.ts`. The web fixture shares one booted page, and the Electron fixture owns one backend port.
