# TLI Builder — Test Expansion Plan

**Written 2026-07-23** against `dev` @ `471b397`, app version 0.6.1. Produced from a read-only audit;
no test or app code was changed. Complements `docs/TEST_BACKLOG.md` (which is stale — it still cites
"271 tests, all green" from 2026-06-07; the backend suite is now 3851 collected).

---

## START HERE

If you have **one afternoon**, do Phase 0. It is the highest impact-to-effort item in this document by a
wide margin: roughly **660 already-written tests come back online with no re-verification and no new test
authoring** — it is a mechanical refactor of *how they are gated*, not new work.

If you have **one week**, do Phase 0 → Phase 1 → the `App.tsx` and `ImportExportOverlay` slices of Phase 2.

Order of operations, and why:

| # | Phase | Effort | Why this order |
|---|---|---|---|
| 0 | Un-gate the season-independent backend tests | **S** (2–4h) | ~19.5% of the backend suite is dark *today*. Nothing else you build matters as much as turning existing guards back on. |
| 1 | Test infrastructure (jsdom, coverage, CI) | **S–M** (4–8h) | Phase 2 is *impossible* without jsdom — no test can currently dispatch a click. CI makes everything after it durable. |
| 2 | Tier-1 renderer interaction tests | **L** (3–5 days) | The critical user journey spine: ~200 handlers with zero coverage, including destructive paths. |
| 3 | Real user-journey E2E (Playwright) | **M–L** (2–4 days) | Answers "test exactly how users interact with it." Cheaper than it looks — see Phase 3. |
| 4 | Tier-2 screens + backfill | **L** (ongoing) | Diminishing returns; do it incrementally alongside feature work. |

**Do not start with Phase 2 or 3 even though they are the stated goal.** Phase 0 is nearly free and Phase 1
is a hard prerequisite. Starting at Phase 2 means hand-rolling DOM scaffolding you'd throw away.

---

## Current state (audit summary)

- **Backend (pytest) — strong on what runs, but a fifth is dark.** 127 test files, ~22,000 test LOC against
  ~19,500 engine LOC. `py -3.12 -m pytest -q` from `backend/` reports **3099 passed, 752 skipped** (~44s).
  3851 collected → **~19.5% never executes**. 746 of the 752 skips (99%) are SS12→SS13 season-flip guards.
- **Renderer (vitest) — 233 tests, zero interaction coverage.** 19 test files / 2,305 test LOC against
  **28,642 LOC** across 81 files (~8%). `vitest.config.ts` sets `environment: 'node'`; there is no `jsdom`,
  no `happy-dom`, no `@testing-library` installed. **No test renders a component or dispatches an event.**
  ~543 interactive handlers (423 in screens, 120 in components) are entirely unexercised.
- **Electron main/preload — 0%.** `src/main/index.ts` (473 LOC) spawns the Python backend (packaged
  `backend.exe` vs dev venv, ports 8765/8766), owns IPC, dirty-state, and `autoUpdater`. Untested.
- **No coverage tooling.** Neither `pytest-cov` nor `@vitest/coverage-v8` is installed. There are **no
  coverage metrics of any kind** in the repo. (Note: `engine/coverage.py`, `test_coverage.py`, and
  `utils/coverage.ts` are a *game-mechanic modeling* audit — full/partial/none — **not** code coverage.
  Do not confuse the two.)
- **No CI.** No `.github/workflows`. Nothing enforces either suite staying green.
- **E2E absent.** One unwired Playwright spike (`spike/browser/smoke.mjs`, own `node_modules`, not in root
  `package.json`, no npm script). It drives `window.__tliWebApi` — a *diagnostic hook* — so it is an
  API-level smoke that clicks nothing. It targets `dist-web`, last built 2026-07-16 and now stale.

### Two ground rules for everything below

1. **Never assert exact DPS values in renderer or E2E tests.** The SS12→SS13 churn that darkened 746 backend
   tests will do the same to any UI test that pins a number. Assert *structure and stability*: a number
   renders, is finite, survives save→reload, round-trips through the build code. Exact values belong in the
   backend golden fixtures, which are the right place for them.
2. **Golden fixtures change additively only** (new keys, zero changed values) unless a behavior change is
   intended and stated — per `CLAUDE.md`. Re-run the golden capture after any merge into `dev`.

---

## Phase 0 — Un-gate the season-independent backend tests

