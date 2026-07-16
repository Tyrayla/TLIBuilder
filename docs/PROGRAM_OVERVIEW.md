# TLI Builder — Program Overview (handoff for a fresh assistant)

> A current, self-contained map of the whole program. Pair this with the `.wolf/` files (`anatomy.md` =
> file index, `memory.md` = session log, `buglog.json` = known bugs, `cerebrum.md` = learned conventions) and
> the auto-memory `MEMORY.md`. Last refreshed after the minion DPS engine landed.

## What it is

**TLI Builder** is a desktop **build planner for *Torchlight: Infinite*** (a "TLI-only" project — never reference
other game titles or "Path of Building"/"PoB" in code/comments/docs; say "source breakdown"). It lets a user
assemble a character (gear, talent trees, hero traits, skills + supports, spirits, blessings, etc.) and see a
fully-broken-down **DPS and defense calculation**, share builds via code/link, and manage multiple builds/loadouts.
The owner is referred to as **Tyra**.

## Tech stack & process model

- **Electron + electron-vite** desktop app (also a **web build** at tlibuilder.com via a Pyodide worker).
- **React + TypeScript** renderer in `src/renderer/src/`.
- **Python FastAPI backend** spawned as a **child process** (port **8765**). ALL game data, stat computation,
  and build-code encode/decode live here (`backend/`).
- **Zustand** for shared renderer state (`src/renderer/src/store/`).
- **Communication:** the renderer calls `api.*` in `src/renderer/src/api/client.ts`, which POST/GET the local
  Python server. In the packaged app these go over an **IPC proxy** (`ipcMain.handle('api-request', …)`) so no
  `webSecurity:false` is needed; browser/web mode falls back to direct HTTP fetch.
- A separate **share service** (`https://api.tlibuilder.com`, private repo) is plain `fetch` from the renderer —
  never IPC, never the local backend.

## Data pipeline (how game data gets in)

1. An external **crawler/scraper** (`C:\Users\tyray\Documents\tlidb-scraper`, separate) writes **one JSON file
   per entity** under `output/<SEASON>/<type>/…` (active_skill, passive_skill, support/noble/magnificent,
   activation_medium_skill, modularization_skill, legendary_gear, pactspirit, hero_trait, talent_tree, …).
2. **Importers** in `backend/tools/` turn that into the season catalogs under `data/seasons/<SEASON>/`:
   - `rebuild_skills.py` + `skill_importer.py` → `_skills.json` (the skill catalog; `{item_id: record}`).
   - Other loaders in `backend/persistence/season_manager.py` read `_hero_traits.json`, `_belt_blends.json`,
     legendary gear, spirits, destiny, prisms, hero memories, `_minion_base_stats.json`, etc.
3. The active season is a `.active` file; `season_manager.get_active_season()` drives all lookups. **Data
   changes require a backend restart** (no hot-reload); frontend hot-reloads.
- **Rule:** always commit `data/seasons/` together with importer changes so the branch stays in sync.

### Skill record shape (post-import)
Each `_skills.json` record carries `item_id`, `name`, `skill_type` (`active_skill` / `passive_skill` /
`support_skill` / `noble_support_skill` / `magnificent_support_skill` / `activation_medium_skill` /
`modularization_skill`), `skill_tags`, `simple_description`/`detailed_description` (Lv1/Lv20 anchors),
`progression` (per-level values), `effectiveness_of_added_damage`, `cast_speed`, `cooldown`, `sealed_mana`,
`max_level`, `glossary`, and (for minion owners) a nested **`minion_skills`** array — see the minion engine below.

## The DPS/defense engine (`backend/engine/`) — the heart of the app

- **`aggregator.py` `aggregate()`** builds a `BuildSource` (a flat list of `(stat, amount)` + a `source_log`
  for badges) from every build input. Verbs on `BuildSource` (in `engine/models.py`): `add`/`add_with_source`
  (global), `add_scoped(stat, amt, tag, entry)` (applies only to skills whose mod-tags include the tag),
  `add_slotted(…, slot, …)` (slot-local). `materialize_for_skill(mod_tags, slot)` folds the matching
  scoped/slot overlays into an effective source per skill. Buff-effect tables (Dual Wield, Hasten, Attack
  Aggression, Aim/Euphoria, Fervor, blessings) are emitted here.
