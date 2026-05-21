import React, { useEffect, useRef, useState } from 'react'
import { api, TreeSlot, SavedSlate, SeasonSummary, StatSheetResponse, StatEntry, StatSource, ConditionDef, ConditionValues, ConditionMaximums, EquippedGearItem, GearEngineItem, GearAffixContribution } from '../api/client'

const NUMERIC_CONDITION_KEYS = new Set(['tenacity_active', 'agility_active', 'focus_active', 'channeled_not_capped'])

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
      if (!affix.stat_key || affix.affix_kind === 'placeholder') return
      const cust = item.customizations.find(c => c.affix_index === affixIdx)
      // For numeric affixes with ranges, find the first range value and use chosen value
      // For fixed-only numeric affixes, use the fixed value directly
      if (affix.affix_kind === 'numeric') {
        let display_value: number | null = null
        const rangeIdx = affix.numeric_values.findIndex(v => v.kind === 'range')
        if (rangeIdx >= 0) {
          const nv = affix.numeric_values[rangeIdx]
          display_value = cust?.chosen_values[rangeIdx] ??
            Math.round(((nv.min ?? 0) + (nv.max ?? 0)) / 2)
        } else {
          const fixedNv = affix.numeric_values.find(v => v.kind === 'fixed')
          if (fixedNv) display_value = fixedNv.value ?? 0
        }
        if (display_value !== null) {
          contributions.push({
            stat: affix.stat_key,
            display_value,
            unit: affix.unit ?? '',
            item_name: item.name,
            slot: item.slot,
          })
        }
      }
    })
    return { contributions }
  })
}

interface Props {
  buildName: string
  buildId: string | null
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  gear: EquippedGearItem[]
  conditions: string[]
  conditionValues: ConditionValues
  conditionMaximums: ConditionMaximums | null
  effectiveConditions: string[]
  onConditionsChange: (conditions: string[]) => void
  onConditionValuesChange: (values: ConditionValues) => void
  onConditionMaximumsChange: (maximums: ConditionMaximums) => void
  onBack: () => void
  onTalentTree: () => void
  onSlates: () => void
  onGear: () => void
  onSave: (name: string) => Promise<void>
  onSaveAs: (name: string) => Promise<void>
  devMode?: boolean
  onSeasonChange?: () => void
}

type SaveMode = 'save' | 'saveas'

