import React, { useEffect, useState } from 'react'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import type { ConditionDef } from '../api/client'

interface Props {
  conditionState: Record<string, number | boolean>
  onConditionStateChange: (state: Record<string, number | boolean>) => void
}

export default function BuildOverviewScreen({ conditionState, onConditionStateChange }: Props) {
  const conditionsData = useReferenceStore(s => s.conditions)
  const referenceResolved = useReferenceStore(s => s.referenceResolved)
  const conditionsFailed = useReferenceStore(s => s.failedCatalogs.has('conditions'))
  const conditionMaximums = useBuildStore(s => s.computedStats.condition_maximums)
  const clampReport = useBuildStore(s => s.computedStats.clamp_report)

  const setBoolean = (key: string, value: boolean) =>
    onConditionStateChange({ ...conditionState, [key]: value })

  const setNumeric = (key: string, value: number) =>
    onConditionStateChange({ ...conditionState, [key]: value })

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
        if (cond.is_derived || cond.visible === false) continue
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
      </div>

      {loading && <div className="panel-empty">Loading…</div>}
      {referenceResolved && conditionsFailed && (
        <div className="panel-empty" style={{ color: '#ff6b6b' }}>Couldn't load condition data — restart to retry.</div>
      )}

      {!loading && !conditionsFailed && (
        <div className="cond-grid">
          {condCategories.map(([cat, items]) => {
            const visibleItems = items.filter(c => c.visible !== false)
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
                        value={(conditionState[cond.key] as number) ?? 0}
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
  const [raw, setRaw] = useState(String(value))

  useEffect(() => { setRaw(String(value)) }, [value])

  const commit = (str: string) => {
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