- **`compute.py` `compute()`** — the orchestrator. A **fixed-point loop** (`_MAX_ITERS = 10`) re-aggregates the
  source each pass, resolves supports/conditions/hero-traits/auras/empower/elixir/curses, derives stats, runs
  reservation + consumption + recovery, then computes **offense per active slot** and returns a `StatResult`.
  Hero traits dispatch here via `hero_traits.apply/stash` at the top/bottom of each pass.
- **`offense.py` `calculate_offense()`** — the per-skill DPS pipeline: base damage (spell per-level / attack
  from weapon) → flat added → **increased pool** (sums into `1+Σ`) → **additional pool** (each affix a distinct
  `×(1+x)` factor) → crit (rating→chance, `1.5 + Σ crit_damage` multiplier) → double/triple/quad → conversion
  cascade → enemy mitigation (`_target_mitigation`) × vulnerability (`_enemy_vuln_mult`) → rate → per-form. The
  result `OffenseResult` is what the UI reads (`total_dps`, `total_dps_vs_target`, `hit_forms`, crit, etc.).
- **`skill_resolver.py` `resolve_skill()`** returns a `ResolvedSkill` (tags, hit forms by level, base damage,
  cast time, main stat). Unregistered skills resolve as data-driven **stubs** (`supported=False` → 0 damage).
  Bespoke skills register a handler; bespoke mechanics live in **`engine/skill_effects/<skill>.py>`**.
- **Subsystems** (each its own module, run inside the compute loop): auras/`aura_resolver`,
  empower/`empower_resolver`, elixirs/`elixir_resolver`, curses/`curse_resolver`, reservation (mana/life
  sealing), consumption (`consumption.py`, life/mana drained per second), recovery/sustain (`recovery.py`).
  Effect scalars combine as **`base × (1 + Σincreased) × (1 + Σadditional)`** (two separate multiplicative
  factors — see `utility.py` Aura/Empower/Elixir, `curse_resolver` groups `_additional` per source).
- **Hero traits** (`engine/hero_traits/`) — one bespoke module per trait, registered in `__init__.py`'s
  `_MODULES` tuple, hooks `apply`/`stash`/`status_lines`/`virtual_supports`, per-node disable gating (a
  disabled node is stored as a negative slot level), fixed-point coupling via an `ls_state` dict. Templates:
  `unsullied_blade.py`, `high_court_chariot.py` (Rosa).
- **Stats & metadata:** `backend/models/stat.py` (the `Stat` enum) + `backend/models/stat_meta.py` (`STAT_META`
  — display name, pool type via `pipeline_stage`, `tags`, `affects`). Offense builds its pools by filtering
  `STAT_META`. Adding a stat = enum entry + StatMeta (+ consumable-universe whitelist if always-read).
- **Conditions** (`data/conditions.json`) — user toggles/numerics (booleans → active set, numerics → values),
  server `_COND_PATTERNS` map gear text → condition, plus auto-derived conditions in compute.
- **Badges / "never silently drop":** the cardinal rule — every modifier is either applied or visibly surfaced
  with a **Consumed / Inactive / Unconsumed / NYI** badge. `consumable_universe.py` defines what the engine can
  ever read; `consumed_stats` (recorded while `source._recording` is on) is what it read for THIS build. A
  badge must be computed by the SAME resolver the engine uses to apply it (avoid badge↔engine drift).

## Minion DPS engine (added recently — Spirit Magus foundation)

Minions used to contribute **zero** DPS. Now:
- **Data:** the crawler nests each minion owner's abilities under a **`minion_skills[]`** array (importer
  preserves it, tags each child with `owner_id`, and parses each ability's **"% of Base Damage" coefficient**).
  Three archetypes share the shape: **Spirit Magus** (passive owner, e.g. `summon_fire_magus` → Blazing Dance
  Base / Blazing Spin Empower / Blazing Incineration Enhanced / Molten Rising Ultimate), **Synthetic Troop**
  (active owner, e.g. `summon_grim_phantom`), **Modularization** (`module_*`, e.g. Trog Mage).