**Effort: S (2–4 hours). Impact: ~660 tests restored. No re-verification required.**

### The problem

Two files carry a **module-level** `pytestmark` skip guard keyed to the active season. `data/seasons/.active`
now reads `SS13`, so both files skip *entirely* — including tests that have nothing to do with SS12 values.

| File | Line | Collected | Skipped under SS13 |
|---|---|---|---|
| `backend/tests/test_coverage.py` | **16–19** | 729 | **716** |
| `backend/tests/test_dps_coverage_defect_fixes.py` | **~30** | 13 | **13** |

```python
# backend/tests/test_coverage.py:16-19  ← the blanket to unpick
pytestmark = pytest.mark.skipif(
    _SEASON != "SS12",
    reason="SS12-specific ground-truth; SS13 values pending re-verification post-flip (...)",
)
```

This matters because `test_coverage.py` is the **only guard on the coverage classification system**, and that
system is user-facing: it drives the `CoverageBadge` pills and the "Modeled only" filter that users rely on to
know whether the engine actually models a skill. With it dark, a `full` overclaim can ship silently — the badge
shows green, the user trusts a DPS number built on an unmodeled mechanic. `docs/BACKLOG.md:566-593` already
documents known overclaim vectors in `coverage.py`; the tests pinning those flips are exactly what's off.

`test_dps_coverage_defect_fixes.py` guards the two 2026-07-12 defect fixes in `support_mapper.py` and
`tooltip.py` — shared plumbing that `CLAUDE.md` names as the repo's highest-conflict files. Most-edited code
with its regression guard switched off is the worst combination in this audit.

### Measured class breakdown of `test_coverage.py`

```
646  TestSkillCoverageInvariants      ← INVARIANT  (89% of the file)
 18  TestOverclaimFlips               ← pinned
 10  TestSupportCoverage              ← pinned
  8  TestTraitCoverage                ← pinned
  8  TestSkillCoverage                ← pinned
  7  TestTraitCoverageInvariants      ← INVARIANT
  5  TestResolveLineKeysScoping       ← rule-level (judgement call)
  4  TestGluedClauseFullLineRule      ← rule-level (judgement call)
  4  TestEndpointWiring               ← structural
  3  TestLegendaryCoverage            ← pinned
  2  TestSupportCoverageInvariants    ← INVARIANT
  1  TestLegendaryCoverageInvariants  ← INVARIANT (whole-catalog sweep)
```

**Invariant + structural = ~660. Genuinely SS12-pinned = ~52.**

### How to tell an invariant test from a pinned-value test

| | Invariant / structural — **un-gate** | Pinned-value — **keep gated** |
|---|---|---|
| Asserts | A *relationship* that holds for any data: `full ⟺ detail == []`, "non-empty detail implies partial" | A *named item has a specific status or number*: "chain_lightning is `full`", "Icebound Beam base = 171-257" |
| Shape | Parametrized sweep over a catalog | Hardcoded `item_id` + expected literal |
| Survives a rebalance? | Yes — a rebalance can't make `full` mean "has detail" | No — that's exactly what a rebalance changes |
| Example | `TestSkillCoverageInvariants::test_full_iff_empty_detail` | `TestSkillCoverage::test_chain_lightning_full` |

Quick grep heuristic: a pinned test contains **both** a literal `item_id` string **and** an expected status
literal (`"full"`, `"partial"`, `"none"`) or a bare number. An invariant test contains neither — it compares
`status` against `detail`.

### Concrete steps

1. **Delete the module-level `pytestmark`** at `test_coverage.py:16-19`.
2. **Introduce a named per-class mark**, mirroring the pattern the repo already uses in `test_dot.py:30`,
   `test_elixirs.py:13`, `test_icebound_supports.py:8`, `test_channeled.py:25`, `test_licorice_note.py:21`
   — so this stays consistent with existing convention rather than inventing a new one:

   ```python
   _SS12_ONLY = pytest.mark.skipif(
       season_manager.get_active_season() != "SS12",
       reason="SS12-pinned ground truth; pending SS13 re-verification post-flip",
   )
   ```
3. **Apply `@_SS12_ONLY` to the pinned classes only**: `TestSkillCoverage`, `TestOverclaimFlips`,
   `TestSupportCoverage`, `TestTraitCoverage`, `TestLegendaryCoverage`. Leave the four `*Invariants` classes
   and `TestEndpointWiring` un-gated.
