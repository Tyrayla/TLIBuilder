# Handoff: Tooltip System (for a revamp)

This document explains how tooltips/hover-popups currently work across TLI Builder, the
program context needed to understand them, and where every separate implementation lives.
Written for a fresh agent who will revamp the system.

---

## TL;DR

**There is no standardized tooltip component or container.** Tooltips are implemented
ad-hoc, screen-by-screen. Each screen owns its own `useState` for hover position, its own
JSX block at the bottom of the render, and its own CSS class set in `index.css`. There are
**~10 distinct tooltip implementations** with overlapping-but-inconsistent patterns.

The only piece of shared infrastructure is [`ItemTooltip.tsx`](src/renderer/src/components/ItemTooltip.tsx) —
a single reusable component for **gear items** (legendaries + crafted gear). It is used by
exactly two screens (Gear, PlayerStats). Everything else is bespoke.

A revamp should consolidate these into one positioning/portal primitive plus a small set
of content renderers.

---

## General project overview

**TLI Builder is a desktop build planner for the ARPG *Torchlight: Infinite*.** It lets a
user assemble a character build — passive trees, gear, skills, hero traits, pact spirits,
slates, memories — and see the resulting offensive/defensive stats computed by a faithful
re-implementation of the game's math. Builds can be saved, loaded, and shared via a compact
build code or link.

> Terminology rule: the codebase **only ever references *Torchlight: Infinite***. Never
> introduce other game titles in code, comments, or docs. (Note: `.wolf/cerebrum.md`
> contains a stale "The Last Immortal" description — that is an error, not the real game.)

### Architecture (three layers)

```
Season JSON data  →  Python backend (importers + engine)  →  React renderer (Zustand + screens)
                          ↑ authoritative game data           ↑ pure presentation, no combat logic
```

- **Electron + electron-vite** desktop shell. Main process in [`src/main/index.ts`](src/main/index.ts)
  spawns the Python backend as a child process, manages ports, data dir bootstrap, and
  auto-updates. Renderer↔backend traffic goes through an **IPC proxy** (`ipcMain.handle('api-request', …)`)
  so the renderer never makes raw cross-origin HTTP from `file://`. Browser dev mode falls
  back to direct `fetch`.
- **Python FastAPI backend** (`backend/`) is the single source of truth for *all* game data,
  stat computation, and the `tli1_` build-code codec. The renderer contains **no combat
  logic** — this is an enforced architectural constraint (see [`architecture.md`](docs/architecture.md)).
- **React + TypeScript renderer** (`src/renderer/src/`) renders screens and edits build
  state, reading already-computed values from the backend.

### Backend subsystems (`backend/`)

| Area | What it does |
|------|--------------|
| `tools/*_importer.py` | Load seasonal crawler/JSON data, normalize it, build lookup maps. One importer per data type (gear, skills, traits, spirits, memories, craft base types, grafts, singletons). |
| `models/` | Data models + the big stat taxonomy: [`stat.py`](backend/models/stat.py) (enum of ~180 stats) and [`stat_meta.py`](backend/models/stat_meta.py) (per-stat metadata: display names, units, pipeline stage, affected damage). |
| `engine/` | All math. `aggregator.py` collects every stat contribution with its source; `offense.py` runs the per-skill damage pipeline; `defense.py` computes EHP-style defenses; `compute.py`/`derive.py`/`pipeline.py` orchestrate; `skill_resolver.py` maps skills to damage forms. |
| `persistence/` | Save/load builds, tree configs, snapshots, season selection. Paths are overridable via `TLI_DATA_DIR` for packaged builds. |
| [`build_code.py`](backend/build_code.py) | `tli1_<base64url(zlib_l9(compact_json))>` codec — **frozen, do not change**. |
| [`server.py`](backend/server.py) | FastAPI endpoint handlers tying it all together. |

The computation flow: build inputs → `aggregator` groups every contribution by source →
`offense`/`defense` run deterministic pipelines → results come back with **per-stat source
breakdowns** (which is exactly what the stat tooltips/popups display).

