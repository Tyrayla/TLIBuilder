import React, { useState } from 'react'
import { createPortal } from 'react-dom'
import { FloatingPortal } from '@floating-ui/react'
import { useBuildStore } from '../store/buildStore'
import type { OffenseResult, DefenseResult, EquippedSkill, StatSource, StatEntry, EquippedGearItem } from '../api/client'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { useDamageDelta, type DeltaRequest } from '../components/tooltip/useDamageDelta'
import { getItemSlots, itemHasSlot } from '../utils/gearItem'
import { GearTooltipBody } from '../components/tooltip/bodies/GearTooltipBody'

// ── Source popup ──────────────────────────────────────────────────────────────

interface GroupedSource { text: string; label: string; amount: number; count: number; source_type: string }

// One source row. Gear-backed rows open a nested gear tooltip (element-anchored) via a
// second floating-tooltip instance — independent of the popup itself.
function SourceRow({ g, matchedItem }: { g: GroupedSource; matchedItem: EquippedGearItem | undefined }) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'left' })
  // Gear contribution: remove this equipped item from its slot and diff vs the current build.
  const slot = matchedItem ? getItemSlots(matchedItem)[0] : undefined
  // What you'd LOSE by unequipping (step = build without it, base = current) — matches talent nodes.
  const req: DeltaRequest | null = slot ? { key: `gear:rm:${slot}`, step: s => ({ ...s, gear: s.gear.filter(i => !itemHasSlot(i, slot)) }) } : null
  const delta = useDamageDelta(tip.open ? req : null, tip.open)
  return (
    <>
      <div
        {...(matchedItem ? tip.triggerProps : {})}
        style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.04)', cursor: matchedItem ? 'default' : undefined }}
      >
        <span style={{ color: '#bbb', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {g.text || g.label}
          {g.count > 1 && <span style={{ color: '#666' }}> ×{g.count}</span>}
        </span>
        <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
          {g.amount % 1 === 0 ? g.amount.toFixed(0) : g.amount.toFixed(2)}
        </span>
      </div>
      {matchedItem && tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--gear" {...tip.floatingProps}>
            <GearTooltipBody item={matchedItem} delta={delta} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

function groupSources(sources: StatSource[]): GroupedSource[] {
  const out: GroupedSource[] = []
  for (const src of sources) {
    const match = out.find(g => g.text === src.text && g.label === src.label)
    if (match) match.count += src.points ?? 1
    else out.push({ text: src.text, label: src.label, amount: src.amount, count: src.points ?? 1, source_type: src.source_type })
  }
  return out
}

function collectSources(keys: string[], stats: Record<string, StatEntry>): StatSource[] {
  return keys.flatMap(k => stats[k]?.sources ?? [])
}

interface SourcePopupProps {
  title: string
  sources: StatSource[]
  x: number
  y: number
  gear: EquippedGearItem[]
  onClose: () => void
}

function SourcePopup({ title, sources, x, y, gear, onClose }: SourcePopupProps) {
  const grouped = groupSources(sources)
  const popupWidth = 300
  const estimatedHeight = 56 + Math.min(grouped.length, 12) * 22
  const left = x + 8 + popupWidth > window.innerWidth - 8 ? Math.max(8, x - popupWidth - 8) : x + 8
  const top = y + 8 + estimatedHeight > window.innerHeight - 8 ? Math.max(8, y - estimatedHeight - 8) : y + 8

  return createPortal(
    <>
      <div style={{ position: 'fixed', inset: 0, zIndex: 9998 }} onClick={onClose} />
      <div style={{
        position: 'fixed', zIndex: 9999, left, top,
        background: '#0e0e1e', border: '1px solid #3a3a6a', borderRadius: 6,
        padding: '8px 12px', minWidth: 220, maxWidth: 320,
        boxShadow: '0 4px 20px rgba(0,0,0,0.65)', fontSize: 11,
      }}>
        <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#666', marginBottom: 6 }}>
          {title}
        </div>
        {grouped.length === 0 ? (
          <div style={{ color: '#555' }}>No sources found</div>
        ) : grouped.map((g, i) => {
          const isGear = g.source_type === 'legendary_gear' || g.source_type === 'normal_gear' || g.source_type === 'gear'
          const matchedItem = isGear ? gear.find(item => item.name === g.text) : undefined
          return <SourceRow key={i} g={g} matchedItem={matchedItem} />
        })}
      </div>
    </>,
    document.body
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

function Row({ label, children, labelColor, onClick, expandable, expanded }: {
  label: string; children: React.ReactNode; labelColor?: string;
  onClick?: (e: React.MouseEvent) => void;
  expandable?: boolean; expanded?: boolean;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 12, borderBottom: '1px solid rgba(255,255,255,0.03)', cursor: onClick ? 'pointer' : undefined }}
      onClick={onClick}>
      <span style={{ color: labelColor ?? '#999' }}>
        {expandable && <span style={{ display: 'inline-block', width: 10, fontSize: 8, color: '#555', marginRight: 2 }}>{expanded ? '▾' : '▸'}</span>}
        {label}
      </span>
      <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums' }}>{children}</span>
    </div>
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

type CellClickHandler = (title: string, keys: string[], e: React.MouseEvent) => void

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

function DamageBreakdownTable({ offense, onCellClick }: { offense: OffenseResult; onCellClick: CellClickHandler }) {
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
  const tdCk: React.CSSProperties = { ...td, cursor: 'pointer' }
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
              return <td key={d} style={v > 0 ? tdCk : tdDim}
                onClick={v > 0 ? e => onCellClick(`Added Min — ${DTYPE_LABEL[d]}`, flatMinKeys(d, offense), e) : undefined}>
                {fmtNum(v)}
              </td>
            })}
          </tr>
          <tr>
            <td style={tdLbl}>Added Max</td>
            <td style={tdDim}>—</td>
            {ALL_DTYPES.map(d => {
              const v = offense.flat_dmg_max[d] ?? 0
              return <td key={d} style={v > 0 ? tdCk : tdDim}
                onClick={v > 0 ? e => onCellClick(`Added Max — ${DTYPE_LABEL[d]}`, flatMaxKeys(d, offense), e) : undefined}>
                {fmtNum(v)}
              </td>
            })}
          </tr>
          {/* ── Multipliers: "All Types" = the catch-all bucket (generic + skill-tag-scoped mods the
               skill qualifies for, e.g. additional attack/area/spell damage); per-type columns show
               ONLY that damage type's specific additional. Empty = the identity (0% / ×1.00), not a
               dash — a type with no specific modifier reads ×1.00. ── */}
          <tr>
            <td style={tdLbl}>Total Increased</td>
            <td style={tdCk} onClick={e => onCellClick('Total Increased — All Types', genericIncKeys(offense), e)}>{(offense.generic_inc * 100).toFixed(0)}%</td>
            {ALL_DTYPES.map(d => {
              // Specific = this type's increase beyond the generic (catch-all) bucket. Types the skill
              // doesn't deal have no entry → treated as generic-only → 0% specific.
              const specific = Math.max(0, (offense.type_inc[d] ?? offense.generic_inc) - offense.generic_inc)
              const show = specific >= 0.005
              return <td key={d} style={show ? tdCk : tdDim}
                onClick={show ? e => onCellClick(`Total Increased — ${DTYPE_LABEL[d]}`, typeIncKeys(d), e) : undefined}>
                {`${(specific * 100).toFixed(0)}%`}
              </td>
            })}
          </tr>
          <tr>
            <td style={tdLbl}>Total Additional</td>
            <td style={tdCk} onClick={e => onCellClick('Total Additional — All Types', genericAddKeys(offense), e)}>×{offense.generic_add.toFixed(2)}</td>
            {ALL_DTYPES.map(d => {
              // Specific = type_add factored over the generic bucket. Types the skill doesn't deal have
              // no entry → ×1.00 (not 1/generic, which would show a phantom multiplier on empty types).
              const specificAdd = offense.type_add[d] !== undefined
                ? offense.type_add[d] / (offense.generic_add || 1)
                : 1
              const show = Math.abs(specificAdd - 1) >= 0.005
              return <td key={d} style={show ? tdCk : tdDim}
                onClick={show ? e => onCellClick(`Total Additional — ${DTYPE_LABEL[d]}`, typeAddKeys(d), e) : undefined}>
                {`×${specificAdd.toFixed(2)}`}
              </td>
            })}
          </tr>
          {/* Damage Bonus from the skill's main-stat attributes (0.5% per point, summed). Its own
              additional pool — already INCLUDED in Total Additional above; broken out here for clarity. */}
          {offense.main_stat_damage_bonus > 0 && (
            <tr>
              <td style={tdSub}>↳ Damage Bonus</td>
              <td style={tdCk} title={`+${(offense.main_stat_damage_bonus * 100).toFixed(1)}% from ${offense.main_stats.join(' + ')}`}
                onClick={e => onCellClick('Damage Bonus — Main Stat', offense.main_stats, e)}>×{(1 + offense.main_stat_damage_bonus).toFixed(2)}</td>
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

function OffensePanels({ offense, onCellClick, statMap }: { offense: OffenseResult | null; onCellClick: CellClickHandler; statMap: Record<string, StatEntry> }) {
  const [critExpanded, setCritExpanded] = useState(false)

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

  return (
    <>
      <StatPanel title={`Offense — ${offense.skill_name} L${offense.effective_level}`} accent={AMBER}>
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
        <DamageBreakdownTable offense={offense} onCellClick={onCellClick} />
      </StatPanel>

      <StatPanel title="Attack Rate" accent={AMBER}>
        <Row label="Attacks per Second" onClick={e => onCellClick('Attacks per Second', ['weapon_attack_speed', 'attack_speed_inc', 'attack_speed_gear', 'attack_speed_mh'], e)}>{offense.attacks_per_second.toFixed(2)}</Row>
        {offense.weapon_attack_speed > 0 && (
          <Row label="Weapon Base APS" onClick={e => onCellClick('Weapon Base APS', ['weapon_attack_speed'], e)}>{offense.weapon_attack_speed.toFixed(3)}</Row>
        )}
        {offense.weapon_aps_gear > 0 && (
          <Row label="APS Gear Bonus" onClick={e => onCellClick('APS Gear Bonus', ['attack_speed_gear'], e)}>{(offense.weapon_aps_gear * 100).toFixed(1)}%</Row>
        )}
        {offense.weapon_aps_mh > 0 && (
          <Row label="APS MH Bonus" onClick={e => onCellClick('APS MH Bonus', ['attack_speed_mh'], e)}>{(offense.weapon_aps_mh * 100).toFixed(1)}%</Row>
        )}
      </StatPanel>

      <StatPanel title="Critical Strikes" accent={AMBER}>
        <Row label="Crit Chance" expandable expanded={critExpanded} onClick={_e => setCritExpanded(c => !c)}>
          {(offense.crit_chance * 100).toFixed(1)}%
        </Row>
        {critExpanded && (
          <>
            {offense.weapon_crit_rating_flat > 0 && (
              <SubRow label="Weapon Base Crit Rating" onClick={e => onCellClick('Weapon Base Crit Rating', ['weapon_crit_rating_flat'], e)}>
                {offense.weapon_crit_rating_flat.toFixed(0)}
              </SubRow>
            )}
            {(offense.weapon_csr_gear > 0 || offense.weapon_csr_mh > 0) && (
              <SubRow label="Gear Increased Crit Rating" onClick={e => onCellClick('Gear Increased Crit Rating', ['attack_crit_rating_gear', 'attack_crit_rating_mh'], e)}>
                +{((offense.weapon_csr_gear + offense.weapon_csr_mh) * 100).toFixed(1)}%
              </SubRow>
            )}
            {(statMap['attack_crit_rating_flat']?.total ?? 0) > 0 && (
              <SubRow label="Other Flat CSR" onClick={e => onCellClick('Other Flat CSR', ['attack_crit_rating_flat'], e)}>
                {(statMap['attack_crit_rating_flat']?.total ?? 0).toFixed(0)}
              </SubRow>
            )}
            {(statMap['attack_crit_rating_inc']?.total ?? 0) > 0 && (
              <SubRow label="Increased" onClick={e => onCellClick('CSR Increased', ['attack_crit_rating_inc'], e)}>
                +{((statMap['attack_crit_rating_inc']?.total ?? 0) * 100).toFixed(0)}%
              </SubRow>
            )}
          </>
        )}
        <Row label="Crit Multiplier" onClick={e => onCellClick('Crit Multiplier', ['crit_damage'], e)}>{(offense.crit_multiplier * 100).toFixed(0)}%</Row>
      </StatPanel>
    </>
  )
}

// ── Defense panels ────────────────────────────────────────────────────────────

function SubRow({ label, children, onClick }: { label: string; children: React.ReactNode; onClick?: (e: React.MouseEvent) => void }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 12, borderBottom: '1px solid rgba(255,255,255,0.03)', cursor: onClick ? 'pointer' : undefined }}
      onClick={onClick}>
      <span style={{ color: '#666' }}>{label}</span>
      <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums' }}>{children}</span>
    </div>
  )
}

function fmtPct(v: number): string { return `${(v * 100).toFixed(0)}%` }
function fmtMult(v: number): string { return `×${(1 + v).toFixed(2)}` }

function DefensePanels({ defense, onCellClick }: { defense: DefenseResult | null; onCellClick: CellClickHandler }) {
  if (!defense) {
    return <StatPanel title="Life" accent="#c03030"><div style={{ fontSize: 12, color: '#555' }}>No data.</div></StatPanel>
  }
  const ck = (title: string, keys: string[], e: React.MouseEvent) => onCellClick(title, keys, e)
  return (
    <>
      <StatPanel title="Life" accent="#c03030">
        <Row label="Max Life" onClick={e => ck('Max Life', ['max_life_flat', 'max_life_inc', 'max_life_additional'], e)}>{fmtNum(defense.max_life)}</Row>
        {defense.life_flat > 0 && <SubRow label="Flat Added" onClick={e => ck('Life — Flat Added', ['max_life_flat'], e)}>{fmtNum(defense.life_flat)}</SubRow>}
        {defense.life_inc !== 0 && <SubRow label="Increased" onClick={e => ck('Life — Increased', ['max_life_inc'], e)}>{fmtPct(defense.life_inc)}</SubRow>}
        {defense.life_additional !== 0 && <SubRow label="Additional" onClick={e => ck('Life — Additional', ['max_life_additional'], e)}>{fmtMult(defense.life_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Mana / Energy Shield" accent="#3060c0">
        <Row label="Max Mana" onClick={e => ck('Max Mana', ['max_mana_flat', 'max_mana_inc'], e)}>{fmtNum(defense.max_mana)}</Row>
        {defense.mana_flat > 0 && <SubRow label="Flat Added" onClick={e => ck('Mana — Flat Added', ['max_mana_flat'], e)}>{fmtNum(defense.mana_flat)}</SubRow>}
        {defense.mana_inc !== 0 && <SubRow label="Increased" onClick={e => ck('Mana — Increased', ['max_mana_inc'], e)}>{fmtPct(defense.mana_inc)}</SubRow>}
        {defense.max_energy_shield > 0 && <>
          <Row label="Max Energy Shield" onClick={e => ck('Max Energy Shield', ['max_energy_shield_flat', 'energy_shield_gear_flat', 'max_energy_shield_inc', 'energy_shield_gear_inc'], e)}>{fmtNum(defense.max_energy_shield)}</Row>
          {defense.es_flat > 0 && <SubRow label="Flat Added" onClick={e => ck('Energy Shield — Flat Added', ['max_energy_shield_flat', 'energy_shield_gear_flat'], e)}>{fmtNum(defense.es_flat)}</SubRow>}
          {defense.es_inc !== 0 && <SubRow label="Increased" onClick={e => ck('Energy Shield — Increased', ['max_energy_shield_inc', 'energy_shield_gear_inc'], e)}>{fmtPct(defense.es_inc)}</SubRow>}
        </>}
      </StatPanel>

      <StatPanel title="Resistances" accent="#7030b0">
        <Row label="Fire" onClick={e => ck('Fire Resistance', ['fire_resistance', 'elemental_resistance'], e)}>{fmtResistValue(defense.fire_resist, defense.fire_resist_raw)}</Row>
        <Row label="Cold" onClick={e => ck('Cold Resistance', ['cold_resistance', 'elemental_resistance'], e)}>{fmtResistValue(defense.cold_resist, defense.cold_resist_raw)}</Row>
        <Row label="Lightning" onClick={e => ck('Lightning Resistance', ['lightning_resistance', 'elemental_resistance'], e)}>{fmtResistValue(defense.lightning_resist, defense.lightning_resist_raw)}</Row>
        <Row label="Erosion" onClick={e => ck('Erosion Resistance', ['erosion_resistance'], e)}>{fmtResistValue(defense.erosion_resist, defense.erosion_resist_raw)}</Row>
      </StatPanel>

      <StatPanel title="Armour &amp; Evasion" accent="#308060">
        <Row label="Armour" onClick={e => ck('Armour', ['armor_flat', 'armor_gear_flat', 'armor_inc', 'armor_gear_inc', 'defense_inc', 'armor_additional'], e)}>{fmtNum(defense.armor)}</Row>
        {defense.armor_flat > 0 && <SubRow label="Flat Added" onClick={e => ck('Armour — Flat Added', ['armor_flat', 'armor_gear_flat'], e)}>{fmtNum(defense.armor_flat)}</SubRow>}
        {defense.armor_inc !== 0 && <SubRow label="Increased" onClick={e => ck('Armour — Increased', ['armor_inc', 'armor_gear_inc', 'defense_inc'], e)}>{fmtPct(defense.armor_inc)}</SubRow>}
        {defense.armor_additional !== 0 && <SubRow label="Additional" onClick={e => ck('Armour — Additional', ['armor_additional'], e)}>{fmtMult(defense.armor_additional)}</SubRow>}
        <Row label="Evasion" onClick={e => ck('Evasion', ['evasion_flat', 'evasion_gear_flat', 'evasion_inc', 'evasion_gear_inc', 'defense_inc', 'evasion_additional'], e)}>{fmtNum(defense.evasion)}</Row>
        {defense.evasion_flat > 0 && <SubRow label="Flat Added" onClick={e => ck('Evasion — Flat Added', ['evasion_flat', 'evasion_gear_flat'], e)}>{fmtNum(defense.evasion_flat)}</SubRow>}
        {defense.evasion_inc !== 0 && <SubRow label="Increased" onClick={e => ck('Evasion — Increased', ['evasion_inc', 'evasion_gear_inc', 'defense_inc'], e)}>{fmtPct(defense.evasion_inc)}</SubRow>}
        {defense.evasion_additional !== 0 && <SubRow label="Additional" onClick={e => ck('Evasion — Additional', ['evasion_additional'], e)}>{fmtMult(defense.evasion_additional)}</SubRow>}
      </StatPanel>

      <StatPanel title="Utility" accent="#505050">
        <Row label="Movement Speed" labelColor="#444">— NYI</Row>
        <Row label="Blessing Uptime" labelColor="#444">— NYI</Row>
      </StatPanel>
    </>
  )
}

// ── Root ──────────────────────────────────────────────────────────────────────

export default function PlayerStatsScreen() {
  const computedStats = useBuildStore(s => s.computedStats)
  const skills = useBuildStore(s => s.skills)
  const gear = useBuildStore(s => s.gear)
  const [selectedSlot, setSelectedSlot] = useState(1)
  const [sourcePopup, setSourcePopup] = useState<{ title: string; sources: StatSource[]; x: number; y: number } | null>(null)

  const offense = (computedStats.offense ?? null) as OffenseResult | null
  const defense = (computedStats.defense ?? null) as DefenseResult | null
  const statMap = (computedStats.stats ?? {}) as Record<string, StatEntry>

  const shownOffense = selectedSlot === 1 ? offense : null

  const handleCellClick: CellClickHandler = (title, keys, e) => {
    const sources = collectSources(keys, statMap)
    setSourcePopup({ title, sources, x: e.clientX, y: e.clientY })
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, height: '100%', overflowY: 'auto', padding: '16px 20px', boxSizing: 'border-box' }}>
      {/* Left lane — skill offense */}
      <div style={{ flex: '41', minWidth: '460px', display: 'flex', flexDirection: 'column' }}>
        <SkillSelector skills={skills} selected={selectedSlot} onSelect={setSelectedSlot} />
        {selectedSlot !== 1 && (
          <div style={{ fontSize: 12, color: '#555', marginBottom: 8 }}>
            Full offense calculation available for Main slot only.
          </div>
        )}
        <OffensePanels offense={shownOffense} onCellClick={handleCellClick} statMap={statMap} />
      </div>

      {/* Right lane — defense + utility */}
      <div style={{ flex: '59', minWidth: '200px', display: 'flex', flexDirection: 'column' }}>
        <DefensePanels defense={defense} onCellClick={handleCellClick} />
      </div>
      {sourcePopup && (
        <SourcePopup
          title={sourcePopup.title}
          sources={sourcePopup.sources}
          x={sourcePopup.x}
          y={sourcePopup.y}
          gear={gear}
          onClose={() => setSourcePopup(null)}
        />
      )}
    </div>
  )
}