4. **Judgement call on the two rule-level classes** (`TestResolveLineKeysScoping` 5,
   `TestGluedClauseFullLineRule` 4): read each test. They assert parser/dedup *rules* but reach for live
   catalog items. If a test's assertion is about the rule, un-gate it; if it names an item and expects a
   status, gate it. Nine tests — a 15-minute read.
5. **Repoint the invariant catalog source to the active season.** `test_coverage.py:21-22` currently hardcodes
   `season_manager.load_skills("SS12")`. Change to `get_active_season()` so the invariant sweep guards the
   **live** catalog. This is what turns Phase 0 from "restore old tests" into "gain new protection" — the
   invariant then covers whatever season ships.
6. **Same treatment for `test_dps_coverage_defect_fixes.py`.** Its 13 tests are **mechanism-pinned, not
   value-pinned** — they assert `map_conditional_line(...) == []` or `stat_key == "dmg_additional" and
   amount > 0`, which are structural. Un-gate the module, then confirm the five named items still exist in the
   SS13 catalog: `thunder_core_lightning_lasso_noble`, `electric_punishment`, `grudge`,
   `modularization_compress`, `groundshaker_cripple_noble`. If an item was renamed, repoint the id — do not
   re-gate the test.
7. **Run it.** `cd backend && py -3.12 -m pytest -q tests/test_coverage.py tests/test_dps_coverage_defect_fixes.py`

> **Expect genuine failures on the first SS13 run — those are findings, not noise.** An invariant that fails
> against SS13 data means `coverage.py` really is overclaiming on some SS13 entity. Triage each one before
> assuming the split was wrong. This is the entire point of the exercise.

### Done when

- Full-suite skip count drops from **752 to under ~100** (~52 pinned in `test_coverage.py` + 14 rebalanced
  values across the six smaller files + 3 live-parity + scraper-parity).
- `test_coverage.py` runs green under `SS13` with only the `@_SS12_ONLY` classes skipped.
- Every remaining skip has a reason naming a *specific rebalanced value*, not a blanket season mismatch.
- Any invariant failure surfaced against SS13 is either fixed in `coverage.py` or filed in `docs/BACKLOG.md`.

**Lane:** engine agent (`backend/**`). Follow-up: add a `data/verification/` entry per `CLAUDE.md` if a real
coverage overclaim is found.

---

## Phase 1 — Test infrastructure

**Effort: S–M (4–8 hours). Unblocks all of Phase 2.**

### 1a. jsdom + Testing Library (the hard prerequisite)

Nothing in the renderer can be interaction-tested today. Install:

```
npm i -D jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom
```

**Do not flip `environment` to `'jsdom'` globally.** All 19 existing test files are pure-logic and run in
`node` in 1.66s; a blanket switch slows them and risks breaking the ones that touch `window` (e.g.
`api/client.ts:14` computes `IS_WEB` from `window.api`). Use per-file opt-in instead:

```ts
// vitest.config.ts
import { defineConfig } from 'vitest/config'
export default defineConfig({
  test: {
    environment: 'node',                                   // unchanged default
    environmentMatchGlobs: [['**/*.dom.test.{ts,tsx}', 'jsdom']],
    setupFiles: ['./src/renderer/src/__tests__/setup.dom.ts'],
    coverage: { provider: 'v8', reporter: ['text', 'html'], reportsDirectory: './coverage' },
  },
})
```

New interaction tests are named `*.dom.test.tsx`. Existing tests are untouched. Note `vite.config` needs the
React plugin available to the test transform for `.tsx` — reuse the `@vitejs/plugin-react` already in
`devDependencies`.

### 1b. Coverage tooling

```
npm i -D @vitest/coverage-v8
```
Add to `backend/requirements-dev.txt` (currently just `pytest>=7.0`):
```
pytest-cov>=5.0
```
Scripts in `package.json`:
```json
"test:coverage": "vitest run --coverage",
"test:dom": "vitest run --coverage src/renderer/src/__tests__"
```
Backend: `cd backend && py -3.12 -m pytest --cov=engine --cov=persistence --cov=. --cov-report=term-missing`

**Set no threshold initially.** Establish the real baseline first, then ratchet. A threshold set blind will
either block every commit or be meaninglessly low.

### 1c. Minimal CI