### Renderer structure (`src/renderer/src/`)

- **Entry:** [`App.tsx`](src/renderer/src/App.tsx) owns navigation, the current `session`, and
  build open/save. The app is a set of full-screen "screens" switched by the sidebar
  ([`BuildSidebar.tsx`](src/renderer/src/components/BuildSidebar.tsx)).
- **Screens** (`screens/`), each roughly one build subsystem:
  - `BuildSelectScreen` — pick/import/export builds
  - `TreeSelectorScreen` / `TreeViewerScreen` — passive talent trees (node allocation)
  - `GearScreen` — equip/craft gear (legendaries + crafted items), the richest screen
  - `SkillsScreen` — active skills + support gems
  - `HeroTraitScreen` — hero traits + socketed memories
  - `PactSpiritScreen` — pact spirit nodes
  - `SlateScreen` — slate board (grid placement)
  - `PlayerStatsScreen` — the main computed-stats view (offense/defense, interactive source breakdowns)
  - `StatsScreen` / `CalcsScreen` / `DevToolsScreen` — debug/dev and custom-mod tooling
- **State:** [`buildStore.ts`](src/renderer/src/store/buildStore.ts) (Zustand) holds the build's
  inputs + computed results; [`referenceStore.ts`](src/renderer/src/store/referenceStore.ts)
  holds prefetched season-global catalogs (gear, traits, memories, spirits, conditions).
  [`useBuildCalculation.ts`](src/renderer/src/store/useBuildCalculation.ts) recomputes stats in
  the background when inputs change.
- **API:** every backend call is a typed wrapper in [`client.ts`](src/renderer/src/api/client.ts)
  (also defines all the TS interfaces that tooltips consume). Share-service calls
  (`api.tlibuilder.com`) are plain `fetch`, separate from the local backend.

### In-flight work a fresh agent should know about

- **Zustand migration (Phase 2, in progress):** screens are being moved off prop-drilling to
  read/write the store directly; the `session`→store bridge in `App.tsx` is being removed.
  Expect some screens (`GearScreen.tsx`, `App.tsx`) to have **pre-existing typecheck errors**
  from this migration — they are expected and not caused by your changes.
- **Build-code sharing:** complete. Share-via-link resolves URLs to raw `tli1_` codes.
- **Reference-data caching:** investigation complete; prefetch all season-global catalogs at
  init keyed on each endpoint's `season` field.

### Conventions / operational rules

- Work on the `dev` branch; merge to `main` only when explicitly asked.
- **Never commit without asking first**; commits carry only the owner's name (no Co-Authored-By).
- Standalone docs go in `docs/`, never the repo root.
- Bug workflow: check `.wolf/buglog.json` before fixing, log to it after. Update
  `.wolf/anatomy.md` + `.wolf/memory.md` after editing files.
- Typecheck: `npx tsc --noEmit -p tsconfig.web.json` from repo root.

---

## Program context (what you need to know first)

- **Stack:** Electron + electron-vite, React + TypeScript renderer in `src/renderer/src/`,
  Python FastAPI backend in `backend/`. The renderer calls `api.*` functions in
  [`client.ts`](src/renderer/src/api/client.ts) which POST/GET the local Python server.
- **State:** Zustand store in [`buildStore.ts`](src/renderer/src/store/buildStore.ts) holds
  build state; [`referenceStore.ts`](src/renderer/src/store/referenceStore.ts) holds prefetched
  season-global catalogs (gear, traits, memories, spirits, etc.). Screens read from these.
- **All tooltip data originates from the backend.** Item affixes, node effects, skill
  descriptions, trait effects, and stat-source breakdowns are all computed/served by Python
  and arrive via the typed interfaces in `client.ts`. Tooltips are pure presentation — they
  format already-resolved data. The one exception is **client-side scaling math** (e.g.
  `scaleEffect` in TreeViewer, range-midpoint reconstruction in ItemTooltip).
