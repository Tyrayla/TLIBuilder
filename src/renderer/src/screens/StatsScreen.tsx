import React, { useEffect, useRef, useState } from 'react'
import { api, TreeSlot, SavedSlate, StatSheetResponse, StatEntry } from '../api/client'

const CATEGORY_ORDER = [
  'Attributes', 'Generic', 'Attack', 'Spell', 'Melee', 'Area', 'Projectile',
  'Minion', 'Sentry', 'Spirit Magi', 'Physical', 'Lightning', 'Cold', 'Fire',
  'Erosion', 'Elemental', 'Ailments', 'Steep Strike', 'Cast Speed', 'Attack Speed',
  'Critical Strike', 'Life', 'Mana', 'Energy Shield', 'Defense', 'Damage Taken',
  'Buffs', 'Gear',
]

const TOOLTIP_WIDTH = 230

function formatStatValue(total: number, unit: string): string {
  if (unit === '%') {
    const pct = Math.round(total * 100)
    return pct >= 0 ? `+${pct}%` : `${pct}%`
  }
  const rounded = Math.round(total * 1000) / 1000
  return rounded >= 0 ? `+${rounded}` : `${rounded}`
}

interface GroupedSource { text: string; label: string; amount: number; count: number }

function groupSources(sources: { text: string; label: string; amount: number }[]): GroupedSource[] {
  const out: GroupedSource[] = []
  for (const src of sources) {
    const match = out.find(g => g.text === src.text && g.label === src.label)
    if (match) match.count++
    else out.push({ text: src.text, label: src.label, amount: src.amount, count: 1 })
  }
  return out
}

function shortenLabel(label: string): string {
  const isSlate = label.startsWith('Slate — ')
  const base = isSlate ? label.slice('Slate — '.length) : label
  const parts = base.split(' ')
  // "Goddess of Hunting Micro" → "Hunting Micro", "Marksman Micro" stays as-is
  const short = parts.length > 2 ? parts.slice(-2).join(' ') : base
  return isSlate ? `Slate · ${short}` : short
}

interface Props {
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  onBack: () => void
}

export default function StatsScreen({ slots, slates, onBack }: Props) {
  const [statSheet, setStatSheet] = useState<StatSheetResponse | null>(null)
  const [selectedStat, setSelectedStat] = useState<string | null>(null)
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const tooltipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (slots.every(s => !s)) { setStatSheet(null); return }
    setLoading(true)
    setError('')
    api.engineStats({ slots, slates })
      .then(setStatSheet)
      .catch(() => setError('Failed to load stats. Check that a season is active and the node type filter has been built.'))
      .finally(() => setLoading(false))
  }, [slots, slates])

  useEffect(() => {
    if (!selectedStat) return
    const handler = (e: MouseEvent) => {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target as Node)) {
        setSelectedStat(null)
        setTooltipPos(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [selectedStat])

  const groupedStats: { category: string; entries: [string, StatEntry][] }[] = []
  if (statSheet) {
    const byCategory: Record<string, [string, StatEntry][]> = {}
    for (const [key, entry] of Object.entries(statSheet.stats)) {
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

  const selectedEntry = selectedStat && statSheet ? statSheet.stats[selectedStat] : null
  const filledSlots = slots.filter(Boolean).length

  function handleStatClick(e: React.MouseEvent, key: string) {
    if (selectedStat === key) {
      setSelectedStat(null)
      setTooltipPos(null)
    } else {
      setSelectedStat(key)
      setTooltipPos({ x: e.clientX, y: e.clientY })
    }
  }

  const tooltipStyle = tooltipPos ? {
    left: Math.min(tooltipPos.x + 16, window.innerWidth - TOOLTIP_WIDTH - 8),
    top: Math.min(tooltipPos.y - 10, window.innerHeight - 320),
  } : {}

  return (
    <div className="screen stats-screen">
      <div className="overview-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <h2 className="title-accent" style={{ fontSize: 20 }}>Character Stats</h2>
        <div style={{ width: 100 }} />
      </div>

      <div className="stat-sheet">
        {loading && <div className="stat-sheet-empty">Computing stats…</div>}
        {!loading && filledSlots === 0 && (
          <div className="stat-sheet-empty">No talent trees selected. Add trees to see stats.</div>
        )}
        {!loading && error && (
          <div className="stat-sheet-empty" style={{ color: '#ff6b6b' }}>{error}</div>
        )}
        {!loading && !error && filledSlots > 0 && groupedStats.length === 0 && (
          <div className="stat-sheet-empty">
            No stats found. Ensure a season is active and run "Rebuild Node Type Filter" in Dev Tools.
          </div>
        )}
        {groupedStats.map(({ category, entries }) => (
          <div key={category} className="stat-category-group">
            <div className="stat-category-header">{category}</div>
            {entries.map(([key, entry]) => (
              <button
                key={key}
                className={`stat-sheet-row${selectedStat === key ? ' selected' : ''}`}
                onClick={e => handleStatClick(e, key)}
              >
                <span className="stat-sheet-row-name">{entry.display_name}</span>
                <span className="stat-sheet-row-value">{formatStatValue(entry.total, entry.unit)}</span>
              </button>
            ))}
          </div>
        ))}
      </div>

      {selectedStat && selectedEntry && tooltipPos && (
        <div className="stat-tooltip" ref={tooltipRef} style={tooltipStyle}>
          <div className="stat-tooltip-header">
            <span className="stat-tooltip-name">{selectedEntry.display_name}</span>
            <span className="stat-tooltip-total">{formatStatValue(selectedEntry.total, selectedEntry.unit)}</span>
          </div>
          <div className="stat-tooltip-list">
            {groupSources(selectedEntry.sources).map((g, i) => (
              <div key={i} className="stat-tooltip-entry">
                <span className="stat-tooltip-entry-value">
                  {g.text || formatStatValue(g.amount, selectedEntry.unit)}
                  {g.count > 1 && <span className="stat-tooltip-entry-count"> ×{g.count}</span>}
                </span>
                <span className="stat-tooltip-entry-source">{shortenLabel(g.label)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