There is no `.github/workflows` at all. Given the multi-worktree/multi-lead protocol in
`.claude/rules/multi-lead-claims.md` — where branches merge locally into `dev` with goldens as the
semantic-conflict tripwire — CI is disproportionately valuable here: it's the only thing that catches a
clean-textual-merge-but-wrong-behavior result before it lands.

`.github/workflows/ci.yml`, on push/PR to `dev` and `main`, three jobs:
- `npm ci && npm run typecheck`
- `npm run test` (vitest)
- `pip install -r backend/requirements.txt -r backend/requirements-dev.txt && cd backend && pytest -q`

Add a **skip-count guard** so the Phase 0 win can't silently regress:
`pytest -q 2>&1 | tail -1` and fail if skipped exceeds an agreed ceiling. This is the single cheapest
protection against another blanket season gate going in unnoticed.

### Done when

- `npm run test:coverage` emits an HTML + text report; backend `--cov` emits `term-missing`.
- A trivial `*.dom.test.tsx` renders a component and asserts on it (proves the harness, then delete or keep).
- CI is green on `dev` and runs on every push.
- Baseline coverage numbers are recorded here or in `docs/TEST_BACKLOG.md` for later comparison.

**Lane:** platform agent (config/CI) + testing agent (vitest setup).

---

## Phase 2 — Tier-1 renderer interaction tests

**Effort: L (3–5 days). ~200 handlers on the critical journey spine.**

What exists today covers *extracted pure helpers* (`sortBuilds`/`sortFolders` in `buildSelectHelpers.test.ts`,
`statsPayload`, `conditions`, `traitTree`, `talentPoints`, `passiveTreeDiff`, `resolveImportInput`) — the
calculations *behind* the handlers, never the handlers. Phase 2 closes that.

Two standing priorities cut across everything below:

- **Drag & drop — 18 handlers, zero coverage**, in `BuildSelectScreen` (10), `GearScreen` (5),
  `SlotSidebar` (3). Highest-complexity interaction class in the app and the hardest to verify by hand.
  `@testing-library/user-event` does not simulate HTML5 DnD well — either fire `dragStart`/`dragOver`/`drop`
  manually with a stubbed `dataTransfer`, or (better) test the extracted state transition and leave the
  drag *gesture* to Phase 3 E2E.
- **Destructive actions have no confirmation tests** — `handleDeleteSelected`, `handleDeleteFolderConfirm`,
  `handleRemoveTree`, `clearSlotFates`, `handleClearSkills`. These are where a regression costs a user their
  data. Test both the confirm path *and* the cancel path.

### 2a. `App.tsx` — build lifecycle spine (~15 handlers) — **do this first**

`src/renderer/src/App.tsx`. Every user touches this on every session.

- `saveBuild`, `saveAsBuild`, `handleSaveModalConfirm`
- **Unsaved-changes guard**: `handleUnsavedSave` / `handleUnsavedDiscard` — silent data loss if broken
- Tree select/remove + cascade confirm: `handleSelectTree`, `handleRemoveTree`, `handleCascadeYes/No`,
  `doRemoveTree`, `handlePreviewTree`, `handleReselect`
- `handleSidebarNav`, `handleSlotClick`, `handleSlotReorder`, `handleShiftUp`

### 2b. `ImportExportOverlay` (20 handlers) — **highest value per test**

`src/renderer/src/components/ImportExportOverlay.tsx` + `utils/resolveImportInput.ts` + `api/share.ts`.
A build-code **round-trip** (export → reimport → assert identical state) crosses the frozen `tli1_` codec, the
share resolver, and the store in a single test. `resolveImportInput` already has 6 unit tests; this adds the
UI path around them. Mock `fetch` to `SHARE_BASE` — never hit the live service from a test.

### 2c. `BuildSelectScreen` (56 handlers + 10 DnD)

`src/renderer/src/screens/BuildSelectScreen.tsx`. **Already backlog-flagged** at `docs/BACKLOG.md:537`
("Deferred test coverage — BuildSelectScreen folder feature", raised by the 2026-07-15 review council).
That entry names the exact targets — treat it as the spec:
`reorderBuilds`, `reorderFolders`, `nestFolder`, `assignBuildToFolder`, `handleDeleteFolderConfirm`
(reparenting/pruning), `handleDeleteSelected` (partial-failure reconciliation), `handleMoveSelectedTo`,
`persistManifest` (PUT-failure recovery), and `App.tsx`'s `assignNewBuildToFolder`.
Close the backlog entry when done.

