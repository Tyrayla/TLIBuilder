# Handoff: Tooltip System Revamp (implementation spec)

This is the **build spec** for revamping TLI Builder's tooltips. It supersedes the
"current state" description in [`HANDOFF_TOOLTIPS.md`](HANDOFF_TOOLTIPS.md) and the code
appendix in [`TOOLTIP_SOURCE_REFERENCE.md`](TOOLTIP_SOURCE_REFERENCE.md) — read both of
those first; this document tells you *what to build and in what order*.

Written for an in-IDE agent. Re-read the live files before relying on the excerpts in the
reference doc; they were captured at a point in time.

---

## TL;DR

Replace ~10–12 ad-hoc, per-screen tooltip implementations with **three clean layers**:

1. **`useFloatingTooltip`** — one positioning/behavior primitive, backed by
   **`@floating-ui/react`**. Owns portal, anchoring (element *or* cursor), collision
   handling (flip/shift/size), open/hover/pin state. Every tooltip routes through this.
2. **`TooltipShell`** — the shared visual container ("chrome"): title, an **optional
   damage-delta band**, and a body slot. Provides the base `.tooltip` styling.
3. **Content bodies** — one small presentational component per domain (gear, node, skill,
   spirit, stat-breakdown), each typed against the real `client.ts` interfaces.

