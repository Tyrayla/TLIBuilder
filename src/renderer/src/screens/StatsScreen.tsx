import React, { useEffect, useRef, useState } from 'react'
import { api, TreeSlot, SavedSlate, StatSheetResponse, StatEntry, StatSource, EquippedGearItem, GearEngineItem, GearAffixContribution, buildEnergyContributions, CreatedHeroMemory, buildMemoryEffects, SelectedPactSpirit, buildSpiritEffects, PactSpirit } from '../api/client'

const CATEGORY_ORDER = [
  'Attributes', 'Generic', 'Attack', 'Spell', 'Melee', 'Area', 'Projectile',
  'Minion', 'Sentry', 'Spirit Magi', 'Physical', 'Lightning', 'Cold', 'Fire',
  'Erosion', 'Elemental', 'Ailments', 'Steep Strike', 'Cast Speed', 'Attack Speed',
  'Critical Strike', 'Life', 'Mana', 'Energy Shield', 'Defense', 'Damage Taken',
  'Buffs', 'Utility', 'Gear',
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

function buildGearPayload(gear: EquippedGearItem[]): GearEngineItem[] {
  return gear.filter(item => item.slot !== null).map(item => {
    const contributions: GearAffixContribution[] = []
    item.affixes.forEach((affix, affixIdx) => {
      if (affix.affix_kind === 'placeholder') return
      const hasKey = affix.stat_key || (affix.stat_keys && affix.stat_keys.length > 0)
      if (!hasKey) return
      const cust = item.customizations.find(c => c.affix_index === affixIdx)
      const slot = Array.isArray(item.slot) ? item.slot[0] ?? null : item.slot
      if (affix.affix_kind === 'numeric') {
        const rangeIdx = affix.numeric_values.findIndex(v => v.kind === 'range')
        const fixedNv = affix.numeric_values.find(v => v.kind === 'fixed')
        const unit = affix.unit ?? ''

        if (affix.min_stat_keys && affix.max_stat_keys && rangeIdx >= 0) {
          // Range-multi: min value fans out to min_stat_keys, max value fans out to max_stat_keys
          const nv = affix.numeric_values[rangeIdx]
          const minVal = cust?.chosen_values[0] ?? Math.round(nv.min ?? 0)
          const maxVal = cust?.chosen_values[1] ?? Math.round(nv.max ?? 0)
          for (const stat of affix.min_stat_keys) {
            contributions.push({ stat, display_value: minVal, unit, item_name: item.name, slot })
          }
          for (const stat of affix.max_stat_keys) {
            contributions.push({ stat, display_value: maxVal, unit, item_name: item.name, slot })
          }
        } else if (affix.dual_stat_groups && affix.dual_stat_groups.length > 0) {
          // Dual-value: each group's value_index picks a numeric value
          const rangeValues = affix.numeric_values.filter(v => v.kind === 'range')
          for (const group of affix.dual_stat_groups) {
            const nv = rangeValues[group.value_index]
            if (!nv) continue
            const val = cust?.chosen_values[group.value_index] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
            for (const stat of group.stat_keys) {
              contributions.push({ stat, display_value: val, unit, item_name: item.name, slot })
            }
          }
        } else if (affix.stat_keys && affix.stat_keys.length > 0) {
          if (affix.is_range_split && rangeIdx >= 0) {
            // Range affix → emit min value to _min stat, max value to _max stat
            const nv = affix.numeric_values[rangeIdx]
            const [minStat, maxStat] = affix.stat_keys
            const minVal = cust?.chosen_values[0] ?? Math.round(nv.min ?? 0)
            const maxVal = cust?.chosen_values[1] ?? Math.round(nv.max ?? 0)
            contributions.push({ stat: minStat, display_value: minVal, unit, item_name: item.name, slot })
            contributions.push({ stat: maxStat, display_value: maxVal, unit, item_name: item.name, slot })
          } else {
            // Multi-stat with shared display value
            let display_value: number | null = null
            if (rangeIdx >= 0) {
              const nv = affix.numeric_values[rangeIdx]
              display_value = cust?.chosen_values[rangeIdx] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
            } else if (fixedNv) {
              display_value = fixedNv.value ?? 0
            }
            if (display_value !== null) {
              for (const stat of affix.stat_keys) {
                contributions.push({ stat, display_value, unit, item_name: item.name, slot })
              }
            }
          }
        } else if (affix.stat_key) {
          let display_value: number | null = null
          if (rangeIdx >= 0) {
            const nv = affix.numeric_values[rangeIdx]
            display_value = cust?.chosen_values[rangeIdx] ?? Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
          } else if (fixedNv) {
            display_value = fixedNv.value ?? 0
          }
          if (display_value !== null) {
            contributions.push({ stat: affix.stat_key, display_value, unit, item_name: item.name, slot })
          }
        }
      }
    })
    return { contributions }
  })
}

interface Props {
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  gear?: EquippedGearItem[]
  characterLevel?: number
  hasPrism?: boolean
  effectiveConditions?: string[]
  heroMemories?: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]
  pactSpirits?: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]
}

export default function StatsScreen({
  slots, slates,
  gear = [], characterLevel = 100, hasPrism = false,
  effectiveConditions = [],
  heroMemories, pactSpirits,
}: Props) {
  const [statSheet, setStatSheet] = useState<StatSheetResponse | null>(null)
  const [selectedStat, setSelectedStat] = useState<string | null>(null)
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [allSpirits, setAllSpirits] = useState<PactSpirit[]>([])
  const tooltipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.getPactSpirits().then(res => setAllSpirits(res.spirits.filter(s => !s.affinities.includes('Drop')))).catch(() => {})
  }, [])

  useEffect(() => {
    const hasSource =
      slots.some(s => !!s) ||
      slates.some(s => s.slots?.some(sl => sl.selectedNodeId !== null)) ||
      gear.some(item => item.slot !== null)
    if (!hasSource) { setStatSheet(null); return }
    setLoading(true)
    setError('')
    api.engineStats({
      slots, slates,
      conditions: effectiveConditions,
      gear: buildGearPayload(gear),
      character: buildEnergyContributions(gear, characterLevel, hasPrism),
      memory_effects: buildMemoryEffects(heroMemories ?? [null, null, null]),
      spirit_effects: buildSpiritEffects(pactSpirits ?? [null, null, null], allSpirits),
    })
      .then(setStatSheet)
      .catch(() => setError('Failed to load stats. Check that a season is active and the node type filter has been built.'))
      .finally(() => setLoading(false))
  }, [slots, slates, effectiveConditions, gear, characterLevel, hasPrism, heroMemories, pactSpirits, allSpirits])

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
      <div className="stats-screen-header">
        <h2 className="title-accent" style={{ fontSize: 20 }}>Character Stats</h2>
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
            <div className="stat-category-entries">
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
