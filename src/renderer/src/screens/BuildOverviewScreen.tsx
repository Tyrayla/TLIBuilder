import React from 'react'
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

  const getNumericMax = (cond: ConditionDef): number => {
    // Prefer engine-derived max (accounts for talent bonuses), fall back to static definition
    if (conditionMaximums[cond.key] !== undefined) return conditionMaximums[cond.key]
    if (cond.numeric_max != null) return cond.numeric_max
    return 99
  }

  // Active count: user-controlled booleans that are on + numerics > 0 (excludes derived)
  let activeCondCount = 0
  if (conditionsData) {
    for (const items of Object.values(conditionsData)) {
      for (const cond of items) {
        if (cond.is_derived) continue
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
            // Skip empty categories (e.g. all items filtered out)
            if (items.length === 0) return null
            return (
              <div key={cat} className="cond-card">
                <div className="cond-card-header">{cat}</div>
                <div className="cond-card-body">
                  {items.map(cond => {
                    if (cond.value_type === 'numeric') {
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
  max: number
  clamp: { requested: number; applied: number } | undefined
  onChange: (v: number) => void
}

function NumericConditionRow({ cond, value, max, clamp, onChange }: NumericRowProps) {
  const min = cond.numeric_min ?? 0
  const effectiveMax = max
  const clamped = Math.min(Math.max(value, min), effectiveMax)

  return (
    <div className="cond-stack-row">
      <span className="cond-stack-label">{cond.label}</span>
      <div className="cond-stack-controls">
        <button
          className="cond-stack-btn"
          onClick={() => onChange(Math.max(min, clamped - 1))}
          disabled={clamped <= min}
        >−</button>
        <span className="cond-stack-value">
          {clamped}
          {effectiveMax < 999 && <span className="cond-stack-max">/{effectiveMax}</span>}
          {cond.unit ? <span className="cond-stack-unit"> {cond.unit}</span> : null}
        </span>
        <button
          className="cond-stack-btn"
          onClick={() => onChange(Math.min(effectiveMax, clamped + 1))}
          disabled={clamped >= effectiveMax}
        >+</button>
      </div>
      {clamp && (
        <div className="cond-clamp-warning">
          ⚠ Capped at {clamp.applied} (entered {clamp.requested})
        </div>
      )}
    </div>
  )
}