- **Styling:** A single global stylesheet, [`index.css`](src/renderer/src/index.css) (~4100
  lines). Every tooltip variant has its own block there. CSS variables: `--accent`, `--ok`,
  etc. There is no CSS-module or styled-component system.

---

## The two structural patterns in use

Every tooltip falls into one of two rendering paradigms:

### Pattern A — Floating, cursor-anchored (the common one)
1. `useState` holds `{ ...content, x, y } | null`.
2. `onMouseEnter`/`onMouseMove` set `{ x: e.clientX, y: e.clientY }`; `onMouseLeave` sets `null`.
3. At the bottom of the render, `state && (<div className="...-tooltip" style={{left, top}}>...)`.
4. Position is clamped against `window.innerWidth/innerHeight` to keep it on screen.

Sub-variants differ on:
- **Portal vs inline.** Some use `createPortal(..., document.body)` to escape overflow/stacking
  contexts; others render inline inside the screen tree.
- **Clamping technique.** Inline `Math.min(...)` math, a shared `clampTooltip()` helper, a
  `flipX/flipY` quadrant flip, or a post-render `useLayoutEffect` that reads the rendered
  element's size and repositions.

### Pattern B — Click-to-open / pinned popups
Instead of hover, the user clicks; the popup stays open and is dismissed by an outside-click
listener (or clicking the same target again). Used where the content is interactive or dense
(StatsScreen stat breakdown, PlayerStats source popup, HeroTrait pinned tooltips).

---

## Inventory of every tooltip implementation

| # | Location | Trigger | Portal? | Positioning | Content / data source |
|---|----------|---------|---------|-------------|------------------------|
| 1 | [`ItemTooltip.tsx`](src/renderer/src/components/ItemTooltip.tsx) | hover (caller-driven) | **Yes** (`document.body`) | inline clamp, fixed 316px width | Gear items — legendary or crafted. **Shared component.** |
| 2 | [`GearScreen.tsx`](src/renderer/src/screens/GearScreen.tsx) — item slots/catalog | hover | via #1 | via #1 | Equipped + catalog gear → renders `<ItemTooltip>` |
| 3 | GearScreen — `gear-slider-tooltip` | hover over affix-value slider | No (inline) | `Math.min` clamp | Live affix text as you drag a range value |
| 4 | GearScreen — `gear-base-stat-tooltip` | hover over base-type chip | No (inline) | tracks cursor | Base-type implicit stats |
| 5 | GearScreen — `BaseItemSelect` / `gear-base-item-tooltip` | hover in base-item dropdown | **Yes** | `Math.min` clamp | Base item name/level/stats (passed-in `getTooltipLines`) |
| 6 | [`PlayerStatsScreen.tsx`](src/renderer/src/screens/PlayerStatsScreen.tsx) — `SourcePopup` | **click** | popup inline; nests #1 | inline clamp | Per-stat source breakdown; hovering a source row that maps to a gear item shows `<ItemTooltip>` |
| 7 | [`StatsScreen.tsx`](src/renderer/src/screens/StatsScreen.tsx) — `stat-tooltip` | **click**, outside-click closes | No (inline) | `Math.min` clamp + `ref` | Grouped stat contributions (value ×count, source label) |
| 8 | [`TreeViewerScreen.tsx`](src/renderer/src/screens/TreeViewerScreen.tsx) — `.tooltip` | hover over passive node | No (inline) | `flipX/flipY` quadrant flip | Node type, current-level effects, "Next Level" preview. Uses client-side `scaleEffect(effect, points)`. |
| 9 | [`SkillsScreen.tsx`](src/renderer/src/screens/SkillsScreen.tsx) — `skill-tooltip` | hover | **Yes** | cursor offset (+14,−8), no clamp | Skill/support name + `getAdvancedLines(description_lines)` |
| 10 | [`PactSpiritScreen.tsx`](src/renderer/src/screens/PactSpiritScreen.tsx) — `pact-spirit-node-tooltip` | hover over spirit node | No (inline) | `ref` + `useEffect` measures & repositions | Node main effect + bonus lines |
| 11 | [`HeroTraitScreen.tsx`](src/renderer/src/screens/HeroTraitScreen.tsx) — trait/memory/affix tooltips | hover **and** click-to-pin | No (inline) | shared `clampTooltip()` helper | 3 separate tooltips: trait effects (pinnable), memory-slot hover, affix-row hover |
| 12 | [`SlateScreen.tsx`](src/renderer/src/screens/SlateScreen.tsx) — `HoverTooltip` | hover over placed slate | No — **fixed side panel**, not floating | n/a (rendered in right panel) | Slate stats. Not a true floating tooltip; lives in a layout panel. |

