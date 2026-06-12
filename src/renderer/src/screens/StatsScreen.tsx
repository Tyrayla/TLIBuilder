import React from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { StatEntry, StatSource, TargetStats } from '../api/client'
import { useBuildStore } from '../store/buildStore'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'

const CATEGORY_ORDER = [
  'Character',
  'Attributes', 'Generic', 'Attack', 'Spell', 'Melee', 'Area', 'Projectile',
  'Minion', 'Sentry', 'Spirit Magi', 'Physical', 'Lightning', 'Cold', 'Fire',
  'Erosion', 'Elemental', 'Ailments', 'Steep Strike', 'Cast Speed', 'Attack Speed',
  'Critical Strike', 'Life', 'Mana', 'Energy Shield', 'Defence', 'Defense',
  'Damage Taken', 'Buffs', 'Utility', 'Gear',
]

function formatStatValue(total: number, unit: string, raw = false): string {
  if (unit === '%') {
    const pct = Math.round(total * 100)
    return pct >= 0 ? `+${pct}%` : `${pct}%`
  }
  const rounded = Math.round(total * 1000) / 1000
  if (raw) return String(Math.round(total))
  return rounded >= 0 ? `+${rounded}` : `${rounded}`
}

interface GroupedSource { text: string; label: string; amount: number; count: number }

function groupSources(sources: StatSource[]): GroupedSource[] {
  const out: GroupedSource[] = []
  for (const src of sources) {
    const match = out.find(g => g.text === src.text && g.label === src.label)
    if (match) {
      match.count += src.points ?? 1
    } else {
      out.push({ text: src.text, label: src.label, amount: src.amount, count: src.points ?? 1 })
    }
  }
  return out
}

function shortenLabel(label: string): string {
  if (label.startsWith('Slate · ')) return label
  const parts = label.split(' ')
  return parts.length > 2 ? parts.slice(-2).join(' ') : label
}