- **Shared base stats:** `data/seasons/SS12/_minion_base_stats.json` (hand-entered from in-game — not scraped):
  `constants` (60% all-res, 150% crit damage, 500 flat crit rating, shared by ALL minions), a shared
  `base_damage_by_level` (all minions), and `life_by_group` with two groups — **`magus`** (= 3× synthetic
  troop life) and **`synthetic_troop`**. Loaded via `season_manager.load_minion_base_stats`.
- **Engine:** `engine/minion_offense.py` `calculate_minion_offense()` — a lean parallel of `calculate_offense`
  that reads **only minion-scoped pools** (`minion_*`, filtered by `"minion" in tags`) so player pools never
  leak; base hit = `shared_base_damage(level) × coefficient`; own crit base (500/150); count from the owner's
  "up to N" + `max_spirit_magi_flat`/`extra_max_minions_flat`; reuses the shared enemy mitigation/vuln helpers.
- **Wiring:** `compute.py` runs a **minion pass** after the player offense pass, producing
  `minion_offense: {owner_id: [MinionOffenseResult]}` on `StatResult` (threaded through `server.py`). The
  Calcs screen renders a **Minion DPS panel** (mirrors the player hit-damage panel, with a dropdown to pick the
  ability), and the sidebar **Full DPS** folds in each owner's Base-ability DPS.
- **NYI (flagged, not silent):** phys→element conversion (owner line), Persistent/domain per-second damage,
  multi-hit/shotgun forms, ailment/DoT. **In progress next:** magus **Origin buffs** to the summoner (Fire =
  +crit rating, Thunder = +AS/CS/dmg; scaled by `spirit_magi_origin_effect_inc/_additional`), then **Iris hero
  traits** (Growing Breeze/Nourishment, Vigilant Breeze/Growth/Breeze). See the minion-DPS plan doc.

## Frontend (renderer)

- **`App.tsx`** — root; owns navigation + (legacy) `session` state + `openBuild`/`getBuildPayload`. A **Zustand
  migration** (Phase 2 in progress) is moving screens off prop-drilling onto `buildStore`.
- **Store:** `store/buildStore.ts` (gear/skills/stats inputs + `computedStats` result), `store/referenceStore.ts`
  (prefetched season-global catalogs), `store/useBuildCalculation.ts` (debounced background recalc → calls
  `api.engineStats` → `setComputedStats`). Any component reads `computedStats.*` (e.g. `offense`, `slot_offense`,
  `minion_offense`).
- **Screens** (`screens/`): `PlayerStatsScreen.tsx` (the **"Calcs"** display screen — offense/defense/minion
  panels + source-breakdown popovers), `BuildOverviewScreen` (**"Config"** — conditions/custom mods), gear,
  build select, hero trait, notes, verification database, etc.
- **Key components:** `BuildSidebar.tsx` (Full DPS box = Σ slot_offense + minion contributors), the
  import/export overlay (share-via-link).
- **Formatting:** `utils/num.ts` `dec()` = up-to-2-decimals trimmed; `PlayerStatsScreen`'s `fmtNum` floors +
  adds magnitude suffix. Show up to 2 decimals, never force to 1.

## Build codes & sharing

- Format: `tli1_<base64url(zlib_level9(compact_json))>`. `CODE_PREFIX="tli1"`, `SCHEMA_VERSION=1` in
  `backend/build_code.py` — **the codec, schema version, and compression are frozen**; add new build fields to
  the `Build` interface + `KNOWN_BUILD_KEYS`, don't change the codec.
- Share-via-link resolves a URL or raw `tli1_` code (`utils/resolveImportInput.ts`) against the share service.

## Verification & testing