### 2d. `GearScreen` (59 handlers + 5 DnD)

`src/renderer/src/screens/GearScreen.tsx` — 3,484 LOC, the densest data entry in the app.
`handleTierChange`, `handleSliderChange`, `handleCraftValueEdit`, `handleLegendaryValueEdit`,
`handleCorrosionChange`/`handleCorrosionTypeChange`/`handleToggleCorroded`, `handleDesecrationToggle`,
`handleRandomAffixChange`, `handleSlotAssign`, `handleAddToBuild`/`handleRemoveBuildItem`,
`handleReorderBuildItem`, `handleSelectLegendary`/`handleClearLegendary`.
Assert *payload shape* into `buildGearPayload` (already unit-tested) rather than DPS output.

### 2e. `SkillsScreen` (50 handlers)

`src/renderer/src/screens/SkillsScreen.tsx`. The inputs every DPS number depends on:
`selectSkillSlot`/`selectSupportSlot`, `removeSkill`/`removeSupport`, `toggleSkillEnabled`/
`toggleSupportEnabled`, `toggleCountInDps`, `setEquippedLevel`, `setTier`, `setGroupChoice`.
Pair with the existing `supportGating.test.ts` (11 tests) — that covers the rules; this covers reaching them.

### Explicitly **out of scope**

**`DevToolsScreen` — 91 handlers, the single largest block, and the least worth testing.** Importers, mapping
CRUD, overrides, catalog rebuild: an internal admin surface, not a user journey. Named here so raw handler
counts don't misdirect effort — they point here first, and they shouldn't.

**`PlayerStatsScreen`** inverts the pattern: 3,278 LOC but only 8 handlers. It's the payoff screen; its risk is
in *derivation and display*, not interaction. Backend tests plus a render-smoke cover it better than click tests.

### Done when

- Each of 2a–2e has: happy path, destructive-confirm **and** cancel, and one failure-recovery case
  (e.g. `persistManifest` PUT failure).
- `docs/BACKLOG.md:537` is closed.
- Renderer line coverage measurably up from the Phase 1 baseline (set the ratchet here).

**Lane:** testing agent writes these — per standing preference, implementers don't write their own tests.

---

## Phase 3 — Real user-journey E2E

**Effort: M–L (2–4 days). This is the "test exactly how users interact with it" phase.**

> **Status 2026-08-04: PARTIAL — harness landed in `e2e/`, journeys 2 & 4 + both smokes green.**
> Remaining work (journeys 1/3/5, testid pass, hermetic CDN, CI job) is tracked in `docs/BACKLOG.md` §10.

### Why this is cheaper than it looks

Two facts from the audit make E2E unusually accessible here:

1. **Playwright drives Electron natively** (`_electron.launch()`), so the *actual shipping product* is
   testable — real clicks, real IPC, real preload, real spawned Python backend. That closes the 0%
   main/preload gap as a side effect.
2. **The web build is not a cut-down port.** There are exactly **two** `IS_WEB` gates in the entire renderer
   (`SettingsOverlay.tsx:51`, `BuildSelectScreen.tsx:689`). It is the same React app running the same Python
   engine via Pyodide — so a browser is a legitimate target for nearly every journey, with *real* engine
   numbers rather than mocks.

### Two targets, different jobs

| Target | Drives | Job |
|---|---|---|
| **Electron** (`_electron.launch()`) | The real desktop product | Primary. Covers IPC, preload, backend spawn. Fast — native Python, no Pyodide boot. |
| **Web** (`dist-web`) | The Cloudflare Pages deploy | Hermetic + CI-friendly. Currently has **no** automated check at all. |

### Steps

1. **Promote the spike.** Move `spike/browser/` → `e2e/`, fold `playwright` into the root `devDependencies`
   (it currently lives in a private `node_modules` under `spike/`), add `"test:e2e"` to `package.json`.
2. **Stop driving the diagnostic hook.** The existing smoke calls `window.__tliWebApi` — keep that as a
   *readiness probe* (`__tliComputeReady`) but drive assertions through real UI interaction. Keep the hook;
   it's genuinely useful for waiting on worker boot.
3. **Add stable test selectors.** Prefer `getByRole`/`getByText`; add `data-testid` only where the DOM is
   ambiguous. Avoid CSS-class selectors — the recent theme-token sweep (`33c3520`, `471b397`) shows styling
   churns.