> Note: `index.css` also has `.memory-affix-hover-tooltip`, `.gear-tooltip-section-line`,
> a "Floating info tooltip" block (~line 3250), and other one-off classes — grep
> `tooltip` in `index.css` for the full list of ~15 class families.

---

## How each tooltip decides *what* to show

This is the part most relevant to a revamp — the content logic is where the real divergence is.

### Gear (legendaries vs crafted) — `ItemTooltip.tsx`
The single component handles **two different data shapes** discriminated at runtime:
- `isLegendaryGearItem(item)` checks for `'variants' in item` → `LegendaryGearItem`.
  - Implicits/explicits pulled from the first variant. Random-affix placeholders are
    reconstructed via `getItemExplicits` (matches placeholder groups against existing
    explicits, appends unfilled placeholders).
- Otherwise it's an `EquippedGearItem` (crafted). Implicits vs explicits are split by
  `implicit_count`. Corrosion/mutation affix text is shown specially
  (`gear-tooltip-affix--corroded`).
- **Range values:** affixes with `kind === 'range'` show a reconstructed string using the
  user's chosen value (from `customizations`) or the midpoint. See `reconstructAffixText`,
  `midpoint`, `tooltipAffixText`.
- **Affix type labels** (Base / Basic / Advanced / Ultimate / Legendary) come from
  `affixTypeLabel(affix.affix_type)` and are appended only for crafted gear.
- `getGearTypeLabel(baseType)` regex-maps a base-type string to a slot label (Belt, Amulet,
  Weapon, …). **This regex list is a maintenance hazard** — new base types must be added here.

`tooltipAffixText` is **duplicated** in both `ItemTooltip.tsx` and `GearScreen.tsx`
(GearScreen line ~202). A revamp should de-dupe this.

### Passive nodes — TreeViewer
`scaleEffect(effect, points)` scales each effect string by the points invested, and a
"Next Level" preview is computed with `points + 1`. Data is `node.effects` from the node map.

### Skills — SkillsScreen
`getAdvancedLines(description_lines)` trims a skill's description down to the "advanced"
section (finds the first line ending in `:` and slices from there). Same tooltip used for
active skills, the focused equipped skill, and support gems.

### Hero traits / memories — HeroTraitScreen
Tooltip content branches on `isBase` (base trait variant vs an advanced trait) and pulls
effects scaled to the relevant slot level (`safeSlotLevels`, `SLOT_IDX`). Memory-slot and
affix-row hovers are separate, smaller tooltips. Supports **pinning** (`pinned` flag) so the
tooltip persists for reading; outside-click on the screen root clears it.

### Stats — StatsScreen / PlayerStats
Content is a **breakdown list**: grouped contributions `{ value, count, label }`, totals, and
units (`formatStatValue`, `shortenLabel`). PlayerStats' `SourcePopup` additionally maps a
source row back to a concrete gear item and nests `ItemTooltip` on hover — the only place two
tooltip systems compose.

### Spirits / slates
Pact spirit node tooltip = main + bonus lines. Slate "tooltip" is really a persistent side
panel, conceptually different from the rest.

---

## Known rough edges (candidates for the revamp)

1. **No shared primitive.** Positioning, clamping, portal logic, and show/hide state are
   re-implemented per screen with subtle differences. A `<Tooltip>` /
   `useTooltip()` primitive would remove ~all of this duplication.
