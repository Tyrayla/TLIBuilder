# Tooltip Source Reference (companion to HANDOFF_TOOLTIPS.md)

This document collects the **actual current source** an agent needs to build the new
tooltip primitive so it matches existing conventions instead of inventing them. Each
excerpt is verbatim from the codebase at the time of writing — re-read the live files
before relying on details, but this captures the shapes, patterns, and look to preserve.

Read [`HANDOFF_TOOLTIPS.md`](docs/HANDOFF_TOOLTIPS.md) first for the overview and the
inventory of every tooltip. This file is the code appendix.

Contents:
1. [`ItemTooltip.tsx`](#1-itemtooltiptsx--the-content-body-pattern-to-generalize) — the content-body pattern to generalize
2. [Element-anchored screen: `TreeViewerScreen.tsx`](#2-element-anchored--scaleeffect-treeviewerscreentsx) — element anchor + `scaleEffect` content logic
3. [Correct clamping: `PactSpiritScreen.tsx`](#3-correct-clamping-measure-then-reposition-pactspiritscreentsx) — the measure-then-reposition pattern to preserve
4. [Tooltip CSS blocks](#4-tooltip-css-blocks-indexcss) — current look for the base `.tooltip` + modifiers
5. [Relevant types from `client.ts`](#5-relevant-types-clientts) — real interfaces to type content bodies against

---

## 1. `ItemTooltip.tsx` — the content-body pattern to generalize

The only existing shared tooltip. It is **content-only with positioning baked in** — it
renders into a portal and computes its own `left/top`. When generalizing, the goal is to
split the *positioning/portal* concern (lines 120–125, 174) from the *content body* (the
JSX inside) so this becomes one content renderer fed by a shared primitive.

Key conventions to match:
- Discriminates `LegendaryGearItem` vs `EquippedGearItem` at runtime via `'variants' in item`.
- Range affixes are reconstructed to display text via `midpoint` / `reconstructAffixText` /
  `tooltipAffixText` (these duplicate logic in `GearScreen.tsx` — de-dupe in the revamp).
- Fixed width `316`, flips left near the right edge, clamps `top`.

Full source (`src/renderer/src/components/ItemTooltip.tsx`):

```tsx
import React from 'react'
import { createPortal } from 'react-dom'
import type {
  LegendaryGearItem, LegendaryAffix, LegendaryNumericValue,
  EquippedGearItem, CustomizedAffix,
} from '../api/client'

export interface ItemTooltipState {
  item: LegendaryGearItem | EquippedGearItem
  x: number
  y: number
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function isLegendaryGearItem(item: LegendaryGearItem | EquippedGearItem): item is LegendaryGearItem {
  return 'variants' in item
}

function getGearTypeLabel(baseType: string): string {
  const b = (baseType ?? '').toLowerCase()
  if (/belt|girdle|waistguard/.test(b)) return 'Belt'
  if (/necklace|pendant|amulet/.test(b)) return 'Amulet'
  if (/\bring\b/.test(b)) return 'Ring'
  if (/crown|helmet|mask|miter|headdress|headscarf|hood/.test(b)) return 'Helmet'
  if (/robe|coat|chestguard|chest armor|outerwear|armor|vest|skin|protection|body/.test(b)) return 'Chest Armor'
  if (/gloves|handguards|gauntlets|wristband|wrists|wristguard|grip/.test(b)) return 'Gloves'
  if (/boots|sabatons|slippers|treads|greaves|shoes|feet/.test(b)) return 'Boots'
  if (/shield/.test(b)) return 'Shield'
  if (/sword|axe|hammer|bow|crossbow|dagger|claw|wand|staff|scepter|musket|pistol|cannon|rod|spear|mace|cudgel|cane/.test(b)) return 'Weapon'
  return ''
}

function getItemImplicits(item: LegendaryGearItem): LegendaryAffix[] {
  const variantKey = Object.keys(item.variants)[0] ?? 'base'
  return item.variants[variantKey]?.implicits ?? []
}

function getItemExplicits(item: LegendaryGearItem): LegendaryAffix[] {
  const variantKey = Object.keys(item.variants)[0] ?? 'base'
  const variant = item.variants[variantKey]
  if (!variant) return []
  const affixes: LegendaryAffix[] = [...variant.explicits]
  const existingCounts: Record<string, number> = {}
  for (const a of variant.explicits) {
    if (a.affix_kind === 'placeholder') existingCounts[a.raw_text] = (existingCounts[a.raw_text] ?? 0) + 1
  }
  const consumed: Record<string, number> = {}
  for (const group of (item.random_affixes[variantKey] ?? [])) {
    const ph = group.placeholder
    const used = consumed[ph] ?? 0
    if (used < (existingCounts[ph] ?? 0)) { consumed[ph] = used + 1 } else {
      affixes.push({ raw_text: ph, modifier_id: null, expression: ph, condition: null, affix_kind: 'placeholder', numeric_values: [] })
    }
  }
  return affixes
}

function hasRangeValues(affix: LegendaryAffix): boolean {
  return affix.affix_kind === 'numeric' && affix.numeric_values.some(v => v.kind === 'range')
}

function decimalPlaces(n: number): number {
  const s = String(n)
  const dot = s.indexOf('.')
  return dot === -1 ? 0 : s.length - dot - 1
}

function rangeDecimals(nv: LegendaryNumericValue): number {
  return Math.max(decimalPlaces(nv.min ?? 0), decimalPlaces(nv.max ?? 0))
}

function midpoint(v: LegendaryNumericValue): number {
  if (v.kind === 'range') {
    const mid = ((v.min ?? 0) + (v.max ?? 0)) / 2
    const dp = rangeDecimals(v)
    return dp > 0 ? parseFloat(mid.toFixed(dp)) : Math.round(mid)
  }
  return v.value ?? 0
}

function reconstructAffixText(affix: LegendaryAffix, chosenValues: Record<number, number>): string {
  let text = affix.raw_text
  for (let i = affix.numeric_values.length - 1; i >= 0; i--) {
    const nv = affix.numeric_values[i]
    if (nv.kind !== 'range') continue
    const chosen = chosenValues[i] ?? midpoint(nv)
    const sign = nv.sign ?? ''
    const dp = rangeDecimals(nv)
    const formatted = dp > 0 ? chosen.toFixed(dp) : String(chosen)
    text = text.replace(nv.raw, `${sign}${formatted}`)
  }
  return text
}

function affixTypeLabel(affixType: string | undefined): string | undefined {
  if (!affixType) return undefined
  if (affixType === 'Base' || affixType === 'Base Affix') return 'Base Affix'
  if (affixType === 'Legendary') return 'Legendary Affix'
  const match = affixType.match(/^(Basic|Advanced|Ultimate)/i)
  return match ? `${match[1]} Affix` : undefined
}

function tooltipAffixText(affix: LegendaryAffix, affixIdx: number, customizations: CustomizedAffix[] | undefined): string {
  if (!hasRangeValues(affix)) return affix.raw_text
  const cust = customizations?.find(c => c.affix_index === affixIdx)
  return reconstructAffixText(affix, cust?.chosen_values ?? {})
}

// ── Component ──────────────────────────────────────────────────────────────────

export function ItemTooltip({ state }: { state: ItemTooltipState }) {
  const customizations = 'customizations' in state.item ? state.item.customizations : undefined
  const baseType = ('base_type' in state.item ? state.item.base_type : undefined) ?? ''
  const typeLabel = getGearTypeLabel(baseType)
  const lgItem = isLegendaryGearItem(state.item) ? state.item : null
  const implicits = lgItem ? getItemImplicits(lgItem) : []
  const explicits = lgItem ? getItemExplicits(lgItem) : []

  const tooltipWidth = 316
  const tooltipLeft = state.x + 16 + tooltipWidth > window.innerWidth ? Math.max(8, state.x - tooltipWidth - 8) : state.x + 16
  const tooltipTop = Math.min(Math.max(8, state.y - 10), window.innerHeight - 360)

  return createPortal(
    <div className="gear-tooltip-portal" style={{ left: tooltipLeft, top: tooltipTop }}>
      {typeLabel && <div className="gear-tooltip-type">{typeLabel}</div>}
      <div className="gear-tooltip-name">{state.item.name}</div>
      {baseType && <div className="gear-tooltip-base">Base: {baseType}</div>}
      <div className="gear-tooltip-level">Required Level: {state.item.required_level}</div>
      <div className="gear-tooltip-divider" />
      {lgItem ? (
        <>
          {implicits.map((affix, i) => (
            <div key={i} className="gear-tooltip-affix gear-tooltip-affix--implicit">{affix.raw_text}</div>
          ))}
          {implicits.length > 0 && explicits.length > 0 && (
            <div className="gear-preview-section-dashes" style={{ margin: '5px 0' }} />
          )}
          {explicits.map((affix, i) => (
            <div key={i} className="gear-tooltip-affix">
              {tooltipAffixText(affix, implicits.length + i, customizations)}
            </div>
          ))}
        </>
      ) : (() => {
        const craftItem = state.item as EquippedGearItem
        const implCount = craftItem.implicit_count ?? 0
        const craftImplicits = craftItem.affixes.slice(0, implCount)
        const craftExplicits = craftItem.affixes.slice(implCount)
        const mutText = craftItem.corrosion_type === 'mutation' ? craftItem.mutation_affix_text : null
        return (
          <>
            {mutText && (
              <div className="gear-tooltip-affix gear-tooltip-affix--corroded">{mutText}</div>
            )}
            {craftImplicits.map((affix, i) => (
              <div key={i} className="gear-tooltip-affix gear-tooltip-affix--implicit">
                {affix.raw_text}
              </div>
            ))}
            {craftImplicits.length > 0 && craftExplicits.length > 0 && (
              <div className="gear-preview-section-dashes" style={{ margin: '5px 0' }} />
            )}
            {craftExplicits.map((affix, i) => (
              <div key={i} className="gear-tooltip-affix">
                {tooltipAffixText(affix, implCount + i, customizations)}
                {affixTypeLabel(affix.affix_type) && <span className="gear-affix-label">({affixTypeLabel(affix.affix_type)})</span>}
              </div>
            ))}
          </>
        )
      })()}
    </div>,
    document.body
  )
}
```

---

## 2. Element-anchored + `scaleEffect` (`TreeViewerScreen.tsx`)

This is the **element-anchored** case (the tooltip is keyed off a node, content scales by
points invested) and it uses a **quadrant flip** for placement (`flipX`/`flipY`) rather than
measure-then-reposition. Note it anchors to `e.clientX/clientY` (cursor) on the node's mouse
events, not the element rect — so it's cursor-anchored in practice, with content driven by
the hovered node id. Contrast with PactSpirit (§3) which anchors to the element rect.

`scaleEffect` is the content logic worth preserving: it multiplies the first number in each
effect string by the rank (points), formatting to 2 decimals when non-integer.

```tsx
// src/renderer/src/screens/TreeViewerScreen.tsx

function scaleEffect(text: string, pts: number): string {
  const rank = Math.max(pts, 1)
  if (rank === 1) return text
  return text.replace(/(\d+(?:\.\d+)?)/, (_, num) => {
    const scaled = parseFloat(num) * rank
    return scaled % 1 === 0 ? String(scaled) : scaled.toFixed(2)
  })
}

interface Tip { nodeId: string; x: number; y: number }
```

State + the per-node mouse handlers:

```tsx
const [tip, setTip] = useState<Tip | null>(null)
// ...
// on each node element:
onMouseEnter={e => setTip({ nodeId: node.id, x: e.clientX, y: e.clientY })}
onMouseLeave={() => setTip(null)}
onMouseMove={e => setTip(t => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
```

Render block (quadrant-flip placement + the `.tooltip` content body):

```tsx
{tip && nodeMap[tip.nodeId] && (() => {
  const node = nodeMap[tip.nodeId]
  const pts = nodeStates[node.id] ?? 0
  const effects = node.effects ?? []
  const atMax = pts >= node.max_points
  const flipX = tip.x > window.innerWidth - 230
  const flipY = tip.y > window.innerHeight - 160
  const tipStyle: React.CSSProperties = {
    left:   flipX ? undefined : tip.x + 14,
    right:  flipX ? window.innerWidth - tip.x + 14 : undefined,
    top:    flipY ? undefined : tip.y + 8,
    bottom: flipY ? window.innerHeight - tip.y + 8 : undefined,
  }
  return (
    <div className="tooltip" style={tipStyle}>
      <div className="tooltip-type">{node.node_type} {pts}/{node.max_points}</div>
      {pts > 0 && effects.length > 0 && (
        <div className="tooltip-stats">
          {effects.map((e, i) => (
            <div key={i} className="tooltip-stat-row">{scaleEffect(e, pts)}</div>
          ))}
        </div>
      )}
      {!atMax && effects.length > 0 && (
        <>
          <div className="tooltip-next-level">Next Level</div>
          <div className="tooltip-stats">
            {effects.map((e, i) => (
              <div key={i} className="tooltip-stat-row">{scaleEffect(e, pts + 1)}</div>
            ))}
          </div>
        </>
      )}
    </div>
  )
})()}
```

---

## 3. Correct clamping (measure-then-reposition) (`PactSpiritScreen.tsx`)

Per the handoff, this is the **only correct clamping implementation** — it anchors to the
hovered element's rect, renders, then in `useLayoutEffect` measures the rendered tooltip and
nudges it back on-screen (and flips below the node if it would clip the top). The new shared
primitive should adopt this measure-then-reposition approach instead of hard-coded height
estimates. The CSS uses `transform: translate(-50%, -100%)` so the tooltip is centered above
the anchor by default (see §4).

State + refs:

```tsx
const [nodeTooltip, setNodeTooltip] = useState<{ lines: string[]; x: number; y: number } | null>(null)
// ...
const tooltipRef = useRef<HTMLDivElement>(null)
const panelRef = useRef<HTMLDivElement>(null)
```

Anchor to the element rect (center-top of the hovered node), not the cursor:

```tsx
const handleNodeEnter = (lines: string[], e: React.MouseEvent) => {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  setNodeTooltip({ lines, x: rect.left + rect.width / 2, y: rect.top - 8 })
}
```

Measure-then-reposition after render:

```tsx
useLayoutEffect(() => {
  if (!nodeTooltip || !tooltipRef.current) return
  const el = tooltipRef.current
  const rect = el.getBoundingClientRect()
  const vw = window.innerWidth
  const overLeft = 8 - rect.left
  const overRight = rect.right - (vw - 8)
  if (overLeft > 0) {
    el.style.left = (parseFloat(el.style.left || '0') + overLeft) + 'px'
  } else if (overRight > 0) {
    el.style.left = (parseFloat(el.style.left || '0') - overRight) + 'px'
  }
  if (rect.top < 8) {
    el.style.top = (nodeTooltip.y + 60) + 'px'
    el.style.transform = 'translateX(-50%)'
  }
}, [nodeTooltip])
```

Element handlers + render (content body = main line + bonus lines):

```tsx
// on each node element:
onMouseEnter={e => handleNodeEnter(tooltipLines, e)}
onMouseLeave={() => setNodeTooltip(null)}

// render:
{nodeTooltip && (
  <div
    ref={tooltipRef}
    className="pact-spirit-node-tooltip"
    style={{ left: nodeTooltip.x, top: nodeTooltip.y }}
  >
    {nodeTooltip.lines.map((line, i) => (
      <div key={i} className={i === 0 ? 'pact-tooltip-main' : 'pact-tooltip-bonus'}>{line}</div>
    ))}
  </div>
)}
```

---

## 4. Tooltip CSS blocks (`index.css`)

All current tooltip styling, so a new base `.tooltip` + modifier set can match the existing
look. These are scattered across the file under separate section headers. Common DNA:
`position: fixed`, dark navy/indigo backgrounds (`#0d0d1e`–`#1e1e32`), `1px` accent border,
`border-radius: 6px`, `pointer-events: none`, high `z-index` (mostly `9999`), and a
`0 4px ~20px rgba(0,0,0,.6)` shadow.

### Generic node tooltip (`.tooltip`) — used by TreeViewer
```css
.tooltip {
  position: fixed;
  background: #0d1b2a;
  border: 1px solid var(--accent);
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 11px;
  color: var(--fg);
  pointer-events: none;
  z-index: 999;
  min-width: 110px;
}
.tooltip-type { color: var(--accent); font-weight: 600; margin-bottom: 4px; font-size: 14px; }
.tooltip-next-level { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #666; margin-top: 6px; margin-bottom: 2px; }
```

### Tooltip stat rows (shared by TreeViewer effect lines)
```css
.tooltip-stats {
  margin-top: 5px;
  border-top: 1px solid #2a2a4a;
  padding-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tooltip-stat-row {
  display: flex;
  gap: 6px;
  font-size: 14px;
}
.tooltip-stat-row span:first-child { color: #8888cc; }
.tooltip-stat-row span:last-child  { color: var(--ok); }
```

### Stat breakdown popup (`.stat-tooltip`) — StatsScreen (click-to-open)
```css
.stat-tooltip {
  position: fixed;
  width: 230px;
  max-height: 320px;
  background: #0d0d22;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
  z-index: 400;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.stat-tooltip-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 10px 12px 8px;
  border-bottom: 1px solid #1e1e3a;
  flex-shrink: 0;
  gap: 8px;
}
.stat-tooltip-name {
  font-size: 12px;
  font-weight: 700;
  color: var(--fg);
  flex: 1;
}
.stat-tooltip-total {
  font-size: 13px;
  font-weight: 700;
  color: #9090e0;
  white-space: nowrap;
}
.stat-tooltip-list {
  overflow-y: auto;
  padding: 4px 0 6px;
}
.stat-tooltip-entry {
  display: flex;
  flex-direction: column;
  padding: 5px 12px 4px;
  border-bottom: 1px solid #111126;
}
.stat-tooltip-entry:last-child { border-bottom: none; }
.stat-tooltip-entry-value {
  font-size: 13px;
  font-weight: 600;
  color: #c8c8e8;
  line-height: 1.3;
}
.stat-tooltip-entry-source {
  font-size: 11px;
  color: #55556a;
  margin-top: 1px;
}
.stat-tooltip-entry-count {
  font-size: 11px;
  font-weight: 400;
  color: #7070a0;
}
```

### Gear item tooltip portal (`.gear-tooltip-*`) — used by ItemTooltip
```css
.gear-tooltip-portal {
  position: fixed;
  z-index: 9999;
  background: #0e0e1e;
  border: 1px solid #3a3a6a;
  border-radius: 6px;
  padding: 10px 12px;
  min-width: 220px;
  max-width: 300px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.65);
  pointer-events: none;
}
.gear-tooltip-type {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #5a5a8a;
  margin-bottom: 2px;
}
.gear-tooltip-name {
  font-size: 13px;
  font-weight: 700;
  color: #c8a050;
  margin-bottom: 2px;
}
.gear-tooltip-base {
  font-size: 11px;
  color: #7070aa;
  margin-bottom: 2px;
}
.gear-tooltip-level {
  font-size: 11px;
  color: #666;
  margin-bottom: 6px;
}
.gear-tooltip-divider {
  border-top: 1px solid #2a2a3a;
  margin-bottom: 6px;
}
.gear-tooltip-section-line {
  border-top: 1px solid #2a2a3a;
  margin: 4px 0 6px;
}
.gear-tooltip-affix {
  font-size: 11px;
  color: #aaa;
  line-height: 1.5;
  margin-bottom: 1px;
}
.gear-tooltip-affix--implicit {
  color: #8888cc;
}
/* NOTE: .gear-tooltip-affix--corroded is referenced in ItemTooltip.tsx but has no
   dedicated rule — it inherits .gear-tooltip-affix. The corroded color (#c678dd) is
   only defined for the GearScreen preview rows (.gear-affix-row--corroded). Worth
   unifying in the revamp. */
```

### Affix label + section divider (referenced by ItemTooltip for crafted affixes)
```css
.gear-affix-label {
  font-size: 12px;
  color: #c8c4a0;
  line-height: 1.4;
}
.gear-preview-section-dashes {
  flex: 1;
  height: 1px;
  background: #252535;
}
```

### Gear base-type implicit tooltip (`.gear-base-stat-tooltip`) — GearScreen
```css
.gear-base-stat-tooltip {
  position: fixed;
  z-index: 9999;
  background: #0d0d1e;
  border: 1px solid #4a4a8a;
  border-radius: 6px;
  padding: 8px 12px;
  min-width: 180px;
  max-width: 260px;
  pointer-events: none;
}
.gear-base-stat-tooltip-name {
  font-size: 12px;
  font-weight: 700;
  color: #c8a050;
  margin-bottom: 5px;
}
.gear-base-stat-tooltip-stat {
  font-size: 11px;
  color: #8888cc;
  line-height: 1.5;
}
```

### Affix-value slider hover (`.gear-slider-tooltip`) — GearScreen
```css
.gear-slider-tooltip {
  position: fixed;
  z-index: 9999;
  background: #0d0d1e;
  border: 1px solid #4a4a8a;
  border-radius: 6px;
  padding: 8px 14px;
  font-size: 13px;
  color: #c8c4a0;
  pointer-events: none;
  box-shadow: 0 4px 16px rgba(0,0,0,0.65);
  white-space: nowrap;
  max-width: 380px;
  margin-bottom: 16px;
}
```

### Base-item dropdown tooltip (`.gear-base-item-tooltip`) — GearScreen `BaseItemSelect`
```css
.gear-base-item-tooltip {
  position: fixed;
  z-index: 9999;
  background: #10101c;
  border: 1px solid #4040a0;
  border-radius: 6px;
  padding: 10px 12px;
  min-width: 180px;
  max-width: 280px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.7);
  pointer-events: none;
}
.gear-base-item-tooltip-name {
  font-size: 12px;
  font-weight: 600;
  color: #e0e0ff;
  margin-bottom: 4px;
}
.gear-base-item-tooltip-level {
  font-size: 10px;
  color: #6060a0;
  margin-bottom: 6px;
}
.gear-base-item-tooltip-stat {
  font-size: 11px;
  color: #8888cc;
  font-style: italic;
  line-height: 1.5;
}
```

### Skill hover tooltip (`.skill-tooltip`) — SkillsScreen
```css
.skill-tooltip {
  position: fixed;
  z-index: 9999;
  pointer-events: none;
  background: #0c0c20;
  border: 1px solid #3a3a6a;
  border-radius: 6px;
  padding: 10px 12px;
  max-width: 280px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.65);
}
.skill-tooltip-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--gold);
  margin-bottom: 6px;
}
.skill-tooltip-desc p {
  font-size: 11px;
  color: #9090aa;
  line-height: 1.5;
  margin: 0 0 2px;
}
```

### Pact spirit node tooltip (`.pact-spirit-node-tooltip`) — note the centered-above transform
```css
.pact-spirit-node-tooltip {
  position: fixed;
  z-index: 9999;
  transform: translate(-50%, -100%);
  background: #1e1e32;
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 6px;
  padding: 7px 11px;
  font-size: 12px;
  color: #d0d0f0;
  pointer-events: none;
  max-width: 300px;
  line-height: 1.45;
  box-shadow: 0 4px 16px rgba(0,0,0,0.6);
  margin-top: -4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pact-tooltip-main {
  color: #e8e8ff;
  font-weight: 500;
}
.pact-tooltip-bonus {
  color: rgba(220,220,255,0.65);
  font-size: 11px;
  padding-left: 4px;
  border-left: 2px solid rgba(255,180,80,0.4);
}
```

> Other tooltip-ish classes not reproduced here (grep `tooltip` in `index.css`):
> `.memory-affix-hover-tooltip` (HeroTrait), a "Floating info tooltip" block (~line 3250),
> and the HeroTrait trait-card styles. They follow the same DNA.

---

## 5. Relevant types (`client.ts`)

The real interfaces the content bodies are typed against. Type the new content renderers
against these directly — do not re-declare shapes.

### Gear shapes (for the ItemTooltip content body)
```ts
export interface LegendaryNumericValue {
  kind: 'range' | 'fixed'
  sign: string | null
  // range
  min?: number
  max?: number
  // fixed
  value?: number
  raw: string
}

export interface LegendaryAffix {
  raw_text: string
  modifier_id: string | null
  expression: string
  condition: string | null
  affix_kind: 'numeric' | 'special' | 'tagged' | 'placeholder' | 'implicit'
  numeric_values: LegendaryNumericValue[]
  // resolved by backend at load time
  stat_key?: string | null
  stat_keys?: string[]
  is_range_split?: boolean
  min_stat_keys?: string[]
  max_stat_keys?: string[]
  dual_stat_groups?: DualStatGroup[]
  unit?: string
  // set for crafted/vorax items: 'Base' | 'Basic Affix' | 'Advanced Affix' | 'Ultimate Affix' | 'Legendary'
  affix_type?: string
  // resolved by backend: structured engine expression if condition text was mapped
  condition_expr?: Record<string, unknown> | string | null
}

export interface LegendaryGearVariant {
  implicits: LegendaryAffix[]
  explicits: LegendaryAffix[]
}

export interface LegendaryRandomAffixGroup {
  placeholder: string
  options: LegendaryAffix[]
}

export interface LegendaryGearItem {
  item_id: string
  name: string
  internal_id: number | null
  base_type: string
  required_level: number
  drop_level: number | null
  flavor_text: string | null
  drop_sources: string[]
  glossary: Record<string, { name: string; description: string }>
  variants: Record<string, LegendaryGearVariant>
  random_affixes: Record<string, LegendaryRandomAffixGroup[]>
}

export type GearSlot = 'helmet' | 'amulet' | 'chest' | 'gloves' | 'belt'
                     | 'boots' | 'ring1' | 'ring2' | 'weapon1' | 'weapon2'

export interface CustomizedAffix {
  affix_index: number
  chosen_values: Record<number, number>   // value_index → chosen number
  chosen_placeholder_key: string | null
}

export interface EquippedGearItem {
  item_id: string
  name: string
  required_level: number
  affixes: LegendaryAffix[]
  customizations: CustomizedAffix[]
  slot: GearSlot | GearSlot[] | null
  base_type?: string
  is_crafted?: boolean
  is_vorax?: boolean
  legendary_source?: string | null
  legendary_affix_count?: number
  base_stats?: Record<string, number>
  implicit_count?: number
  craft_slot_positions?: number[]
  corrosion_type?: 'none' | 'desecration' | 'mutation'
  corroded_explicit_indices?: number[]
  mutation_affix_text?: string | null
  mutation_resolved_affix?: LegendaryAffix | null
  selected_random_affixes?: Record<number, string>
}
```
> `DualStatGroup` is referenced by `LegendaryAffix.dual_stat_groups` — see `client.ts` for
> its (optional) definition; not needed for the basic tooltip body.

### Node-effect shape (for the TreeViewer content body)
Node effects are just `string[]` (display-ready lines that `scaleEffect` mutates client-side):
```ts
export interface TreeNode {
  id: string
  column: number
  row: number
  max_points: number
  node_type: string
  current_points: number
  effects: string[]
}

export interface CoreTalentSlotOption {
  id: string
  name: string
  effects: string[]
}
```

### Pact spirit shape (for the PactSpirit content body)
The PactSpirit tooltip `lines: string[]` are assembled in-screen from these fields:
```ts
export interface PactSpirit {
  item_id: string
  name: string
  description: string
  affinities: string[]
  main_skill_name: string
  main_skill_effect: string
  upgrade_ranks: PactSpiritRank[]
  slots: PactSpiritSlot[]
  glossary: Record<string, { name: string; description: string }>
}
```

### Skill shape (for the SkillsScreen content body)
The skill tooltip uses `name` + `description_lines` (trimmed by `getAdvancedLines`):
```ts
export interface SkillItem {
  // ...
  description_lines: string[]
  // ...
}
```
