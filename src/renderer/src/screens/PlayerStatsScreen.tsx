import React, { useState, useMemo, useEffect, useContext } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { useBuildStore } from '../store/buildStore'
import type { OffenseResult, DefenseResult, EquippedSkill, StatEntry, EquippedGearItem, TargetStats, BlessingSummary } from '../api/client'
import { api, buildSpiritEffects, buildMemoryEffects, MEMORY_RARITY_COLORS } from '../api/client'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { GearTooltipBody } from '../components/tooltip/bodies/GearTooltipBody'
import { SpiritTooltipBody } from '../components/tooltip/bodies/SpiritTooltipBody'
import { SkillTooltipBody } from '../components/tooltip/bodies/SkillTooltipBody'
import { MiniTree } from '../components/MiniTree'
import { gearQualityColor } from '../utils/gearItem'
import { sourceKindLabel, sourceKindColor } from '../utils/sourceKind'

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
    const s = Math.abs(p % 1) < 1e-9 ? p.toFixed(0) : p.toFixed(1)
    return `${v > 0 ? '+' : ''}${s}%`
  }
  const s = v % 1 === 0 ? v.toFixed(0) : v.toFixed(2)
  return `${v > 0 ? '+' : ''}${s}`
}

// Grid shared by the breakdown header + each source row: Value · Stat · Source · Source Name.
const BD_GRID = 'auto minmax(0,1fr) auto minmax(0,1.3fr)'

// Format a breakdown TOTAL: '%' unit treats the value as a fraction (0.6 → "60%"); else plain number.
function fmtTotalVal(v: number, unit: string): string {
  return unit === '%' ? `${(v * 100).toFixed(0)}%` : (v % 1 === 0 ? v.toFixed(0) : v.toFixed(2))
}

