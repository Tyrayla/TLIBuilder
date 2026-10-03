# Architecture docs

How TLI Builder is built, one subsystem per page. Each page starts with the commit it was last
checked against; if the code has moved on since, trust the code and refresh the page with the `how`
skill.

| Page | Covers |
|---|---|
| [Stat engine pipeline](engine-pipeline.md) | Build payload to computed stats: `server.py`, `compute.py`, `mod_parser.py`, aggregation, derive, the fixed-point loop, offense and defense |
| [Skills, supports, hero traits, minions](skills-supports-traits.md) | `skill_resolver._REGISTRY`, support resolution, hero-trait modules, minion damage |
| [Renderer](renderer.md) | `App.tsx` build lifecycle, Zustand stores, background recalculation, the API boundary, screens |
| [Desktop and web](desktop-and-web.md) | Electron main/preload and the spawned backend; the web build with Pyodide and the data CDN; what differs |
| [Build codes and sharing](build-codes-and-sharing.md) | The frozen `tli1_` format, import/export, the share service, deep links |
| [Data and release](data-and-release.md) | `tli-data`, `fetch:data`, importers, the data CDN, CI and release workflows |
| [Testing and verification](testing-and-verification.md) | pytest and goldens, vitest, Playwright, dev slots and the app harness, the Verification Database |

Deeper references that stay separate: [ENGINE_AUTHORING.md](../ENGINE_AUTHORING.md),
[ADDITIONAL_DAMAGE_POOLING.md](../ADDITIONAL_DAMAGE_POOLING.md),
[ENGINE_FEEDBACK_LOOPS.md](../ENGINE_FEEDBACK_LOOPS.md),
[SUPPORT_MODELING_SPEC.md](../SUPPORT_MODELING_SPEC.md), [TEST_EXPANSION_PLAN.md](../TEST_EXPANSION_PLAN.md),
[TEST_BACKLOG.md](../TEST_BACKLOG.md).