The motivating new feature is a cross-cutting **damage-delta band** ("how much damage this
node/gear/slate would gain or lose if allocated"). That backend endpoint **does not exist
yet** — build the band and its data hook against the stubbed contract in §6 so it ships in
an NYI state and lights up when the engine lands. The refactor must **not** block on the
damage engine.

**Decision already made:** use Floating UI (not Radix, not hand-rolled). Rationale in §2.

---

## 1. Why consolidate (the load-bearing reason)

The damage-delta band must appear on *most* tooltips. Adding it to 10–12 separate
implementations — each with its own positioning, clamping, and state — would mean
implementing the band (and its loading / value / NYI / error states) a dozen times. Doing it
once in a shared shell is the whole point. The secondary win is killing the four divergent
clamping strategies and mixed portal usage that currently cause clipping bugs.

---

## 2. Why Floating UI specifically

- Positioning math (flip, shift, collision, variable-size handling, cursor/virtual anchoring)
  is exactly the fiddly, edge-case-heavy code that the current four hand-rolled clamping
  strategies get wrong. Floating UI solves it as a maintained library.
- It is **lower-level than Radix** — Radix's `Tooltip` is opinionated toward
  element-anchored, non-interactive hover hints, which fights our cursor-following and
  pinnable/interactive tooltips. Floating UI gives just the anchoring math + optional
  interaction hooks, so our custom hover+pin model and the async delta band sit cleanly on top.
- It is a **clean dependency**: focused scope, first-party transitive packages
  (`@floating-ui/core` / `dom` / `react-dom`), no sprawling tree. This is the first
  third-party positioning dependency in the renderer's tooltip subsystem; that trade is
  justified because it lets us delete the most bug-prone hand-rolled code in the app.

Install: `npm i @floating-ui/react`

> If for any reason the dependency is rejected later, the fallback is to hand-roll layer 1
> around the **measure-then-reposition** pattern from `PactSpiritScreen.tsx` (the only
> currently-correct clamping impl) — but the default plan is Floating UI.

---

## 3. Target architecture

```
useFloatingTooltip (layer 1)   →  positioning + portal + hover/pin state   [Floating UI]
        ↓
TooltipShell (layer 2)         →  title · [damage-delta band] · body slot · base .tooltip CSS
        ↓
Content body (layer 3)         →  GearTooltipBody / NodeTooltipBody / SkillTooltipBody / …
```

Consumer shape on every screen:

```tsx
function TalentNode({ node, delta }) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right', pinnable: true })
  return (
    <>
      <button className="tree-node" {...tip.triggerProps}>{node.name}</button>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--node" {...tip.floatingProps}>
            <TooltipShell title={`${node.node_type} ${pts}/${node.max_points}`} delta={delta}>
              <NodeTooltipBody node={node} pts={pts} />
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}
```

Only the content body and the `tooltip--*` modifier change per type. Informational tooltips
(stat breakdown, skill description) simply **omit the `delta` prop** — the band is opt-in.

---

## 4. Layer 1 — `useFloatingTooltip`

**File:** `src/renderer/src/components/tooltip/useFloatingTooltip.ts`

### Public contract (this is the stable interface — keep it)

```ts
import type { Placement } from '@floating-ui/react'

export interface UseFloatingTooltipOptions {
  anchor: 'element' | 'cursor'   // sit beside the trigger, or follow the pointer
  side?: Placement               // preferred placement; auto-flips. default: 'right' (element) / 'top' (cursor)
  pinnable?: boolean             // click trigger to keep open after mouse leaves
  interactive?: boolean          // tooltip body receives pointer events (scroll / click inside). default false
  openDelay?: number             // ms hover delay before showing. default 0
  viewportPadding?: number       // px gap from viewport edges. default 8
}

export interface FloatingTooltip {
  open: boolean
  pinned: boolean
  triggerProps: Record<string, unknown> // spread onto the hovered element
  floatingProps: Record<string, unknown> // spread onto the floating .tooltip div
}
```

### Reference implementation (verify against the installed Floating UI version)

```ts
import { useState, useCallback } from 'react'
import {
  useFloating, autoUpdate, offset, flip, shift, size,
  useHover, useDismiss, useInteractions, safePolygon,
} from '@floating-ui/react'

export function useFloatingTooltip(opts: UseFloatingTooltipOptions): FloatingTooltip {
  const {
    anchor, side, pinnable = false, interactive = false,
    openDelay = 0, viewportPadding = 8,
  } = opts

  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false)

  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: (next) => { setOpen(next); if (!next) setPinned(false) },
    placement: side ?? (anchor === 'cursor' ? 'top' : 'right'),
    whileElementsMounted: autoUpdate,
    middleware: [
      offset(8),
      flip({ padding: viewportPadding }),
      shift({ padding: viewportPadding }),
      // variable size: cap to available height, let the body scroll if genuinely too tall
      size({
        padding: viewportPadding,
        apply({ availableHeight, elements }) {
          Object.assign(elements.floating.style, { maxHeight: `${Math.max(120, availableHeight)}px` })
        },
      }),
    ],
  })

  // Cursor anchoring: feed a zero-size virtual element at the pointer.
  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (anchor !== 'cursor') return
    refs.setPositionReference({
      getBoundingClientRect: () => ({
        width: 0, height: 0,
        x: e.clientX, y: e.clientY,
        left: e.clientX, top: e.clientY, right: e.clientX, bottom: e.clientY,
      }),
    })
  }, [anchor, refs])

  const hover = useHover(context, {
    enabled: !pinned,                              // pinned tooltips ignore mouseleave
    delay: { open: openDelay, close: 0 },
    handleClose: interactive ? safePolygon() : null, // lets the cursor travel into an interactive body
  })
  const dismiss = useDismiss(context, { enabled: pinned }) // outside-click / Escape closes a pinned tip

  const { getReferenceProps, getFloatingProps } = useInteractions([hover, dismiss])

  const triggerProps = getReferenceProps({
    ref: refs.setReference,
    onMouseMove,
    onClick: pinnable ? () => { setPinned(p => !p); setOpen(true) } : undefined,
  })

  const floatingProps = getFloatingProps({
    ref: refs.setFloating,
    style: { ...floatingStyles, pointerEvents: interactive ? 'auto' : 'none' },
  })

  return { open, pinned, triggerProps, floatingProps }
}
```

**Test these interaction edges explicitly** (they are the historically buggy parts):

- Cursor-anchored tooltip tracks the pointer smoothly and flips near right/bottom edges.
- A **tall** tooltip (e.g. a long gear item) near the bottom edge caps its height and scrolls
  instead of clipping — this is the failure mode of the old `Math.min`/`TIP_H_EST` approach.
- Pin: click keeps it open after mouseleave; click again or outside-click/Escape closes it.
- `interactive: true` + `safePolygon()`: the cursor can move from the trigger onto a scrollable
  body without the tooltip closing.

> Caller renders the floating element conditionally on `tip.open`, wrapped in
> `<FloatingPortal>` (imported from `@floating-ui/react`). The primitive does **not** render —
> it only supplies props — so it composes with any content body.

---

## 5. Layer 2 — `TooltipShell`

**File:** `src/renderer/src/components/tooltip/TooltipShell.tsx`

The chrome. Renders a title block, the optional delta band, then the body. It does **not**
position itself — it lives inside the `.tooltip` div that got `floatingProps`.

```tsx
import type { DamageDelta } from './useDamageDelta'

export interface TooltipShellProps {
  title?: string
  subtitle?: string         // e.g. "Base: Sacred Robe" / "Required Level: 80"
  delta?: DamageDelta       // OMIT for informational tooltips (stat breakdown, skill desc)
  children: React.ReactNode // the layer-3 content body
}

export function TooltipShell({ title, subtitle, delta, children }: TooltipShellProps) {
  return (
    <>
      {title && <div className="tooltip-title">{title}</div>}
      {subtitle && <div className="tooltip-subtitle">{subtitle}</div>}
      {delta && <DamageDeltaBand delta={delta} />}
      {(title || subtitle || delta) && <div className="tooltip-divider" />}
      <div className="tooltip-body">{children}</div>
    </>
  )
}
```

`DamageDeltaBand` renders the four states (see §6). The band sits directly under the title so
it reads as a headline number for the hovered thing.

---

## 6. The damage-delta band + data contract (backend endpoint NOT YET BUILT)

The delta is a **backend recompute** — the renderer holds no combat logic (enforced
constraint). So the band consumes data from the Python backend, never computes it locally.

### 6a. Renderer-side UI shape

**File:** `src/renderer/src/components/tooltip/useDamageDelta.ts`

```ts
export type DamageDelta =
  | { state: 'loading' }
  | { state: 'value'; absolute: number; percent: number; direction: 'gain' | 'loss' | 'neutral' }
  | { state: 'nyi'; reason: string }     // engine doesn't support the active skill yet
  | { state: 'error'; message: string }
```

`DamageDeltaBand` renders accordingly: a spinner/placeholder for `loading`, a colored
+/- number for `value` (green `--ok` for gain, a loss color for loss), a muted "Damage
preview not yet supported" line for `nyi`, and a quiet error line for `error`.

### 6b. The change descriptor + fetch contract (define now, implement on the backend later)

The delta only makes sense for **allocatable / swappable** things. Model the hypothetical:

```ts
// add to src/renderer/src/api/client.ts when wiring the backend
export type HypotheticalChange =
  | { kind: 'allocate_node'; node_id: string; points: number }
  | { kind: 'equip_gear'; slot: GearSlot; item_id: string }
  | { kind: 'place_slate'; slate_id: string /* + position */ }
  | { kind: 'socket_memory'; slot: number; memory_id: string }
  | { kind: 'pact_spirit_node'; node_id: string }

export interface DamageDeltaResult {
  supported: boolean   // false → render the NYI band (engine's all-or-nothing per-skill support)
  absolute: number     // change in the headline damage metric
  percent: number      // change as a percentage of current
}

// TODO(backend): POST current build + change → DamageDeltaResult.
// Until this exists, the hook below returns { state: 'nyi' }.
```

### 6c. The hook (build now, stubbed)

```ts
export function useDamageDelta(change: HypotheticalChange | null): DamageDelta {
  // TODO: when the backend endpoint lands, debounce on hover (~120ms),
  //       cache keyed on (buildHash, change), map DamageDeltaResult → DamageDelta.
  //       supported === false → { state: 'nyi', reason: ... }
  // For now, ship the NYI state so the band is visible and wired but inert:
  return { state: 'nyi', reason: 'Damage preview coming soon' }
}
```

**Compute strategy when the backend exists:** compute **on hover, debounced, and cached** —
not precomputed for every visible node (a full recompute per node is wasteful). Cache key =
(build hash, change descriptor).

> Because the damage engine uses an explicit per-skill registry with all-or-nothing support,
> the `nyi` state is permanent infrastructure, not a temporary stub — keep it even after the
> endpoint ships.

---

## 7. Layer 3 — content bodies

Each is a pure presentational component, typed against `client.ts` (do **not** re-declare
shapes). Preserve the existing content logic from the reference doc:

| Body | Source to port from | Logic to preserve |
|------|---------------------|-------------------|
| `GearTooltipBody` | `ItemTooltip.tsx` | `isLegendaryGearItem` discriminator; implicit/explicit split; range reconstruction; `affixTypeLabel`; corroded/mutation handling |
| `NodeTooltipBody` | `TreeViewerScreen.tsx` | `scaleEffect(text, pts)` and the "Next Level" preview (`pts + 1`) |
| `SkillTooltipBody` | `SkillsScreen.tsx` | `getAdvancedLines(description_lines)` |
| `SpiritTooltipBody` | `PactSpiritScreen.tsx` | main line + bonus lines |
| `StatBreakdownBody` | `StatsScreen.tsx` / `PlayerStatsScreen.tsx` | grouped contributions, totals, `formatStatValue` / `shortenLabel`; **interactive + pinnable**; this is where `SourcePopup` nests gear — see §9 |

### De-duplication required

- `tooltipAffixText` is **duplicated** in `ItemTooltip.tsx` and `GearScreen.tsx`. Extract it
  (plus `midpoint`, `reconstructAffixText`, `rangeDecimals`, `decimalPlaces`, `hasRangeValues`,
  `affixTypeLabel`) into **`src/renderer/src/utils/affixText.ts`** and import from both.
- `getGearTypeLabel` is a fragile regex that must be extended for every new base type. Keep it
  for now but move it into the gear body (or a util); flag in `.wolf/buglog.json` as a known
  maintenance hazard, do not attempt to redesign it in this pass.

---

## 8. CSS consolidation

**Target:** a base `.tooltip` block + per-type modifier classes, replacing the ~15
independent class families. The current shared DNA (from the reference doc): `position: fixed`,
dark navy/indigo background (`#0d0d1e`–`#1e1e32`), `1px` accent border, `border-radius: 6px`,
`box-shadow: 0 4px ~20px rgba(0,0,0,.6)`, `pointer-events: none` (override to `auto` for
interactive ones via the inline style from layer 1).

```css
.tooltip {
  position: fixed;
  z-index: 9999;
  background: #0e0e1e;
  border: 1px solid #3a3a6a;
  border-radius: 6px;
  padding: 10px 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.65);
  /* width is intrinsic — let content size it; layer 1's size() middleware caps height */
}
.tooltip--gear   { /* gold-name accent already on .gear-tooltip-name */ }
.tooltip--node   { background: #0d1b2a; border-color: var(--accent); }
.tooltip--skill  { max-width: 280px; }
.tooltip--spirit { /* centered-above handled by Floating UI placement now, drop the old translate */ }
.tooltip--stat   { width: 230px; max-height: 320px; overflow: hidden; } /* interactive, scrolls */

.tooltip-title    { font-size: 13px; font-weight: 700; color: #c8a050; margin-bottom: 2px; }
.tooltip-subtitle { font-size: 11px; color: #7070aa; margin-bottom: 4px; }
.tooltip-divider  { border-top: 1px solid #2a2a3a; margin: 6px 0; }
.tooltip-delta            { display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; }
.tooltip-delta--gain      { color: var(--ok); }
.tooltip-delta--loss      { color: #e06060; }
.tooltip-delta--nyi       { color: #55556a; font-weight: 500; }
```

**Migration note:** keep the existing inner content classes (`.gear-tooltip-affix`,
`.tooltip-stat-row`, `.pact-tooltip-main/bonus`, `.stat-tooltip-*`) as-is initially so the
content bodies render unchanged — only the *container* moves to base + modifier. Migrate inner
classes opportunistically, not in one pass.

**Bug to fix while here:** `.gear-tooltip-affix--corroded` is referenced in code but has **no
CSS rule** (it silently inherits the default affix color). Add a rule using the corroded color
`#c678dd` (matches `.gear-affix-row--corroded` in GearScreen). Log to `.wolf/buglog.json`.

The old centered-above `transform: translate(-50%, -100%)` on `.pact-spirit-node-tooltip` is
no longer needed — Floating UI's `placement: 'top'` + `offset` handles it. Remove it when
porting that screen to avoid a double transform fighting `floatingStyles`.

---

## 9. Special cases & scope

- **`SourcePopup` (PlayerStats) nests `ItemTooltip`.** This is the one place two tooltip
  systems compose. After the refactor it becomes: an interactive/pinnable `StatBreakdownBody`
  whose rows, on hover, open a second (element-anchored, non-interactive) gear tooltip using a
  *second* `useFloatingTooltip` instance. Two independent primitive instances compose fine;
  just don't share one instance between the popup and the nested gear tip.
- **`SlateScreen` — DECISION (2026-06-07): KEEP THE SIDE PANEL. Do NOT migrate.** The owner
  chose to leave SlateScreen's info as its existing fixed right-side panel rather than convert
  it to a floating tooltip. Reason: slate grid cells already use left-click for select/edit
  and drag for moving slates, so a click-to-pin floating tooltip would conflict, and the panel
  works well as-is. This screen is intentionally **out of scope** for the tooltip primitive.
  (Original plan, now cancelled: anchor a pinnable element tooltip to the slate cells.)
- **GearScreen sub-tooltips** (`gear-slider-tooltip`, `gear-base-stat-tooltip`,
  `gear-base-item-tooltip`) are all cursor- or element-anchored hover tips — straightforward
  ports to `anchor: 'cursor'` / `'element'` with small custom bodies.
- **HeroTrait** has three tooltips (trait circle, memory-slot hover, affix-row hover) plus
  `.memory-affix-hover-tooltip`. DECISION (2026-06-07): trait tooltips are **hover-only, NOT
  pinnable and NOT interactive** — show only while hovering the icon, vanish immediately on
  leave; clicking selects the node, never pins. (Overrides the earlier "pinnable trait" idea.)
  Use `anchor: 'element'` for the circles (snappier than cursor-follow).

---

## 10. Migration plan (incremental — do NOT big-bang)

- **Phase A — scaffold + proof.** `npm i @floating-ui/react`. Create
  `components/tooltip/{useFloatingTooltip.ts, TooltipShell.tsx, useDamageDelta.ts}` and the
  base `.tooltip` CSS. Port the **TreeViewer node tooltip** first (simplest: cursor-anchored,
  string-array content, has `scaleEffect`). Validates layer 1 end to end.
- **Phase B — gear body + composition.** Refactor `ItemTooltip.tsx` into `GearTooltipBody`
  rendered through `TooltipShell`; extract `affixText.ts`. Update `GearScreen` and the
  `PlayerStats` `SourcePopup` nesting (§9).
- **Phase C — remaining hover tooltips.** PactSpirit (drop the old transform), Skills, the
  three GearScreen sub-tooltips, and **SlateScreen** (replace the side panel with a
  pinnable element-anchored tooltip; tooltip only, not a layout overhaul).
- **Phase D — interactive/pinned.** StatsScreen breakdown and HeroTrait pinned trait tooltip
  (`interactive: true`, `pinnable: true`).
- **Phase E — delta band wiring.** Render `DamageDeltaBand` in the shell for allocatable
  variants (node, gear, spirit, slate, memory) using `useDamageDelta`. Backend endpoint (§6b)
  is a **separate follow-up task** and may be deferred; the band ships in `nyi` until then.

After each phase: typecheck, manual-verify the ported screen, then move on. One screen can
coexist on the new primitive while others are still on the old code.

---

## 11. Files to create / touch

**Create**

| File | Purpose |
|------|---------|
| `src/renderer/src/components/tooltip/useFloatingTooltip.ts` | Layer 1 primitive |
| `src/renderer/src/components/tooltip/TooltipShell.tsx` | Layer 2 chrome + delta band |
| `src/renderer/src/components/tooltip/DamageDeltaBand.tsx` | The four-state band (can live in TooltipShell file) |
| `src/renderer/src/components/tooltip/useDamageDelta.ts` | Delta data hook (stubbed — NYI) |
| `src/renderer/src/components/tooltip/bodies/*.tsx` | Content bodies, one per domain |
| `src/renderer/src/utils/affixText.ts` | De-duped affix-text helpers |

**Touch**

`ItemTooltip.tsx` (→ becomes/feeds `GearTooltipBody`), `GearScreen.tsx`,
`TreeViewerScreen.tsx`, `SkillsScreen.tsx`, `PactSpiritScreen.tsx`, `HeroTraitScreen.tsx`,
`StatsScreen.tsx`, `PlayerStatsScreen.tsx`, `SlateScreen.tsx` (swap panel → pinnable tooltip),
`index.css`, and later `client.ts` + backend `server.py`/engine for the delta endpoint.

---

## 12. Operational rules (from the project handoff — follow exactly)

- Work on the **`dev`** branch. Merge to `main` only when explicitly asked.
- **Never commit without asking first.** Commits carry only the owner's name — **no
  Co-Authored-By tags.**
- Standalone docs go in **`docs/`**, never the repo root.
- Bug workflow: check **`.wolf/buglog.json`** before fixing, log to it after. Update
  **`.wolf/anatomy.md`** and **`.wolf/memory.md`** after editing files.
- The renderer contains **no combat logic** — the delta comes from the backend. Do not compute
  damage in the renderer.
- **Only ever reference *Torchlight: Infinite*** in code, comments, and docs. Introduce no
  other game titles. (The stale `.wolf/cerebrum.md` line is a known error; ignore it.)
- Typecheck from repo root: `npx tsc --noEmit -p tsconfig.web.json`. Pre-existing errors in
  `GearScreen.tsx` and `App.tsx` from the in-progress Zustand migration are **expected** and
  not caused by this work.

---

## 13. Definition of done (for the renderer portion)

- All hover tooltips route through `useFloatingTooltip`; the four old clamping strategies and
  the hard-coded height estimates are gone.
- Tall tooltips near a viewport edge cap-and-scroll instead of clipping.
- One base `.tooltip` + modifiers replaces the per-screen container classes; inner content
  classes may remain.
- `tooltipAffixText` exists in exactly one place.
- `.gear-tooltip-affix--corroded` has a real rule.
- The damage-delta band renders (in `nyi` state) on allocatable tooltips, wired through
  `useDamageDelta`, ready for the backend endpoint.
- `npx tsc --noEmit -p tsconfig.web.json` shows no new errors beyond the known
  GearScreen/App.tsx migration ones.

---

## Implementation progress (live — update as phases land)

See `.wolf/memory.md` for the detailed running log. Status as of 2026-06-07:

- **Phase A — scaffold + proof:** ✅ done (primitive + shell + delta scaffold + TreeViewer node tooltip).
- **Phase B — gear body + composition:** ✅ done (affixText.ts, GearTooltipBody, GearScreen hover tooltips, PlayerStats SourcePopup nesting, ItemTooltip.tsx deleted).
- **Delta footer redesign** (owner request): ✅ done — contributions now render in a separate bottom area (`TooltipContributions`) that grows downward; gear tooltips show the NYI band.
- **Phase C — remaining hover tooltips:** ✅ mostly done — PactSpirit, Skills, and GearScreen sub-tooltips (base-stat, base-item, both craft-slot sliders) ported.
  - ⏳ **Deferred (1):** the `CustomizePanel` affix-row slider tooltip still uses the old state — needs `renderAffixRow` extracted into an `AffixRow` component to host a per-row hook (high-risk to the affix editor; do deliberately).
  - 🚫 **Cancelled:** SlateScreen — owner chose to keep its side panel (see §9).
- **Phase D — interactive/pinned:** ✅ done. StatsScreen breakdown is now a click-triggered, interactive, dismissible popover (added a `trigger: 'hover' | 'click'` option to the primitive). HeroTrait's three tooltips (pinnable trait circles with pin+select-coupled click, memory-slot hover, creator affix-row hover) are ported via `TraitCircle` / `MemorySlotCircle` / `AffixRow` components; their bespoke card CSS is kept, only positioning moved to the primitive.
  - ✅ The `CustomizePanel` affix-row slider tooltip is now ported too (via an `AffixSliderTooltip` wrapper using `cloneElement`, low-risk — `renderAffixRow`'s body left intact). **Every hover/click tooltip now routes through the primitive** (SlateScreen panel intentionally excluded).
- **Phase E — delta band wiring:** 🟡 in progress. **Passive nodes** now show a live delta
  (`+N dps (+x.x%)`, negative for removing a maxed node) by reusing `/engine/stats` (no backend
  changes): the renderer builds a modified payload via the shared `buildEngineStatsPayload`,
  recomputes, and subtracts the store baseline DPS; gated on `offense.supported`, debounced +
  cached, only the hovered node fetches. Gear/slate/memory/spirit still render `nyi` (future
  pass — extend `applyChange` in `useDamageDelta.ts`).