// The title + Total header shared by the main breakdown and each section, so they look identical.
function BreakdownHeader({ title, total, totalUnit, formula }: { title: string; total?: number; totalUnit?: string; formula?: string }) {
  return (
    <>
      <div style={{ marginBottom: 3 }}>
        <span style={{ fontWeight: 700, color: '#cfcfe6' }}>{title}</span>
        {formula && <span style={{ fontWeight: 400, color: '#5f5f72', fontSize: 10, marginLeft: 8, fontVariantNumeric: 'tabular-nums' }}>{formula}</span>}
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
  const isLines = g.source_type === 'pact_spirit' || g.source_type === 'hero_memory' || g.source_type === 'support'

  // Gear: the backend carries the item NAME in source_name → match the equipped item for its tooltip.
  const matchedItem = isGear
    ? ctx.gear.find(it => it.name === g.source_name || it.name === g.text || it.name === g.label)
    : undefined
  // Talent: tree name + node id from the "Tree · node_id" label; the mini tree highlights the node.
  const hasNodeLabel = g.label.includes(' · ')
  const treeName = g.source_name || (hasNodeLabel ? g.label.split(' · ')[0] : g.label)
  const nodeId = hasNodeLabel ? g.label.split(' · ').slice(-1)[0] : ''
  // Spirit / memory / support: the source's effect lines (built once at the root).
  const lines = isLines && g.source_name ? (ctx.sourceLines.get(g.source_name) ?? []) : []

  const hasHover = !!matchedItem || (isTalent && !!nodeId) || (isLines && lines.length > 0)
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
  // Source Name column = the real name (item / spirit / memory / support / tree); talents show just the tree.
  const sourceName = g.source_name || (isTalent ? treeName : (g.text || g.label || '—'))

  return (
    <>
      <div {...(hasHover ? tip.triggerProps : {})}
        style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: 'subgrid', alignItems: 'baseline', padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: hasHover ? 'help' : undefined, outline: tip.open ? '1px solid #fff' : undefined, outlineOffset: tip.open ? 3 : undefined, background: tip.open ? 'rgba(255,255,255,0.06)' : undefined }}>
        <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', textAlign: 'right' }}>
          {fmtSourceValue(g)}{g.count > 1 && <span style={{ color: '#666' }}> ×{g.count}</span>}
        </span>
        <span style={{ color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{g.statName}</span>
        <span style={{ color: kindColor, fontSize: 10, whiteSpace: 'nowrap' }}>{sourceLabel}</span>
        <span style={{ color: kindColor, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textDecoration: hasHover ? 'underline dotted' : undefined }}>
          {sourceName}
        </span>
      </div>
      {hasHover && tip.open && (
        <FloatingPortal>
          {matchedItem ? (
            <div className="tooltip tooltip--gear" {...tip.floatingProps}><GearTooltipBody item={matchedItem} hideBadges /></div>
          ) : isTalent ? (
            <div className="tooltip" {...tip.floatingProps}><MiniTree treeName={treeName} nodeId={nodeId} /></div>
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
    <div style={{ gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: 'subgrid', alignItems: 'baseline', padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', textAlign: 'right' }}>{e.value}</span>
      <span style={{ color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.stat}</span>
      <span style={{ color: '#8a8aa0', fontSize: 10, whiteSpace: 'nowrap' }}>{e.source}</span>
      <span style={{ color: '#8a8aa0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.sourceName}</span>
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
  if (n >= 1_000_000_000_000_000) return `${(n / 1_000_000_000_000_000).toFixed(2)}Q`
  if (n >= 1_000_000_000_000)     return `${(n / 1_000_000_000_000).toFixed(2)}T`
  if (n >= 1_000_000_000)         return `${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000)             return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 100_000)               return `${(n / 1_000).toFixed(1)}k`
  return n.toFixed(0)
}

function fmtResistValue(capped: number, raw: number): React.ReactNode {
  const cappedStr = `${capped.toFixed(0)}%`
  const display = raw > capped ? `${cappedStr} (${raw.toFixed(0)}% raw)` : cappedStr
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
}: {
  title: string
  accent: string
  children: React.ReactNode
  defaultCollapsed?: boolean
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  return (
    <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderLeft: `3px solid ${accent}`, borderRadius: 4, marginBottom: 6 }}>
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '5px 10px', background: accent + '22', cursor: 'pointer', userSelect: 'none',
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase', color: '#ccc' }}>{title}</span>
        <span style={{ color: '#666', fontSize: 13, lineHeight: 1 }}>{collapsed ? '+' : '−'}</span>
      </div>
      {!collapsed && <div style={{ padding: '6px 10px' }}>{children}</div>}
    </div>
  )
}

// ── Skill selector ────────────────────────────────────────────────────────────

const SLOT_LABELS = ['Main', 'Act 2', 'Act 3', 'Act 4', 'Pas 1', 'Pas 2', 'Pas 3', 'Pas 4']

function SkillSelector({
  skills,
  selected,
  onSelect,
}: {
  skills: EquippedSkill[]
  selected: number
  onSelect: (slot: number) => void
}) {
  const bySlot = Object.fromEntries(skills.map(s => [s.slot, s]))
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
      {SLOT_LABELS.map((label, i) => {
        const slot = i + 1
        const skill = bySlot[slot]
        const isSelected = selected === slot
        const isEmpty = !skill
        return (
          <button
            key={slot}
            disabled={isEmpty}
            onClick={() => !isEmpty && onSelect(slot)}
            title={skill ? `${skill.name} (L${skill.level})` : 'Empty'}
            style={{
              padding: '3px 8px', fontSize: 11, borderRadius: 3, cursor: isEmpty ? 'default' : 'pointer',
              background: isSelected ? 'rgba(200,120,32,0.35)' : 'rgba(255,255,255,0.05)',
              border: isSelected ? '1px solid #c87820' : '1px solid rgba(255,255,255,0.1)',
              color: isEmpty ? '#444' : isSelected ? '#f0c070' : '#bbb',
            }}
          >
            {label}
          </button>
        )
      })}
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
  return keys
}

function typeIncKeys(dtype: string): string[] {
  const keys = [`${dtype}_dmg_inc`]
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_inc')
  return keys
}

function genericAddKeys(offense: OffenseResult): string[] {
  const keys = ['dmg_additional']
  if (hasTag(offense,'attack'))     keys.push('attack_dmg_additional')
  if (hasTag(offense,'spell'))      keys.push('spell_dmg_additional')
  if (hasTag(offense,'melee'))      keys.push('melee_dmg_additional')
  if (hasTag(offense,'area'))       keys.push('area_dmg_additional')
  if (hasTag(offense,'projectile')) keys.push('projectile_dmg_additional')
  return keys
}

function typeAddKeys(dtype: string): string[] {
  const keys = [`${dtype}_dmg_additional`]
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_additional')
  return keys
}

function DamageBreakdownTable({ offense }: { offense: OffenseResult }) {
  const totalDps = offense.total_dps_vs_target

  // Per-dtype DPS total across all forms (proportional attribution via avg hit)
  const dtypeDpsTotal: Record<string, number> = {}
  for (const dtype of ALL_DTYPES) {
    dtypeDpsTotal[dtype] = offense.hit_forms.reduce((sum, form) => {
      const dtypeAvg = form.damage_by_type[dtype] ?? 0
      const prop = form.avg_hit_pre_crit > 0 ? dtypeAvg / form.avg_hit_pre_crit : 0
      return sum + prop * form.dps_vs_target
    }, 0)
  }

  // Shared cell styles
  const thSt: React.CSSProperties = { textAlign: 'right', fontSize: 11, color: '#888', fontWeight: 600, paddingBottom: 3, paddingLeft: 4, paddingRight: 4, whiteSpace: 'nowrap' }
  const td:   React.CSSProperties = { textAlign: 'right', fontSize: 11, fontVariantNumeric: 'tabular-nums', paddingLeft: 4, paddingRight: 4, color: '#e0e0e0', whiteSpace: 'nowrap' }
  const tdLbl: React.CSSProperties = { textAlign: 'left', fontSize: 11, color: '#888', paddingRight: 8, whiteSpace: 'nowrap' }
  const tdDim: React.CSSProperties = { ...td, color: '#444' }
  const tdSub: React.CSSProperties = { ...tdLbl, color: '#666' }

  // Mini formulas shown dim next to each breakdown title (so the math is verifiable). Flat-damage build-up
  // differs for spells (intrinsic base + added×effectiveness) vs attacks (weapon base × gear + added).
  const addedFormula = hasTag(offense, 'spell') ? 'Skill Base + Added × Effectiveness' : 'Weapon Base × (1 + Gear) + Added'

  return (
    <div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
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
            <td style={td}><Breakdown title="Total Increased — All Types" keys={genericIncKeys(offense)} formula="Σ Increased %">{(offense.generic_inc * 100).toFixed(0)}%</Breakdown></td>
            {ALL_DTYPES.map(d => {
              // Specific = this type's increase beyond the generic (catch-all) bucket. Types the skill
              // doesn't deal have no entry → treated as generic-only → 0% specific.
              const specific = Math.max(0, (offense.type_inc[d] ?? offense.generic_inc) - offense.generic_inc)
              const show = specific >= 0.005
              const txt = `${(specific * 100).toFixed(0)}%`
              return <td key={d} style={show ? td : tdDim}>
                {show ? <Breakdown title={`Total Increased — ${DTYPE_LABEL[d]}`} keys={typeIncKeys(d)} formula="Σ this type's Increased %">{txt}</Breakdown> : txt}
              </td>
            })}
          </tr>
          <tr>
            <td style={tdLbl}>Total Additional</td>
            <td style={td}><Breakdown title="Total Additional — All Types" keys={genericAddKeys(offense)} formula="Π (1 + Additional)">×{offense.generic_add.toFixed(2)}</Breakdown></td>
            {ALL_DTYPES.map(d => {
              // Specific = type_add factored over the generic bucket. Types the skill doesn't deal have
              // no entry → ×1.00 (not 1/generic, which would show a phantom multiplier on empty types).
              const specificAdd = offense.type_add[d] !== undefined
                ? offense.type_add[d] / (offense.generic_add || 1)
                : 1
              const show = Math.abs(specificAdd - 1) >= 0.005
              const txt = `×${specificAdd.toFixed(2)}`
              return <td key={d} style={show ? td : tdDim}>
                {show ? <Breakdown title={`Total Additional — ${DTYPE_LABEL[d]}`} keys={typeAddKeys(d)} formula="Π (1 + Additional)">{txt}</Breakdown> : txt}
              </td>
            })}
          </tr>
          {/* Damage Bonus from the skill's main-stat attributes (0.5% per point, summed). Its own
              additional pool — already INCLUDED in Total Additional above; broken out here for clarity. */}
          {offense.main_stat_damage_bonus > 0 && (
            <tr>
              <td style={tdSub}>↳ Damage Bonus</td>
              <td style={td} title={`+${(offense.main_stat_damage_bonus * 100).toFixed(1)}% from ${offense.main_stats.join(' + ')}`}>
                <Breakdown title="Damage Bonus — Main Stat" keys={offense.main_stats}>×{(1 + offense.main_stat_damage_bonus).toFixed(2)}</Breakdown>
              </td>
              {ALL_DTYPES.map(d => <td key={d} style={tdDim}>—</td>)}
            </tr>
          )}

          {/* ── Per hit form ── */}
          {offense.hit_forms.map(form => {
            const formMin = ALL_DTYPES.reduce((s, d) => s + (form.hit_min_by_type[d] ?? 0), 0)
            const formMax = ALL_DTYPES.reduce((s, d) => s + (form.hit_max_by_type[d] ?? 0), 0)
            const formPct = totalDps > 0 ? `${(form.dps_vs_target / totalDps * 100).toFixed(0)}%` : '—'

            return (
              <React.Fragment key={form.name}>
                <tr>
                  <td colSpan={7} style={{ paddingTop: 8, paddingBottom: 2, fontSize: 11, color: '#bbb', fontWeight: 600 }}>
                    {form.name}
                    {form.proc_chance < 1.0 && (
                      <span style={{ color: '#666', fontWeight: 400, marginLeft: 6 }}>
                        {(form.proc_chance * 100).toFixed(0)}% chance
                      </span>
                    )}
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
                  <td style={{ ...td, color: '#f0c070' }}>{fmtNum(form.dps_vs_target)}</td>
                  {ALL_DTYPES.map(d => {
                    const dtypeAvg = form.damage_by_type[d] ?? 0
                    const prop = form.avg_hit_pre_crit > 0 ? dtypeAvg / form.avg_hit_pre_crit : 0
                    const dtypeDps = prop * form.dps_vs_target
                    return <td key={d} style={dtypeDps > 0 ? td : tdDim}>
                      {dtypeDps > 0 ? fmtNum(dtypeDps) : '—'}
                    </td>
                  })}
                </tr>
                <tr>
                  <td style={tdSub}>% of Total</td>
                  <td style={{ ...td, color: '#aaa' }}>{formPct}</td>
                  {ALL_DTYPES.map(d => {
                    const dtypeAvg = form.damage_by_type[d] ?? 0
                    const prop = form.avg_hit_pre_crit > 0 ? dtypeAvg / form.avg_hit_pre_crit : 0
                    const dtypeDps = prop * form.dps_vs_target
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
            <td style={{ ...tdLbl, color: '#666', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              Type Contribution
            </td>
            <td style={{ ...td, color: '#aaa' }}>100%</td>
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

function OffensePanels({ offense }: { offense: OffenseResult | null }) {

  if (!offense) {
    return (
      <StatPanel title="Offense" accent={AMBER}>
        <div style={{ fontSize: 12, color: '#555' }}>No skill selected.</div>
      </StatPanel>
    )
  }

  if (!offense.supported) {
    return (
      <StatPanel title={`Offense — ${offense.skill_name}`} accent={AMBER}>
        <div style={{ fontSize: 12, color: '#ff6b6b' }}>Skill calculation not yet supported.</div>
      </StatPanel>
    )
  }

  const isSpell = hasTag(offense,'spell')
  const rateLabel = isSpell ? 'Casts per Second' : 'Attacks per Second'
  const rateKeys = isSpell
    ? ['cast_speed_inc', 'cast_speed_additional', 'combo_starter_cast_speed_additional']
    : ['weapon_attack_speed', 'attack_speed_inc', 'attack_speed_gear', 'attack_speed_mh', 'attack_speed_additional', 'combo_starter_attack_speed_additional']

  return (
    <>
      <StatPanel title={`Offense — ${offense.skill_name} (Level ${offense.effective_level})`} accent={AMBER}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '4px 0 6px' }}>
          <span style={{ fontSize: 12, color: '#999' }}>DPS</span>
          <span style={{ fontSize: 17, fontWeight: 700, color: '#f0c070', fontVariantNumeric: 'tabular-nums' }}>
            {fmtNum(offense.total_dps_vs_target)}
          </span>
        </div>
        {offense.above_max_mult > 1.0 && (
          <Row label="Above Max Multiplier">×{offense.above_max_mult.toFixed(3)}</Row>
        )}
        {hasTag(offense,'area') && (
          <Row label="Area of Effect">{offense.skill_area_inc !== 0 ? `+${(offense.skill_area_inc * 100).toFixed(0)}%` : '+0%'}</Row>
        )}
        {hasTag(offense,'projectile') && (
          <Row label="Projectile Count" labelColor="#555">— NYI</Row>
        )}
      </StatPanel>

      <StatPanel title="Skill Hit Damage" accent={AMBER}>
        <div style={{ fontSize: 10, color: '#777', marginBottom: 4 }}>
          Hit = Base flat × (1 + Increased) × Additional × Crit × Above-max
        </div>
        <DamageBreakdownTable offense={offense} />
      </StatPanel>

      <StatPanel title="Hit Rate" accent={AMBER}>
        <Row label={rateLabel} breakdown={{
          title: rateLabel, keys: rateKeys, total: offense.attacks_per_second, totalUnit: '',
          formula: isSpell ? '1 ÷ Cast Time × (1 + Increased) × Additional' : 'Weapon APS × (1 + Gear) × (1 + Increased) × Additional',
          extra: isSpell && offense.base_cast_time > 0
            ? [{ value: `${offense.base_cast_time.toFixed(2)}s`, stat: 'Base Cast Time', source: 'Baseline', sourceName: offense.skill_name }]
            : undefined,
        }}>{offense.attacks_per_second.toFixed(2)}</Row>
      </StatPanel>

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
        }}>{(offense.crit_chance * 100).toFixed(1)}%</Row>
        <Row label="Crit Multiplier" breakdown={{
          title: 'Crit Multiplier',
          keys: ['crit_damage'],
          total: offense.crit_multiplier, totalUnit: '%',
          formula: '150% + Σ Crit Damage',
          extra: [{ value: '150%', stat: 'Crit Multiplier', source: 'Baseline', sourceName: 'Base ×1.5' }],
        }}>{(offense.crit_multiplier * 100).toFixed(0)}%</Row>
      </StatPanel>
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
function fmtPct1(v: number): string { return `${(v * 100).toFixed(1)}%` }
function fmtSignedPct(v: number): string { return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%` }
function fmtMult(v: number): string { return `×${(1 + v).toFixed(2)}` }

// ── Middle-column panels: Attributes / Blessings / Utility ──────────────────────

function AttributesPanel({ statMap }: { statMap: Record<string, StatEntry> }) {
  const row = (key: string, label: string, comp: string[]) => (
    <Row key={key} label={label} labelColor={ATTR_COLOR[key]} breakdown={{ title: label, keys: comp, total: statMap[key]?.total ?? 0, formula: DEF_FORMULA }}>
      {fmtNum(statMap[key]?.total ?? 0)}
    </Row>
  )
  return (
    <StatPanel title="Attributes" accent="#9a8ac0">
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
    <StatPanel title="Blessings" accent="#c0a040">
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

function DefensePanels({ defense }: { defense: DefenseResult | null }) {
  if (!defense) {
    return <StatPanel title="Life" accent="#c03030"><div style={{ fontSize: 12, color: '#555' }}>No data.</div></StatPanel>
  }
  return (
    <>
      <StatPanel title="Life" accent="#c03030">
        <Row label="Max Life" breakdown={{ title: 'Max Life', keys: ['max_life_flat', 'max_life_inc', 'max_life_additional'], total: defense.max_life, formula: DEF_FORMULA }}>{fmtNum(defense.max_life)}</Row>
        {defense.life_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Life — Flat Added', keys: ['max_life_flat'] }}>{fmtNum(defense.life_flat)}</SubRow>}
        {defense.life_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Life — Increased', keys: ['max_life_inc'] }}>{fmtPct(defense.life_inc)}</SubRow>}
        {defense.life_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Life — Additional', keys: ['max_life_additional'] }}>{fmtMult(defense.life_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Mana" accent="#3060c0">
        <Row label="Max Mana" breakdown={{ title: 'Max Mana', keys: ['max_mana_flat', 'max_mana_inc', 'max_mana_additional'], total: defense.max_mana, formula: DEF_FORMULA }}>{fmtNum(defense.max_mana)}</Row>
        {defense.mana_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Mana — Flat Added', keys: ['max_mana_flat'] }}>{fmtNum(defense.mana_flat)}</SubRow>}
        {defense.mana_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Mana — Increased', keys: ['max_mana_inc'] }}>{fmtPct(defense.mana_inc)}</SubRow>}
        {defense.mana_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Mana — Additional', keys: ['max_mana_additional'] }}>{fmtMult(defense.mana_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Energy Shield" accent="#5aa0d0">
        <Row label="Max Energy Shield" breakdown={{ title: 'Max Energy Shield', keys: ['max_energy_shield_flat', 'energy_shield_gear_flat', 'max_energy_shield_inc', 'energy_shield_gear_inc', 'max_energy_shield_additional'], total: defense.max_energy_shield, formula: DEF_FORMULA }}>{fmtNum(defense.max_energy_shield)}</Row>
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

      <StatPanel title="Armour" accent="#308060">
        <Row label="Armour" breakdown={{ title: 'Armour', keys: ['armor_flat', 'armor_gear_flat', 'armor_inc', 'armor_gear_inc', 'defense_inc', 'armor_additional'], total: defense.armor, formula: DEF_FORMULA }}>{fmtNum(defense.armor)}</Row>
        {defense.armor_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Armour — Flat Added', keys: ['armor_flat', 'armor_gear_flat'] }}>{fmtNum(defense.armor_flat)}</SubRow>}
        {defense.armor_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Armour — Increased', keys: ['armor_inc', 'armor_gear_inc', 'defense_inc'] }}>{fmtPct(defense.armor_inc)}</SubRow>}
        {defense.armor_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Armour — Additional', keys: ['armor_additional'] }}>{fmtMult(defense.armor_additional)}</SubRow>}
        <Row label="Physical Damage Mitigation" breakdown={{ title: 'Physical Damage Mitigation', keys: [], total: defense.armor_phys_mitigation, totalUnit: '%', formula: 'Armor ÷ (0.9×Armor + 3000 + 300×min(Lvl,90)), cap 80%', extra: [{ value: fmtNum(defense.armor), stat: 'Armour', source: 'Rating', sourceName: '' }] }}>{fmtPct1(defense.armor_phys_mitigation)}</Row>
        <Row label="Non-Physical Damage Mitigation" breakdown={{ title: 'Non-Physical Damage Mitigation', keys: ['armor_effective_rate_non_physical_inc'], total: defense.armor_nonphys_mitigation, totalUnit: '%', formula: 'Armor × (60% + Eff. Rate) ÷ same formula (cap 80%)', extra: [{ value: fmtNum(defense.armor), stat: 'Armour', source: 'Rating', sourceName: '' }, { value: '+60%', stat: 'Effective Rate (non-phys)', source: 'Baseline', sourceName: 'Default' }] }}>{fmtPct1(defense.armor_nonphys_mitigation)}</Row>
      </StatPanel>

      <StatPanel title="Evasion" accent="#3a8a66">
        <Row label="Evasion" breakdown={{ title: 'Evasion', keys: ['evasion_flat', 'evasion_gear_flat', 'evasion_inc', 'evasion_gear_inc', 'defense_inc', 'evasion_additional'], total: defense.evasion, formula: DEF_FORMULA }}>{fmtNum(defense.evasion)}</Row>
        {defense.evasion_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Evasion — Flat Added', keys: ['evasion_flat', 'evasion_gear_flat'] }}>{fmtNum(defense.evasion_flat)}</SubRow>}
        {defense.evasion_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Evasion — Increased', keys: ['evasion_inc', 'evasion_gear_inc', 'defense_inc'] }}>{fmtPct(defense.evasion_inc)}</SubRow>}
        {defense.evasion_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Evasion — Additional', keys: ['evasion_additional'] }}>{fmtMult(defense.evasion_additional)}</SubRow>}
        <Row label="Attack Evasion Rate" breakdown={{ title: 'Attack Evasion Rate', keys: [], total: defense.attack_evade_chance, totalUnit: '%', formula: '1 − (Acc×1.15)/(Acc + 0.5×Evasion^0.75), cap 75%', extra: [{ value: fmtNum(defense.evasion), stat: 'Evasion', source: 'Rating', sourceName: '' }] }}>{fmtPct1(defense.attack_evade_chance)}</Row>
        <Row label="Spell Evasion Chance" breakdown={{ title: 'Spell Evasion Chance', keys: [], total: defense.spell_evade_chance, totalUnit: '%', formula: 'Same formula on 60% of Evasion (spell −40%)', extra: [{ value: fmtNum(defense.evasion * 0.6), stat: 'Evasion (×0.6)', source: 'Rating', sourceName: '' }] }}>{fmtPct1(defense.spell_evade_chance)}</Row>
      </StatPanel>

      <StatPanel title="Block" accent="#6080b0">
        <Row label="Attack Block Chance" breakdown={{ title: 'Attack Block Chance', keys: ['attack_block_chance_inc'], total: defense.attack_block_chance, totalUnit: '%' }}>{fmtPct1(defense.attack_block_chance)}</Row>
        <Row label="Spell Block Chance" breakdown={{ title: 'Spell Block Chance', keys: ['spell_block_chance_inc'], total: defense.spell_block_chance, totalUnit: '%' }}>{fmtPct1(defense.spell_block_chance)}</Row>
        <Row label="Block Ratio" breakdown={{ title: 'Block Ratio', keys: ['block_ratio_inc'], total: defense.block_ratio, totalUnit: '%' }}>{fmtPct1(defense.block_ratio)}</Row>
      </StatPanel>

      <StatPanel title="Damage Avoidance" accent="#7060b0">
        <Row label="Chance to Avoid Damage" breakdown={{ title: 'Chance to Avoid Damage', keys: ['dmg_avoid_chance'], total: defense.dmg_avoid_chance, totalUnit: '%' }}>{fmtPct1(defense.dmg_avoid_chance)}</Row>
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
  const rows = [
    { label: 'Armour (Physical)', color: DTYPE_COLOR.physical, base: a.base_phys, reduction: 0, pen: a.pen ?? 0, effective: a.effective_phys },
    { label: 'Armour (Non-Physical)', color: DTYPE_COLOR.physical, base: a.base_nonphys, reduction: 0, pen: a.pen ?? 0, effective: a.effective_nonphys },
    ...(['fire', 'cold', 'lightning', 'erosion'] as const).map(t => {
      const r = target.resists[t] ?? { base: 0, effective: 0 }
      return { label: `${t.charAt(0).toUpperCase() + t.slice(1)} Resistance`, color: DTYPE_COLOR[t], base: r.base, reduction: r.reduction ?? 0, pen: r.pen ?? 0, effective: r.effective }
    }),
  ]
  const details = target.debuff_details ?? []
  return (
    <StatPanel title="Target (Dummy)" accent="#b03030">
      <div style={{ fontSize: 9, color: '#777', marginBottom: 5 }}>
        Base values from <span style={{ color: '#aaa' }}>{src}</span>. Penetration is applied at the hit — it does <i>not</i> lower the enemy's resistance.
      </div>
      {rows.map(r => {
        const changed = Math.abs(r.base - r.effective) > 1e-9
        const amplified = r.effective < 0
        const extra: ExtraRow[] = [{ value: pct(r.base), stat: r.label.replace(/ \((Physical|Non-Physical)\)/, ''), source: 'Base', sourceName: src }]
        if (Math.abs(r.reduction) > 1e-9) extra.push({ value: spct(r.reduction), stat: 'Resistance Reduction', source: 'Debuff', sourceName: 'lowers enemy resistance' })
        if (Math.abs(r.pen) > 1e-9) extra.push({ value: `−${pct(r.pen)}`, stat: 'Penetration', source: 'At hit', sourceName: 'ignored — not a resistance reduction' })
        return (
          <Row key={r.label} label={r.label} labelColor={r.color}
            breakdown={{ title: r.label, keys: [], total: r.effective, totalUnit: '%', extra }}>
            {pct(r.base)}
            {changed && (
              <span style={{ color: amplified ? '#ff8c6b' : '#8fd98f' }}>
                {' → '}{pct(r.effective)}{amplified ? ' (amplified)' : ''}
                {!!r.pen && Math.abs(r.pen) > 1e-9 && <span style={{ color: '#666' }}> ({pct(r.pen)} pen)</span>}
              </span>
            )}
          </Row>
        )
      })}
      {(details.length > 0 || target.debuffs.length > 0) && (
        <div style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: '#9a6a9a', margin: '6px 0 2px' }}>
          Active Debuffs
        </div>
      )}
      {details.length > 0
        ? details.map(d => (
            <Row key={d.name} label={`${d.name}${d.stacks ? ` ×${Math.round(d.stacks)}` : ''}`} labelColor="#d0a0e0">
              <span style={{ color: '#e0b0e0' }}>+{(d.taken_inc * 100).toFixed(0)}% {d.scope} taken</span>
            </Row>
          ))
        : target.debuffs.length > 0 && (
            <Row label="Active"><span style={{ color: '#d0a0e0' }}>{target.debuffs.join(', ')}</span></Row>
          )}
    </StatPanel>
  )
}

// ── Root ──────────────────────────────────────────────────────────────────────

export default function PlayerStatsScreen() {
  const computedStats = useBuildStore(s => s.computedStats)
  const skills = useBuildStore(s => s.skills)
  const gear = useBuildStore(s => s.gear)
  const pactSpirits = useBuildStore(s => s.pactSpirits)
  const allSpirits = useBuildStore(s => s.allSpirits)
  const heroMemories = useBuildStore(s => s.heroMemories)
  const [selectedSlot, setSelectedSlot] = useState(1)

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

  // memory name → its rarity color, for coloring hero-memory sources in breakdowns.
  const memoryColors = useMemo(() => {
    const m: Record<string, string> = {}
    for (const mem of heroMemories) if (mem) m[MEMORY_NAMES[mem.memoryType]] = MEMORY_RARITY_COLORS[mem.rarity] ?? '#6fc0b0'
    return m
  }, [heroMemories])

  const offense = (computedStats.offense ?? null) as OffenseResult | null
  const defense = (computedStats.defense ?? null) as DefenseResult | null
  const statMap = (computedStats.stats ?? {}) as Record<string, StatEntry>
  const slotOffense = ((computedStats as { slot_offense?: Record<string, OffenseResult> | null }).slot_offense) ?? null

  // Main slot uses the headline offense; other active slots use their per-slot offense (slot_offense).
  const shownOffense = selectedSlot === 1 ? offense : (slotOffense?.[String(selectedSlot)] ?? null)
  const blessings = ((computedStats as { blessings?: BlessingSummary[] | null }).blessings) ?? null

  return (
    <BreakdownCtx.Provider value={{ statMap, gear, sourceLines, treeColors, memoryColors }}>
      <div className="dark-scroll" style={{ display: 'flex', flexWrap: 'wrap', gap: 10, height: '100%', overflowY: 'auto', padding: '16px 20px', boxSizing: 'border-box' }}>
        {/* Left — skill offense */}
        <div style={{ flex: '34', minWidth: '440px', display: 'flex', flexDirection: 'column' }}>
          <SkillSelector skills={skills} selected={selectedSlot} onSelect={setSelectedSlot} />
          {selectedSlot !== 1 && !shownOffense && (
            <div style={{ fontSize: 12, color: '#555', marginBottom: 8 }}>
              No offense calculation for this slot yet.
            </div>
          )}
          <OffensePanels offense={shownOffense} />
        </div>

        {/* Middle — calculation target, attributes, blessings, utility */}
        <div style={{ flex: '30', minWidth: '240px', display: 'flex', flexDirection: 'column' }}>
          <TargetPanel target={computedStats.target_stats} />
          <AttributesPanel statMap={statMap} />
          <BlessingsPanel blessings={blessings} />
          <UtilityPanel statMap={statMap} />
        </div>

        {/* Right — defensive pools */}
        <div style={{ flex: '36', minWidth: '240px', display: 'flex', flexDirection: 'column' }}>
          <DefensePanels defense={defense} />
        </div>
      </div>
    </BreakdownCtx.Provider>
  )
}
