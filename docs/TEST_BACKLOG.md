# Test backlog (backburner)

Tracks test coverage that's intentionally deferred. Run the suite from `backend/` with
`py -3.12 -m pytest tests/`. As of 2026-06-07 the backend suite is **271 tests, all green**.

## Recently added (done)
- `tests/test_passive_tree.py` — the preceding-columns unlock rule: `is_column_unlocked` /
  `points_before_column`, `allocate` (locks, full node, connection prereqs normal=3/legendary=1,
  multiple sources), `deallocate` (right-column stranding, connection prereqs), end-to-end.
- `tests/test_engine_offense.py` — `calculate_offense`: supported flag, crit-chance + crit-mult
  formulas, APS (gear/mh/inc/additional), dummy-target mitigation, hit-form summing, steep split.
- `tests/test_engine_derive.py` — `derive_stats` (attributes, life/mana/ES, armor/evasion shared
  `defense_inc`, additional pools, clamp-at-0, source injection).
- `tests/test_engine_compute.py` — pure helpers `_derive_views`, `_clamp_and_rederive`
  (clamping + `*_active` re-derivation), `derive_condition_maximums` / `_minimums`.

## Deferred — backend
- **`compute()` full fixed-point loop** (engine/compute.py): convergence over
  aggregate → derive → clamp → re-derive, the `computed_stat` condition injection, the stat_map
  / Character-section assembly, and the clamp_report. Needs a small season-tree + filter-data
  fixture (or a faked `aggregate`). The pure helpers it calls are already covered.
- **server.py endpoints** — `/api/validate-allocate` and `/api/engine/stats` integration tests.
  Both depend on loaded season data (`TREES`, `_build_tree`, skill data), so they need a fixture
  or a test season; the underlying logic (PassiveTree, offense, derive, compute helpers) is
  already unit-tested.
- **engine/aggregator.py** — already covered (`tests/test_engine_aggregator.py`); consider adding
  gear-contribution + memory/spirit-effect aggregation edge cases if those change.

## Deferred — frontend (vitest)
Setup: `vitest.config.ts` (node env); example in `src/renderer/src/__tests__/stats-computing.test.ts`.
- `utils/statsPayload.ts` — `buildEngineStatsPayload` shape + `buildGearPayload`
  (single vs dual-wield, weapon-implicit parsing, customization values).
- `utils/affixText.ts` — `tooltipAffixText` / `reconstructAffixText` range reconstruction.
- **Damage-delta classification** in `components/tooltip/useDamageDelta.ts` — extract the
  ≈0-delta classification into a pure function and test it. NOTE: this is changing — the
  "not yet supported" vs "no damage change" split currently uses a frontend category list and
  will be reworked when the engine models "consume stats" (life/mana/ES → damage). Test it after
  that lands.
