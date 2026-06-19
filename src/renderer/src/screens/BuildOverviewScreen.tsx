import React, { useEffect, useState } from 'react'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import type { ConditionDef, CurseConflict } from '../api/client'

// Conditions that only make sense when a specific skill is equipped (checked across ALL skill slots).
// e.g. Berserking Blade's buff stacks are meaningless unless Berserking Blade is slotted somewhere.
const SKILL_GATED_CONDITIONS: Record<string, string> = {
  berserking_blade_stacks: 'berserking_blade',
}

export default function BuildOverviewScreen() {
  const conditionsData = useReferenceStore(s => s.conditions)
  const referenceResolved = useReferenceStore(s => s.referenceResolved)
  const conditionsFailed = useReferenceStore(s => s.failedCatalogs.has('conditions'))
  const conditionMaximums = useBuildStore(s => s.computedStats.condition_maximums)
  const clampReport = useBuildStore(s => s.computedStats.clamp_report)
  const conditionState = useBuildStore(s => s.conditionState)
  const setConditionState = useBuildStore(s => s.setConditionState)
  const skills = useBuildStore(s => s.skills)
  const traitId = useBuildStore(s => s.traitId)
  // Show-all reveals every conditional (skill-gated + hero-trait for other/unselected traits). Defaults OFF
  // so the screen stays focused on what's relevant; computed/auto-derived (visible:false) stay hidden always.
  const [showAll, setShowAll] = useState(false)
  const curseConflict = useBuildStore(
    s => (s.computedStats as { curse_conflict?: CurseConflict | null }).curse_conflict) ?? null
  const warnings = useBuildStore(
    s => (s.computedStats as { warnings?: { kind: string; text: string }[] | null }).warnings) ?? null

  // Curse over-limit resolution: pick which curse(s) apply (up to the limit). Selection rides per-curse boolean
  // conditions `curse_sel_<name>` (set here, read by the engine's apply_curses). Hidden unless there's a conflict.
  const curseSelKeys = curseConflict?.active.map(a => a.sel_key) ?? []
  const curseSelected = curseSelKeys.filter(k => conditionState[k] === true)
  const applyCurseSelection = (keys: string[]) => {
    const set = new Set(keys.filter(Boolean))
    const next = { ...conditionState }
    for (const k of curseSelKeys) next[k] = set.has(k)
    setConditionState(next)
  }
  const chooseCurseAt = (i: number, v: string) => {
    const arr = [...curseSelected]
    arr[i] = v
    applyCurseSelection(arr)
  }

  // General CONFLICTS (red) — these block correct calculation until the player resolves them. Curse over-limit
  // is the only one today; future blocking conflicts append here so the banner stays one general surface.
  // (Contrast WARNINGS, which are purely informational and never gate functionality.)
  const conflicts: { title: string; detail: string }[] = []
  if (curseConflict) conflicts.push({
    title: 'Curse conflict',
    detail: `${curseConflict.active.length} curses are active but your curse limit is ${curseConflict.limit} — `
      + 'resolve it in the Curse Conflict panel below (curse damage-taken isn\'t applied until you do).',
  })

  const slottedSkillIds = new Set(skills.map(sk => sk.item_id))
  // A condition is hidden when it requires a skill that isn't equipped in any slot.
  const isSkillGatedOut = (key: string): boolean => {
    const req = SKILL_GATED_CONDITIONS[key]
    return req !== undefined && !slottedSkillIds.has(req)
  }

  // What shows in the conditionals list. Computed/auto-derived (visible:false) are never user-shown. With
  // show-all OFF: hide skill-gated conditions whose skill isn't equipped, and hero-trait conditions (those
  // carry a trait_id) unless THAT trait is the selected one. Show-all reveals everything else.
  const isCondVisible = (c: ConditionDef): boolean => {
    if (c.visible === false) return false
    if (showAll) return true
    if (isSkillGatedOut(c.key)) return false
    if (c.trait_id) return c.trait_id === traitId
    return true
  }

  const setBoolean = (key: string, value: boolean) =>
    setConditionState({ ...conditionState, [key]: value })

  const setNumeric = (key: string, value: number) =>
    setConditionState({ ...conditionState, [key]: value })

  const getNumericMax = (cond: ConditionDef): number | null => {
    if (conditionMaximums[cond.key] !== undefined) return conditionMaximums[cond.key]
    if (cond.numeric_max != null) return cond.numeric_max
    if (cond.max_base) return cond.max_base
    return null
  }

  // Active count: user-controlled booleans that are on + numerics > 0 (excludes derived + hidden)
  let activeCondCount = 0
  if (conditionsData) {
    for (const items of Object.values(conditionsData)) {
      for (const cond of items) {
        if (cond.is_derived || cond.visible === false || isSkillGatedOut(cond.key)) continue
        const val = conditionState[cond.key]
        if (cond.value_type === 'boolean' && val === true) activeCondCount++
        if (cond.value_type === 'numeric' && (val as number) > 0) activeCondCount++
      }
    }
  }

  const condCategories = conditionsData ? Object.entries(conditionsData) : []
  const loading = !referenceResolved && !conditionsData

  return (
    <div className="screen build-overview">
      <div className="cond-screen-header">
        <span>Conditionals</span>
        {activeCondCount > 0 && <span className="panel-header-badge">{activeCondCount} active</span>}
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#9aa', cursor: 'pointer', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
          <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />
          Show all
        </label>
      </div>

      {conflicts.length > 0 && (
        <div style={{
          margin: '0 0 10px', padding: '8px 12px', borderRadius: 4,
          background: 'rgba(192,57,43,0.12)', border: '1px solid #c0392b', color: '#e07a6e', fontSize: 11,
        }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>⚠ Conflicts — must resolve</div>
          {conflicts.map((c, i) => (
            <div key={i} style={{ lineHeight: 1.5, color: '#df8d82' }}><strong>{c.title}:</strong> {c.detail}</div>
          ))}
        </div>
      )}

      {warnings && warnings.length > 0 && (
        <div style={{
          margin: '0 0 10px', padding: '8px 12px', borderRadius: 4,
          background: 'rgba(176,138,74,0.12)', border: '1px solid #b08a4a', color: '#d8b45a', fontSize: 11,
        }}>
          <div style={{ fontWeight: 700, marginBottom: warnings.length ? 4 : 0 }}>⚠ Warnings</div>
          {warnings.map((w, i) => (
            <div key={i} style={{ lineHeight: 1.5, color: '#c9a865' }}>• {w.text}</div>
          ))}
        </div>
      )}

      {loading && <div className="panel-empty">Loading…</div>}
      {referenceResolved && conditionsFailed && (
        <div className="panel-empty" style={{ color: '#ff6b6b' }}>Couldn't load condition data — restart to retry.</div>
      )}

      {!loading && !conditionsFailed && (
        <div className="cond-grid">
          <div className="cond-masonry">
          {curseConflict && (
            <div className="cond-card" style={{ border: '1px solid #c0392b' }}>
              <div className="cond-card-header" style={{ color: '#e07a6e' }}>⚠ Curse Conflict</div>
              <div className="cond-card-body">
                <div style={{ fontSize: 10.5, color: '#cf7d72', lineHeight: 1.45, marginBottom: 8 }}>
                  Limit {curseConflict.limit}. Select which {curseConflict.limit === 1 ? 'curse applies' : `${curseConflict.limit} curses apply`} (rest suppressed):
                </div>
                {Array.from({ length: curseConflict.limit }).map((_, i) => (
                  <select
                    key={i}
                    className="cond-stack-input"
                    style={{ width: '100%', marginBottom: 6 }}
                    value={curseSelected[i] ?? ''}
                    onChange={e => chooseCurseAt(i, e.target.value)}
                  >
                    <option value="">— None —</option>
                    {curseConflict.active
                      .filter(a => a.sel_key === curseSelected[i] || !curseSelected.includes(a.sel_key))
                      .map(a => <option key={a.sel_key} value={a.sel_key}>{a.name} ({a.source})</option>)}
                  </select>
                ))}
              </div>
            </div>
          )}
          {condCategories.map(([cat, items]) => {
            const visibleItems = items.filter(isCondVisible)
            if (visibleItems.length === 0) return null
            return (
              <div key={cat} className="cond-card">
                <div className="cond-card-header">{cat}</div>
                <div className="cond-card-body">
                  {visibleItems.map(cond => {
                    const isComputed = cond.source === 'computed_stat'
                    if (cond.value_type === 'numeric') {
                      if (isComputed) {
                        const val = (conditionState[cond.key] as number) ?? 0
                        return (
                          <div key={cond.key} className="cond-item cond-item--derived">
                            <span className="cond-label cond-label--derived">{cond.label}</span>
                            <span className="cond-derived-hint">{val}{cond.unit ? ` ${cond.unit}` : ''}</span>
                          </div>
                        )
                      }
                      return <NumericConditionRow
                        key={cond.key}
                        cond={cond}
                        // Unset → the condition's own default (e.g. Character Level 90), not a bare 0.
                        value={(conditionState[cond.key] as number) ?? cond.default_value ?? 0}
                        max={getNumericMax(cond)}
                        clamp={clampReport[cond.key]}
                        onChange={v => setNumeric(cond.key, v)}
                      />
                    }
                    if (cond.is_derived) {
                      // Auto-derived from corresponding stacks condition — read-only indicator
                      const stackKey = cond.key.replace('_active', '_stacks')
                      const isActive = ((conditionState[stackKey] as number) ?? 0) > 0
                      return (
                        <div key={cond.key} className="cond-item cond-item--derived">
                          <span className={`cond-derived-dot ${isActive ? 'cond-derived-dot--on' : ''}`} />
                          <span className="cond-label cond-label--derived">{cond.label}</span>
                          <span className="cond-derived-hint">{isActive ? 'active' : 'inactive'}</span>
                        </div>
                      )
                    }
                    // Regular boolean — user-togglable checkbox
                    return (
                      <label key={cond.key} className="cond-item">
                        <input
                          type="checkbox"
                          className="cond-check"
                          checked={conditionState[cond.key] === true}
                          onChange={e => setBoolean(cond.key, e.target.checked)}
                        />
                        <span className="cond-label">{cond.label}</span>
                      </label>
                    )
                  })}
                </div>
              </div>
            )
          })}
          </div>
        </div>
      )}
    </div>
  )
}

interface NumericRowProps {
  cond: ConditionDef
  value: number
  max: number | null
  clamp: { requested: number; applied: number } | undefined
  onChange: (v: number) => void
}

function NumericConditionRow({ cond, value, max, clamp, onChange }: NumericRowProps) {
  const min = cond.numeric_min ?? 0
  // The value an emptied field falls back to: the condition's own default (not a hardcoded 0).
  const def = cond.default_value ?? min
  const [raw, setRaw] = useState(String(value))

  useEffect(() => { setRaw(String(value)) }, [value])

  const commit = (str: string) => {
    // Cleared input → reset to the condition's default value, not the previous value or a hardcoded 0.
    if (str.trim() === '') { onChange(def); setRaw(String(def)); return }
    const n = parseFloat(str)
    if (isNaN(n)) { setRaw(String(value)); return }
    const clamped = max !== null ? Math.min(Math.max(n, min), max) : Math.max(n, min)
    onChange(clamped)
    setRaw(String(clamped))
  }

  return (
    <div className="cond-stack-row">
      <span className="cond-stack-label">{cond.label}</span>
      <div className="cond-stack-controls">
        <input
          type="number"
          className="cond-stack-input"
          value={raw}
          min={min}
          max={max ?? undefined}
          onChange={e => setRaw(e.target.value)}
          onBlur={e => commit(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') commit((e.target as HTMLInputElement).value) }}
        />
        {max !== null && <span className="cond-stack-max">/ {max}</span>}
        {cond.unit && <span style={{ fontSize: 10, color: '#555577', marginLeft: 2 }}>{cond.unit}</span>}
      </div>
      {clamp && (
        <div style={{ fontSize: 10, color: '#ff9800', padding: '2px 12px 4px' }}>
          ⚠ capped at {clamp.applied}
        </div>
      )}
    </div>
  )
}