- **Python tests:** `py -3.12 -m pytest` from `backend/` (2600+ tests). The `engine-verify` skill runs the full
  gate: typecheck, pytest, consumable-universe scan, golden re-capture (additive-only diff).
- **Web typecheck:** `npx tsc --noEmit -p tsconfig.web.json` from repo root (currently **clean/0 errors** — the
  old CLAUDE.md note about pre-existing GearScreen/App errors is stale).
- **In-app verification is the real check:** run the **client** (`npm run dev`; in a Bash shell `unset
  ELECTRON_RUN_AS_NODE` first) — don't hand-start `server.py`. Validate DPS against the in-game **Recount** on a
  90s+ training-dummy run, not the tooltip. The dummy = 30% elemental/erosion res + 50% armor (60% to
  non-phys) → ×0.49 non-phys multiplier.
- **Verification Knowledge Base:** `data/verification/*.json` (one entry per mechanic, defaults status
  "unverified") + an in-app Verification Database screen; add an entry when a mechanic ships.
- **Authoring skills:** `/add-skill`, `/add-support`, `/add-stat`, `/add-condition`, `/add-hero-trait`,
  `/add-verification`, `/engine-verify` scaffold + gate common engine changes.

## Conventions & guardrails (non-negotiable)

- **TLI-only terminology**; never reference other games or "PoB". Call the owner **Tyra**.
- **Never silently drop a modifier** — apply it or surface a badge.
- **Work on `dev`**; merge to `main` only when asked. **Never commit without explicitly asking**, and Tyra
  **tests in-app before committing** — leave finished work uncommitted and summarize. **Push is per-exchange,
  explicit only.** No `Co-Authored-By` tags; plain commit subjects (no `feat()/fix()`).
- **Flag calculation/mechanic uncertainties before implementing** — no silent assumptions.
- **`.wolf` logging:** check `buglog.json` before fixing a bug + log after; `anatomy.md`/`memory.md` are
  auto-maintained; check `cerebrum.md` Do-Not-Repeat before generating code.
- Docs live in `docs/`, never the repo root.
- The **TLI Help Database** (`C:\Users\tyray\Claude\Projects\TLI Help Database`) and
  `data/master_glossary.json` are authoritative references — cite, don't modify; flag inconsistencies.

## Current status snapshot

- **Minion DPS engine (Spirit Magus foundation): shipped, uncommitted, unverified in-app.** Backend + panel +
  Full-DPS fold done and typechecking/tests green; awaiting in-app validation with real numbers. Origin buffs
  and Iris traits are the next phases.
- **Zustand migration Phase 2** in progress (screens → store; remove the `session` bridge).
- Many mechanics are "shipped, unverified" (see `MEMORY.md` for the full ledger). When touching one, check its
  memory entry + verification-KB status first.

## Key file map

| Area | Path |
|------|------|
| Backend entry / endpoints | `backend/server.py` |
| Aggregation | `backend/engine/aggregator.py`, `backend/engine/models.py` (`BuildSource`, `StatResult`) |
| Compute loop | `backend/engine/compute.py` |
| Offense / minion offense | `backend/engine/offense.py`, `backend/engine/minion_offense.py` |
| Skill resolution / bespoke | `backend/engine/skill_resolver.py`, `backend/engine/skill_effects/` |
| Hero traits | `backend/engine/hero_traits/` |
| Stats | `backend/models/stat.py`, `backend/models/stat_meta.py` |
| Data importers | `backend/tools/rebuild_skills.py`, `backend/tools/skill_importer.py` |
| Season data loaders | `backend/persistence/season_manager.py` |
| Build codes | `backend/build_code.py` (frozen codec) |
| Renderer API client + types | `src/renderer/src/api/client.ts` |
| Store | `src/renderer/src/store/{buildStore,referenceStore,useBuildCalculation}.ts` |
| Calcs screen | `src/renderer/src/screens/PlayerStatsScreen.tsx` |
| Sidebar / Full DPS | `src/renderer/src/components/BuildSidebar.tsx` |
| Project instructions | `CLAUDE.md`, `.claude/rules/openwolf.md` |
