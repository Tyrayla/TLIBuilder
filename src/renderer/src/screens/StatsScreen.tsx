import React, { useEffect, useRef, useState } from 'react'
import { api, TreeSlot, SavedSlate, StatSheetResponse, StatEntry } from '../api/client'

const CATEGORY_ORDER = [
  'Attributes', 'Generic', 'Attack', 'Spell', 'Melee', 'Area', 'Projectile',
  'Minion', 'Sentry', 'Spirit Magi', 'Physical', 'Lightning', 'Cold', 'Fire',
  'Erosion', 'Elemental', 'Ailments', 'Steep Strike', 'Cast Speed', 'Attack Speed',
  'Critical Strike', 'Life', 'Mana', 'Energy Shield', 'Defense', 'Damage Taken',
  'Buffs', 'Gear',
]

function formatStatValue(total: number, unit: string): string {
  if (unit === '%') {
    const pct = Math.round(total * 100)
    return pct >= 0 ? `+${pct}%` : `${pct}%`
  }
  const rounded = Math.round(total * 1000) / 1000
  return rounded >= 0 ? `+${rounded}` : `${rounded}`
}

interface Props {
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  onBack: () => void
}

export default function StatsScreen({ slots, slates, onBack }: Props) {
  const [statSheet, setStatSheet] = useState<StatSheetResponse | null>(null)
  const [selectedStat, setSelectedStat] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const drawerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (slots.every(s => !s)) {
      setStatSheet(null)
      return
    }
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
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        setSelectedStat(null)
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
      if (byCategory[cat]) {
        groupedStats.push({ category: cat, entries: byCategory[cat] })
      }
    }
  }

  const selectedEntry = selectedStat && statSheet ? statSheet.stats[selectedStat] : null
  const filledSlots = slots.filter(Boolean).length

  return (
    <div className="screen stats-screen">
      <div className="overview-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <h2 className="title-accent" style={{ fontSize: 20 }}>Character Stats</h2>
        <div style={{ width: 100 }} />
      </div>

      <div className="stat-sheet">
        {loading && (
          <div className="stat-sheet-empty">Computing stats…</div>
        )}
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
                className={`stat-row${selectedStat === key ? ' selected' : ''}`}
                onClick={() => setSelectedStat(selectedStat === key ? null : key)}
              >
                <span className="stat-row-name">{entry.display_name}</span>
                <span className="stat-row-value">{formatStatValue(entry.total, entry.unit)}</span>
                <span className="stat-row-chevron">›</span>
              </button>
            ))}
          </div>
        ))}
      </div>

      {selectedStat && selectedEntry && (
        <div className="source-drawer" ref={drawerRef}>
          <div className="source-drawer-header">
            <span className="source-drawer-title">{selectedEntry.display_name}</span>
            <button className="source-drawer-close" onClick={() => setSelectedStat(null)}>✕</button>
          </div>
          <div className="source-drawer-total">
            Total: {formatStatValue(selectedEntry.total, selectedEntry.unit)}
          </div>
          <div className="source-drawer-list">
            {selectedEntry.sources.map((src, i) => (
              <div key={i} className="source-entry">
                <span className="source-entry-label">{src.label}</span>
                {src.text && (
                  <span className="source-entry-text">{src.text}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
