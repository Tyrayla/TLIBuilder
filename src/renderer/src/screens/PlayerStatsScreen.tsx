import React, { useState, useMemo, useEffect, useContext, useRef, useLayoutEffect } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { useBuildStore } from '../store/buildStore'
import { useUiPrefs } from '../store/uiPrefsStore'
import type { OffenseResult, DefenseResult, EquippedSkill, StatEntry, EquippedGearItem, TargetStats, BlessingSummary, SkillItem, AuraSummary, ReservationResult, ReservationSummary, CurseSummary, CurseMeta, EmpowerSummary, HeroTrait } from '../api/client'
import { api, buildSpiritEffects, buildMemoryEffects, MEMORY_RARITY_COLORS } from '../api/client'
import { useReferenceStore } from '../store/referenceStore'
import { TraitTooltipBody } from './HeroTraitScreen'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { GearTooltipBody } from '../components/tooltip/bodies/GearTooltipBody'
import { SpiritTooltipBody } from '../components/tooltip/bodies/SpiritTooltipBody'
import { SkillTooltipBody } from '../components/tooltip/bodies/SkillTooltipBody'
import { StructuredSkillTooltipBody } from '../components/tooltip/bodies/StructuredSkillTooltipBody'
import { MiniTree } from '../components/MiniTree'
import { gearQualityColor } from '../utils/gearItem'
import { sourceKindLabel, sourceKindColor } from '../utils/sourceKind'
import { dec } from '../utils/num'

// ── Source breakdown ────────────────────────────────────────────────────────────
// Hover a stat/cell to open its breakdown; click to pin; click-off / Escape closes (the existing
// useFloatingTooltip pinnable+interactive mode). Shows a Min/Max/Total header + a
// Value · Stat · Source · Source Name table, plus a "Skill-specific (slot N)" group for slot-local
// contributions (supports / skill self-buffs that fold into a slot's offense, not the character total).

interface BreakdownCtxValue {
  statMap: Record<string, StatEntry>
  gear: EquippedGearItem[]
  // sourceName → its effect lines, for the spirit/memory/support hover tooltips. Built once at the root.
  sourceLines: Map<string, string[]>
  // tree name → its branch color (War/Knowledge/Hunting/…), for coloring talent + core-talent sources.
  treeColors: Record<string, string>
  // memory name ("Memory of Origin") → its rarity color, for coloring hero-memory sources.
  memoryColors: Record<string, string>
  // skill/support name → catalog SkillItem (carries the structured `tooltip` spec) for the new
  // contribution hover; and support name → its equipped level/rolls so the spec resolves at the right tier.
  skillsByName: Record<string, SkillItem> | null
  supportInstances: Record<string, { level: number; specific_rolls?: Record<string, number> }>
  // hero-trait source name (node name) → the granting node's tooltip data (same tooltip as the Hero Trait
  // screen). null when the name doesn't resolve to a node on the selected trait.
  traitNodeTooltip: (sourceName: string) => { name: string; level: number; effects: string[]; moonEffects?: string[] } | null
  // The skill slot currently being viewed — slot-local contributions are filtered to this so a stat's
  // breakdown shows only the selected skill's supports (plus global sources), never another slot's.
  selectedSlot: number
}

const MEMORY_NAMES: Record<string, string> = {
  origin: 'Memory of Origin', discipline: 'Memory of Discipline', progress: 'Memory of Progress',
}
const BreakdownCtx = React.createContext<BreakdownCtxValue | null>(null)

interface Collected {
  statKey: string; statName: string; unit: string
  source_type: string; label: string; text: string; source_name: string | null
  amount: number; points: number; slot: number | null
}

function collectSources(keys: string[], stats: Record<string, StatEntry>): { main: Collected[]; slot: Collected[] } {
  const main: Collected[] = []
  const slot: Collected[] = []
  for (const k of keys) {
    const entry = stats[k]
    if (!entry) continue
    const base = { statKey: k, statName: entry.display_name || k, unit: entry.unit || '' }
    for (const s of entry.sources ?? [])
      main.push({ ...base, source_type: s.source_type, label: s.label, text: s.text, source_name: s.source_name ?? null, amount: s.amount, points: s.points, slot: s.slot ?? null })
    for (const s of entry.slot_sources ?? [])
      slot.push({ ...base, source_type: s.source_type, label: s.label, text: s.text, source_name: s.source_name ?? null, amount: s.amount, points: s.points, slot: s.slot ?? null })
  }
  return { main, slot }
}

type GroupedCollected = Collected & { count: number }
function groupCollected(list: Collected[]): GroupedCollected[] {
  const out: GroupedCollected[] = []
  for (const c of list) {
    const m = out.find(g => g.text === c.text && g.label === c.label && g.statKey === c.statKey && g.slot === c.slot)
    if (m) m.count += c.points ?? 1
    else out.push({ ...c, count: c.points ?? 1 })
  }
  return out
}

function fmtSourceValue(c: Collected): string {
  const v = c.amount
  // Increased/additional pools are stored as fractions (0.09 = 9%) — show them as percent, not "0.09%".
  if (c.unit === '%') {
    const p = v * 100
    const s = Math.abs(p % 1) < 1e-9 ? p.toFixed(0) : dec(p)
    return `${v > 0 ? '+' : ''}${s}%`
  }
  const s = v % 1 === 0 ? v.toFixed(0) : dec(v)
  return `${v > 0 ? '+' : ''}${s}`
}

// Grid shared by the breakdown header + each source row: Value · Stat · Source · Source Name.
// Value/Stat/Source size to their content (Stat is often a single repeated name like "Max Life", so it
// shouldn't eat width); Source Name is the only flexible track, absorbing slack and truncating long names.
const BD_GRID = 'auto auto auto minmax(0,1fr)'

// Format a breakdown TOTAL: '%' unit treats the value as a fraction (0.6 → "60%"); else plain number.
function fmtTotalVal(v: number, unit: string): string {
  if (unit === '%') return `${dec(v * 100)}%`   // up to 2 decimals, trims trailing zeros (14.44%, 50%)
  if (unit === '×') return `×${dec(v)}`   // multiplier pools (e.g. Total Additional = Π(1+x))
  return v % 1 === 0 ? v.toFixed(0) : dec(v)
}

// The title + Total header shared by the main breakdown and each section, so they look identical.
function BreakdownHeader({ title, total, totalUnit, formula }: { title: string; total?: number; totalUnit?: string; formula?: string }) {
  return (
    <>
      <div style={{ marginBottom: 3 }}>
        <span style={{ fontWeight: 700, color: '#cfcfe6' }}>{title}</span>
        {formula && <span style={{ fontWeight: 400, color: '#bdb4e6', fontSize: 11, marginLeft: 8, fontVariantNumeric: 'tabular-nums' }}>{formula}</span>}
      </div>
      {total !== undefined && (
        <div style={{ marginBottom: 6, display: 'flex', alignItems: 'baseline', gap: 12 }}>
          <span style={{ fontSize: 10, color: '#888' }}>Total</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: '#e8e8f4', fontVariantNumeric: 'tabular-nums' }}>{fmtTotalVal(total, totalUnit ?? '')}</span>
        </div>
      )}
    </>
  )
}

// Column header row (subgrid) shared by the main table + each section table.
function BreakdownColHeader() {
  return (
    <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: 'subgrid', fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: '#666', paddingBottom: 3, borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
      <span style={{ textAlign: 'right' }}>Value</span><span>Stat</span><span>Source</span><span>Source Name</span>
    </div>
  )
}

// One breakdown row: Value · Stat · Source(type+context) · Source Name. The Source Name hovers a
// type-appropriate tooltip — gear → item tooltip + unequip delta, talent → mini tree, spirit/memory/
// support → their effect lines.
function BreakdownSourceRow({ g, ctx }: { g: GroupedCollected; ctx: BreakdownCtxValue }) {
  const isGear = g.source_type === 'gear' || g.source_type === 'normal_gear' || g.source_type === 'legendary_gear'
  const isTalent = g.source_type === 'talent' || g.source_type === 'slate'
  const isLines = g.source_type === 'pact_spirit' || g.source_type === 'hero_memory' || g.source_type === 'support' || g.source_type === 'aura'

  // Gear: the backend carries the item NAME in source_name → match the equipped item for its tooltip.
  // Two dual-wield weapons share the SAME name, so name-only would always match the first; disambiguate by the
  // slot encoded in the label ("Gear · Weapon 1"/"Weapon 2" → weapon1/weapon2) and fall back to name-only.
  const _byName = (it: { name: string }) => it.name === g.source_name || it.name === g.text || it.name === g.label
  const _labelSlot = g.label.startsWith('Gear · ') ? g.label.slice(7).toLowerCase().replace(/\s+/g, '') : null
  const _slotMatches = (s: unknown) => _labelSlot == null ? true
    : Array.isArray(s) ? s.map(String).map(x => x.toLowerCase()).includes(_labelSlot)
    : String(s).toLowerCase() === _labelSlot
  const matchedItem = isGear
    ? (ctx.gear.find(it => _byName(it) && _slotMatches((it as { slot?: unknown }).slot)) ?? ctx.gear.find(_byName))
    : undefined
  // Talent: tree name + node id from the "Tree · node_id" label; the mini tree highlights the node.
  const hasNodeLabel = g.label.includes(' · ')
  const treeName = g.source_name || (hasNodeLabel ? g.label.split(' · ')[0] : g.label)
  const nodeId = hasNodeLabel ? g.label.split(' · ').slice(-1)[0] : ''
  // Support keeps its full effect list (that's the gem's identity, not stacked ranks). Pact spirit /
  // hero memory show ONLY this contribution's own line — not the spirit's entire rank/value dump
  // (hovering a single "+8% Attack Speed" row used to list every modifier the spirit grants).
  const lines = !isLines ? []
    : g.source_type === 'support'
      ? (g.source_name ? (ctx.sourceLines.get(g.source_name) ?? []) : [])
      // Aura buff text carries a " |aura|<id>" pooling-identity suffix — strip it for the tooltip.
      : g.source_type === 'aura'
        ? (g.text ? [g.text.replace(/\s*\|aura\|.*$/, '')] : [])
        : (g.text ? [g.text] : [])

  // Support contribution → prefer the structured, level-aware tooltip (same one the Skills screen uses)
  // when its catalog SkillItem (with a tooltip spec) is found by name. Resolve at the equipped tier.
  const supSkill = g.source_type === 'support' && g.source_name ? ctx.skillsByName?.[g.source_name] : undefined
  const supSpec = supSkill?.tooltip
  const supInst = g.source_name ? ctx.supportInstances[g.source_name] : undefined

  // Hero trait: resolve the granting node → its full tooltip (same as the Hero Trait screen).
  const traitNode = g.source_type === 'hero_trait' && g.source_name ? ctx.traitNodeTooltip(g.source_name) : null

  const hasHover = !!matchedItem || (isTalent && !!nodeId) || !!supSpec || (isLines && lines.length > 0) || !!traitNode
  const tip = useFloatingTooltip({ anchor: 'element', side: 'left', interactive: true })

  // Color by attribution (pure display — no recompute): gear → rarity/legendary color; talent + core talent
  // → their tree's branch color; hero memory → its rarity color; else the flat source-type color.
  const kindColor = matchedItem ? gearQualityColor(matchedItem)
    : isTalent ? (ctx.treeColors[treeName] ?? sourceKindColor(g.source_type))
    : g.source_type === 'core_talent' ? (ctx.treeColors[g.source_name ?? ''] ?? sourceKindColor(g.source_type))
    : g.source_type === 'hero_memory' ? (ctx.memoryColors[g.source_name ?? ''] ?? sourceKindColor(g.source_type))
    : sourceKindColor(g.source_type)
  // Source column = type+context. Gear shows just its slot (drop the "Gear · " prefix → "Weapon 1");
  // everything else uses the short kind ("Pact Spirit", "Tree", …).
  const sourceLabel = isGear ? g.label.replace(/^Gear · /, '') : sourceKindLabel(g.source_type)
  // Character baselines (50+13/level life, etc.) carry the value+scaling in their text; the scaling now
  // lives in the breakdown's top formula, so the Source Name shows a clean identity instead ("Base
  // Character" for the base, else the role: Gear / Levels / Prism).
  const charName = g.source_type === 'character'
    ? (() => { const sub = g.label.replace(/^Character · /, ''); return sub === 'Base' || !sub ? 'Base Character' : sub })()
    : null
  // Core talents show the NODE name (from the "Core · <node>" label, e.g. "Play Safe") rather than just the
  // granting tree — more specific, and the tree still drives the row color above. Other talents show the tree.
  const coreName = g.source_type === 'core_talent' && hasNodeLabel
    ? g.label.split(' · ').slice(1).join(' · ')
    : null
  // Source Name column = the real name (item / spirit / memory / support / tree); talents show just the tree.
  const sourceName = coreName || g.source_name || charName || (isTalent ? treeName : (g.text || g.label || '—'))

  return (
    <>
      <div {...(hasHover ? tip.triggerProps : {})}
        style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: 'subgrid', alignItems: 'start', padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: hasHover ? 'help' : undefined, outline: tip.open ? '1px solid #fff' : undefined, outlineOffset: tip.open ? 3 : undefined, background: tip.open ? 'rgba(255,255,255,0.06)' : undefined }}>
        <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', textAlign: 'right' }}>
          {g.count > 1 && <span style={{ color: '#666' }}>×{g.count} </span>}{fmtSourceValue(g)}
        </span>
        <span style={{ color: '#888', whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{g.statName}</span>
        <span style={{ color: kindColor, fontSize: 10, whiteSpace: 'nowrap' }}>{sourceLabel}</span>
        <span style={{ color: kindColor, whiteSpace: 'normal', overflowWrap: 'anywhere', textDecoration: hasHover ? 'underline dotted' : undefined }}>
          {sourceName}
        </span>
      </div>
      {hasHover && tip.open && (
        <FloatingPortal>
          {matchedItem ? (
            <div className="tooltip tooltip--gear" {...tip.floatingProps}><GearTooltipBody item={matchedItem} hideBadges /></div>
          ) : isTalent ? (
            <div className="tooltip" {...tip.floatingProps}><MiniTree treeName={treeName} nodeId={nodeId} /></div>
          ) : supSpec ? (
            <div className="tooltip tooltip--skill" {...tip.floatingProps}>
              <StructuredSkillTooltipBody spec={supSpec} level={supInst?.level ?? supSpec.default_level}
                                          specificRolls={supInst?.specific_rolls} />
            </div>
          ) : traitNode ? (
            <div className="trait-info-card" {...tip.floatingProps}>
              <TraitTooltipBody name={traitNode.name} slotLevel={traitNode.level}
                                effects={traitNode.effects} moonEffects={traitNode.moonEffects} />
            </div>
          ) : (
            <div className="tooltip" {...tip.floatingProps}>
              {g.source_type === 'support' ? <SkillTooltipBody lines={lines} /> : <SpiritTooltipBody lines={lines} />}
            </div>
          )}
        </FloatingPortal>
      )}
    </>
  )
}

// A non-source contribution shown verbatim in a breakdown (e.g. an intrinsic baseline like a spell's
// base crit rating or the ×1.5 base crit multiplier) — no stat_map source backs it.
interface ExtraRow { value: string; stat: string; source: string; sourceName: string }

// A secondary labelled group inside a breakdown (e.g. "Max Fire Resistance" under "Fire Resistance"),
// with its own baseline rows + stat_map sources.
interface BreakdownSection { label: string; keys: string[]; extra?: ExtraRow[]; formula?: string; total?: number; totalUnit?: string }