// A clickable stat row. Clicking opens an interactive, dismissible source-breakdown popover
// (element-anchored) via the shared primitive — outside-click / Escape closes it.
function StatRow({ entry }: { entry: StatEntry }) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right', trigger: 'click', interactive: true })
  return (
    <>
      <button {...tip.triggerProps} className={`stat-sheet-row${tip.open ? ' selected' : ''}`}>
        <span className="stat-sheet-row-name">{entry.display_name}</span>
        <span className="stat-sheet-row-value">{formatStatValue(entry.total, entry.unit)}</span>
      </button>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--stat" {...tip.floatingProps}>
            <div className="stat-tooltip-header">
              <span className="stat-tooltip-name">{entry.display_name}</span>
              <span className="stat-tooltip-total">{formatStatValue(entry.total, entry.unit)}</span>
            </div>
            <div className="stat-tooltip-list">
              {groupSources(entry.sources).map((g, i) => (
                <div key={i} className="stat-tooltip-entry">
                  <span className="stat-tooltip-entry-value">
                    {g.text || formatStatValue(g.amount, entry.unit)}
                    {g.count > 1 && <span className="stat-tooltip-entry-count"> ×{g.count}</span>}
                  </span>
                  <span className="stat-tooltip-entry-source">{shortenLabel(g.label)}</span>
                </div>
              ))}
            </div>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// Calculation-target (dummy) defenses: each row shows the base damage-reduction and the effective value
// after this build's penetration. A negative effective value means over-penetration → amplified damage.
function pctReduction(x: number): string {
  return `${Math.round(x * 100)}%`
}

function TargetCard({ target }: { target: TargetStats }) {
  const { armor, resists, debuffs } = target
  const rows = [
    { label: 'Armor (Physical)', base: armor.base_phys, eff: armor.effective_phys },
    { label: 'Armor (Non-Physical)', base: armor.base_nonphys, eff: armor.effective_nonphys },
    { label: 'Fire Resistance', base: resists.fire?.base ?? 0, eff: resists.fire?.effective ?? 0 },
    { label: 'Cold Resistance', base: resists.cold?.base ?? 0, eff: resists.cold?.effective ?? 0 },
    { label: 'Lightning Resistance', base: resists.lightning?.base ?? 0, eff: resists.lightning?.effective ?? 0 },
    { label: 'Erosion Resistance', base: resists.erosion?.base ?? 0, eff: resists.erosion?.effective ?? 0 },
  ]
  return (
    <div className="stat-category-group">
      <div className="stat-category-header">Target (Dummy)</div>
      <div className="stat-category-entries">
        {rows.map((r) => {
          const changed = Math.abs(r.base - r.eff) > 1e-9
          const amplified = r.eff < 0
          return (
            <div key={r.label} className="stat-sheet-row stat-sheet-row--derived">
              <span className="stat-sheet-row-name">{r.label}</span>
              <span className="stat-sheet-row-value">
                {pctReduction(r.base)}
                {changed && (
                  <>
                    {' → '}
                    <span style={{ color: amplified ? '#ff8c6b' : '#8fd98f' }}>
                      {pctReduction(r.eff)}{amplified ? ' (amplified)' : ''}
                    </span>
                  </>
                )}
              </span>
            </div>
          )
        })}
        {debuffs.length > 0 && (
          <div className="stat-sheet-row stat-sheet-row--derived">
            <span className="stat-sheet-row-name">Active Debuffs</span>
            <span className="stat-sheet-row-value">{debuffs.join(', ')}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function StatsScreen() {
  const computedStats = useBuildStore((s) => s.computedStats)
  const loading = useBuildStore((s) => s.statsLoading)
  const error = useBuildStore((s) => s.statsError)
  const slots = useBuildStore((s) => s.slots)

  const groupedStats: { category: string; entries: [string, StatEntry][] }[] = []
  if (computedStats) {
    const byCategory: Record<string, [string, StatEntry][]> = {}
    for (const [key, entry] of Object.entries(computedStats.stats)) {
      if (entry.total === 0) continue
      const cat = entry.category || 'Other'
      if (!byCategory[cat]) byCategory[cat] = []
      byCategory[cat].push([key, entry])
    }
    const orderedCats = [...CATEGORY_ORDER, 'Other'].filter(c => byCategory[c]?.length)
    for (const cat of orderedCats) {
      if (byCategory[cat]) groupedStats.push({ category: cat, entries: byCategory[cat] })
    }
  }

  const filledSlots = slots.filter(Boolean).length

  return (
    <div className="screen stats-screen">
      <div className="stats-screen-header">
        <h2 className="title-accent" style={{ fontSize: 20 }}>Character Stats</h2>
      </div>

      <div className="stat-sheet">
        {loading && <div className="stat-sheet-empty">Computing stats…</div>}
        {!loading && error && (
          <div className="stat-sheet-empty" style={{ color: '#ff6b6b' }}>{error}</div>
        )}
        {!loading && !error && filledSlots > 0 && groupedStats.length === 0 && (
          <div className="stat-sheet-empty">
            No stats found. Ensure a season is active and run "Rebuild Node Type Filter" in Dev Tools.
          </div>
        )}
        {!loading && !error && computedStats?.target_stats && (
          <TargetCard target={computedStats.target_stats} />
        )}
        {groupedStats.map(({ category, entries }) => (
          <div key={category} className="stat-category-group">
            <div className="stat-category-header">{category}</div>
            <div className="stat-category-entries">
              {entries.map(([key, entry]) => {
                const isCharacter = category === 'Character'
                return isCharacter ? (
                  <div key={key} className="stat-sheet-row stat-sheet-row--derived">
                    <span className="stat-sheet-row-name">{entry.display_name}</span>
                    <span className="stat-sheet-row-value">{formatStatValue(entry.total, entry.unit, true)}</span>
                  </div>
                ) : (
                  <StatRow key={key} entry={entry} />
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