4. **Boot Pyodide once per run**, not per test — reuse one page across journeys. The current smoke allows up
   to 180s for worker readiness; per-test boot would make the suite unusable.
5. **Rebuild `dist-web` as a CI step** (`npm run build:web`) — the checked-in copy is from 2026-07-16 and
   already stale against `dev`.

### First five journeys

1. **New build end-to-end** — create → pick hero/tree → allocate a few nodes → equip a weapon → slot a skill
   + support → land on Player Stats and assert a **finite, non-zero** DPS number renders.
2. **Build-code round trip** *(highest value)* — build → export `tli1_` → clear → reimport → assert the
   restored build matches. Crosses the frozen codec, the share resolver, and the store in one journey.
3. **Persistence across restart** — save → close/reopen (Electron) or reload (web) → build is intact. The
   existing smoke already proves the web/IDBFS half; extend to Electron.
4. **Unsaved-changes guard** — modify → attempt navigation → confirm the prompt appears, and that *discard*
   discards and *save* saves. Pure data-loss protection.
5. **Folder CRUD + drag-and-drop** — create folder, drag a build in, nest a folder, delete a folder with
   children, confirm reparenting. The one place a real browser beats jsdom outright.

**Assert structure, never exact DPS** (see ground rule 1) — otherwise the next season flip darkens the E2E
suite the same way it darkened the backend.

### Done when

- `npm run test:e2e` runs all five journeys against Electron locally.
- The web target runs in CI on every push, gating the Pages deploy.
- A deliberately broken handler fails a journey (verify the harness actually catches regressions).

**Lane:** testing agent + platform agent (Electron launch harness).

---

## Phase 4 — Tier-2 screens + backfill

**Effort: L, ongoing. Fold into feature work rather than running as a project.**

- **Tier-2 interaction coverage**: `TreeViewerScreen` (23 — node allocate/deallocate, `handleCoreTalentSelect`,
  `handleReset`, `clearDownstreamOfAnchor`), `HeroTraitScreen` (38) + `HeroTraitTree` (2), `LoadoutOverlay`
  (29), `BuildSidebar` (21), `PrismOverlay` (19), `SlateScreen` (27), `PactSpiritScreen` (24),
  `SettingsOverlay` (13).
- **Modal keyboard handling** — a thin surface (9 `Enter`, 1 `Escape`, 2 global `keydown`, 4 `ctrlKey`/
  3 `metaKey`), so scope it tight: confirm/dismiss on modals is the real gap. There is no broad shortcut
  system to cover.
- **`api/client.ts` contract tests** — 2,788 LOC, currently imported by 14 tests for types/helpers only.
  Nothing verifies request shaping or response handling. Consider `msw` for a mock server layer.
- **Backfill `docs/TEST_BACKLOG.md`'s deferred items** — `compute()` fixed-point loop, `server.py`
  `/api/validate-allocate` + `/api/engine/stats` integration tests, `utils/affixText.ts`. Refresh that file's
  stale "271 tests" header while you're in it.
- **Re-verify and un-gate the remaining SS12-pinned values** as SS13 measurements land — the ~52 pinned tests
  from Phase 0 plus the 14 rebalanced values across `test_dot`, `test_elixirs`, `test_icebound_supports`,
  `test_channeled`, `test_licorice_note`, and the 4 `_SS12_PINNED_GOLDENS` in `test_support_skill_goldens.py`.
  Use `/add-verification` per `CLAUDE.md`.
- **`test_live_parity.py`** (3 tests) currently skips unless a dev backend is live on 8765–8774. Consider a CI
  job that spawns the backend so the one real integration test actually runs.

### Done when

- No screen with >20 handlers lacks at least a render-smoke plus its destructive paths.
- Suite-wide skip count is understood line-by-line — every skip names a specific pending measurement.

---

## Quick reference — commands

```bash
# from repo root
npx tsc --noEmit -p tsconfig.web.json     # typecheck (currently clean)
npm run test                              # vitest — 233 tests, ~1.7s
npm run test:coverage                     # after Phase 1

# from backend/
py -3.12 -m pytest -q                     # 3099 passed, 752 skipped, ~44s
py -3.12 -m pytest -q tests/test_coverage.py          # Phase 0 target
py -3.12 -m pytest --cov=engine --cov-report=term-missing   # after Phase 1
```

Per `CLAUDE.md`: typecheck and the backend suite should both be green before proposing a commit, and the
read-only review council runs over the diff first.