// One static (non-source) row, used for baselines + section extras.
function ExtraRowView({ e }: { e: ExtraRow }) {
  return (
    <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: 'subgrid', alignItems: 'start', padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', textAlign: 'right' }}>{e.value}</span>
      <span style={{ color: '#888', whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{e.stat}</span>
      <span style={{ color: '#8a8aa0', fontSize: 10, whiteSpace: 'nowrap' }}>{e.source}</span>
      <span style={{ color: '#8a8aa0', whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{e.sourceName}</span>
    </div>
  )
}

function BreakdownBody({ title, keys, ctx, totalOverride, totalUnit, extra, formula, sections }: { title: string; keys: string[]; ctx: BreakdownCtxValue; totalOverride?: number; totalUnit?: string; extra?: ExtraRow[]; formula?: string; sections?: BreakdownSection[] }) {
  const { main, slot } = collectSources(keys, ctx.statMap)
  // When a row passes its already-derived value (e.g. Max Energy Shield = flat × (1+increased)), show THAT
  // as the header — summing mixed flat/increased/additional keys is meaningless (it printed "0.27" for a 0
  // ES with 27% increased). Otherwise (single-pool breakdowns like "Increased — All Types") sum the keys.
  const headerVal = totalOverride !== undefined ? totalOverride : keys.reduce((s, k) => s + (ctx.statMap[k]?.total ?? 0), 0)
  const headerUnit = totalOverride !== undefined ? (totalUnit ?? '') : (ctx.statMap[keys[0]]?.unit ?? '')
  const groupedMain = groupCollected(main)
  const slotGroups = new Map<number, GroupedCollected[]>()
  for (const g of groupCollected(slot)) {
    const k = g.slot ?? 0
    if (k !== ctx.selectedSlot) continue   // show only the slot being viewed — no cross-slot leak
    if (!slotGroups.has(k)) slotGroups.set(k, [])
    slotGroups.get(k)!.push(g)
  }
  const empty = groupedMain.length === 0 && slotGroups.size === 0 && !(extra && extra.length) && !(sections && sections.length)
  return (
    <div style={{ minWidth: 340, maxWidth: 520, fontSize: 11 }}>
      <BreakdownHeader title={title} total={headerVal} totalUnit={headerUnit} formula={formula} />
      {empty ? <div style={{ color: '#555' }}>No sources found</div> : (
        // ONE grid so every column sizes to the widest entry across ALL rows (header + extras + sources);
        // each row is a subgrid spanning all columns so it keeps its own box (hover/outline) while its
        // cells snap to the shared column tracks. columnGap lives on the parent; subgrids inherit it.
        <div style={{ display: 'grid', gridTemplateColumns: BD_GRID, columnGap: 8, padding: '0 8px' }}>
          <BreakdownColHeader />
          {(extra ?? []).map((e, i) => <ExtraRowView key={`e${i}`} e={e} />)}
          {groupedMain.map((g, i) => <BreakdownSourceRow key={`m${i}`} g={g} ctx={ctx} />)}
          {[...slotGroups.entries()].map(([slotNo, rows]) => (
            <React.Fragment key={`s${slotNo}`}>
              <div style={{ gridColumn: '1 / -1', fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: '#7a9af0', margin: '6px 0 2px' }}>
                Skill-specific (slot {slotNo})
              </div>
              {rows.map((g, i) => <BreakdownSourceRow key={`s${slotNo}-${i}`} g={g} ctx={ctx} />)}
            </React.Fragment>
          ))}
          {/* Each section is its own titled mini-table sharing the same column tracks (same size/style as
              the main breakdown), separated by a divider. */}
          {(sections ?? []).map((sec, si) => {
            const secRows = groupCollected(collectSources(sec.keys, ctx.statMap).main)
            return (
              <React.Fragment key={`sec${si}`}>
                <div style={{ gridColumn: '1 / -1', marginTop: 10, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                  <BreakdownHeader title={sec.label} total={sec.total} totalUnit={sec.totalUnit} formula={sec.formula} />
                </div>
                <BreakdownColHeader />
                {(sec.extra ?? []).map((e, i) => <ExtraRowView key={`sec${si}-e${i}`} e={e} />)}
                {secRows.map((g, i) => <BreakdownSourceRow key={`sec${si}-r${i}`} g={g} ctx={ctx} />)}
              </React.Fragment>
            )
          })}
        </div>
      )}
    </div>
  )
}

// Wrap any value/label to make it a hover-open, click-pin source breakdown. No-op (renders children
// only) outside a BreakdownCtx provider.
function Breakdown({ title, keys, children, block, total, totalUnit, extra, formula, sections }: { title: string; keys: string[]; children: React.ReactNode; block?: boolean; total?: number; totalUnit?: string; extra?: ExtraRow[]; formula?: string; sections?: BreakdownSection[] }) {
  const ctx = useContext(BreakdownCtx)
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right', trigger: 'hover', pinnable: true, interactive: true, openDelay: 90 })
  if (!ctx) return <>{children}</>
  return (
    <>
      <span {...tip.triggerProps} style={{ cursor: 'pointer', display: block ? 'block' : undefined, outline: tip.open ? '1px solid #fff' : undefined, outlineOffset: 3, background: tip.open ? 'rgba(255,255,255,0.06)' : undefined }}>{children}</span>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--breakdown" {...tip.floatingProps}>
            <BreakdownBody title={title} keys={keys} ctx={ctx} totalOverride={total} totalUnit={totalUnit} extra={extra} formula={formula} sections={sections} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const DTYPE_COLOR: Record<string, string> = {
  physical:  '#e0d0b0',
  fire:      '#e87030',
  cold:      '#60b8e8',
  lightning: '#e0d040',
  erosion:   '#80c878',
}

// Attribute colors (match the in-game tags): STR red, DEX green, INT blue.
const ATTR_COLOR: Record<string, string> = {
  strength:     '#e0726a',
  dexterity:    '#7fc97f',
  intelligence: '#6fa8e0',
}

function fmtNum(n: number): string {
  if (n >= 1_000_000_000_000_000) return `${dec((n / 1_000_000_000_000_000))}Q`
  if (n >= 1_000_000_000_000)     return `${dec((n / 1_000_000_000_000))}T`
  if (n >= 1_000_000_000)         return `${dec((n / 1_000_000_000))}B`
  if (n >= 1_000_000)             return `${dec((n / 1_000_000))}M`
  if (n >= 100_000)               return `${dec((n / 1_000))}k`
  return n.toFixed(0)
}

function fmtResistValue(capped: number, raw: number): React.ReactNode {
  const cappedStr = `${capped.toFixed(0)}%`
  const display = raw > capped ? `${cappedStr} (${raw.toFixed(0)}% total)` : cappedStr
  let color = '#e0e0e0'
  if (capped >= 60) color = '#6ddb6d'
  else if (capped >= 30) color = '#e0c050'
  else color = '#e05050'
  return <span style={{ color }}>{display}</span>
}

// ── Layout primitives ─────────────────────────────────────────────────────────

function Row({ label, children, labelColor, onClick, expandable, expanded, breakdown }: {
  label: string; children: React.ReactNode; labelColor?: string;
  onClick?: (e: React.MouseEvent) => void;
  expandable?: boolean; expanded?: boolean;
  breakdown?: { title: string; keys: string[]; total?: number; totalUnit?: string; extra?: ExtraRow[]; formula?: string; sections?: BreakdownSection[] };
}) {
  const ctx = useContext(BreakdownCtx)
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right', trigger: 'hover', pinnable: true, interactive: true, openDelay: 90 })
  const bd = !!breakdown && !!ctx
  return (
    <>
      {/* When this is a breakdown row, spread tip.triggerProps (incl. its click-to-pin onClick) and do
          NOT add our own onClick — an explicit onClick here (even undefined) overrides the pin handler. */}
      <div {...(bd ? tip.triggerProps : {})}
        style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 12, borderBottom: '1px solid rgba(255,255,255,0.03)', cursor: (bd || onClick) ? 'pointer' : undefined, outline: bd && tip.open ? '1px solid #fff' : undefined, outlineOffset: bd && tip.open ? 3 : undefined, background: bd && tip.open ? 'rgba(255,255,255,0.06)' : undefined }}
        {...(!bd && onClick ? { onClick } : {})}>
        <span style={{ color: labelColor ?? '#999' }}>
          {expandable && <span style={{ display: 'inline-block', width: 10, fontSize: 8, color: '#555', marginRight: 2 }}>{expanded ? '▾' : '▸'}</span>}
          {label}
        </span>
        <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums' }}>{children}</span>
      </div>
      {bd && tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--breakdown" {...tip.floatingProps}>
            <BreakdownBody title={breakdown!.title} keys={breakdown!.keys} ctx={ctx!} totalOverride={breakdown!.total} totalUnit={breakdown!.totalUnit} extra={breakdown!.extra} formula={breakdown!.formula} sections={breakdown!.sections} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

function StatPanel({
  title,
  accent,
  children,
  defaultCollapsed = false,
  info,
}: {
  title: string
  accent: string
  children: React.ReactNode
  defaultCollapsed?: boolean
  // Optional explanatory prose (the old grey description/formula text). Surfaced on a CLICK of the title rather
  // than printed inline — keeps the box uncluttered while the detail stays one click away.
  info?: string
}) {
  // Collapsing is opt-in (Settings → Display). When off, the box is always expanded and shows no +/− control.
  const collapsible = useUiPrefs(s => s.collapsiblePanels)
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  const tip = useFloatingTooltip({ anchor: 'element', side: 'bottom', trigger: 'click', interactive: true })
  const showCollapsed = collapsible && collapsed
  return (
    <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderLeft: `3px solid ${accent}`, borderRadius: 4, marginBottom: 6 }}>
      <div
        style={{
          // Uniform cool-charcoal header across every box (category is conveyed by the accent left border, not the
          // header tint) so Channeled / Skill Effects / Skill Damage etc. all read the same — but with a bit more
          // depth/color than a flat grey.
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '5px 10px', background: 'rgba(86,98,130,0.18)', userSelect: 'none',
        }}
      >
        <span
          {...(info ? tip.triggerProps : {})}
          style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: '#ccc', cursor: info ? 'help' : 'default', outline: info && tip.open ? '1px solid #fff' : undefined, outlineOffset: 3 }}
        >
          {title}{info ? <span style={{ color: '#888', fontWeight: 400, marginLeft: 5 }}>ⓘ</span> : null}
        </span>
        {collapsible && (
          <span onClick={() => setCollapsed(c => !c)} style={{ color: '#888', fontSize: 13, lineHeight: 1, cursor: 'pointer', padding: '0 2px' }}>
            {collapsed ? '+' : '−'}
          </span>
        )}
      </div>
      {info && tip.open && (
        <FloatingPortal>
          <div className="tooltip" {...tip.floatingProps} style={{ ...(tip.floatingProps as { style?: React.CSSProperties }).style, maxWidth: 320, fontSize: 11, lineHeight: 1.4, padding: '8px 10px', color: '#cfd6e6' }}>
            {info}
          </div>
        </FloatingPortal>
      )}
      {!showCollapsed && <div style={{ padding: '6px 10px' }}>{children}</div>}
    </div>
  )
}

// ── Skill selector ────────────────────────────────────────────────────────────

// Slot → human label. Slots 1-5 active (1 = main), 6-9 passive (slot = index + 1).
function slotLabel(slot: number): string {
  if (slot === 1) return 'Main Skill Slot'
  if (slot >= 2 && slot <= 5) return `Active Slot ${slot}`
  if (slot >= 6 && slot <= 9) return `Passive Slot ${slot - 5}`
  return `Slot ${slot}`
}


// Calculation modes — only "full_uptime" is wired today (≈ the engine's current "max"); the rest are stubbed
// placeholders for a future uptime/scenario pass (Phase 2).
// Enemy type → Enemy-Count weight for "for each enemy" lines (Normal/Magic 1, Rare 2, Boss 5). Set via the
// enemy_count_weight condition; Boss (5) is the training-dummy default so unset builds are unchanged.
const ENEMY_TYPES: { label: string; weight: number }[] = [
  { label: 'Boss', weight: 5 },
  { label: 'Rare', weight: 2 },
  { label: 'Normal', weight: 1 },
]

const CALC_MODES: { key: string; label: string; enabled: boolean }[] = [
  { key: 'full_uptime', label: 'Full Uptime', enabled: true },
  { key: 'effective', label: 'Effective', enabled: false },
  { key: 'mapping', label: 'Mapping', enabled: false },
  { key: 'boss', label: 'Boss', enabled: false },
]

// Selection bar for the skill/offense area: pick the skill by NAME (not slot label), the calculation mode
// (stub), and which damage form to show (All forms, or a single form's contribution).
function SkillSelectionBar({
  skills, selected, onSelect,
  forms, selectedForm, onSelectForm,
  calcMode, onCalcMode,
}: {
  skills: EquippedSkill[]
  selected: number
  onSelect: (slot: number) => void
  forms: string[]
  selectedForm: string | null
  onSelectForm: (form: string | null) => void
  calcMode: string
  onCalcMode: (mode: string) => void
}) {
  // Equipped skills in slot order, by name. Each carries its slot so selection maps back to slot_offense.
  const ordered = [...skills].sort((a, b) => a.slot - b.slot)
  const showAll = useUiPrefs(s => s.statsShowAllBoxes)
  const setShowAll = useUiPrefs(s => s.setStatsShowAllBoxes)
  // Enemy type (target scenario) drives the enemy_count_weight condition → recompute. Default Boss (5).
  const conditionState = useBuildStore(s => s.conditionState)
  const setConditionState = useBuildStore(s => s.setConditionState)
  const enemyWeight = Number(conditionState['enemy_count_weight'] ?? 5)
  const selectSt: React.CSSProperties = {
    fontSize: 11, background: 'rgba(255,255,255,0.06)', color: '#cfd6e6',
    border: '1px solid rgba(255,255,255,0.12)', borderRadius: 3, padding: '2px 4px',
  }
  const skillSelectSt: React.CSSProperties = {
    fontSize: 12, fontWeight: 600, background: 'rgba(200,120,32,0.18)', color: '#f0c070',
    border: '1px solid #c87820', borderRadius: 3, padding: '4px 6px', maxWidth: '100%',
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
      {/* Skill dropdown — select by name */}
      <div>
        {ordered.length === 0
          ? <span style={{ fontSize: 11, color: '#555' }}>No skills equipped.</span>
          : (
            <select
              value={selected}
              onChange={e => onSelect(Number(e.target.value))}
              style={skillSelectSt}
            >
              {ordered.map(sk => (
                <option key={sk.slot} value={sk.slot}>{sk.name}</option>
              ))}
            </select>
          )}
      </div>
      {/* Mode + form controls */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#888' }}>
          Mode
          <select value={calcMode} onChange={e => onCalcMode(e.target.value)} style={selectSt}>
            {CALC_MODES.map(m => (
              <option key={m.key} value={m.key} disabled={!m.enabled}>
                {m.label}{m.enabled ? '' : ' (soon)'}
              </option>
            ))}
          </select>
        </label>
        {/* Enemy type → enemy-count weight for "for each enemy" lines (e.g. Rosa's Unbreakable Stand). */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#888' }}>
          Enemy
          <select value={enemyWeight}
            onChange={e => setConditionState({ ...conditionState, enemy_count_weight: Number(e.target.value) })}
            style={selectSt}>
            {ENEMY_TYPES.map(t => <option key={t.weight} value={t.weight}>{t.label}</option>)}
          </select>
        </label>
        {forms.length > 1 && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#888' }}>
            Form
            <select
              value={selectedForm ?? '__all__'}
              onChange={e => onSelectForm(e.target.value === '__all__' ? null : e.target.value)}
              style={selectSt}
            >
              <option value="__all__">All forms (combined)</option>
              {forms.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
        )}
        {/* Reveal every mechanic/ailment/CC box even when this skill can't use it (find a box you think is
            wrongly hidden). Default off → boxes are skill-gated. */}
        <label style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#888', cursor: 'pointer' }}>
          <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />
          Show all boxes
        </label>
      </div>
    </div>
  )
}

// ── Damage breakdown table ────────────────────────────────────────────────────

const ALL_DTYPES = ['physical', 'fire', 'cold', 'lightning', 'erosion']

const DTYPE_LABEL: Record<string, string> = {
  physical:  'Physical',
  fire:      'Fire',
  cold:      'Cold',
  lightning: 'Lightning',
  erosion:   'Erosion',
}

// Skill tags arrive capitalized from the engine (e.g. "Spell", "Attack", "Area") — compare
// case-insensitively so spell/attack detection and key selection actually match.
const hasTag = (offense: OffenseResult, tag: string) => offense.skill_tags.some(t => t.toLowerCase() === tag)

function flatMinKeys(dtype: string, offense: OffenseResult): string[] {
  const keys = [`${dtype}_dmg_gear_flat_min`]
  if (hasTag(offense,'attack')) keys.push(`${dtype}_attack_dmg_flat_min`)
  if (hasTag(offense,'spell')) keys.push(`${dtype}_spell_dmg_flat_min`)
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_gear_flat_min')
  return keys
}

function flatMaxKeys(dtype: string, offense: OffenseResult): string[] {
  const keys = [`${dtype}_dmg_gear_flat_max`]
  if (hasTag(offense,'attack')) keys.push(`${dtype}_attack_dmg_flat_max`)
  if (hasTag(offense,'spell')) keys.push(`${dtype}_spell_dmg_flat_max`)
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_gear_flat_max')
  return keys
}

function genericIncKeys(offense: OffenseResult): string[] {
  const keys = ['dmg_inc']
  if (hasTag(offense,'attack'))     keys.push('attack_dmg_inc')
  if (hasTag(offense,'spell'))      keys.push('spell_dmg_inc')
  if (hasTag(offense,'melee'))      keys.push('melee_dmg_inc')
  if (hasTag(offense,'area'))       keys.push('area_dmg_inc')
  if (hasTag(offense,'projectile')) keys.push('projectile_dmg_inc')
  // Tangle mode adds the "tangle" tag inside offense (not on the skill's tags), so key off tangle_count.
  if ((offense.tangle_count ?? 0) > 0) keys.push('tangle_dmg_inc')
  return keys
}

function typeIncKeys(dtype: string): string[] {
  const keys = [`${dtype}_dmg_inc`]
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_inc')
  return keys
}

function genericAddKeys(offense: OffenseResult): string[] {
  // 'hit_dmg_additional' is generic (untagged) hit-only additional — e.g. Splendor's "+additional Hit Damage".
  // It folds into generic_add in offense, so it belongs in the All-Types breakdown alongside dmg_additional.
  const keys = ['dmg_additional', 'hit_dmg_additional']
  if (hasTag(offense,'attack'))     keys.push('attack_dmg_additional')
  if (hasTag(offense,'spell'))      keys.push('spell_dmg_additional')
  if (hasTag(offense,'melee'))      keys.push('melee_dmg_additional')
  if (hasTag(offense,'area'))       keys.push('area_dmg_additional')
  if (hasTag(offense,'projectile')) keys.push('projectile_dmg_additional')
  // Tangle mode: additional + the enhancement pool (both ride the "tangle" tag, added inside offense).
  if ((offense.tangle_count ?? 0) > 0) keys.push('tangle_dmg_additional', 'tangle_dmg_enhancement_additional')
  // Spell Burst mode adds the "spell_burst" tag inside offense → the burst-cast hit-damage pool applies.
  if ((offense.spell_burst_count ?? 0) > 0) keys.push('spell_burst_hit_dmg_additional')
  return keys
}

function typeAddKeys(dtype: string): string[] {
  const keys = [`${dtype}_dmg_additional`]
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_additional')
  return keys
}

// The enemy-vulnerability stat keys that feed _enemy_vuln_mult for a given damage type — mirrors the engine so
// the Enemy Multiplier breakdown shows the real sources of the amplification (Numbed/Paralysis/Frostbite/…).
function enemyVulnKeys(dtype: string, isSpell: boolean): string[] {
  const keys = ['paralysis_dmg_taken', 'no_guard_dmg_taken', 'knockback_dmg_taken', 'hit_curse_taken', `${dtype}_curse_taken`]
  if (dtype === 'cold') keys.push('frostbite_cold_taken')
  if (dtype === 'lightning') keys.push('numbed_lightning_taken')
  if (dtype === 'fire' || dtype === 'cold' || dtype === 'lightning') keys.push(`${dtype}_infiltration_taken`)
  if (isSpell) keys.push('frail_spell_taken')
  return keys
}

function DamageBreakdownTable({ offense }: { offense: OffenseResult }) {
  const ctx = useContext(BreakdownCtx)
  const isSpell = hasTag(offense, 'spell')
  const totalDps = offense.total_dps_vs_target
  // Same-target shotgun multiplier (e.g. Chain Lightning Merge+Web): total_dps_vs_target includes it but the
  // per-form dps_vs_target does NOT, so every per-form / per-type figure below must apply it to reconcile to
  // 100% (otherwise both "% of Total" and "Type Contribution" read 1/cast_multiplier). 1.0 when no shotgun.
  const castMult = offense.cast_multiplier ?? 1
  // Tangle mode multiplier: total_dps_vs_target multiplies by the attached tangle COUNT (each tangle a full
  // caster), which per-form dps_vs_target does NOT — so the breakdown applies it alongside the shotgun multiplier
  // to reconcile to 100%. (Tangle Damage Enhancement is NOT here — it rides the additional pool, already in each
  // form's damage.) 1 when not tangled (tangle_count 0).
  const tangleMult = (offense.tangle_count ?? 0) > 0 ? offense.tangle_count : 1
  // Spell Burst mode multiplier: total_dps_vs_target multiplies by (casts/burst × bursts/sec ÷ aps), which the
  // per-form dps_vs_target does NOT — so apply it alongside the shotgun/tangle multipliers to reconcile to 100%.
  // 1 when not bursting. (The spell-burst hit-damage pool is already in each form's damage.)
  const spellBurstMult = (offense.spell_burst_count ?? 0) > 0 ? (offense.spell_burst_mult ?? 1) : 1
  const breakdownMult = castMult * tangleMult * spellBurstMult

  // Per-dtype DPS total across all forms (proportional attribution via avg hit)
  const dtypeDpsTotal: Record<string, number> = {}
  for (const dtype of ALL_DTYPES) {
    dtypeDpsTotal[dtype] = offense.hit_forms.reduce((sum, form) => {
      const dtypeAvg = form.damage_by_type[dtype] ?? 0
      const prop = form.avg_hit_pre_crit > 0 ? dtypeAvg / form.avg_hit_pre_crit : 0
      return sum + prop * form.dps_vs_target * breakdownMult
    }, 0)
  }

  // Shared cell styles. Tight font/padding so all six damage-type columns (incl. Erosion) fit the
  // left column without overflowing into the middle column.
  const thSt: React.CSSProperties = { textAlign: 'right', fontSize: 12, color: '#888', fontWeight: 600, paddingBottom: 3, paddingLeft: 2, paddingRight: 2, whiteSpace: 'nowrap' }
  const td:   React.CSSProperties = { textAlign: 'right', fontSize: 12, fontVariantNumeric: 'tabular-nums', paddingLeft: 2, paddingRight: 2, color: '#e0e0e0', whiteSpace: 'nowrap' }
  const tdLbl: React.CSSProperties = { textAlign: 'left', fontSize: 12, color: '#888', paddingRight: 6, whiteSpace: 'nowrap' }
  const tdDim: React.CSSProperties = { ...td, color: '#444' }
  const tdSub: React.CSSProperties = { ...tdLbl, color: '#666' }

  // Mini formulas shown dim next to each breakdown title (so the math is verifiable). Flat-damage build-up
  // differs for spells (intrinsic base + added×effectiveness) vs attacks (weapon base × gear + added).
  const addedFormula = hasTag(offense, 'spell') ? 'Skill Base + Added × Effectiveness' : 'Weapon Base × (1 + Gear) + Added'

  return (
    <div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr>
            <th style={{ ...thSt, textAlign: 'left', color: '#555' }}></th>
            <th style={{ ...thSt, color: '#aaa' }}>All Types</th>
            {ALL_DTYPES.map(d => (
              <th key={d} style={{ ...thSt, color: DTYPE_COLOR[d] }}>{DTYPE_LABEL[d]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* ── Flat damage ── */}
          <tr>
            <td style={tdLbl}>Added Min</td>
            <td style={tdDim}>—</td>
            {ALL_DTYPES.map(d => {
              const v = offense.flat_dmg_min[d] ?? 0
              const base = offense.base_dmg_min[d] ?? 0
              return <td key={d} style={v > 0 ? td : tdDim}>
                {v > 0 ? <Breakdown title={`Added Min — ${DTYPE_LABEL[d]}`} keys={flatMinKeys(d, offense)} total={v} formula={addedFormula}
                  extra={base > 0 ? [{ value: fmtNum(base), stat: 'Base damage', source: 'Baseline', sourceName: offense.skill_name }] : undefined}>{fmtNum(v)}</Breakdown> : fmtNum(v)}
              </td>
            })}
          </tr>
          <tr>
            <td style={tdLbl}>Added Max</td>
            <td style={tdDim}>—</td>
            {ALL_DTYPES.map(d => {
              const v = offense.flat_dmg_max[d] ?? 0
              const base = offense.base_dmg_max[d] ?? 0
              return <td key={d} style={v > 0 ? td : tdDim}>
                {v > 0 ? <Breakdown title={`Added Max — ${DTYPE_LABEL[d]}`} keys={flatMaxKeys(d, offense)} total={v} formula={addedFormula}
                  extra={base > 0 ? [{ value: fmtNum(base), stat: 'Base damage', source: 'Baseline', sourceName: offense.skill_name }] : undefined}>{fmtNum(v)}</Breakdown> : fmtNum(v)}
              </td>
            })}
          </tr>
          {/* ── Multipliers: "All Types" = the catch-all bucket (generic + skill-tag-scoped mods the
               skill qualifies for, e.g. additional attack/area/spell damage); per-type columns show
               ONLY that damage type's specific additional. Empty = the identity (0% / ×1.00), not a
               dash — a type with no specific modifier reads ×1.00. ── */}
          <tr>
            <td style={tdLbl}>Total Increased</td>
            <td style={td}><Breakdown title="Total Increased — All Types" keys={genericIncKeys(offense)} total={offense.generic_inc} totalUnit="%" formula="Σ Increased %">{(offense.generic_inc * 100).toFixed(0)}%</Breakdown></td>
            {ALL_DTYPES.map(d => {
              // Specific = this type's increase beyond the generic (catch-all) bucket. Types the skill
              // doesn't deal have no entry → treated as generic-only → 0% specific.
              const specific = Math.max(0, (offense.type_inc[d] ?? offense.generic_inc) - offense.generic_inc)
              const show = specific >= 0.005
              const txt = `${(specific * 100).toFixed(0)}%`
              return <td key={d} style={show ? td : tdDim}>
                {show ? <Breakdown title={`Total Increased — ${DTYPE_LABEL[d]}`} keys={typeIncKeys(d)} total={specific} totalUnit="%" formula="Σ this type's Increased %">{txt}</Breakdown> : txt}
              </td>
            })}
          </tr>
          <tr>
            <td style={tdLbl}>Total Additional</td>
            <td style={td}><Breakdown title="Total Additional — All Types" keys={genericAddKeys(offense)} total={offense.generic_add} totalUnit="×" formula="Π (1 + Additional)"
              extra={offense.main_stat_damage_bonus > 0 ? [{ value: `×${dec((1 + offense.main_stat_damage_bonus))}`, stat: 'Additional Damage', source: 'Main Stat', sourceName: `${offense.main_stats.join(' + ')} Damage Bonus (+${dec((offense.main_stat_damage_bonus * 100))}%)` }] : undefined}>×{dec(offense.generic_add)}</Breakdown></td>
            {ALL_DTYPES.map(d => {
              // Specific = type_add factored over the generic bucket. Types the skill doesn't deal have
              // no entry → ×1.00 (not 1/generic, which would show a phantom multiplier on empty types).
              const specificAdd = offense.type_add[d] !== undefined
                ? offense.type_add[d] / (offense.generic_add || 1)
                : 1
              const show = Math.abs(specificAdd - 1) >= 0.005
              const txt = `×${dec(specificAdd)}`
              return <td key={d} style={show ? td : tdDim}>
                {show ? <Breakdown title={`Total Additional — ${DTYPE_LABEL[d]}`} keys={typeAddKeys(d)} total={specificAdd} totalUnit="×" formula="Π (1 + Additional)">{txt}</Breakdown> : txt}
              </td>
            })}
          </tr>
          {/* Main-stat Damage Bonus (0.5%/point) is part of Total Additional above — shown as a source inside that
              breakdown (not its own row), since it's one cumulative additional multiplier, not a separate pool. */}

          {/* ── Enemy Multiplier: the cumulative outgoing multiplier the TARGET applies per type — armor/resist
               mitigation × enemy vulnerability (Paralysis/Numbed/Frostbite/Infiltration/curses). All Types = the
               net multiplier across the skill's damage (total vs-target ÷ total pre-mitigation). ── */}
          {offense.enemy_mult_by_type && Object.keys(offense.enemy_mult_by_type).length > 0 && (
            <tr>
              <td style={tdLbl}>Enemy Multiplier</td>
              <td style={td}>{offense.total_dps > 0 ? `×${dec(offense.total_dps_vs_target / offense.total_dps)}` : '—'}</td>
              {ALL_DTYPES.map(d => {
                const m = offense.enemy_mult_by_type?.[d]
                if (m === undefined) return <td key={d} style={tdDim}>—</td>
                // Split the multiplier into (target mitigation) × (Π enemy vulnerability) for the breakdown:
                // the vuln keys carry the real sources; mitigation = m ÷ that product (the armour/resist part).
                const vk = enemyVulnKeys(d, isSpell)
                const vulnProduct = vk.reduce((p, k) => p * (1 + (ctx?.statMap[k]?.total ?? 0)), 1)
                const mitigation = vulnProduct > 0 ? m / vulnProduct : m
                return <td key={d} style={td}>
                  <Breakdown title={`Enemy Multiplier — ${DTYPE_LABEL[d]}`} keys={vk} total={m} totalUnit="×"
                    formula="Target Mitigation × Π(1 + enemy vulnerability)"
                    extra={[{ value: `×${dec(mitigation)}`, stat: 'Target Mitigation', source: 'Target', sourceName: '(1 − armour) × (1 − resistance)' }]}>
                    ×{dec(m)}
                  </Breakdown>
                </td>
              })}
            </tr>
          )}

          {/* ── Per hit form ── */}
          {offense.hit_forms.map(form => {
            const formMin = ALL_DTYPES.reduce((s, d) => s + (form.hit_min_by_type[d] ?? 0), 0)
            const formMax = ALL_DTYPES.reduce((s, d) => s + (form.hit_max_by_type[d] ?? 0), 0)
            const formPct = totalDps > 0 ? `${(form.dps_vs_target * breakdownMult / totalDps * 100).toFixed(0)}%` : '—'

            const multiForm = offense.hit_forms.length > 1
            return (
              <React.Fragment key={form.name}>
                {/* Each form is its own visually-separated area (border + faint background) so multi-form
                    skills (e.g. Icebound Beam: Cold Beam + Icy Blade) read as distinct damage sources. */}
                <tr>
                  {/* Form name only — no full-row banner. A neutral separator line divides forms; the name keeps
                      its own colour to mark it as a distinct damage source. */}
                  <td colSpan={7} style={{
                    paddingTop: 6, paddingBottom: 4, marginTop: 4, fontSize: 13, color: '#e0d0a0', fontWeight: 700,
                    borderTop: multiForm ? '1px solid rgba(255,255,255,0.10)' : undefined,
                  }}>
                    {form.name}
                    {form.proc_chance < 1.0 && (
                      <span style={{ color: '#666', fontWeight: 400, marginLeft: 6 }}>
                        {(form.proc_chance * 100).toFixed(0)}% chance
                      </span>
                    )}
                    {/* Per-form rate lives in the Hit Rate box now, not here. Shotgun details live in the
                        Shotgunning box. The damage table stays purely about damage. */}
                  </td>
                </tr>
                <tr>
                  <td style={tdLbl}>Hit Range</td>
                  <td style={td}>{fmtNum(formMin)}–{fmtNum(formMax)}</td>
                  {ALL_DTYPES.map(d => {
                    const mn = form.hit_min_by_type[d] ?? 0
                    const mx = form.hit_max_by_type[d] ?? 0
                    return <td key={d} style={mn > 0 || mx > 0 ? td : tdDim}>
                      {mn > 0 || mx > 0 ? `${fmtNum(mn)}–${fmtNum(mx)}` : '—'}
                    </td>
                  })}
                </tr>
                <tr>
                  <td style={tdLbl}>DPS</td>
                  <td style={{ ...td, color: '#f0c070' }}>{fmtNum(form.dps_vs_target * breakdownMult)}</td>
                  {ALL_DTYPES.map(d => {
                    const dtypeAvg = form.damage_by_type[d] ?? 0
                    const prop = form.avg_hit_pre_crit > 0 ? dtypeAvg / form.avg_hit_pre_crit : 0
                    const dtypeDps = prop * form.dps_vs_target * breakdownMult
                    return <td key={d} style={dtypeDps > 0 ? td : tdDim}>
                      {dtypeDps > 0 ? fmtNum(dtypeDps) : '—'}
                    </td>
                  })}
                </tr>
                <tr>
                  <td style={tdSub}>% of Total</td>
                  {/* "All Types" is the whole, so its own % is trivially 100% — show the form's SHARE only when
                      there are multiple forms (where it's informative); blank it for a single form. */}
                  <td style={{ ...td, color: '#aaa' }}>{multiForm ? formPct : ''}</td>
                  {ALL_DTYPES.map(d => {
                    const dtypeAvg = form.damage_by_type[d] ?? 0
                    const prop = form.avg_hit_pre_crit > 0 ? dtypeAvg / form.avg_hit_pre_crit : 0
                    const dtypeDps = prop * form.dps_vs_target * breakdownMult
                    const pct = totalDps > 0 && dtypeDps > 0 ? `${(dtypeDps / totalDps * 100).toFixed(0)}%` : '—'
                    return <td key={d} style={{ ...td, color: dtypeDps > 0 ? '#888' : '#444' }}>{pct}</td>
                  })}
                </tr>
              </React.Fragment>
            )
          })}

          {/* ── Type contribution summary ── */}
          <tr><td colSpan={7} style={{ paddingTop: 6 }} /></tr>
          <tr>
            <td style={{ ...tdLbl, color: '#666', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Type Contribution
            </td>
            {/* "All Types" contribution is always 100% (it's the sum) — meaningless, so leave it blank. */}
            <td style={td}></td>
            {ALL_DTYPES.map(d => {
              const dtypeDps = dtypeDpsTotal[d] ?? 0
              const pct = totalDps > 0 && dtypeDps > 0 ? `${(dtypeDps / totalDps * 100).toFixed(0)}%` : '—'
              return <td key={d} style={dtypeDps > 0 ? { ...td, color: DTYPE_COLOR[d] } : tdDim}>{pct}</td>
            })}
          </tr>
        </tbody>
      </table>
    </div>
  )
}

// ── Offense panels ────────────────────────────────────────────────────────────

const AMBER = '#c87820'
const SKYBLUE = '#3a86c8'
const GREY = '#555'

// Mechanic scaffolding: skills tagged with one of these get a dedicated box. The modeled mechanics (Tangle,
// Spell Burst, Channeled) render their real boxes from offense data above; these are the not-yet-modeled ones —
// each shows a small "modeling pending" stub so filling it in later is just swapping the body for real data.
// Gated on skill_tags so only relevant skills surface a stub (mirrors how the real boxes gate on their data).
const MECH_STUBS: { label: string; tag: string; note: string }[] = [
  { label: 'Combo', tag: 'combo', note: 'Combo-stage scaling, stage gain/loss, and finisher hits are not modeled yet.' },
  { label: 'Demolisher Charges', tag: 'demolisher', note: 'Demolisher charge generation, cap, and consumption are not modeled yet.' },
  { label: 'Barrage', tag: 'barrage', note: 'Barrage wave count and release cadence are not modeled yet.' },
]

// Wrapper for each box in the offense grid. Just a block — the MasonryGrid handles columns/placement.
function GridBox({ children }: { children: React.ReactNode }) {
  return <div>{children}</div>
}

function sameBuckets(a: number[][], b: number[][]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i].length !== b[i].length) return false
    for (let j = 0; j < a[i].length; j++) if (a[i][j] !== b[i][j]) return false
  }
  return true
}

// Row-major masonry: keeps source order across the top row (Hit Rate → Crit → Skill Effects fill columns
// 0..N-1), then drops each remaining box into whichever column is currently shortest (measured heights) so the
// vertical gaps fill in. Column count derives purely from container width / columnWidth (no hard cap); each
// column is capped at columnMax so boxes don't sprawl on very wide screens. Empty children are dropped.
function MasonryGrid({ children, columnWidth = 220, columnMax = 340, gap = 6 }: {
  children: React.ReactNode; columnWidth?: number; columnMax?: number; gap?: number
}) {
  const items = React.Children.toArray(children)
  const wrapRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<Array<HTMLDivElement | null>>([])
  const [cols, setCols] = useState(1)
  const [buckets, setBuckets] = useState<number[][]>([])

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const compute = () => setCols(Math.max(1, Math.floor((el.clientWidth + gap) / (columnWidth + gap))))
    compute()
    const ro = new ResizeObserver(compute)
    ro.observe(el)
    return () => ro.disconnect()
  }, [columnWidth, gap])

  // Re-measure each render; bail (same ref) when the layout is unchanged so we don't loop.
  useLayoutEffect(() => {
    const heights = new Array(cols).fill(0)
    const next: number[][] = Array.from({ length: cols }, () => [])
    items.forEach((_, i) => {
      let c: number
      if (i < cols) c = i                                   // first row: keep source order across the columns
      else { c = 0; for (let k = 1; k < cols; k++) if (heights[k] < heights[c]) c = k }  // then shortest column
      next[c].push(i)
      heights[c] += (itemRefs.current[i]?.offsetHeight ?? 0) + gap
    })
    setBuckets(prev => sameBuckets(prev, next) ? prev : next)
  })

  // Fallback distribution (round-robin) until heights are measured / when cols changes — also guarantees the
  // first row stays in source order (i < cols → column i).
  const valid = buckets.length === cols && buckets.reduce((s, c) => s + c.length, 0) === items.length
  const layout = valid ? buckets : (() => {
    const b: number[][] = Array.from({ length: cols }, () => [])
    items.forEach((_, i) => b[i % cols].push(i))
    return b
  })()

  return (
    <div ref={wrapRef} style={{ display: 'flex', gap, alignItems: 'flex-start', justifyContent: 'flex-start' }}>
      {layout.map((col, ci) => (
        <div key={ci} style={{ flex: '1 1 0', minWidth: 0, maxWidth: columnMax, display: 'flex', flexDirection: 'column' }}>
          {col.map(i => (
            <div key={i} ref={el => { itemRefs.current[i] = el }}>{items[i]}</div>
          ))}
        </div>
      ))}
    </div>
  )
}

// A grey "modeling pending" box for an unimplemented mechanic — collapsed by default to stay out of the way.
function MechanicStubPanel({ label, note }: { label: string; note: string }) {
  return (
    <StatPanel title={label} accent={GREY} defaultCollapsed>
      <div style={{ fontSize: 10, color: '#777' }}>
        {note} <span style={{ color: '#c8645a' }}>(NYI)</span>
      </div>
    </StatPanel>
  )
}

// Non-hit skills (passives / empower-style buffs) have no hit-DPS offense yet. Surface a Skill-Viewer
// foundation with the mechanics we intend to model, marked NYI so nothing reads as silently missing.
// Tailored by slot kind: passives (6-9) → reservation/aura/AoE; active buffs → empower effect/duration/cooldown.
function _curseDebuffLabel(statKey: string | null): string {
  if (!statKey) return 'Damage taken'
  if (statKey === 'hit_curse_taken') return 'Hit Damage taken'
  const t = statKey.replace('_curse_taken', '')
  return `${t.charAt(0).toUpperCase()}${t.slice(1)} Damage taken`
}

function SkillFoundationPanel({ slot, skill, aura, reservation, curse, curseMeta, empower }: { slot: number; skill: EquippedSkill; aura?: AuraSummary | null; reservation?: ReservationSummary | null; curse?: CurseSummary | null; curseMeta?: CurseMeta | null; empower?: EmpowerSummary | null }) {
  const ctx = useContext(BreakdownCtx)
  const conditionState = useBuildStore(s => s.conditionState)
  const setConditionState = useBuildStore(s => s.setConditionState)
  const isPassive = skill.slot >= 6
  const rows = (isPassive
    ? ['Reservation (Sealing)', 'Aura / Magus / Focus Effect', 'Area of Effect']
    : ['Empower Effect', 'Skill Duration', 'Cooldown', 'Area of Effect']
  ).filter(r => !(reservation && r === 'Reservation (Sealing)'))   // real seal row shown below when modeled
  const statMapName = (stat: string) => ctx?.statMap?.[stat]?.display_name ?? stat
  const fmtGrant = (stat: string, amt: number) =>
    /_flat$/.test(stat) ? fmtNum(amt) : fmtPct(amt)
  return (
    <StatPanel title={`${slotLabel(slot)} — ${skill.name} (Level ${skill.level})`} accent={AMBER}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6 }}>
        {skill.skill_tags?.map(t => <span key={t} style={{ fontSize: 9, color: '#888', background: '#1a1a2e', borderRadius: 3, padding: '1px 5px' }}>{t}</span>)}
      </div>
      <div style={{ fontSize: 10, color: '#777', marginBottom: 4 }}>
        {isPassive ? 'This skill contributes build-wide (no hit DPS of its own).' : 'Buff / utility skill (no hit DPS of its own).'}
      </div>
      {reservation && (() => {
        const baseSeal = reservation.base_fraction * reservation.pool_max
        const poolLabel = reservation.pool === 'life' ? 'Max Life' : 'Max Mana'
        const fmtPctSigned = (v: number) => `${v > 0 ? '+' : ''}${dec((v * 100))}%`
        // Increased and additional comp are SEPARATE multiplicative pools. Show each per-support source under its
        // pool, plus a "Global (talents/gear)" row per pool for the slice not coming from a support, so the
        // breakdown reconciles with the total: Base × Π(Mult) ÷ ((1+Σinc) × (1+Σadd)).
        const supInc = reservation.comp_sources.filter(c => c.kind === 'increased').reduce((a, c) => a + c.value, 0)
        const supAdd = reservation.comp_sources.filter(c => c.kind === 'additional').reduce((a, c) => a + c.value, 0)
        const globalInc = reservation.comp_increased - supInc
        const globalAdd = reservation.comp_additional - supAdd
        const extra = [
          { value: fmtNum(baseSeal), stat: 'Base seal', source: 'Skill', sourceName: `${(reservation.base_fraction * 100).toFixed(0)}% of ${poolLabel}` },
          ...reservation.support_mults.map(m => ({ value: `×${dec(m.mult)}`, stat: 'Mana Multiplier', source: 'Support', sourceName: m.name })),
          ...reservation.comp_sources.map(c => ({
            value: fmtPctSigned(c.value),
            stat: c.kind === 'additional' ? 'Additional Sealed Mana Comp.' : 'Increased Sealed Mana Comp.',
            source: 'Support', sourceName: c.label,
          })),
        ]
        // Global Sealed Mana Compensation (talents/gear, i.e. not from a support) — shown as a real per-source
        // breakdown over the comp stats instead of one lumped "Talents / Gear" row.
        const compSections = ((Math.abs(globalInc) > 1e-9 || Math.abs(globalAdd) > 1e-9)
          ? [{ label: 'Global Sealed Mana Compensation', keys: ['sealed_mana_compensation_inc', 'sealed_mana_compensation_additional'] }]
          : [])
        return (
          <Row label={`Reservation — Sealed ${reservation.pool === 'life' ? 'Life' : 'Mana'}`} breakdown={{
            title: `Sealed ${reservation.pool === 'life' ? 'Life' : 'Mana'}`, keys: [], total: reservation.amount, totalUnit: '',
            formula: 'Base × Π(Mana Multiplier) ÷ ((1 + Σ increased) × (1 + Σ additional)) Sealed Mana Compensation',
            extra, sections: compSections,
          }}>{fmtNum(reservation.amount)}</Row>
        )
      })()}
      {curse ? (
        <>
          {/* Base stats (from the curse skill data) — always shown ("—" when absent), each with a source
              breakdown (the skill base; curse base stats aren't engine-modified yet). */}
          {(() => {
            const bs = curseMeta?.base_stats
            const baseRow = (label: string, raw: number | string | null | undefined, suffix = '') => {
              const has = raw != null && raw !== ''
              const display = has ? `${raw}${suffix}` : '—'
              const n = parseFloat(String(raw))
              return (
                <Row key={label} label={label} breakdown={has ? {
                  title: label, keys: [], total: isNaN(n) ? undefined : n,
                  extra: [{ value: display, stat: 'Base', source: 'Skill', sourceName: curse.curse_name }],
                } : undefined}>{display}</Row>
              )
            }
            return (
              <>
                {baseRow('Mana Cost', bs?.mana_cost)}
                {baseRow('Cast Speed', bs?.cast_speed)}
                {baseRow('Cooldown', bs?.cooldown)}
                {baseRow('Duration', bs?.duration, 's')}
              </>
            )
          })()}
          <Row label="Curse Effect" breakdown={{
            title: 'Curse Effect', keys: ['curse_effect_inc'], total: curse.curse_effect_inc, totalUnit: '%',
            formula: 'Σ increased Curse Effect',
          }}>{fmtPct(curse.curse_effect_inc)}</Row>
          <Row label="Additional Curse Effect" breakdown={{
            title: 'Additional Curse Effect', keys: ['curse_effect_additional'], total: curse.curse_effect_additional,
            totalUnit: '%', formula: 'Π(1 + additional) − 1',
          }}>{fmtPct(curse.curse_effect_additional)}</Row>
          <Row label="Curse Limit" breakdown={{
            title: 'Curse Limit', keys: ['max_curses_flat', 'curse_limit_cap_flat'], total: curse.limit, totalUnit: '',
            formula: '1 + Max Curses (capped by Curse Limit Cap)',
          }}>{`${curse.n_active} / ${curse.limit}`}</Row>
          <div style={{ fontSize: 10, color: '#777', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 6, marginBottom: 2 }}>Debuff applied to enemy</div>
          {curse.modeled ? (() => {
            // Final = Base × (1 + Curse Effect) × (1 + Additional Curse Effect). Show the derivation on hover.
            const extra = [
              { value: fmtPct(curse.base_amount), stat: 'Base', source: 'Curse', sourceName: curse.curse_name },
              ...(curse.curse_effect_inc ? [{ value: `×${dec((1 + curse.curse_effect_inc))}`, stat: 'Curse Effect', source: '', sourceName: `+${Math.round(curse.curse_effect_inc * 100)}%` }] : []),
              ...(curse.curse_effect_additional ? [{ value: `×${dec((1 + curse.curse_effect_additional))}`, stat: 'Additional Curse Effect', source: '', sourceName: `+${Math.round(curse.curse_effect_additional * 100)}%` }] : []),
            ]
            return (
              <Row label={_curseDebuffLabel(curse.stat_key)} breakdown={{
                title: _curseDebuffLabel(curse.stat_key), keys: [], total: curse.scaled_amount, totalUnit: '%',
                formula: 'Base × (1 + Curse Effect) × (1 + Additional Curse Effect)', extra,
              }}>{fmtPct(curse.scaled_amount)}{curse.applied ? '' : ' (suppressed)'}</Row>
            )
          })() : <Row label="Debuff" labelColor="#a05a5a">— NYI</Row>}
          {!curse.applied && <div style={{ fontSize: 10, color: '#b08a4a', lineHeight: 1.4, marginTop: 2 }}>Suppressed — over the curse limit. Resolve the conflict on the Conditionals screen.</div>}
          <Row label="Skill Area" labelColor="#555">— NYI</Row>
          {(curseMeta?.nyi?.length ?? 0) > 0 && (
            <>
              <div style={{ fontSize: 10, color: '#a05a5a', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 6, marginBottom: 2 }}>Not yet modeled</div>
              {curseMeta!.nyi.map((t, i) => <div key={i} style={{ fontSize: 10, color: '#7a5a5a', lineHeight: 1.4 }}>{t}</div>)}
            </>
          )}
        </>
      ) : aura ? (
        <>
          <Row label="Aura Effect" breakdown={{
            title: 'Aura Effect', keys: ['aura_effect_inc', 'aura_effect_additional'],
            total: aura.aura_effect_inc, totalUnit: '%',
            formula: '(1 + Σ increased) × (1 + Σ additional) − 1',
          }}>{fmtPct(aura.aura_effect_inc)}</Row>
          {aura.stack_condition && aura.max_stacks ? (() => {
            const key = aura.stack_condition!
            const cur = Number(conditionState[key] ?? 0)
            return (
              <Row label="Buff Stacks">
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <input type="range" min={0} max={aura.max_stacks} value={cur}
                    onChange={e => setConditionState({ ...conditionState, [key]: Number(e.target.value) })}
                    style={{ width: 90 }} />
                  <span style={{ fontSize: 11, color: '#bbb', minWidth: 34, textAlign: 'right' }}>{cur}/{aura.max_stacks}</span>
                </span>
              </Row>
            )
          })() : null}
          <div style={{ fontSize: 10, color: '#777', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 6, marginBottom: 2 }}>Grants (you &amp; allies)</div>
          {aura.granted.length === 0 && <div style={{ fontSize: 11, color: '#555' }}>No modeled buff lines.</div>}
          {aura.granted.map((g, i) => {
            // Final = Base × (1 + Aura Effect). Show that derivation on hover (the Aura Effect pool itself is
            // not scaled — its base IS its final, so only show the multiplier step for the scaled buffs).
            const scaled = !g.is_aura_effect && aura.aura_effect_inc !== 0
            const extra = scaled ? [
              { value: fmtGrant(g.stat, g.base), stat: 'Base', source: 'Aura', sourceName: aura.name },
              { value: `×${dec((1 + aura.aura_effect_inc))}`, stat: 'Aura Effect', source: '', sourceName: `+${Math.round(aura.aura_effect_inc * 100)}%` },
            ] : undefined
            return (
              <Row key={i} label={statMapName(g.stat)} breakdown={extra ? {
                title: statMapName(g.stat), keys: [], total: g.amount,
                totalUnit: /_flat$/.test(g.stat) ? '' : '%',
                formula: 'Base × (1 + Aura Effect)', extra,
              } : undefined}>{fmtGrant(g.stat, g.amount)}</Row>
            )
          })}
          {aura.nyi.length > 0 && (
            <>
              <div style={{ fontSize: 10, color: '#a05a5a', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 6, marginBottom: 2 }}>Not yet modeled</div>
              {aura.nyi.map((t, i) => <div key={i} style={{ fontSize: 10, color: '#7a5a5a', lineHeight: 1.4 }}>{t}</div>)}
            </>
          )}
          {(aura.review?.length ?? 0) > 0 && (
            <>
              <div style={{ fontSize: 10, color: '#b08a4a', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 6, marginBottom: 2 }}>Needs manual review (scaling unverified)</div>
              {aura.review!.map((t, i) => <div key={i} style={{ fontSize: 10, color: '#8a7550', lineHeight: 1.4 }}>{t}</div>)}
            </>
          )}
        </>
      ) : empower ? (
        <>
          <Row label="Empower Effect" breakdown={{
            title: 'Empower Effect', keys: ['empower_effect_inc', 'empower_effect_additional'],
            total: empower.empower_effect_inc, totalUnit: '%',
            formula: '(1 + Σ increased) × (1 + Σ additional) − 1',
          }}>{fmtPct(empower.empower_effect_inc)}</Row>
          {empower.stack_condition && empower.max_stacks ? (() => {
            const key = empower.stack_condition!
            const cur = Number(conditionState[key] ?? 0)
            return (
              <Row label="Buff Stacks">
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <input type="range" min={0} max={empower.max_stacks} value={cur}
                    onChange={e => setConditionState({ ...conditionState, [key]: Number(e.target.value) })}
                    style={{ width: 90 }} />
                  <span style={{ fontSize: 11, color: '#bbb', minWidth: 34, textAlign: 'right' }}>{cur}/{empower.max_stacks}</span>
                </span>
              </Row>
            )
          })() : null}
          <div style={{ fontSize: 10, color: '#777', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 6, marginBottom: 2 }}>Grants (Euphoria)</div>
          {empower.granted.length === 0 && <div style={{ fontSize: 11, color: '#555' }}>No modeled buff lines.</div>}
          {empower.granted.map((g, i) => {
            // Final = Base × (1 + Empower Effect); show the derivation on hover (the Empower-Effect pool isn't scaled).
            const scaled = !g.is_empower_effect && empower.empower_effect_inc !== 0
            const extra = scaled ? [
              { value: fmtGrant(g.stat, g.base), stat: 'Base', source: 'Empower', sourceName: empower.name },
              { value: `×${dec((1 + empower.empower_effect_inc))}`, stat: 'Empower Effect', source: '', sourceName: `+${Math.round(empower.empower_effect_inc * 100)}%` },
            ] : undefined
            return (
              <Row key={i} label={statMapName(g.stat)} breakdown={extra ? {
                title: statMapName(g.stat), keys: [], total: g.amount,
                totalUnit: /_flat$/.test(g.stat) ? '' : '%',
                formula: 'Base × (1 + Empower Effect)', extra,
              } : undefined}>{fmtGrant(g.stat, g.amount)}</Row>
            )
          })}
          {empower.nyi.length > 0 && (
            <>
              <div style={{ fontSize: 10, color: '#a05a5a', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 6, marginBottom: 2 }}>Not yet modeled</div>
              {empower.nyi.map((t, i) => <div key={i} style={{ fontSize: 10, color: '#7a5a5a', lineHeight: 1.4 }}>{t}</div>)}
            </>
          )}
          {(empower.review?.length ?? 0) > 0 && (
            <>
              <div style={{ fontSize: 10, color: '#b08a4a', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 6, marginBottom: 2 }}>Needs manual review (scaling unverified)</div>
              {empower.review!.map((t, i) => <div key={i} style={{ fontSize: 10, color: '#8a7550', lineHeight: 1.4 }}>{t}</div>)}
            </>
          )}
        </>
      ) : (
        rows.map(label => <Row key={label} label={label} labelColor="#555">— NYI</Row>)
      )}
    </StatPanel>
  )
}

function OffensePanels({ offense, slot, skill, aura, reservation, curse, curseMeta, empower }: { offense: OffenseResult | null; slot: number; skill?: EquippedSkill; aura?: AuraSummary | null; reservation?: ReservationSummary | null; curse?: CurseSummary | null; curseMeta?: CurseMeta | null; empower?: EmpowerSummary | null }) {
  // Character-wide stats the Skill Effects box surfaces (projectile speed / penetration / jumps). Per-skill
  // scoping is Phase-2 engine work; for now we show the build-wide totals with their source breakdowns.
  const bdCtx = useContext(BreakdownCtx)
  const statMap = bdCtx?.statMap ?? {}
  // "Show all boxes" reveals every mechanic/ailment/CC box regardless of skill-gating.
  const showAll = useUiPrefs(s => s.statsShowAllBoxes)

  if (!offense) {
    // No computed offense for this slot. If a skill IS equipped here (passive/buff/curse/empower), show its
    // foundation panel; otherwise the slot is empty.
    return skill
      ? <SkillFoundationPanel slot={slot} skill={skill} aura={aura} reservation={reservation} curse={curse} curseMeta={curseMeta} empower={empower} />
      : <StatPanel title={slotLabel(slot)} accent={AMBER}><div style={{ fontSize: 12, color: '#555' }}>No skill selected.</div></StatPanel>
  }

  if (!offense.supported) {
    return skill
      ? <SkillFoundationPanel slot={slot} skill={skill} aura={aura} reservation={reservation} curse={curse} curseMeta={curseMeta} empower={empower} />
      : (
        <StatPanel title={`${slotLabel(slot)} — ${offense.skill_name}`} accent={AMBER}>
          <div style={{ fontSize: 12, color: '#ff6b6b' }}>Skill calculation not yet supported.</div>
        </StatPanel>
      )
  }

  const isSpell = hasTag(offense,'spell')
  const rateLabel = isSpell ? 'Casts per Second' : 'Attacks per Second'
  const rateKeys = isSpell
    ? ['cast_speed_inc', 'cast_speed_additional', 'combo_starter_cast_speed_additional']
    : ['weapon_attack_speed', 'attack_speed_inc', 'attack_speed_gear', 'attack_speed_mh', 'attack_speed_additional', 'combo_starter_attack_speed_additional']

  // Whether this skill lands hits — a precondition for inflicting ailments / crowd control. A skill that deals
  // no hit damage (pure aura/buff/persistent with no strike) can't apply these unless it has special behavior,
  // so those boxes stay hidden for it.
  const canHit = (offense.total_dps ?? 0) > 0 || (offense.hit_forms ?? []).some(f => (f.dps_contribution ?? 0) > 0)
  const stat = (k: string) => statMap[k]?.total ?? 0
  // Per-skill value: the character-wide total PLUS this slot's skill-specific (support) contributions — same
  // slot scoping the breakdown body uses, so Skill Effects shows the value for the SELECTED skill, not build-wide.
  const statForSlot = (k: string) => {
    const e = statMap[k]
    if (!e) return 0
    const slotPart = (e.slot_sources ?? []).filter(s => s.slot === slot).reduce((sum, s) => sum + (s.amount ?? 0), 0)
    return (e.total ?? 0) + slotPart
  }

  // The damage types this skill actually deals — each ailment is gated to its element (fire→Ignite, cold→
  // Frostbite/Freeze, lightning→Numbed, physical→Trauma, erosion→Wilt), so e.g. a pure-cold skill never shows
  // an Ignite box. (Build-wide vs per-skill scoping of the chances/effects is Phase-2; Show-all overrides.)
  const dealtTypes = new Set<string>()
  for (const f of offense.hit_forms ?? []) {
    for (const d of ALL_DTYPES) {
      if ((f.hit_max_by_type?.[d] ?? 0) > 0 || (f.damage_by_type?.[d] ?? 0) > 0) dealtTypes.add(d)
    }
  }
  const dealsType = (d: string) => dealtTypes.has(d)

  // Damaging ailments (DoT damage itself is NOT modeled yet → "Damage NYI"); each box shows the inflict chance
  // and the build's scaling mods, gated to skills that deal the matching damage type.
  const AILMENTS: { key: string; name: string; accent: string; dtype: string; chanceKey: string;
    mods: { label: string; keys: string[] }[] }[] = [
    { key: 'ignite', name: 'Ignite', accent: '#e87030', dtype: 'fire', chanceKey: 'ignite_chance', mods: [
      { label: 'Increased Damage', keys: ['ignite_dmg_inc'] },
      { label: 'Additional Damage', keys: ['ignite_dmg_additional'] },
      { label: 'Duration', keys: ['ignite_duration_inc'] } ] },
    { key: 'wilt', name: 'Wilt', accent: '#80c878', dtype: 'erosion', chanceKey: 'wilt_chance', mods: [
      { label: 'Increased Damage', keys: ['wilt_dmg_inc'] },
      { label: 'Additional Damage', keys: ['wilt_dmg_additional'] },
      { label: 'Duration', keys: ['wilt_duration_inc'] } ] },
    { key: 'trauma', name: 'Trauma', accent: '#d09060', dtype: 'physical', chanceKey: 'trauma_chance', mods: [
      { label: 'Increased Damage', keys: ['trauma_dmg_inc'] },
      { label: 'Additional Damage', keys: ['trauma_dmg_additional'] } ] },
  ]
  const generalAilmentChance = stat('damaging_ailment_chance')

  // Non-damage ailments — debuffs on the target rather than DoT. Cold → Frostbite (+ Freeze status); Lightning →
  // Numbed. Gated to skills that deal the matching type. Numbed/Frostbite surface their effect + damage-taken
  // amplification from the build's stats; Freeze is a status stub until its chance/duration is modeled.
  const NONDMG: { key: string; name: string; accent: string; dtype: string;
    rows: { label: string; keys: string[] }[]; note?: string; statusNYI?: string }[] = [
    { key: 'numbed', name: 'Numbed', accent: '#e0d040', dtype: 'lightning', rows: [
      { label: 'Effect', keys: ['numbed_effect_inc'] },
      { label: 'Lightning Damage Taken', keys: ['numbed_lightning_taken'] } ] },
    // Frostbite and Freeze share a box — Freeze is the heavy-Cold-buildup status that follows Frostbite.
    { key: 'frostbite', name: 'Frostbite / Freeze', accent: '#60b8e8', dtype: 'cold', rows: [
      { label: 'Effect', keys: ['frostbite_effect_inc'] },
      { label: 'Cold Damage Taken', keys: ['frostbite_cold_taken'] } ], statusNYI: 'Freeze',
      note: 'Frostbite amplifies the Cold damage enemies take; heavy Cold buildup also Freezes them. Freeze chance / duration / shatter aren\'t modeled yet.' },
  ]

  // Crowd control — chance-only stats (effects beyond chance aren't simulated). One box, listing whichever apply.
  const CC: { label: string; key: string }[] = [
    { label: 'Knockback', key: 'knockback_chance' },
    { label: 'Slow', key: 'slow_chance' },
    { label: 'Blind', key: 'blind_chance' },
    { label: 'Paralyze', key: 'paralyze_chance' },
    { label: 'Taunt on Hit', key: 'taunt_on_hit_chance' },
  ]
  const ccActive = CC.filter(c => stat(c.key) > 0)

  return (
    <>
      <StatPanel title={`${slotLabel(slot)} — ${offense.skill_name} (Level ${offense.effective_level})`} accent={AMBER}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '4px 0 6px' }}>
          <span style={{ fontSize: 12, color: '#999' }}>DPS</span>
          <span style={{ fontSize: 17, fontWeight: 700, color: '#f0c070', fontVariantNumeric: 'tabular-nums' }}>
            {fmtNum(offense.total_dps_vs_target)}
          </span>
        </div>
        {(offense.spell_burst_count ?? 0) > 0 && (offense.non_spell_burst_dps_vs_target ?? 0) > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1, padding: '0 0 6px', marginTop: -2 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span style={{ color: '#7fb0e0' }}>Spell Burst</span>
              <span style={{ color: '#7fb0e0', fontVariantNumeric: 'tabular-nums' }}>{fmtNum(offense.spell_burst_dps_vs_target)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span style={{ color: '#999' }}>Non Spell Burst</span>
              <span style={{ color: '#aaa', fontVariantNumeric: 'tabular-nums' }}>{fmtNum(offense.non_spell_burst_dps_vs_target)}</span>
            </div>
          </div>
        )}
        {offense.above_max_mult > 1.0 && (
          <Row label="Above Max Multiplier">×{offense.above_max_mult.toFixed(3)}</Row>
        )}
      </StatPanel>

      <StatPanel title="Skill Hit Damage" accent={AMBER}>
        <DamageBreakdownTable offense={offense} />
      </StatPanel>

      {/* Box grid: rate · crit · skill effects always present, then any mechanic boxes that apply (shotgun,
          tangle, spell burst, channeled, ailments, stubs). Row-major masonry keeps Hit Rate → Crit → Skill
          Effects across the top, then fills the shortest column. Column count scales with width; box width is
          capped by columnMax so boxes don't sprawl. */}
      <MasonryGrid columnWidth={220} columnMax={340} gap={6}>
        <GridBox>
          <StatPanel title="Hit Rate" accent={AMBER}
            info={isSpell ? 'Cast Rate = 1 ÷ Cast Time × (1 + Increased) × Additional. Multi-form skills list each form\'s own firing rate — some forms fire every cast, others on a slower cadence.'
              : 'Attack Rate = Weapon APS × (1 + Gear) × (1 + Increased) × Additional. Multi-form skills list each form\'s own firing rate.'}>
            {/* Multi-form skills list each form's own firing rate (forms fire at different cadences — e.g. beam
                every cast, blade slower); the general cast/attack rate is dropped since the main form duplicates
                it. Single-form skills show the one general rate. Each row carries its own source breakdown. */}
            {offense.hit_forms.length > 1 ? (
              offense.hit_forms.map(f => (
                <Row key={f.name} label={f.name} labelColor="#8aa" breakdown={{
                  title: `${f.name} — firing rate`, keys: rateKeys, total: f.fires_per_sec, totalUnit: ' /s',
                  formula: isSpell ? '1 ÷ Cast Time × (1 + Increased) × Additional, at this form\'s cadence' : 'Weapon APS × (1 + Gear) × (1 + Increased) × Additional, at this form\'s cadence',
                  extra: isSpell && offense.base_cast_time > 0
                    ? [{ value: `${dec(offense.base_cast_time)}s`, stat: 'Base Cast Time', source: 'Baseline', sourceName: offense.skill_name }]
                    : undefined,
                }}>{dec(f.fires_per_sec)}/s</Row>
              ))
            ) : (
              <Row label={rateLabel} breakdown={{
                title: rateLabel, keys: rateKeys, total: offense.attacks_per_second, totalUnit: '',
                formula: isSpell ? '1 ÷ Cast Time × (1 + Increased) × Additional' : 'Weapon APS × (1 + Gear) × (1 + Increased) × Additional',
                extra: isSpell && offense.base_cast_time > 0
                  ? [{ value: `${dec(offense.base_cast_time)}s`, stat: 'Base Cast Time', source: 'Baseline', sourceName: offense.skill_name }]
                  : undefined,
              }}>{dec(offense.attacks_per_second)}</Row>
            )}
          </StatPanel>
        </GridBox>

        <GridBox>
          <StatPanel title="Critical Strikes" accent={AMBER}>
            {/* Hover for the full breakdown (like the other rows) — no inline accordion. For spells the
                intrinsic base crit rating is shown as a "Spell base" baseline; for attacks the weapon's base
                crit rating shows as a real gear source via weapon_crit_rating_flat. */}
            <Row label="Crit Chance" breakdown={{
              title: 'Crit Chance',
              keys: isSpell
                ? ['spell_crit_rating_flat', 'spell_crit_rating_inc', 'crit_rating_inc', 'crit_rating_additional', 'projectile_crit_rating_inc']
                : ['weapon_crit_rating_flat', 'attack_crit_rating_gear', 'attack_crit_rating_mh', 'attack_crit_rating_flat', 'attack_crit_rating_inc', 'crit_rating_inc', 'crit_rating_additional'],
              total: offense.crit_chance, totalUnit: '%',
              formula: '(Base + Flat) × (1 + Increased) ÷ 100',
              extra: isSpell && offense.base_csr > 0
                ? [{ value: offense.base_csr.toFixed(0), stat: 'Base Crit Rating', source: 'Baseline', sourceName: 'Spell base' }]
                : undefined,
            }}>{dec((offense.crit_chance * 100))}%</Row>
            <Row label="Crit Multiplier" breakdown={{
              title: 'Crit Multiplier',
              keys: ['crit_damage'],
              total: offense.crit_multiplier, totalUnit: '%',
              formula: '150% + Σ Crit Damage',
              extra: [{ value: '150%', stat: 'Crit Multiplier', source: 'Baseline', sourceName: 'Base ×1.5' }],
            }}>{(offense.crit_multiplier * 100).toFixed(0)}%</Row>
          </StatPanel>
        </GridBox>

        {/* Skill Effects — one of the 3 always-present boxes. Area/count/speed show for projectile-or-area skills;
            penetrations and jumps only appear when the build actually has them. (Values are build-wide today;
            per-skill scoping is Phase-2.) */}
        {(() => {
          const projSpeedInc = statForSlot('projectile_speed_inc')
          const penetrations = statForSlot('horizontal_projectile_penetration_flat')
          const baseJumps = offense.jumps_base ?? 0
          const extraJumps = statForSlot('extra_jumps_flat')
          const totalJumps = offense.jumps ?? (baseJumps + extraJumps)
          const manaCost = offense.mana_cost ?? 0
          return (
            <GridBox>
              <StatPanel title="Skill Effects" accent={AMBER}>
                {hasTag(offense, 'area') && (
                  <Row label="Area of Effect">{offense.skill_area_inc !== 0 ? `+${(offense.skill_area_inc * 100).toFixed(0)}%` : '+0%'}</Row>
                )}
                {hasTag(offense, 'projectile') && (
                  (offense.projectile_count ?? -1) >= 0
                    ? <Row label="Projectile Count" breakdown={{
                        title: 'Projectile Count', keys: ['projectile_quantity_flat'], total: offense.projectile_count, totalUnit: '',
                        formula: 'skill base projectiles + Σ +Projectile Quantity (all home onto one target and shotgun); 0 = the projectile form does not fire',
                      }}>{offense.projectile_count}</Row>
                    : <Row label="Projectile Count" labelColor="#555">— NYI</Row>
                )}
                {/* Projectile Speed: always shown for projectile skills (even at +0%), with its source breakdown. */}
                {hasTag(offense, 'projectile') && (
                  <Row label="Projectile Speed" breakdown={{
                    title: 'Projectile Speed', keys: ['projectile_speed_inc', 'projectile_speed_additional'],
                    total: projSpeedInc, totalUnit: '%', formula: 'Σ Increased Projectile Speed × Π(1 + Additional)',
                  }}>{projSpeedInc !== 0 ? `+${dec(projSpeedInc * 100)}%` : '+0%'}</Row>
                )}
                {/* Horizontal Penetration: only when the build has it. */}
                {penetrations > 0 && (
                  <Row label="Horizontal Penetration" breakdown={{
                    title: 'Horizontal Penetration', keys: ['horizontal_projectile_penetration_flat'],
                    total: penetrations, totalUnit: '', formula: 'Σ +Horizontal Projectile Penetration',
                  }}>{penetrations}</Row>
                )}
                {/* Jumps / Chains: shown for jump skills (e.g. Chain Lightning's +2) = skill base + support extras. */}
                {totalJumps > 0 && (
                  <Row label="Jumps" breakdown={{
                    title: 'Jumps', keys: ['extra_jumps_flat'],
                    total: totalJumps, totalUnit: '',
                    formula: `skill base ${baseJumps}${extraJumps ? ` + ${extraJumps} extra (supports)` : ''}`,
                  }}>{totalJumps}</Row>
                )}
                {/* Mana Cost — the skill's BASE per-cast cost. Cost reductions/conversions and "Skills no longer cost
                    Mana" aren't modeled yet, so this is the unmodified base (reservation/sealing is its own panel). */}
                {manaCost > 0 && (
                  <Row label="Mana Cost" breakdown={{
                    title: 'Mana Cost', keys: [], total: manaCost, totalUnit: '',
                    formula: 'Skill base per-cast cost. Cost reductions / conversions and "Skills no longer cost Mana" are not modeled yet.',
                  }}>{dec(manaCost)}</Row>
                )}
              </StatPanel>
            </GridBox>
          )
        })()}

        {/* Shotgunning: shows each form that lands multiple same-target hits (projectiles/blades) plus any
            cast-level same-target shotgun. Hidden when nothing shotguns. */}
        {(() => {
          const sgForms = (offense.hit_forms ?? []).filter(f => (f.hits_per_fire ?? 0) > 1)
          const castShotgun = (offense.shotgun_hits ?? 0) > 1
          if (sgForms.length === 0 && !castShotgun) return null
          return (
            <GridBox>
              <StatPanel title="Shotgunning" accent={AMBER}
                info="Multiple hits land on the same target each occurrence; each subsequent hit is reduced by the falloff coefficient. Same-target multiplier = 1 + (hits − 1) × (1 − falloff).">
                {sgForms.map((f, i) => (
                  <React.Fragment key={f.name}>
                    {/* One sub-block per form: name header, then the count / falloff / multiplier broken out
                        across their own rows rather than crammed into a single line. */}
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#e0d0a0', marginTop: i > 0 ? 6 : 0, marginBottom: 1 }}>{f.name}</div>
                    <Row label="Projectiles / hits">{f.hits_per_fire}</Row>
                    <Row label="Falloff coefficient">{dec(f.shotgun_falloff * 100)}%</Row>
                    <Row label="Same-target multiplier"><span style={{ color: '#f0c070' }}>×{dec(f.shotgun_mult)}</span></Row>
                  </React.Fragment>
                ))}
                {castShotgun && (
                  <>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#e0d0a0', marginTop: sgForms.length ? 6 : 0, marginBottom: 1 }}>Per cast</div>
                    <Row label="Same-target hits">{offense.shotgun_hits}</Row>
                    <Row label="Multiplier"><span style={{ color: '#f0c070' }}>×{dec(offense.cast_multiplier)}</span></Row>
                  </>
                )}
              </StatPanel>
            </GridBox>
          )
        })()}

        {/* Per-element split for Chromatic Shot's compulsory conversion is shown inline in the Skill Hit Damage table
            (each element's contribution + % of total), so no standalone box is needed here. */}

      {(offense.tangle_count ?? 0) > 0 && (
        <GridBox><StatPanel title="Tangle" accent={AMBER}
          info="Cast by attached Tangles (each a full caster) — Tangle DPS = per-cast × attached count. Tangle Damage / Enhancement / Crit feed the normal damage pools above.">
          <Row label="Attached (casting)" breakdown={{
            title: 'Attached Tangles', keys: ['extra_tangle_applied_flat'], total: offense.tangle_count, totalUnit: '',
            extra: [{ value: '1', stat: 'Base', source: 'Baseline', sourceName: 'Base attach per enemy' }],
            formula: 'min(1 base + Additional Tangles Applied, Max Placeable)',
          }}>{offense.tangle_count}</Row>
          <Row label="Max Placeable" breakdown={{
            title: 'Max Tangle Quantity', keys: ['max_tangle_quantity_flat'], total: offense.tangle_placeable, totalUnit: '',
            extra: [{ value: '2', stat: 'Base', source: 'Baseline', sourceName: 'Base Max Tangle Quantity' }],
            formula: '2 base + Max Tangle Quantity',
          }}>{offense.tangle_placeable}</Row>
          <Row label="Inactivated" breakdown={{
            title: 'Inactivated Tangles', keys: [], total: offense.tangle_inactivated, totalUnit: '',
            formula: 'Max Placeable − Active (feeds Dormant Entanglement)',
          }}>{offense.tangle_inactivated}</Row>
          <Row label="Duration" breakdown={{
            title: 'Tangle Duration', keys: ['tangle_duration_inc', 'tangle_duration_additional'], total: offense.tangle_duration, totalUnit: ' s',
            extra: [{ value: '8 s', stat: 'Base', source: 'Baseline', sourceName: 'Base Duration' }],
            formula: '8 s × (1 + Increased) × (1 + Additional)',
          }}>{dec(offense.tangle_duration)} s</Row>
          <Row label="Attach Range" breakdown={{
            title: 'Tangle Attach Range', keys: ['tangle_attach_range_inc'], total: offense.tangle_attach_range, totalUnit: ' m',
            extra: [{ value: '8 m', stat: 'Base', source: 'Baseline', sourceName: 'Base Attach Range' }],
            formula: '8 m × (1 + Increased)',
          }}>{dec(offense.tangle_attach_range)} m</Row>
          <Row label="Tangle Damage Multiplier" labelColor="#d8b878">
            <span style={{ color: '#f0c070' }}>×{dec((offense.tangle_mult ?? offense.tangle_count))}</span>
          </Row>
        </StatPanel></GridBox>
      )}

      {(offense.spell_burst_count ?? 0) > 0 && (
        <GridBox><StatPanel title="Spell Burst" accent={SKYBLUE}
          info="An eligible Spell cast at full charge consumes all stacks and recasts itself (the triggering cast counts too). Charge is a server-timed whole-tick countdown (30 Hz), so charge speed only helps at integer-tick crossings. Spell Burst Hit Damage feeds the additional pool above.">
          <Row label="Max Spell Burst" breakdown={{
            title: 'Max Spell Burst', keys: ['max_spell_burst_flat'], total: offense.spell_burst_count, totalUnit: '',
            formula: 'Σ +Max Spell Burst (base 0)',
          }}>{offense.spell_burst_count}</Row>
          <Row label="Casts / Burst" breakdown={{
            title: 'Casts per Burst', keys: ['max_spell_burst_flat'], total: offense.spell_burst_casts_per_burst, totalUnit: '',
            formula: '1 (triggering cast) + Max Spell Burst',
            extra: [{ value: '1', stat: 'Base', source: 'Baseline', sourceName: 'Triggering cast' }],
          }}>{offense.spell_burst_casts_per_burst}</Row>
          <Row label="Charge Time" breakdown={{
            title: 'Spell Burst Charge Time', keys: ['spell_burst_charge_speed_inc', 'spell_burst_charge_speed_additional'],
            total: offense.spell_burst_charge_time, totalUnit: ' s',
            extra: [{ value: '2 s', stat: 'Base', source: 'Baseline', sourceName: 'Base Charge Time' }],
            formula: '2 s ÷ (1 + Increased) ÷ Π(1 + Additional)  [Play Safe feeds Cast Speed]',
          }}>{dec(offense.spell_burst_charge_time)} s</Row>
          <Row label="Charge Speed (Increased)" breakdown={{
            title: 'Spell Burst Charge Speed — Increased', keys: ['spell_burst_charge_speed_inc'],
            total: offense.spell_burst_charge_inc, totalUnit: '%',
            formula: 'Σ Spell Burst Charge Speed Increased — matches the in-game stat. Additional bonuses are NOT '
              + 'included here (they already shorten Charge Time above); Solid River’s auto-trigger checks THIS '
              + 'increased total against its threshold, before additional.',
          }}>+{dec((offense.spell_burst_charge_inc * 100))}%</Row>
          {(() => {
            const chg = offense.spell_burst_charge_to_next_inc, cast = offense.spell_burst_cast_to_next_inc
            const chgPct = `+${dec((chg * 100))}%`, castPct = `+${dec((cast * 100))}%`
            return (
              <Row label="Charge Ticks" labelColor="#9ab" breakdown={{
                title: 'Charge Ticks → next bursts/sec breakpoint', keys: [], total: offense.spell_burst_charge_ticks, totalUnit: ' ticks',
                formula: 'Charge Ticks = ceil(30 × Charge Time) — server-timed, rounds UP to a whole tick. '
                  + (offense.spell_burst_auto
                    ? 'Auto: bursts/sec = 30 ÷ ticks, so every whole tick is a real gain (only sub-tick rounding is wasted).'
                    : 'Manual: bursts/sec = 30 ÷ (ceil(charge ÷ cast)·cast), gated by BOTH charge speed AND cast speed — '
                      + 'so many intermediate charge ticks add nothing, and cast speed can be the closer breakpoint. '
                      + 'Both levers are scanned (incl. Play Safe cast→charge) for the next that actually raises bursts/sec.')
                  + ' (Surging, if it is the limiter, masks this.)',
                extra: [
                  ...(chg > 0
                    ? [{ value: chgPct, stat: `Charge Speed → next breakpoint${offense.spell_burst_next_breakpoint_ticks > 0 ? ` (${offense.spell_burst_next_breakpoint_ticks} ticks)` : ''}`, source: '', sourceName: 'more Spell Burst Charge Speed → higher bursts/sec' }]
                    : [{ value: '—', stat: 'Charge Speed', source: '', sourceName: offense.spell_burst_charge_ticks <= 1 ? 'already at 1 tick (30 bursts/s)' : 'no reachable breakpoint' }]),
                  ...(!offense.spell_burst_auto
                    ? [cast > 0
                        ? { value: castPct, stat: 'Cast Speed → next breakpoint', source: '', sourceName: 'raises bursts/sec (and feeds charge via Play Safe)' }
                        : { value: '—', stat: 'Cast Speed', source: '', sourceName: 'charge-limited — cast speed cannot raise bursts/sec here' }]
                    : []),
                ],
              }}>
                {offense.spell_burst_charge_ticks}
              </Row>
            )
          })()}
          <Row label="Bursts / sec" breakdown={{
            title: 'Bursts per Second', keys: [], total: offense.spell_burst_rate, totalUnit: ' /s',
            formula: offense.spell_burst_auto
              ? '30 ÷ Charge Ticks  (auto: fires the tick it is fully charged)'
              : '30 ÷ (cast-aligned charge period)  (manual: waits for the next cast at/after the charge tick)',
            extra: [
              { value: `${offense.spell_burst_charge_ticks} ticks`, stat: 'Charge Ticks', source: 'Tick', sourceName: 'ceil(30 × Charge Time)' },
              { value: offense.spell_burst_auto ? 'Auto' : 'Manual', stat: 'Trigger', source: '', sourceName: offense.spell_burst_auto ? 'instant at full charge' : 'gated by cast rate' },
              ...(offense.spell_burst_auto ? [] : [{ value: `${dec(offense.attacks_per_second)} /s`, stat: 'Cast Rate', source: '', sourceName: 'player casts/sec (30-capped)' }]),
            ],
          }}>{dec(offense.spell_burst_rate)}</Row>
          <Row label="Effective casts / sec" breakdown={{
            title: 'Effective Casts per Second', keys: [],
            total: offense.spell_burst_casts_per_burst * offense.spell_burst_rate, totalUnit: ' /s',
            formula: 'Casts per Burst × Bursts per Second',
            extra: [
              { value: `${offense.spell_burst_casts_per_burst}`, stat: 'Casts / Burst', source: '', sourceName: 'M + 1' },
              { value: `${dec(offense.spell_burst_rate)} /s`, stat: 'Bursts / sec', source: '', sourceName: '' },
            ],
          }}>{dec((offense.spell_burst_casts_per_burst * offense.spell_burst_rate))}</Row>
          <Row label="Trigger" breakdown={{
            title: 'Spell Burst Trigger', keys: [],
            formula: offense.spell_burst_auto
              ? 'Auto-trigger: Spell Burst fires the instant it is fully charged — you do not cast manually, so only burst casts count.'
              : 'Manual: you cast the skill yourself; a cast at full charge triggers the burst, and the casts you make between bursts are also counted.',
            extra: [offense.spell_burst_auto
              ? { value: '', stat: 'Source', source: '', sourceName: offense.spell_burst_auto_source || 'Auto-trigger' }
              : { value: '', stat: 'Source', source: '', sourceName: 'Manual cast (base) — Solid River / Vorax / Burst Activation switch to Auto' }],
          }}>{offense.spell_burst_auto ? 'Auto' : 'Manual'}</Row>
          <Row label="Spell Burst DPS" labelColor="#9ad">
            <span style={{ color: '#7fb0e0' }}>{fmtNum(offense.spell_burst_dps_vs_target)}</span>
          </Row>
          {!offense.spell_burst_auto && (
            <Row label="Non Spell Burst DPS" breakdown={{
              title: 'Non Spell Burst DPS', keys: [], total: offense.non_spell_burst_dps_vs_target, totalUnit: '',
              formula: 'Casts made BETWEEN bursts (manual only) — normal casts that do NOT get the Spell Burst Hit '
                + 'Damage pool. = per-normal-cast × (cast rate − bursts/sec). Auto-trigger has none (you do not cast manually).',
              extra: [
                { value: `${dec(Math.max(0, offense.attacks_per_second - offense.spell_burst_rate))} /s`, stat: 'Normal casts / sec', source: '', sourceName: 'cast rate − bursts/sec' },
              ],
            }}>{fmtNum(offense.non_spell_burst_dps_vs_target)}</Row>
          )}
          <Row label="Combined DPS" labelColor="#9ad" breakdown={{
            title: 'Combined Skill DPS', keys: [], total: offense.total_dps_vs_target, totalUnit: '',
            formula: offense.spell_burst_auto
              ? 'Auto-trigger: all output is Spell Burst (you do not cast manually).'
              : 'Manual: Spell Burst casts + the normal casts you make between bursts.',
            extra: [
              { value: fmtNum(offense.spell_burst_dps_vs_target), stat: 'Spell Burst DPS', source: '', sourceName: `${offense.spell_burst_casts_per_burst} casts/burst × ${dec(offense.spell_burst_rate)}/s` },
              ...(offense.spell_burst_auto ? [] : [{ value: fmtNum(offense.non_spell_burst_dps_vs_target), stat: 'Non Spell Burst DPS', source: '', sourceName: 'casts between bursts' }]),
            ],
          }}>
            <span style={{ color: '#f0c070' }}>{fmtNum(offense.total_dps_vs_target)}</span>
          </Row>
        </StatPanel></GridBox>
      )}

      {(offense.channeled_max_stacks ?? 0) > 0 && (
        <GridBox><StatPanel title="Channeled" accent={SKYBLUE}
          info={'Gains 1 channeled stack per use (the first round from 0 gains 1 + Min). '
            + (offense.channeled_behavior === 'reset'
              ? 'At max stacks it dumps ALL stacks and fires its burst form, then ramps again — so the continuous form fires every use while the burst fires once per cycle.'
              : 'Holds at max while channeling.')
            + ((offense.channeled_attack_frequency ?? 0) > 0
              ? ' The damage is dealt by a persistent entity striking at its own Attack Frequency (below), not the channel rate.'
              : '')}>
          <Row label="Max Channeled Stacks" breakdown={{
            title: 'Max Channeled Stacks', keys: ['max_channeled_stacks_flat'], total: offense.channeled_max_stacks, totalUnit: '',
            formula: 'skill base + Σ +Max Channeled Stacks',
          }}>{offense.channeled_max_stacks}</Row>
          <Row label="Min Channeled Stacks" breakdown={{
            title: 'Min Channeled Stacks', keys: ['min_channeled_stacks_flat'], total: offense.channeled_min_stacks, totalUnit: '',
            formula: 'Σ +Min Channeled Stacks — the first round from 0 gains 1 + Min (shortens the ramp)',
          }}>{offense.channeled_min_stacks}</Row>
          {(offense.channeled_attack_frequency ?? 0) > 0 && (
            <>
              <Row label="Channel Rate" breakdown={{
                title: 'Channel Rate', keys: ['cast_speed_inc', 'cast_speed_additional', 'channeled_cast_speed_inc'],
                total: offense.attacks_per_second, totalUnit: ' /s',
                formula: '1 ÷ Cast Time × (1 + Increased) × Additional — how fast channeled stacks build (0 → Max)',
              }}>{dec(offense.attacks_per_second)} /s</Row>
              <Row label="Gale Attack Frequency" breakdown={{
                title: 'Gale Attack Frequency', keys: ['cast_speed_inc', 'cast_speed_additional', 'channeled_attack_frequency_additional'],
                total: offense.channeled_attack_frequency, totalUnit: ' /s',
                formula: 'Base Attack Frequency × cast-speed multiplier × (1 + additional Gale Attack Frequency) — the persistent entity\'s strike rate (the damage rate)',
                extra: [{ value: '1.5 /s', stat: 'Base Attack Frequency', source: 'Baseline', sourceName: offense.skill_name }],
              }}>{dec(offense.channeled_attack_frequency)} /s</Row>
            </>
          )}
          {offense.channeled_behavior === 'reset' && (
            <>
              <Row label="Uses / Cycle" breakdown={{
                title: 'Uses per Reset Cycle', keys: [], total: offense.channeled_rounds_per_cycle, totalUnit: '',
                formula: 'max(1, Max − Min) — uses to ramp 0 → Max before the dump',
                extra: [
                  { value: `${offense.channeled_max_stacks}`, stat: 'Max', source: '', sourceName: 'Max Channeled Stacks' },
                  { value: `${offense.channeled_min_stacks}`, stat: 'Min', source: '', sourceName: 'Min Channeled Stacks' },
                ],
              }}>{dec(offense.channeled_rounds_per_cycle)}</Row>
              <Row label="Burst Rate" breakdown={{
                title: 'Reset Burst Rate', keys: [], total: offense.channeled_burst_rate, totalUnit: ' /s',
                formula: 'Cast Rate ÷ Uses per Cycle — how often the dump/burst form fires',
                extra: [
                  { value: `${dec(offense.attacks_per_second)} /s`, stat: 'Cast Rate', source: '', sourceName: 'uses/sec' },
                  { value: `${dec(offense.channeled_rounds_per_cycle)}`, stat: 'Uses / Cycle', source: '', sourceName: 'max(1, Max − Min)' },
                ],
              }}>{dec(offense.channeled_burst_rate)} /s</Row>
            </>
          )}
        </StatPanel></GridBox>
      )}

      {/* Damaging-ailment boxes (Ignite=fire / Wilt=erosion / Trauma=physical) — informational: inflict chance +
          scaling mods, with DoT damage flagged NYI (not modeled). Shown when this skill deals the matching type
          (or Show-all). Per-skill scoping + "cannot inflict" override chains in the breakdown are Phase-2. */}
      {AILMENTS.filter(a => (canHit && dealsType(a.dtype)) || showAll).map(a => {
        const chance = stat(a.chanceKey)
        return (
          <GridBox key={a.key}>
            <StatPanel title={a.name} accent={a.accent}
              info={`Chance to inflict ${a.name} on hit (${a.dtype} damage), plus the build's ${a.name} scaling. The damage-over-time itself is not modeled yet (Damage: NYI).`}>
              <Row label="Chance" breakdown={{
                title: `${a.name} Chance`, keys: [a.chanceKey], total: chance, totalUnit: '%',
                formula: `Σ ${a.name} Chance${generalAilmentChance > 0 ? ' (+ Damaging Ailment Chance)' : ''}`,
              }}>{dec(chance * 100)}%</Row>
              {a.mods.map(m => {
                const v = stat(m.keys[0])
                return (
                  <Row key={m.label} label={m.label} breakdown={{ title: `${a.name} — ${m.label}`, keys: m.keys, total: v, totalUnit: '%', formula: `Σ ${a.name} ${m.label}` }}>
                    {v !== 0 ? `+${dec(v * 100)}%` : '+0%'}
                  </Row>
                )
              })}
              <Row label="Damage" labelColor="#c8645a">NYI</Row>
            </StatPanel>
          </GridBox>
        )
      })}

      {/* Non-damage ailment boxes (Numbed=lightning / Frostbite=cold / Freeze=cold) — debuffs on the target.
          Gated to skills that deal the matching type. */}
      {NONDMG.filter(n => (canHit && dealsType(n.dtype)) || showAll).map(n => (
        <GridBox key={n.key}>
          <StatPanel title={n.name} accent={n.accent}
            info={n.note ?? `${n.name} debuff applied to enemies hit by ${n.dtype} damage. Values are the build's ${n.name} scaling.`}>
            {n.rows.length > 0
              ? n.rows.map(r => {
                  const v = stat(r.keys[0])
                  return (
                    <Row key={r.label} label={r.label} breakdown={{ title: `${n.name} — ${r.label}`, keys: r.keys, total: v, totalUnit: '%', formula: `Σ ${n.name} ${r.label}` }}>
                      {v !== 0 ? `+${dec(v * 100)}%` : '+0%'}
                    </Row>
                  )
                })
              : <Row label="Status" labelColor="#888">applied · <span style={{ color: '#c8645a' }}>NYI</span></Row>}
            {n.statusNYI && (
              <Row label={n.statusNYI} labelColor="#888"><span style={{ color: '#c8645a' }}>NYI</span></Row>
            )}
          </StatPanel>
        </GridBox>
      ))}

      {/* Crowd Control — chance-only stats (the effects beyond chance aren't simulated). */}
      {((canHit && ccActive.length > 0) || showAll) && (
        <GridBox>
          <StatPanel title="Crowd Control" accent={GREY}
            info="Chance to apply each crowd-control effect on hit. The effects themselves (duration, distance, etc.) aren't simulated yet.">
            {(showAll ? CC : ccActive).map(c => {
              const v = stat(c.key)
              return (
                <Row key={c.key} label={c.label} breakdown={{ title: `${c.label} Chance`, keys: [c.key], total: v, totalUnit: '%', formula: `Σ ${c.label} Chance` }}>
                  {dec(v * 100)}%
                </Row>
              )
            })}
          </StatPanel>
        </GridBox>
      )}

      {/* Multistrike (attack skills): the auto-repeat DPS multiplier + its inputs. Shown when this skill has any
          Multistrike Chance (or Show-all). */}
      {((offense.multistrike_chance ?? 0) > 0 || showAll) && (
        <GridBox><StatPanel title="Multistrike" accent={AMBER}
          info="Using an attack skill has a chance to auto-repeat it: every full 100% chance = +1 guaranteed repeat, the leftover is the chance of one more. Each repeat pays its own attack time (repeats get +20% increased attack speed) and deals increasing damage (the n-th hit of a chain gets (n−1) increment stacks; Initial Count pre-stacks it). DPS multiplier = expected chain damage ÷ (rate × expected chain time).">
          <Row label="DPS Multiplier" labelColor="#d8b878"><span style={{ color: '#f0c070' }}>×{dec(offense.multistrike_mult ?? 1)}</span></Row>
          <Row label="Chance">{dec((offense.multistrike_chance ?? 0) * 100)}%</Row>
          <Row label="Repeat Attack Speed" breakdown={{
            title: 'Repeat Attack Speed', keys: [], total: offense.multistrike_repeat_aps ?? 0, totalUnit: ' /s',
            formula: 'Base Attack Rate × (1 + Increased AS + 0.20) ÷ (1 + Increased AS) — repeats gain +20% INCREASED attack speed; the first hit of a chain does not.',
            extra: [{ value: `${dec(offense.attacks_per_second)} /s`, stat: 'Base Attack Rate', source: 'Rate', sourceName: 'first hit / no multistrike' }],
          }}>{dec(offense.multistrike_repeat_aps ?? 0)} /s</Row>
          <Row label="Avg Count">{dec(offense.multistrike_avg_count ?? 0)}</Row>
          <Row label="Max Count">{offense.multistrike_max_count ?? 0}</Row>
          <Row label="Damage Increment / stack">+{dec((offense.multistrike_increment ?? 0) * 100)}%</Row>
          {(offense.multistrike_chain ?? []).length > 0 && (
            <>
              <div style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: '#888', margin: '6px 0 2px' }}>Chain length</div>
              {(offense.multistrike_chain ?? []).map(ch => (
                <Row key={ch.count} label={`${ch.count} attacks`}>{dec(ch.prob * 100)}%</Row>
              ))}
            </>
          )}
        </StatPanel></GridBox>
      )}

      {/* Stub boxes for mechanics this skill has but the engine doesn't model yet (Combo / Demolisher / Barrage).
          The modeled mechanics above (Tangle / Spell Burst / Channeled / Multistrike) render real data instead.
          Show-all reveals every stub regardless of the skill's tags. */}
      {MECH_STUBS.filter(m => showAll || hasTag(offense, m.tag)).map(m => (
        <GridBox key={m.tag}><MechanicStubPanel label={m.label} note={m.note} /></GridBox>
      ))}

      {/* Consume boxes — not wired yet. Made now and hidden (only the Show-all toggle reveals them) so they're
          easy to populate later with the skill's per-cast / over-time Life & Mana consumption. */}
      {showAll && (
        <>
          <GridBox><MechanicStubPanel label="Mana Consume" note="Mana consumed by this skill (per cast / over time) is not wired yet." /></GridBox>
          <GridBox><MechanicStubPanel label="Life Consume" note="Life consumed by this skill (per cast / over time) is not wired yet." /></GridBox>
        </>
      )}
      </MasonryGrid>
    </>
  )
}

// ── Defense panels ────────────────────────────────────────────────────────────

function SubRow({ label, children, breakdown }: { label: string; children: React.ReactNode; breakdown?: { title: string; keys: string[]; total?: number; totalUnit?: string; extra?: ExtraRow[]; formula?: string; sections?: BreakdownSection[] } }) {
  const ctx = useContext(BreakdownCtx)
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right', trigger: 'hover', pinnable: true, interactive: true, openDelay: 90 })
  const bd = !!breakdown && !!ctx
  return (
    <>
      <div {...(bd ? tip.triggerProps : {})}
        style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 12, borderBottom: '1px solid rgba(255,255,255,0.03)', cursor: bd ? 'pointer' : undefined, outline: bd && tip.open ? '1px solid #fff' : undefined, outlineOffset: bd && tip.open ? 3 : undefined, background: bd && tip.open ? 'rgba(255,255,255,0.06)' : undefined }}>
        <span style={{ color: '#666' }}>{label}</span>
        <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums' }}>{children}</span>
      </div>
      {bd && tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--breakdown" {...tip.floatingProps}>
            <BreakdownBody title={breakdown!.title} keys={breakdown!.keys} ctx={ctx!} totalOverride={breakdown!.total} totalUnit={breakdown!.totalUnit} extra={breakdown!.extra} formula={breakdown!.formula} sections={breakdown!.sections} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

function fmtPct(v: number): string { return `${(v * 100).toFixed(0)}%` }
function fmtPct2(v: number): string { return `${dec((v * 100))}%` }
function fmtSignedPct(v: number): string { return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%` }
function fmtMult(v: number): string { return `×${dec((1 + v))}` }

// ── Middle-column panels: Attributes / Blessings / Utility ──────────────────────

function AttributesPanel({ statMap }: { statMap: Record<string, StatEntry> }) {
  const row = (key: string, label: string, comp: string[]) => (
    <Row key={key} label={label} labelColor={ATTR_COLOR[key]} breakdown={{ title: label, keys: comp, total: statMap[key]?.total ?? 0, formula: DEF_FORMULA }}>
      {fmtNum(statMap[key]?.total ?? 0)}
    </Row>
  )
  return (
    <StatPanel title="Attributes" accent="#c0a040">
      {row('strength', 'Strength', ['strength_flat', 'all_stats_flat', 'strength_inc', 'all_stats_inc', 'strength_additional'])}
      {row('dexterity', 'Dexterity', ['dexterity_flat', 'all_stats_flat', 'dexterity_inc', 'all_stats_inc', 'dexterity_additional'])}
      {row('intelligence', 'Intelligence', ['intelligence_flat', 'all_stats_flat', 'intelligence_inc', 'all_stats_inc', 'intelligence_additional'])}
    </StatPanel>
  )
}

// Strip "+5% " and " per Focus Blessing" / trailing "(Source)" from a blessing line → just the descriptor.
function blessingDesc(text: string): string {
  return text.replace(/^[+-][\d.]+\s*%?\s*/, '').replace(/\s*per\b.*?Blessing\b/i, '').replace(/\s*\([^)]*\)\s*$/, '').trim()
}

function BlessingsPanel({ blessings }: { blessings: BlessingSummary[] | null | undefined }) {
  if (!blessings || blessings.length === 0) return null
  return (
    <StatPanel title="Blessings" accent="#9a8ac0">
      {blessings.map(b => {
        // Each effect → a breakdown row (its total + the override source if the base effect was changed).
        const extra = b.effects.map(e => {
          const m = e.text.match(/\(([^)]+)\)\s*$/)   // trailing "(Divine Grace)" etc.
          return {
            value: fmtSignedPct(e.total),
            stat: blessingDesc(e.text),
            source: b.overridden ? 'Override' : 'Base',
            sourceName: m ? m[1] : '',
          }
        })
        return (
          <Row key={b.type} label={b.label.replace(' Blessing', '')}
            breakdown={{ title: `${b.label} — ${Math.round(b.stacks)}/${Math.round(b.max)}`, keys: [], extra, formula: b.overridden ? 'base effect changed' : undefined }}>
            {`${Math.round(b.stacks)}/${Math.round(b.max)}`}
          </Row>
        )
      })}
    </StatPanel>
  )
}

function UtilityPanel({ statMap }: { statMap: Record<string, StatEntry> }) {
  // Movement speed is the NET bonus at a 0% baseline (engine already nets it; reductions go negative).
  const net = statMap['movement_speed']?.total ?? 0
  return (
    <StatPanel title="Utility" accent="#607080">
      <Row label="Movement Speed" breakdown={{ title: 'Movement Speed', keys: ['movement_speed_inc', 'movement_speed_additional'], total: net, totalUnit: '%', formula: '(1 + Increased) × (1 + Additional)' }}>
        {fmtSignedPct(net)}
      </Row>
      <Row label="Reservation (Sealing)" labelColor="#555">— NYI</Row>
    </StatPanel>
  )
}

const DEF_FORMULA = '(Base + Flat) × (1 + Increased) × Additional'
// Evasion has a character base of 2 per level gained (Help DB), folded into evasion_flat — surface it in the
// formula like Life/Mana do their 50+13/level, 40+5/level bases.
const EVASION_FORMULA = '(2/level + Flat) × (1 + Increased) × Additional'
// Life/Mana spell out the character base scaling (was buried in the base row's source name) — see
// buildCharacterContributions: 50 + 13/level life, 40 + 5/level mana.
const LIFE_FORMULA = '(50 + 13/level + Flat) × (1 + Increased) × Additional'
const MANA_FORMULA = '(40 + 5/level + Flat) × (1 + Increased) × Additional'
const RES_FORMULA = 'Σ Resist'

// "Max <type> Resistance" sub-section for a resist breakdown: a 60% baseline (the default cap, mirrors
// engine _BASE_RESIST_CAP) plus any +max-resistance sources, raisable toward the 90% absolute ceiling.
const maxResSection = (typeLabel: string, maxKey: string, maxVal: number): BreakdownSection => ({
  label: `Max ${typeLabel} Resistance`,
  keys: [maxKey],
  formula: '60% base + Σ Max (cap 90%)',
  total: maxVal / 100,   // engine reports the cap in points (e.g. 60); fmtTotalVal('%') ×100 → "60%"
  totalUnit: '%',
  extra: [{ value: '60%', stat: `Max ${typeLabel} Resistance`, source: 'Baseline', sourceName: 'Default' }],
})

function DefensePanels({ defense, reservation }: { defense: DefenseResult | null; reservation: ReservationResult | null }) {
  if (!defense) {
    return <StatPanel title="Life" accent="#c03030"><div style={{ fontSize: 12, color: '#555' }}>No data.</div></StatPanel>
  }
  // Per-pool seal breakdowns (Σ of each sealing skill's whole-number reservation), reused by the Sealed and
  // Unsealed rows so both surface the same Max − Σ-reservations math on hover/click.
  const sealRows = (pool: 'life' | 'mana') => (reservation?.per_skill ?? [])
    .filter(p => p.pool === pool)
    .map(p => ({ value: fmtNum(p.amount), stat: p.name, source: 'Reservation', sourceName: `${(p.base_fraction * 100).toFixed(0)}% seal` }))
  const sealedBreakdown = (pool: 'life' | 'mana', total: number) => ({
    title: pool === 'life' ? 'Sealed Life' : 'Sealed Mana', keys: [] as string[], total, totalUnit: '',
    formula: 'Σ per-skill reservations', extra: sealRows(pool),
  })
  const unsealedBreakdown = (pool: 'life' | 'mana', max: number, sealed: number, total: number) => ({
    title: pool === 'life' ? 'Unsealed (Available) Life' : 'Unsealed (Available) Mana', keys: [] as string[], total, totalUnit: '',
    formula: pool === 'life'
      ? 'Max Life − Sealed Life (available floored — rounds against you)'
      : 'Max Mana − Sealed Mana (available floored — rounds against you)',
    extra: [
      { value: fmtNum(max), stat: `Max ${pool === 'life' ? 'Life' : 'Mana'}`, source: 'Base', sourceName: 'Total pool' },
      { value: `−${fmtNum(sealed)}`, stat: `Sealed ${pool === 'life' ? 'Life' : 'Mana'}`, source: 'Reservation', sourceName: 'Reserved by sealing skills' },
    ],
  })
  // Match the in-game "round against the player" display: floor the available pool, then derive Sealed = Max −
  // Available so the two always sum to Max exactly (and Sealed effectively rounds up). Energy Shield is likewise
  // truncated, not rounded (Ward example: 78.81 → 78). Scoped to these pools for now; the game appears to
  // truncate every stat display (option B) — tracked in docs/BACKLOG.md.
  const availDisp = (unsealedExact: number) => Math.floor(unsealedExact)
  const sealedDisp = (max: number, unsealedExact: number) => Math.round(max) - Math.floor(unsealedExact)
  return (
    <>
      <StatPanel title="Life" accent="#c03030">
        <Row label="Max Life" breakdown={{ title: 'Max Life', keys: ['max_life_flat', 'max_life_inc', 'max_life_additional'], total: defense.max_life, formula: LIFE_FORMULA }}>{fmtNum(defense.max_life)}</Row>
        {defense.life_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Life — Flat Added', keys: ['max_life_flat'] }}>{fmtNum(defense.life_flat)}</SubRow>}
        {defense.life_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Life — Increased', keys: ['max_life_inc'] }}>{fmtPct(defense.life_inc)}</SubRow>}
        {defense.life_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Life — Additional', keys: ['max_life_additional'] }}>{fmtMult(defense.life_additional)}</SubRow>}
        {(defense.sealed_life ?? 0) > 0 && (
          <>
            <Row label="Sealed Life" labelColor={defense.insufficient_life ? '#e05050' : '#c87820'} breakdown={sealedBreakdown('life', defense.sealed_life!)}>{fmtNum(sealedDisp(defense.max_life, defense.unsealed_life ?? defense.max_life))}</Row>
            <Row label="Unsealed Life" labelColor={defense.insufficient_life ? '#e05050' : undefined} breakdown={unsealedBreakdown('life', defense.max_life, defense.sealed_life!, defense.unsealed_life ?? defense.max_life)}>{fmtNum(availDisp(defense.unsealed_life ?? defense.max_life))}</Row>
            {defense.insufficient_life && <div style={{ fontSize: 10, color: '#e05050', marginTop: 2 }}>Insufficient Life — sealed exceeds Max Life by {fmtNum((defense.sealed_life ?? 0) - defense.max_life)} ({dec((((defense.sealed_life ?? 0) / defense.max_life - 1) * 100))}%)</div>}
          </>
        )}
      </StatPanel>

      <StatPanel title="Mana" accent="#3060c0">
        <Row label="Max Mana" breakdown={{ title: 'Max Mana', keys: ['max_mana_flat', 'max_mana_inc', 'max_mana_additional'], total: defense.max_mana, formula: MANA_FORMULA }}>{fmtNum(defense.max_mana)}</Row>
        {defense.mana_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Mana — Flat Added', keys: ['max_mana_flat'] }}>{fmtNum(defense.mana_flat)}</SubRow>}
        {defense.mana_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Mana — Increased', keys: ['max_mana_inc'] }}>{fmtPct(defense.mana_inc)}</SubRow>}
        {defense.mana_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Mana — Additional', keys: ['max_mana_additional'] }}>{fmtMult(defense.mana_additional)}</SubRow>}
        {(defense.sealed_mana ?? 0) > 0 && (
          <>
            <Row label="Sealed (Reserved) Mana" labelColor={defense.insufficient_mana ? '#e05050' : '#c87820'} breakdown={sealedBreakdown('mana', defense.sealed_mana!)}>{fmtNum(sealedDisp(defense.max_mana, defense.unsealed_mana ?? defense.max_mana))}</Row>
            <Row label="Unsealed (Available) Mana" labelColor={defense.insufficient_mana ? '#e05050' : undefined} breakdown={unsealedBreakdown('mana', defense.max_mana, defense.sealed_mana!, defense.unsealed_mana ?? defense.max_mana)}>{fmtNum(availDisp(defense.unsealed_mana ?? defense.max_mana))}</Row>
            {defense.insufficient_mana && <div style={{ fontSize: 10, color: '#e05050', marginTop: 2 }}>Insufficient Mana — reserved exceeds Max Mana by {fmtNum((defense.sealed_mana ?? 0) - defense.max_mana)} ({dec((((defense.sealed_mana ?? 0) / defense.max_mana - 1) * 100))}%)</div>}
          </>
        )}
      </StatPanel>

      <StatPanel title="Energy Shield" accent="#5aa0d0">
        {/* Energy Shield is truncated in-game, not rounded (Ward example: 78.81 → 78) — floor the display. */}
        <Row label="Max Energy Shield" breakdown={{ title: 'Max Energy Shield', keys: ['max_energy_shield_flat', 'energy_shield_gear_flat', 'max_energy_shield_inc', 'energy_shield_gear_inc', 'max_energy_shield_additional'], total: defense.max_energy_shield, formula: DEF_FORMULA }}>{fmtNum(Math.floor(defense.max_energy_shield))}</Row>
        {defense.es_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Energy Shield — Flat Added', keys: ['max_energy_shield_flat', 'energy_shield_gear_flat'] }}>{fmtNum(defense.es_flat)}</SubRow>}
        {defense.es_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Energy Shield — Increased', keys: ['max_energy_shield_inc', 'energy_shield_gear_inc'] }}>{fmtPct(defense.es_inc)}</SubRow>}
        {defense.es_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Energy Shield — Additional', keys: ['max_energy_shield_additional'] }}>{fmtMult(defense.es_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Resistances" accent="#7030b0">
        <Row label="Fire" labelColor={DTYPE_COLOR.fire} breakdown={{ title: 'Fire Resistance', keys: ['fire_resistance', 'elemental_resistance'], formula: RES_FORMULA, sections: [maxResSection('Fire', 'fire_resistance_max_inc', defense.fire_resist_max)] }}>{fmtResistValue(defense.fire_resist, defense.fire_resist_raw)}</Row>
        <Row label="Cold" labelColor={DTYPE_COLOR.cold} breakdown={{ title: 'Cold Resistance', keys: ['cold_resistance', 'elemental_resistance'], formula: RES_FORMULA, sections: [maxResSection('Cold', 'cold_resistance_max_inc', defense.cold_resist_max)] }}>{fmtResistValue(defense.cold_resist, defense.cold_resist_raw)}</Row>
        <Row label="Lightning" labelColor={DTYPE_COLOR.lightning} breakdown={{ title: 'Lightning Resistance', keys: ['lightning_resistance', 'elemental_resistance'], formula: RES_FORMULA, sections: [maxResSection('Lightning', 'lightning_resistance_max_inc', defense.lightning_resist_max)] }}>{fmtResistValue(defense.lightning_resist, defense.lightning_resist_raw)}</Row>
        <Row label="Erosion" labelColor={DTYPE_COLOR.erosion} breakdown={{ title: 'Erosion Resistance', keys: ['erosion_resistance'], formula: RES_FORMULA, sections: [maxResSection('Erosion', 'erosion_resistance_max_inc', defense.erosion_resist_max)] }}>{fmtResistValue(defense.erosion_resist, defense.erosion_resist_raw)}</Row>
      </StatPanel>

      <StatPanel title="Armour" accent="#8a6a3a">
        <Row label="Armour" breakdown={{ title: 'Armour', keys: ['armor_flat', 'armor_gear_flat', 'armor_inc', 'armor_gear_inc', 'defense_inc', 'armor_additional'], total: defense.armor, formula: DEF_FORMULA }}>{fmtNum(defense.armor)}</Row>
        {defense.armor_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Armour — Flat Added', keys: ['armor_flat', 'armor_gear_flat'] }}>{fmtNum(defense.armor_flat)}</SubRow>}
        {defense.armor_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Armour — Increased', keys: ['armor_inc', 'armor_gear_inc', 'defense_inc'] }}>{fmtPct(defense.armor_inc)}</SubRow>}
        {defense.armor_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Armour — Additional', keys: ['armor_additional'] }}>{fmtMult(defense.armor_additional)}</SubRow>}
        <Row label="Physical Damage Mitigation" breakdown={{ title: 'Physical Damage Mitigation', keys: [], total: defense.armor_phys_mitigation, totalUnit: '%', formula: 'Armor ÷ (0.9×Armor + 3000 + 300×min(Lvl,90)), cap 80%', extra: [{ value: fmtNum(defense.armor), stat: 'Armour', source: 'Rating', sourceName: '' }] }}>{fmtPct2(defense.armor_phys_mitigation)}</Row>
        <Row label="Non-Physical Damage Mitigation" breakdown={{ title: 'Non-Physical Damage Mitigation', keys: ['armor_effective_rate_non_physical_inc'], total: defense.armor_nonphys_mitigation, totalUnit: '%', formula: 'Armor × (60% + Eff. Rate) ÷ same formula (cap 80%)', extra: [{ value: fmtNum(defense.armor), stat: 'Armour', source: 'Rating', sourceName: '' }, { value: '+60%', stat: 'Effective Rate (non-phys)', source: 'Baseline', sourceName: 'Default' }] }}>{fmtPct2(defense.armor_nonphys_mitigation)}</Row>
      </StatPanel>

      <StatPanel title="Evasion" accent="#3a8a66">
        <Row label="Evasion" breakdown={{ title: 'Evasion', keys: ['evasion_flat', 'evasion_gear_flat', 'evasion_inc', 'evasion_gear_inc', 'defense_inc', 'evasion_additional'], total: defense.evasion, formula: EVASION_FORMULA }}>{fmtNum(defense.evasion)}</Row>
        {defense.evasion_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Evasion — Flat Added', keys: ['evasion_flat', 'evasion_gear_flat'] }}>{fmtNum(defense.evasion_flat)}</SubRow>}
        {defense.evasion_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Evasion — Increased', keys: ['evasion_inc', 'evasion_gear_inc', 'defense_inc'] }}>{fmtPct(defense.evasion_inc)}</SubRow>}
        {defense.evasion_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Evasion — Additional', keys: ['evasion_additional'] }}>{fmtMult(defense.evasion_additional)}</SubRow>}
        <Row label="Attack Evasion Rate" breakdown={{ title: 'Attack Evasion Rate', keys: [], total: defense.attack_evade_chance, totalUnit: '%', formula: '1 − (Acc×1.15)/(Acc + 0.5×Evasion^0.75), cap 75%', extra: [{ value: fmtNum(defense.evasion), stat: 'Evasion', source: 'Rating', sourceName: '' }] }}>{fmtPct2(defense.attack_evade_chance)}</Row>
        <Row label="Spell Evasion Chance" breakdown={{ title: 'Spell Evasion Chance', keys: [], total: defense.spell_evade_chance, totalUnit: '%', formula: 'Same formula on 60% of Evasion (spell −40%)', extra: [{ value: fmtNum(defense.evasion * 0.6), stat: 'Evasion (×0.6)', source: 'Rating', sourceName: '' }] }}>{fmtPct2(defense.spell_evade_chance)}</Row>
      </StatPanel>

      <StatPanel title="Block" accent="#6080b0">
        <Row label="Attack Block Chance" breakdown={{ title: 'Attack Block Chance', keys: ['attack_block_chance_inc'], total: defense.attack_block_chance, totalUnit: '%' }}>{fmtPct2(defense.attack_block_chance)}</Row>
        <Row label="Spell Block Chance" breakdown={{ title: 'Spell Block Chance', keys: ['spell_block_chance_inc'], total: defense.spell_block_chance, totalUnit: '%' }}>{fmtPct2(defense.spell_block_chance)}</Row>
        <Row label="Block Ratio" breakdown={{ title: 'Block Ratio', keys: ['block_ratio_inc'], total: defense.block_ratio, totalUnit: '%',
          formula: '30% base + Σ Block Ratio, capped at the Upper Limit',
          extra: [{ value: '30%', stat: 'Base', source: 'Baseline', sourceName: 'every character' }] }}>{fmtPct2(defense.block_ratio)}</Row>
        {(defense.block_ratio_upper_limit ?? 0.6) !== 0.6 && (
          <Row label="Block Ratio Upper Limit" breakdown={{ title: 'Block Ratio Upper Limit', keys: ['block_ratio_upper_limit_flat'], total: defense.block_ratio_upper_limit, totalUnit: '%',
            formula: '60% base + Σ, capped at 80%',
            extra: [{ value: '60%', stat: 'Base', source: 'Baseline', sourceName: 'every character' }] }}>{fmtPct2(defense.block_ratio_upper_limit)}</Row>
        )}
      </StatPanel>

      <StatPanel title="Damage Avoidance" accent="#7060b0">
        <Row label="Chance to Avoid Damage" breakdown={{ title: 'Chance to Avoid Damage', keys: ['dmg_avoid_chance'], total: defense.dmg_avoid_chance, totalUnit: '%' }}>{fmtPct2(defense.dmg_avoid_chance)}</Row>
      </StatPanel>

      <StatPanel title="Absorb" accent="#50a0a0">
        <Row label="Barrier" labelColor="#555">— NYI</Row>
      </StatPanel>
    </>
  )
}

// The calculation target ("dummy"): its armour and per-type resistance, shown as the base reduction and
// the effective reduction after this build's penetration. A negative effective value = over-penetration,
// i.e. the target takes amplified damage of that type.
function TargetPanel({ target }: { target: TargetStats | null | undefined }) {
  if (!target) return null
  const pct = (x: number) => `${Math.round(x * 100)}%`
  const spct = (x: number) => `${x >= 0 ? '+' : ''}${Math.round(x * 100)}%`
  const src = target.source ?? 'Target'
  const a = target.armor
  // Each row carries the SEPARATED steps: base (dummy constant) → reduction (enemy resist debuff) → resist
  // → pen (ignored at hit, NOT a resistance reduction) → effective.
  // Each row shows the EFFECTIVE value (after this build's penetration) as a single number; the base + the
  // penetration that produced it live in the source breakdown. Base resists are the dummy default for now —
  // they'll be set on the Conditionals/Config screen after its rework.
  // penKeys = the stat keys whose penetration produced this row's effective value — fed into the breakdown so
  // it shows the REAL source(s) of the penetration (e.g. "+50% Cold Resistance Penetration · custom config").
  const rows = [
    { label: 'Effective Armour (Physical)', baseStat: 'Armour', color: DTYPE_COLOR.physical, base: a.base_phys, reduction: 0, penKeys: ['armor_pen'], effective: a.effective_phys },
    { label: 'Effective Armour (Non-Physical)', baseStat: 'Armour', color: DTYPE_COLOR.physical, base: a.base_nonphys, reduction: 0, penKeys: ['armor_pen'], effective: a.effective_nonphys },
    ...(['fire', 'cold', 'lightning', 'erosion'] as const).map(t => {
      const r = target.resists[t] ?? { base: 0, effective: 0 }
      const T = `${t.charAt(0).toUpperCase() + t.slice(1)} Resistance`
      const penKeys = t === 'erosion' ? ['erosion_pen'] : [`${t}_pen`, 'elemental_pen']
      return { label: `Effective ${T}`, baseStat: T, color: DTYPE_COLOR[t], base: r.base, reduction: r.reduction ?? 0, penKeys, effective: r.effective }
    }),
  ]
  const details = target.debuff_details ?? []
  return (
    <StatPanel title={`Target (${src})`} accent="#b03030">
      {rows.map(r => {
        const amplified = r.effective < 0
        const extra: ExtraRow[] = [{ value: pct(r.base), stat: r.baseStat, source: 'Base', sourceName: src }]
        if (Math.abs(r.reduction) > 1e-9) extra.push({ value: spct(r.reduction), stat: 'Resistance Reduction', source: 'Debuff', sourceName: 'lowers enemy resistance' })
        return (
          <Row key={r.label} label={r.label} labelColor={r.color}
            breakdown={{ title: r.label, keys: r.penKeys, total: r.effective, totalUnit: '%', extra,
              formula: 'Base − Penetration (penetration is ignored at the hit, it is not a resistance reduction)' }}>
            <span style={{ color: amplified ? '#ff8c6b' : undefined }}>{pct(r.effective)}</span>
          </Row>
        )
      })}
      {(details.length > 0 || target.debuffs.length > 0) && (
        <>
          {/* Names-only list of the debuffs currently on the target — the exact amplification values live in the
              per-type resistance rows above (and their breakdowns), so they're not repeated here. */}
          <div style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: '#9a6a9a', margin: '6px 0 2px' }}>
            Active Debuffs
          </div>
          <div style={{ fontSize: 12, color: '#d0a0e0', lineHeight: 1.5 }}>
            {details.length > 0
              ? details.map(d => `${d.name}${d.stacks ? ` ×${Math.round(d.stacks)}` : ''}`).join(', ')
              : target.debuffs.join(', ')}
          </div>
        </>
      )}
    </StatPanel>
  )
}

// The interactive Numbed-stacks panel was removed from this (Calculations) screen — condition stacks are set on
// the Conditionals screen. The Numbed effect now shows read-only as a damage-type-gated box in the skill area.

// ── Root ──────────────────────────────────────────────────────────────────────

export default function PlayerStatsScreen() {
  const computedStats = useBuildStore(s => s.computedStats)
  const skills = useBuildStore(s => s.skills)
  const gear = useBuildStore(s => s.gear)
  const pactSpirits = useBuildStore(s => s.pactSpirits)
  const allSpirits = useBuildStore(s => s.allSpirits)
  const heroMemories = useBuildStore(s => s.heroMemories)
  // Persisted in uiPrefs so the viewed skill sticks across screen navigation (new/empty builds fall back to
  // the first populated slot via the effect below).
  const selectedSlot = useUiPrefs(s => s.statsSelectedSlot)
  const setSelectedSlot = useUiPrefs(s => s.setStatsSelectedSlot)
  const [calcMode, setCalcMode] = useState('full_uptime')   // stub; only full_uptime is wired (Phase 2)
  const [selectedForm, setSelectedForm] = useState<string | null>(null)   // null = all forms combined
  // Reset the form filter whenever the selected skill changes (forms differ per skill).
  useEffect(() => { setSelectedForm(null) }, [selectedSlot])

  // If the selected slot has no skill (e.g. the main damage skill is parked in slot 2 and slot 1 is
  // empty), jump to the first populated slot so the viewer opens on a real skill instead of "Main · empty".
  useEffect(() => {
    if (skills.some(sk => sk.slot === selectedSlot)) return
    const first = [...skills].sort((a, b) => a.slot - b.slot)[0]
    if (first) setSelectedSlot(first.slot)
  }, [skills, selectedSlot])

  // Tree name → branch color, fetched once (static; used to color talent sources in breakdowns).
  const [treeColors, setTreeColors] = useState<Record<string, string>>({})
  useEffect(() => {
    let live = true
    api.getTrees().then(list => { if (live) setTreeColors(Object.fromEntries(list.map(t => [t.name, t.color]))) }).catch(() => { /* colors stay empty → fallback */ })
    return () => { live = false }
  }, [])

  // sourceName → effect lines, for the spirit/memory/support breakdown hovers. Built from the same data
  // the engine payload uses, so the lines match what was sent.
  const sourceLines = useMemo(() => {
    const m = new Map<string, string[]>()
    const add = (name: string | undefined, line: string) => {
      if (!name) return
      const arr = m.get(name) ?? []
      arr.push(line)
      m.set(name, arr)
    }
    for (const e of buildSpiritEffects(pactSpirits, allSpirits)) add(e.source, e.text)
    for (const e of buildMemoryEffects(heroMemories)) add(e.source, e.text)
    for (const sk of skills) for (const sup of sk.supports ?? []) {
      for (const line of sup.description_lines ?? []) add(sup.name, line)
    }
    return m
  }, [pactSpirits, allSpirits, heroMemories, skills])

  // Skill catalog (with tooltip specs) + each equipped support's level/rolls — for the structured
  // contribution hover. Contributions carry only a source NAME, so we look the SkillItem up by name.
  const skillsByName = useReferenceStore(s => s.skillsByName)
  const supportInstances = useMemo(() => {
    const m: Record<string, { level: number; specific_rolls?: Record<string, number> }> = {}
    for (const sk of skills) for (const sup of sk.supports ?? []) {
      m[sup.name] = { level: sup.level, specific_rolls: sup.specific_rolls }
    }
    return m
  }, [skills])

  // memory name → its rarity color, for coloring hero-memory sources in breakdowns.
  const memoryColors = useMemo(() => {
    const m: Record<string, string> = {}
    for (const mem of heroMemories) if (mem) m[MEMORY_NAMES[mem.memoryType]] = MEMORY_RARITY_COLORS[mem.rarity] ?? '#6fc0b0'
    return m
  }, [heroMemories])

  // hero-trait source name (node name) → the granting node's tooltip data, so hovering a "Hero Trait" source
  // shows the SAME tooltip as the Hero Trait screen. Base trait = variant_name; "Artificial Moon"; else an
  // advanced-trait name. Uses |level| so a disabled (negative-level) node still resolves its remembered level.
  const traitId = useBuildStore(s => s.traitId)
  const traitSlotLevels = useBuildStore(s => s.traitSlotLevels)
  const heroTraitsCatalog = useReferenceStore(s => s.heroTraits)
  const traitNodeTooltip = useMemo(() => {
    const trait = (heroTraitsCatalog ?? []).find((t: HeroTrait) => t.trait_id === traitId)
    const lvl = (i: number) => Math.max(1, Math.min(5, Math.abs(traitSlotLevels?.[i] ?? 1)))
    return (sourceName: string) => {
      if (!trait) return null
      if (sourceName === trait.variant_name) {
        const baseLevel = lvl(0)
        return { name: trait.variant_name, level: baseLevel, effects: trait.levels?.[baseLevel - 1]?.effects ?? [],
          moonEffects: baseLevel === 5 ? trait.artificial_moon?.effects : undefined }
      }
      if (sourceName === 'Artificial Moon') {
        return { name: 'Artificial Moon', level: lvl(0), effects: trait.artificial_moon?.effects ?? [] }
      }
      const adv = trait.advanced_traits?.find(a => a.name === sourceName)
      if (adv) {
        const slotIdx = adv.unlock_level >= 75 ? 3 : adv.unlock_level >= 60 ? 2 : 1
        return { name: adv.name, level: lvl(slotIdx), effects: adv.effects ?? [] }
      }
      return null
    }
  }, [heroTraitsCatalog, traitId, traitSlotLevels])

  const offense = (computedStats.offense ?? null) as OffenseResult | null
  const defense = (computedStats.defense ?? null) as DefenseResult | null
  const statMap = (computedStats.stats ?? {}) as Record<string, StatEntry>
  const slotOffense = ((computedStats as { slot_offense?: Record<string, OffenseResult> | null }).slot_offense) ?? null

  // slot_offense holds EVERY active slot's offense (incl. the main slot), so index it by the selected
  // slot directly — don't assume the main skill is slot 1. Fall back to the headline offense only if the
  // per-slot map is absent (legacy response).
  const shownOffense = slotOffense
    ? (slotOffense[String(selectedSlot)] ?? null)
    : (selectedSlot === 1 ? offense : null)
  // Form filter (Phase 1 = display-only): when a single form is selected, show just its damage by filtering
  // hit_forms and scaling the headline DPS to that form's share of the combined total (so it reconciles with
  // the shown numbers). Phase 2 swaps this for a true engine recompute (forced forms, Chilling Spike split).
  const formNames = shownOffense?.hit_forms?.map(f => f.name) ?? []
  const displayOffense = useMemo(() => {
    if (!shownOffense || !selectedForm) return shownOffense
    const form = shownOffense.hit_forms.find(f => f.name === selectedForm)
    if (!form) return shownOffense
    const sumVt = shownOffense.hit_forms.reduce((s, f) => s + f.dps_vs_target, 0) || 1
    const sumD = shownOffense.hit_forms.reduce((s, f) => s + f.dps_contribution, 0) || 1
    return {
      ...shownOffense,
      hit_forms: [form],
      total_dps_vs_target: shownOffense.total_dps_vs_target * (form.dps_vs_target / sumVt),
      total_dps: shownOffense.total_dps * (form.dps_contribution / sumD),
    }
  }, [shownOffense, selectedForm])
  const blessings = ((computedStats as { blessings?: BlessingSummary[] | null }).blessings) ?? null
  const auras = ((computedStats as { auras?: AuraSummary[] | null }).auras) ?? null
  const curses = ((computedStats as { curses?: CurseSummary[] | null }).curses) ?? null
  const curseMeta = ((computedStats as { curse_meta?: Record<string, CurseMeta> | null }).curse_meta) ?? null
  const empowers = ((computedStats as { empowers?: EmpowerSummary[] | null }).empowers) ?? null
  const reservation = ((computedStats as { reservation?: ReservationResult | null }).reservation) ?? null
  const selectedSkill = skills.find(sk => sk.slot === selectedSlot)
  const selectedAura = auras?.find(a => a.skill_id === selectedSkill?.item_id) ?? null
  const selectedCurse = curses?.find(c => c.skill_id === selectedSkill?.item_id) ?? null
  const selectedCurseMeta = (curseMeta && selectedSkill?.item_id) ? curseMeta[selectedSkill.item_id] ?? null : null
  const selectedEmpower = empowers?.find(e => e.skill_id === selectedSkill?.item_id) ?? null
  const selectedReservation = reservation?.per_skill?.find(
    p => p.skill_id === selectedSkill?.item_id && p.slot === selectedSlot) ?? null

  return (
    <BreakdownCtx.Provider value={{ statMap, gear, sourceLines, treeColors, memoryColors, skillsByName, supportInstances, traitNodeTooltip, selectedSlot }}>
      <div className="dark-scroll" style={{ display: 'flex', flexWrap: 'wrap', gap: 10, height: '100%', overflowY: 'auto', padding: '16px 20px', boxSizing: 'border-box' }}>
        {/* Left — skill offense (widest min: must fit the 6-column damage-type table) */}
        <div style={{ flex: '55', minWidth: '500px', display: 'flex', flexDirection: 'column' }}>
          <SkillSelectionBar
            skills={skills} selected={selectedSlot} onSelect={setSelectedSlot}
            forms={formNames} selectedForm={selectedForm} onSelectForm={setSelectedForm}
            calcMode={calcMode} onCalcMode={setCalcMode} />
          <OffensePanels offense={displayOffense} slot={selectedSlot} skill={selectedSkill} aura={selectedAura} reservation={selectedReservation} curse={selectedCurse} curseMeta={selectedCurseMeta} empower={selectedEmpower} />
        </div>

        {/* Middle — calculation target, attributes, blessings, utility. (Condition-setting controls like Numbed
            stacks live on the Conditionals screen, not here — this screen only displays the calculation.) */}
        <div style={{ flex: '22', minWidth: '225px', display: 'flex', flexDirection: 'column' }}>
          <TargetPanel target={computedStats.target_stats} />
          <AttributesPanel statMap={statMap} />
          <BlessingsPanel blessings={blessings} />
          <UtilityPanel statMap={statMap} />
        </div>

        {/* Right — defensive pools (trimmed to give the offense table room) */}
        <div style={{ flex: '23', minWidth: '225px', display: 'flex', flexDirection: 'column' }}>
          <DefensePanels defense={defense} reservation={reservation} />
        </div>
      </div>
    </BreakdownCtx.Provider>
  )
}
