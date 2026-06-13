import React, { useState, useMemo, useContext } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { useBuildStore } from '../store/buildStore'
import type { OffenseResult, DefenseResult, EquippedSkill, StatEntry, EquippedGearItem, TargetStats } from '../api/client'
import { buildSpiritEffects, buildMemoryEffects } from '../api/client'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { useDamageDelta, type DeltaRequest } from '../components/tooltip/useDamageDelta'
import { getItemSlots, itemHasSlot } from '../utils/gearItem'
import { GearTooltipBody } from '../components/tooltip/bodies/GearTooltipBody'
import { SpiritTooltipBody } from '../components/tooltip/bodies/SpiritTooltipBody'
import { SkillTooltipBody } from '../components/tooltip/bodies/SkillTooltipBody'
import { MiniTree } from '../components/MiniTree'
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
  const itemSlot = matchedItem ? getItemSlots(matchedItem)[0] : undefined
  const req: DeltaRequest | null = itemSlot ? { key: `gear:rm:${itemSlot}`, step: s => ({ ...s, gear: s.gear.filter(i => !itemHasSlot(i, itemSlot)) }) } : null
  const delta = useDamageDelta(matchedItem && tip.open ? req : null, tip.open)

  const kindColor = sourceKindColor(g.source_type)
  // Source column = type+context. Gear shows just its slot (drop the "Gear · " prefix → "Weapon 1");
  // everything else uses the short kind ("Pact Spirit", "Tree", …).
  const sourceLabel = isGear ? g.label.replace(/^Gear · /, '') : sourceKindLabel(g.source_type)
  // Source Name column = the real name (item / spirit / memory / support / tree); talents show just the tree.
  const sourceName = g.source_name || (isTalent ? treeName : (g.text || g.label || '—'))

  return (
    <>
      <div {...(hasHover ? tip.triggerProps : {})}
        style={{ display: 'grid', gridTemplateColumns: BD_GRID, gap: 8, alignItems: 'baseline', padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: hasHover ? 'help' : undefined }}>
        <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
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
            <div className="tooltip tooltip--gear" {...tip.floatingProps}><GearTooltipBody item={matchedItem} delta={delta} /></div>
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

function BreakdownBody({ title, keys, ctx, totalOverride, totalUnit, extra }: { title: string; keys: string[]; ctx: BreakdownCtxValue; totalOverride?: number; totalUnit?: string; extra?: ExtraRow[] }) {
  const { main, slot } = collectSources(keys, ctx.statMap)
  const isResist = keys.some(k => k.includes('resist'))
  // When a row passes its already-derived value (e.g. Max Energy Shield = flat × (1+increased)), show THAT
  // as the header — summing mixed flat/increased/additional keys is meaningless (it printed "0.27" for a 0
  // ES with 27% increased). Otherwise (single-pool breakdowns like "Increased — All Types") sum the keys.
  const headerVal = totalOverride !== undefined ? totalOverride : keys.reduce((s, k) => s + (ctx.statMap[k]?.total ?? 0), 0)
  const headerUnit = totalOverride !== undefined ? (totalUnit ?? '') : (ctx.statMap[keys[0]]?.unit ?? '')
  const fmtTot = (v: number) => headerUnit === '%' ? `${(v * 100).toFixed(0)}%` : (v % 1 === 0 ? v.toFixed(0) : v.toFixed(2))
  const groupedMain = groupCollected(main)
  const slotGroups = new Map<number, GroupedCollected[]>()
  for (const g of groupCollected(slot)) {
    const k = g.slot ?? 0
    if (!slotGroups.has(k)) slotGroups.set(k, [])
    slotGroups.get(k)!.push(g)
  }
  const empty = groupedMain.length === 0 && slotGroups.size === 0 && !(extra && extra.length)
  return (
    <div style={{ minWidth: 340, maxWidth: 520, fontSize: 11 }}>
      <div style={{ fontWeight: 700, color: '#cfcfe6', marginBottom: 3 }}>{title}</div>
      <div style={{ marginBottom: 6, display: 'flex', alignItems: 'baseline', gap: 12 }}>
        {isResist && <span style={{ fontSize: 10, color: '#888' }}>Min: -200%  Max: 75%</span>}
        <span style={{ fontSize: 10, color: '#888' }}>Total</span>
        <span style={{ fontSize: 16, fontWeight: 700, color: '#e8e8f4', fontVariantNumeric: 'tabular-nums' }}>{fmtTot(headerVal)}</span>
      </div>
      {empty ? <div style={{ color: '#555' }}>No sources found</div> : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: BD_GRID, gap: 8, fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: '#666', paddingBottom: 3, borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
            <span>Value</span><span>Stat</span><span>Source</span><span>Source Name</span>
          </div>
          {(extra ?? []).map((e, i) => (
            <div key={`e${i}`} style={{ display: 'grid', gridTemplateColumns: BD_GRID, gap: 8, alignItems: 'baseline', padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{e.value}</span>
              <span style={{ color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.stat}</span>
              <span style={{ color: '#8a8aa0', fontSize: 10, whiteSpace: 'nowrap' }}>{e.source}</span>
              <span style={{ color: '#8a8aa0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.sourceName}</span>
            </div>
          ))}
          {groupedMain.map((g, i) => <BreakdownSourceRow key={`m${i}`} g={g} ctx={ctx} />)}
          {[...slotGroups.entries()].map(([slotNo, rows]) => (
            <React.Fragment key={`s${slotNo}`}>
              <div style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: '#7a9af0', margin: '6px 0 2px' }}>
                Skill-specific (slot {slotNo})
              </div>
              {rows.map((g, i) => <BreakdownSourceRow key={`s${slotNo}-${i}`} g={g} ctx={ctx} />)}
            </React.Fragment>
          ))}
        </>
      )}
    </div>
  )
}

// Wrap any value/label to make it a hover-open, click-pin source breakdown. No-op (renders children
// only) outside a BreakdownCtx provider.
function Breakdown({ title, keys, children, block }: { title: string; keys: string[]; children: React.ReactNode; block?: boolean }) {
  const ctx = useContext(BreakdownCtx)
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right', trigger: 'hover', pinnable: true, interactive: true, openDelay: 90 })
  if (!ctx) return <>{children}</>
  return (
    <>
      <span {...tip.triggerProps} style={{ cursor: 'pointer', display: block ? 'block' : undefined }}>{children}</span>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--breakdown" {...tip.floatingProps}>
            <BreakdownBody title={title} keys={keys} ctx={ctx} />
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
  breakdown?: { title: string; keys: string[]; total?: number; totalUnit?: string; extra?: ExtraRow[] };
}) {
  const ctx = useContext(BreakdownCtx)
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right', trigger: 'hover', pinnable: true, interactive: true, openDelay: 90 })
  const bd = !!breakdown && !!ctx
  return (
    <>
      <div {...(bd ? tip.triggerProps : {})}
        style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 12, borderBottom: '1px solid rgba(255,255,255,0.03)', cursor: (bd || onClick) ? 'pointer' : undefined }}
        onClick={bd ? undefined : onClick}>
        <span style={{ color: labelColor ?? '#999' }}>
          {expandable && <span style={{ display: 'inline-block', width: 10, fontSize: 8, color: '#555', marginRight: 2 }}>{expanded ? '▾' : '▸'}</span>}
          {label}
        </span>
        <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums' }}>{children}</span>
      </div>
      {bd && tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--breakdown" {...tip.floatingProps}>
            <BreakdownBody title={breakdown!.title} keys={breakdown!.keys} ctx={ctx!} totalOverride={breakdown!.total} totalUnit={breakdown!.totalUnit} extra={breakdown!.extra} />
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

function flatMinKeys(dtype: string, offense: OffenseResult): string[] {
  const keys = [`${dtype}_dmg_gear_flat_min`]
  if (offense.skill_tags.includes('attack')) keys.push(`${dtype}_attack_dmg_flat_min`)
  if (offense.skill_tags.includes('spell')) keys.push(`${dtype}_spell_dmg_flat_min`)
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_gear_flat_min')
  return keys
}

function flatMaxKeys(dtype: string, offense: OffenseResult): string[] {
  const keys = [`${dtype}_dmg_gear_flat_max`]
  if (offense.skill_tags.includes('attack')) keys.push(`${dtype}_attack_dmg_flat_max`)
  if (offense.skill_tags.includes('spell')) keys.push(`${dtype}_spell_dmg_flat_max`)
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_gear_flat_max')
  return keys
}

function genericIncKeys(offense: OffenseResult): string[] {
  const keys = ['dmg_inc']
  if (offense.skill_tags.includes('attack'))     keys.push('attack_dmg_inc')
  if (offense.skill_tags.includes('spell'))      keys.push('spell_dmg_inc')
  if (offense.skill_tags.includes('melee'))      keys.push('melee_dmg_inc')
  if (offense.skill_tags.includes('area'))       keys.push('area_dmg_inc')
  if (offense.skill_tags.includes('projectile')) keys.push('projectile_dmg_inc')
  return keys
}

function typeIncKeys(dtype: string): string[] {
  const keys = [`${dtype}_dmg_inc`]
  if (['fire', 'cold', 'lightning'].includes(dtype)) keys.push('elemental_dmg_inc')
  return keys
}

function genericAddKeys(offense: OffenseResult): string[] {
  const keys = ['dmg_additional']
  if (offense.skill_tags.includes('attack'))     keys.push('attack_dmg_additional')
  if (offense.skill_tags.includes('spell'))      keys.push('spell_dmg_additional')
  if (offense.skill_tags.includes('melee'))      keys.push('melee_dmg_additional')
  if (offense.skill_tags.includes('area'))       keys.push('area_dmg_additional')
  if (offense.skill_tags.includes('projectile')) keys.push('projectile_dmg_additional')
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
              return <td key={d} style={v > 0 ? td : tdDim}>
                {v > 0 ? <Breakdown title={`Added Min — ${DTYPE_LABEL[d]}`} keys={flatMinKeys(d, offense)}>{fmtNum(v)}</Breakdown> : fmtNum(v)}
              </td>
            })}
          </tr>
          <tr>
            <td style={tdLbl}>Added Max</td>
            <td style={tdDim}>—</td>
            {ALL_DTYPES.map(d => {
              const v = offense.flat_dmg_max[d] ?? 0
              return <td key={d} style={v > 0 ? td : tdDim}>
                {v > 0 ? <Breakdown title={`Added Max — ${DTYPE_LABEL[d]}`} keys={flatMaxKeys(d, offense)}>{fmtNum(v)}</Breakdown> : fmtNum(v)}
              </td>
            })}
          </tr>
          {/* ── Multipliers: "All Types" = the catch-all bucket (generic + skill-tag-scoped mods the
               skill qualifies for, e.g. additional attack/area/spell damage); per-type columns show
               ONLY that damage type's specific additional. Empty = the identity (0% / ×1.00), not a
               dash — a type with no specific modifier reads ×1.00. ── */}
          <tr>
            <td style={tdLbl}>Total Increased</td>
            <td style={td}><Breakdown title="Total Increased — All Types" keys={genericIncKeys(offense)}>{(offense.generic_inc * 100).toFixed(0)}%</Breakdown></td>
            {ALL_DTYPES.map(d => {
              // Specific = this type's increase beyond the generic (catch-all) bucket. Types the skill
              // doesn't deal have no entry → treated as generic-only → 0% specific.
              const specific = Math.max(0, (offense.type_inc[d] ?? offense.generic_inc) - offense.generic_inc)
              const show = specific >= 0.005
              const txt = `${(specific * 100).toFixed(0)}%`
              return <td key={d} style={show ? td : tdDim}>
                {show ? <Breakdown title={`Total Increased — ${DTYPE_LABEL[d]}`} keys={typeIncKeys(d)}>{txt}</Breakdown> : txt}
              </td>
            })}
          </tr>
          <tr>
            <td style={tdLbl}>Total Additional</td>
            <td style={td}><Breakdown title="Total Additional — All Types" keys={genericAddKeys(offense)}>×{offense.generic_add.toFixed(2)}</Breakdown></td>
            {ALL_DTYPES.map(d => {
              // Specific = type_add factored over the generic bucket. Types the skill doesn't deal have
              // no entry → ×1.00 (not 1/generic, which would show a phantom multiplier on empty types).
              const specificAdd = offense.type_add[d] !== undefined
                ? offense.type_add[d] / (offense.generic_add || 1)
                : 1
              const show = Math.abs(specificAdd - 1) >= 0.005
              const txt = `×${specificAdd.toFixed(2)}`
              return <td key={d} style={show ? td : tdDim}>
                {show ? <Breakdown title={`Total Additional — ${DTYPE_LABEL[d]}`} keys={typeAddKeys(d)}>{txt}</Breakdown> : txt}
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

  const isSpell = offense.skill_tags.includes('spell')
  const rateLabel = isSpell ? 'Casts per Second' : 'Attacks per Second'
  const rateKeys = isSpell ? ['cast_speed_inc'] : ['weapon_attack_speed', 'attack_speed_inc', 'attack_speed_gear', 'attack_speed_mh']

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
        {offense.skill_tags.includes('area') && (
          <Row label="Area of Effect">{offense.skill_area_inc !== 0 ? `+${(offense.skill_area_inc * 100).toFixed(0)}%` : '+0%'}</Row>
        )}
        {offense.skill_tags.includes('projectile') && (
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
        <Row label={rateLabel} breakdown={{ title: rateLabel, keys: rateKeys }}>{offense.attacks_per_second.toFixed(2)}</Row>
        {!isSpell && offense.weapon_attack_speed > 0 && (
          <Row label="Weapon Base APS" breakdown={{ title: 'Weapon Base APS', keys: ['weapon_attack_speed'] }}>{offense.weapon_attack_speed.toFixed(3)}</Row>
        )}
        {!isSpell && offense.weapon_aps_gear > 0 && (
          <Row label="APS Gear Bonus" breakdown={{ title: 'APS Gear Bonus', keys: ['attack_speed_gear'] }}>{(offense.weapon_aps_gear * 100).toFixed(1)}%</Row>
        )}
        {!isSpell && offense.weapon_aps_mh > 0 && (
          <Row label="APS MH Bonus" breakdown={{ title: 'APS MH Bonus', keys: ['attack_speed_mh'] }}>{(offense.weapon_aps_mh * 100).toFixed(1)}%</Row>
        )}
      </StatPanel>

      <StatPanel title="Critical Strikes" accent={AMBER}>
        {/* Hover for the full breakdown (like the other rows) — no inline accordion. For spells the
            intrinsic base crit rating is shown as a "Spell base" baseline; for attacks the weapon's base
            crit rating shows as a real gear source via weapon_crit_rating_flat. */}
        <Row label="Crit Chance" breakdown={{
          title: 'Crit Chance',
          keys: isSpell
            ? ['spell_crit_rating_flat', 'crit_rating_flat', 'crit_rating_inc']
            : ['weapon_crit_rating_flat', 'attack_crit_rating_gear', 'attack_crit_rating_mh', 'attack_crit_rating_flat', 'attack_crit_rating_inc'],
          total: offense.crit_chance, totalUnit: '%',
          extra: isSpell && offense.base_csr > 0
            ? [{ value: offense.base_csr.toFixed(0), stat: 'Base Crit Rating', source: 'Baseline', sourceName: 'Spell base' }]
            : undefined,
        }}>{(offense.crit_chance * 100).toFixed(1)}%</Row>
        <Row label="Crit Multiplier" breakdown={{
          title: 'Crit Multiplier',
          keys: ['crit_damage'],
          total: offense.crit_multiplier, totalUnit: '%',
          extra: [{ value: '150%', stat: 'Crit Multiplier', source: 'Baseline', sourceName: 'Base ×1.5' }],
        }}>{(offense.crit_multiplier * 100).toFixed(0)}%</Row>
      </StatPanel>
    </>
  )
}

// ── Defense panels ────────────────────────────────────────────────────────────

function SubRow({ label, children, breakdown }: { label: string; children: React.ReactNode; breakdown?: { title: string; keys: string[]; total?: number; totalUnit?: string; extra?: ExtraRow[] } }) {
  const ctx = useContext(BreakdownCtx)
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right', trigger: 'hover', pinnable: true, interactive: true, openDelay: 90 })
  const bd = !!breakdown && !!ctx
  return (
    <>
      <div {...(bd ? tip.triggerProps : {})}
        style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 12, borderBottom: '1px solid rgba(255,255,255,0.03)', cursor: bd ? 'pointer' : undefined }}>
        <span style={{ color: '#666' }}>{label}</span>
        <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums' }}>{children}</span>
      </div>
      {bd && tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--breakdown" {...tip.floatingProps}>
            <BreakdownBody title={breakdown!.title} keys={breakdown!.keys} ctx={ctx!} totalOverride={breakdown!.total} totalUnit={breakdown!.totalUnit} extra={breakdown!.extra} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

function fmtPct(v: number): string { return `${(v * 100).toFixed(0)}%` }
function fmtMult(v: number): string { return `×${(1 + v).toFixed(2)}` }

function DefensePanels({ defense }: { defense: DefenseResult | null }) {
  if (!defense) {
    return <StatPanel title="Life" accent="#c03030"><div style={{ fontSize: 12, color: '#555' }}>No data.</div></StatPanel>
  }
  return (
    <>
      <StatPanel title="Life" accent="#c03030">
        <Row label="Max Life" breakdown={{ title: 'Max Life', keys: ['max_life_flat', 'max_life_inc', 'max_life_additional'], total: defense.max_life }}>{fmtNum(defense.max_life)}</Row>
        {defense.life_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Life — Flat Added', keys: ['max_life_flat'] }}>{fmtNum(defense.life_flat)}</SubRow>}
        {defense.life_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Life — Increased', keys: ['max_life_inc'] }}>{fmtPct(defense.life_inc)}</SubRow>}
        {defense.life_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Life — Additional', keys: ['max_life_additional'] }}>{fmtMult(defense.life_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Mana" accent="#3060c0">
        <Row label="Max Mana" breakdown={{ title: 'Max Mana', keys: ['max_mana_flat', 'max_mana_inc', 'max_mana_additional'], total: defense.max_mana }}>{fmtNum(defense.max_mana)}</Row>
        {defense.mana_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Mana — Flat Added', keys: ['max_mana_flat'] }}>{fmtNum(defense.mana_flat)}</SubRow>}
        {defense.mana_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Mana — Increased', keys: ['max_mana_inc'] }}>{fmtPct(defense.mana_inc)}</SubRow>}
        {defense.mana_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Mana — Additional', keys: ['max_mana_additional'] }}>{fmtMult(defense.mana_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Energy Shield" accent="#5aa0d0">
        <Row label="Max Energy Shield" breakdown={{ title: 'Max Energy Shield', keys: ['max_energy_shield_flat', 'energy_shield_gear_flat', 'max_energy_shield_inc', 'energy_shield_gear_inc', 'max_energy_shield_additional'], total: defense.max_energy_shield }}>{fmtNum(defense.max_energy_shield)}</Row>
        {defense.es_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Energy Shield — Flat Added', keys: ['max_energy_shield_flat', 'energy_shield_gear_flat'] }}>{fmtNum(defense.es_flat)}</SubRow>}
        {defense.es_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Energy Shield — Increased', keys: ['max_energy_shield_inc', 'energy_shield_gear_inc'] }}>{fmtPct(defense.es_inc)}</SubRow>}
        {defense.es_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Energy Shield — Additional', keys: ['max_energy_shield_additional'] }}>{fmtMult(defense.es_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Resistances" accent="#7030b0">
        <Row label="Fire" breakdown={{ title: 'Fire Resistance', keys: ['fire_resistance', 'elemental_resistance'] }}>{fmtResistValue(defense.fire_resist, defense.fire_resist_raw)}</Row>
        <Row label="Cold" breakdown={{ title: 'Cold Resistance', keys: ['cold_resistance', 'elemental_resistance'] }}>{fmtResistValue(defense.cold_resist, defense.cold_resist_raw)}</Row>
        <Row label="Lightning" breakdown={{ title: 'Lightning Resistance', keys: ['lightning_resistance', 'elemental_resistance'] }}>{fmtResistValue(defense.lightning_resist, defense.lightning_resist_raw)}</Row>
        <Row label="Erosion" breakdown={{ title: 'Erosion Resistance', keys: ['erosion_resistance'] }}>{fmtResistValue(defense.erosion_resist, defense.erosion_resist_raw)}</Row>
      </StatPanel>

      <StatPanel title="Armour &amp; Evasion" accent="#308060">
        <Row label="Armour" breakdown={{ title: 'Armour', keys: ['armor_flat', 'armor_gear_flat', 'armor_inc', 'armor_gear_inc', 'defense_inc', 'armor_additional'], total: defense.armor }}>{fmtNum(defense.armor)}</Row>
        {defense.armor_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Armour — Flat Added', keys: ['armor_flat', 'armor_gear_flat'] }}>{fmtNum(defense.armor_flat)}</SubRow>}
        {defense.armor_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Armour — Increased', keys: ['armor_inc', 'armor_gear_inc', 'defense_inc'] }}>{fmtPct(defense.armor_inc)}</SubRow>}
        {defense.armor_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Armour — Additional', keys: ['armor_additional'] }}>{fmtMult(defense.armor_additional)}</SubRow>}
        <Row label="Evasion" breakdown={{ title: 'Evasion', keys: ['evasion_flat', 'evasion_gear_flat', 'evasion_inc', 'evasion_gear_inc', 'defense_inc', 'evasion_additional'], total: defense.evasion }}>{fmtNum(defense.evasion)}</Row>
        {defense.evasion_flat > 0 && <SubRow label="Flat Added" breakdown={{ title: 'Evasion — Flat Added', keys: ['evasion_flat', 'evasion_gear_flat'] }}>{fmtNum(defense.evasion_flat)}</SubRow>}
        {defense.evasion_inc !== 0 && <SubRow label="Increased" breakdown={{ title: 'Evasion — Increased', keys: ['evasion_inc', 'evasion_gear_inc', 'defense_inc'] }}>{fmtPct(defense.evasion_inc)}</SubRow>}
        {defense.evasion_additional !== 0 && <SubRow label="Additional" breakdown={{ title: 'Evasion — Additional', keys: ['evasion_additional'] }}>{fmtMult(defense.evasion_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Utility" accent="#505050">
        <Row label="Movement Speed" labelColor="#444">— NYI</Row>
        <Row label="Blessing Uptime" labelColor="#444">— NYI</Row>
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
  const pen = target.pen
  const rows = [
    { label: 'Armour (Physical)', base: target.armor.base_phys, eff: target.armor.effective_phys, penPct: pen?.armor },
    { label: 'Armour (Non-Physical)', base: target.armor.base_nonphys, eff: target.armor.effective_nonphys, penPct: pen?.armor },
    { label: 'Fire Resistance', base: target.resists.fire?.base ?? 0, eff: target.resists.fire?.effective ?? 0, penPct: (pen?.fire ?? 0) + (pen?.elemental ?? 0) },
    { label: 'Cold Resistance', base: target.resists.cold?.base ?? 0, eff: target.resists.cold?.effective ?? 0, penPct: (pen?.cold ?? 0) + (pen?.elemental ?? 0) },
    { label: 'Lightning Resistance', base: target.resists.lightning?.base ?? 0, eff: target.resists.lightning?.effective ?? 0, penPct: (pen?.lightning ?? 0) + (pen?.elemental ?? 0) },
    { label: 'Erosion Resistance', base: target.resists.erosion?.base ?? 0, eff: target.resists.erosion?.effective ?? 0, penPct: pen?.erosion ?? 0 },
  ]
  const details = target.debuff_details ?? []
  return (
    <StatPanel title="Target (Dummy)" accent="#b03030">
      {rows.map(r => {
        const changed = Math.abs(r.base - r.eff) > 1e-9
        const amplified = r.eff < 0
        return (
          <Row key={r.label} label={r.label}>
            {pct(r.base)}
            {changed && (
              <span style={{ color: amplified ? '#ff8c6b' : '#8fd98f' }}>
                {' → '}{pct(r.eff)}{amplified ? ' (amplified)' : ''}
                {!!r.penPct && r.penPct > 0 && <span style={{ color: '#666' }}> ({pct(r.penPct)} pen)</span>}
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

  const offense = (computedStats.offense ?? null) as OffenseResult | null
  const defense = (computedStats.defense ?? null) as DefenseResult | null
  const statMap = (computedStats.stats ?? {}) as Record<string, StatEntry>
  const slotOffense = ((computedStats as { slot_offense?: Record<string, OffenseResult> | null }).slot_offense) ?? null

  // Main slot uses the headline offense; other active slots use their per-slot offense (slot_offense).
  const shownOffense = selectedSlot === 1 ? offense : (slotOffense?.[String(selectedSlot)] ?? null)

  return (
    <BreakdownCtx.Provider value={{ statMap, gear, sourceLines }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, height: '100%', overflowY: 'auto', padding: '16px 20px', boxSizing: 'border-box' }}>
        {/* Left lane — skill offense */}
        <div style={{ flex: '41', minWidth: '460px', display: 'flex', flexDirection: 'column' }}>
          <SkillSelector skills={skills} selected={selectedSlot} onSelect={setSelectedSlot} />
          {selectedSlot !== 1 && !shownOffense && (
            <div style={{ fontSize: 12, color: '#555', marginBottom: 8 }}>
              No offense calculation for this slot yet.
            </div>
          )}
          <OffensePanels offense={shownOffense} />
        </div>

        {/* Right lane — defense + utility + calculation target */}
        <div style={{ flex: '59', minWidth: '200px', display: 'flex', flexDirection: 'column' }}>
          <DefensePanels defense={defense} />
          <TargetPanel target={computedStats.target_stats} />
        </div>
      </div>
    </BreakdownCtx.Provider>
  )
}