2. **Four different clamping strategies** (inline `Math.min`, `clampTooltip()` helper,
   `flipX/flipY`, post-render `useLayoutEffect`). Only the measure-then-reposition approach
   (PactSpirit) handles variable-height tooltips correctly; the `Math.min` ones use
   hard-coded height estimates (`TIP_H_EST`, `window.innerHeight - 360`, etc.) that can clip.
3. **Inconsistent portal usage.** Mixing portal and inline tooltips means some get clipped by
   `overflow:hidden`/stacking contexts and some don't. Standardize on portals.
4. **Duplicated logic:** `tooltipAffixText` exists in both `ItemTooltip.tsx` and
   `GearScreen.tsx`.
5. **`getGearTypeLabel` regex** must be manually extended for new base types — fragile.
6. **Mixed trigger models** (hover vs click-to-pin vs outside-click-close) with no shared
   convention. Decide on a unified interaction model (e.g. hover-to-show + optional pin).
7. **Hard-coded widths/offsets** scattered through both TSX and CSS (`316`, `TIP_W`,
   `+14,-8`, `-300`, `-360`).

---

## Suggested revamp shape (not prescriptive)

A reasonable target architecture:

- **One positioning primitive** — a `useFloatingTooltip()` hook (or a `<FloatingTooltip
  anchor=... >` portal component) that owns: portal mount, cursor/element anchoring,
  measure-then-clamp against the viewport, and show/hide/pin state. (Consider whether to pull
  in `@floating-ai/react`-style logic or keep it hand-rolled — currently zero deps.)
- **Content renderers** kept per domain (gear, node, skill, trait, stat-breakdown) but fed
  through the single primitive. `ItemTooltip` becomes one such renderer.
- **De-duplicate** affix-text formatting into a shared util (likely alongside
  `statsPayload.ts` / a new `utils/affixText.ts`).
- **Consolidate CSS** into a base `.tooltip` block + modifier classes instead of ~15
  independent class families.

---

## Files to touch / reference

| File | Why |
|------|-----|
| [`components/ItemTooltip.tsx`](src/renderer/src/components/ItemTooltip.tsx) | The only existing shared tooltip; the model to generalize from |
| [`screens/GearScreen.tsx`](src/renderer/src/screens/GearScreen.tsx) | Most tooltip variants live here (4+); has duplicated `tooltipAffixText` |
| [`screens/TreeViewerScreen.tsx`](src/renderer/src/screens/TreeViewerScreen.tsx) | Node tooltip + `scaleEffect` scaling |
| [`screens/SkillsScreen.tsx`](src/renderer/src/screens/SkillsScreen.tsx) | Skill tooltip + `getAdvancedLines` |
| [`screens/HeroTraitScreen.tsx`](src/renderer/src/screens/HeroTraitScreen.tsx) | Pinning model + `clampTooltip` + 3 tooltips |
| [`screens/PactSpiritScreen.tsx`](src/renderer/src/screens/PactSpiritScreen.tsx) | Best clamping approach (measure-then-reposition) |
| [`screens/StatsScreen.tsx`](src/renderer/src/screens/StatsScreen.tsx) | Click-to-open breakdown popup |
| [`screens/PlayerStatsScreen.tsx`](src/renderer/src/screens/PlayerStatsScreen.tsx) | `SourcePopup` that nests `ItemTooltip` |
| [`screens/SlateScreen.tsx`](src/renderer/src/screens/SlateScreen.tsx) | Panel-style "tooltip" — decide if it stays separate |
| [`index.css`](src/renderer/src/index.css) | All tooltip CSS (grep `tooltip`) |
| [`api/client.ts`](src/renderer/src/api/client.ts) | Source types: `LegendaryGearItem`, `EquippedGearItem`, `CustomizedAffix`, etc. |

## Typecheck

```
npx tsc --noEmit -p tsconfig.web.json
```
(Pre-existing errors in `GearScreen.tsx`, `App.tsx` from the Zustand migration are expected.)