export default function BuildOverviewScreen({
  buildName, buildId, slots, slates, conditions, conditionValues, conditionMaximums, effectiveConditions,
  onConditionsChange, onConditionValuesChange, onConditionMaximumsChange,
  onBack, onTalentTree, onSlates, onGear, onSave, onSaveAs,
  gear = [],
  devMode = false, onSeasonChange,
}: Props) {
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveMode, setSaveMode] = useState<SaveMode>('save')
  const [saveName, setSaveName] = useState(buildName)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')

  const [seasons, setSeasons] = useState<SeasonSummary[]>([])
  const [activeSeason, setActiveSeason] = useState<string | null>(null)

  const [conditionsData, setConditionsData] = useState<Record<string, ConditionDef[]> | null>(null)

  const [statSheet, setStatSheet] = useState<StatSheetResponse | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState('')
  const [selectedStat, setSelectedStat] = useState<string | null>(null)
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | null>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!devMode) return
    api.listSeasons().then(s => {
      setSeasons(s)
      setActiveSeason(s.find(x => x.is_active)?.name ?? null)
    }).catch(() => {})
  }, [devMode])

  useEffect(() => {
    api.getConditions().then(setConditionsData).catch(() => {})
  }, [])

  useEffect(() => {
    const hasSource =
      slots.some(s => !!s) ||
      slates.some(s => s.slots?.some(sl => sl.selectedNodeId !== null)) ||
      gear.some(item => item.slot !== null)
    if (!hasSource) { setStatSheet(null); return }
    setStatsLoading(true)
    setStatsError('')
    api.engineStats({ slots, slates, conditions: effectiveConditions, gear: buildGearPayload(gear) })
      .then(res => {
        setStatSheet(res)
        if (res.condition_maximums) onConditionMaximumsChange(res.condition_maximums)
      })
      .catch(() => setStatsError('Failed to load stats.'))
      .finally(() => setStatsLoading(false))
  }, [slots, slates, effectiveConditions, gear])

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

  const handleSeasonChange = async (name: string | null) => {
    try {
      await api.setActiveSeason(name)
      setActiveSeason(name)
      setSeasons(prev => prev.map(s => ({ ...s, is_active: s.name === name })))
      onSeasonChange?.()
    } catch { /* ignore */ }
  }

  const showMsg = (msg: string) => {
    setSavedMsg(msg)
    setTimeout(() => setSavedMsg(''), 2500)
  }

  const handleSave = async () => {
    if (buildId) {
      setSaving(true)
      try {
        await onSave(buildName || 'Untitled')
        showMsg('Saved!')
      } catch { showMsg('Save failed.') }
      finally { setSaving(false) }
    } else {
      setSaveMode('save')
      setSaveName(buildName || '')
      setSaveOpen(true)
    }
  }

  const handleSaveAs = () => {
    setSaveMode('saveas')
    setSaveName(buildName || '')
    setSaveOpen(true)
  }

  const handleModalConfirm = async () => {
    const name = saveName.trim() || 'Untitled'
    setSaving(true)
    try {
      if (saveMode === 'saveas') await onSaveAs(name)
      else await onSave(name)
      setSaveOpen(false)
      showMsg('Saved!')
    } catch { showMsg('Save failed.') }
    finally { setSaving(false) }
  }

  const toggleCondition = (key: string) => {
    const next = conditions.includes(key)
      ? conditions.filter(c => c !== key)
      : [...conditions, key]
    onConditionsChange(next)
  }

  const setConditionValue = (field: keyof ConditionValues, value: number) => {
    onConditionValuesChange({ ...conditionValues, [field]: value })
  }

  const tenacityMax = conditionMaximums?.tenacity_max ?? 4
  const agilityMax  = conditionMaximums?.agility_max  ?? 4
  const focusMax    = conditionMaximums?.focus_max    ?? 4
  const channeledMax = conditionValues.channeled_base_max + (conditionMaximums?.channeled_max_bonus ?? 0)

  function handleStatClick(e: React.MouseEvent, key: string) {
    if (selectedStat === key) {
      setSelectedStat(null)
      setTooltipPos(null)
    } else {
      setSelectedStat(key)
      setTooltipPos({ x: e.clientX, y: e.clientY })
    }
  }

  const filledSlots = slots.filter(Boolean).length
  const hasAnySource =
    slots.some(s => !!s) ||
    slates.some(s => s.slots?.some(sl => sl.selectedNodeId !== null)) ||
    gear.some(item => item.slot !== null)

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
  const tooltipStyle = tooltipPos ? {
    left: Math.min(tooltipPos.x + 16, window.innerWidth - TOOLTIP_WIDTH - 8),
    top: Math.min(tooltipPos.y - 10, window.innerHeight - 320),
  } : {}

  const condCategories = conditionsData ? Object.entries(conditionsData) : []
  const numericActive =
    (conditionValues.tenacity_stacks > 0 ? 1 : 0) +
    (conditionValues.agility_stacks > 0 ? 1 : 0) +
    (conditionValues.focus_stacks > 0 ? 1 : 0) +
    (channeledMax > 0 && conditionValues.channeled_stacks < channeledMax ? 1 : 0)
  const activeCondCount = conditions.length + numericActive

  return (
    <div className="screen build-overview">
      <div className="overview-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <h2 className="title-accent" style={{ fontSize: 20 }}>{buildName || 'New Build'}</h2>
        <div className="overview-save-btns">
          <button className="btn btn-sm overview-save-btn" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button className="btn btn-sm overview-saveas-btn" onClick={handleSaveAs} disabled={saving}>
            Save As
          </button>
        </div>
      </div>

      {savedMsg && <div className="overview-saved-msg">{savedMsg}</div>}

      {devMode && seasons.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', background: '#0e0e28', borderBottom: '1px solid #2a2a4a', fontSize: 12 }}>
          <span style={{ color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>Season:</span>
          <select
            value={activeSeason ?? ''}
            onChange={e => handleSeasonChange(e.target.value || null)}
            style={{ background: '#1a1a3a', color: '#ddd', border: '1px solid #3a3a5a', borderRadius: 4, padding: '3px 8px', fontSize: 12 }}
          >
            <option value="">— Current (Python builders) —</option>
            {seasons.map(s => <option key={s.name} value={s.name}>{s.name}</option>)}
          </select>
          {activeSeason && (
            <span style={{ fontSize: 11, color: '#c0a0ff' }}>
              {seasons.find(s => s.name === activeSeason)?.trees.length ?? 0} trees loaded
            </span>
          )}
        </div>
      )}

      <div className="overview-body">
        {/* Nav column */}
        <div className="overview-nav-col">
          <button className="overview-nav-btn active" onClick={onTalentTree}>
            <span className="overview-nav-icon">🌿</span>
            <div className="overview-nav-text">
              <span className="overview-nav-label">Talent Tree</span>
              {filledSlots > 0 && <span className="overview-nav-sub">{filledSlots} / 4 slots</span>}
            </div>
          </button>
          <button className="overview-nav-btn active" onClick={onSlates}>
            <span className="overview-nav-icon">📋</span>
            <div className="overview-nav-text">
              <span className="overview-nav-label">Slates</span>
            </div>
          </button>
          <button className="overview-nav-btn active" onClick={onGear}>
            <span className="overview-nav-icon">⚔️</span>
            <div className="overview-nav-text">
              <span className="overview-nav-label">Gear</span>
            </div>
          </button>
        </div>

        {/* Conditions panel */}
        <div className="overview-panel">
          <div className="panel-header">
            Conditions
            {activeCondCount > 0 && <span className="panel-header-badge">{activeCondCount}</span>}
          </div>
          <div className="conditions-scroll">
            {condCategories.length === 0 && (
              <div className="panel-empty">Loading…</div>
            )}

            {/* Blessing stacks — numeric inputs replacing Blessings checkboxes */}
            <div className="cond-category">
              <div className="cond-category-label">Blessings</div>
              {([
                { field: 'tenacity_stacks' as const, label: 'Tenacity Stacks', max: tenacityMax },
                { field: 'agility_stacks'  as const, label: 'Agility Stacks',  max: agilityMax },
                { field: 'focus_stacks'    as const, label: 'Focus Stacks',    max: focusMax },
              ]).map(({ field, label, max }) => (
                <div key={field} className="cond-stack-row">
                  <span className="cond-stack-label">{label}</span>
                  <div className="cond-stack-controls">
                    <button
                      className="cond-stack-btn"
                      onClick={() => setConditionValue(field, Math.max(0, conditionValues[field] - 1))}
                      disabled={conditionValues[field] <= 0}
                    >−</button>
                    <span className="cond-stack-value">{conditionValues[field]}<span className="cond-stack-max">/{max}</span></span>
                    <button
                      className="cond-stack-btn"
                      onClick={() => setConditionValue(field, Math.min(max, conditionValues[field] + 1))}
                      disabled={conditionValues[field] >= max}
                    >+</button>
                  </div>
                </div>
              ))}
            </div>

            {/* Channeled stacks */}
            <div className="cond-category">
              <div className="cond-category-label">Channeled Stacks</div>
              <div className="cond-stack-row">
                <span className="cond-stack-label">Skill Base Max</span>
                <input
                  type="number"
                  className="cond-stack-input"
                  min={0}
                  max={99}
                  value={conditionValues.channeled_base_max}
                  onChange={e => setConditionValue('channeled_base_max', Math.max(0, parseInt(e.target.value) || 0))}
                />
              </div>
              {channeledMax > 0 && (
                <div className="cond-stack-row">
                  <span className="cond-stack-label">Current Stacks</span>
                  <div className="cond-stack-controls">
                    <button
                      className="cond-stack-btn"
                      onClick={() => setConditionValue('channeled_stacks', Math.max(0, conditionValues.channeled_stacks - 1))}
                      disabled={conditionValues.channeled_stacks <= 0}
                    >−</button>
                    <span className="cond-stack-value">{conditionValues.channeled_stacks}<span className="cond-stack-max">/{channeledMax}</span></span>
                    <button
                      className="cond-stack-btn"
                      onClick={() => setConditionValue('channeled_stacks', Math.min(channeledMax, conditionValues.channeled_stacks + 1))}
                      disabled={conditionValues.channeled_stacks >= channeledMax}
                    >+</button>
                  </div>
                </div>
              )}
              {channeledMax === 0 && (
                <div className="cond-stack-hint">Set skill base max above to enable</div>
              )}
            </div>

            {/* Boolean condition checkboxes — skip keys managed by numeric inputs */}
            {condCategories
              .filter(([cat]) => cat !== 'Blessings')
              .map(([cat, items]) => {
                const filtered = items.filter(c => !NUMERIC_CONDITION_KEYS.has(c.key))
                if (filtered.length === 0) return null
                return (
                  <div key={cat} className="cond-category">
                    <div className="cond-category-label">{cat}</div>
                    {filtered.map(cond => (
                      <label key={cond.key} className="cond-item">
                        <input
                          type="checkbox"
                          className="cond-check"
                          checked={conditions.includes(cond.key)}
                          onChange={() => toggleCondition(cond.key)}
                        />
                        <span className="cond-label">{cond.label}</span>
                      </label>
                    ))}
                  </div>
                )
              })}
          </div>
        </div>

        {/* Stats panel */}
        <div className="overview-panel overview-stats-panel">
          <div className="panel-header">Stats</div>
          <div className="stat-sheet">
            {statsLoading && <div className="stat-sheet-empty">Computing…</div>}
            {!statsLoading && !hasAnySource && (
              <div className="stat-sheet-empty">Nothing allocated yet.</div>
            )}
            {!statsLoading && statsError && (
              <div className="stat-sheet-empty" style={{ color: '#ff6b6b' }}>{statsError}</div>
            )}
            {!statsLoading && !statsError && hasAnySource && groupedStats.length === 0 && (
              <div className="stat-sheet-empty">No stats. Rebuild filter in Dev Tools.</div>
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
        </div>
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

      {saveOpen && (
        <div className="modal-backdrop" onClick={() => setSaveOpen(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">
              {saveMode === 'saveas' ? 'Save As New Build' : 'Name Your Build'}
            </h3>
            <input
              className="modal-input"
              type="text"
              placeholder="Enter a build name…"
              value={saveName}
              onChange={e => setSaveName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleModalConfirm()}
              autoFocus
            />
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleModalConfirm} disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button className="btn btn-danger" onClick={() => setSaveOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
