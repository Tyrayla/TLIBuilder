import React, { useEffect, useState } from 'react'
import { api, ConditionDef, ConditionValues, ConditionMaximums } from '../api/client'

const NUMERIC_CONDITION_KEYS = new Set(['tenacity_active', 'agility_active', 'focus_active', 'channeled_not_capped'])

interface Props {
  conditions: string[]
  conditionValues: ConditionValues
  conditionMaximums: ConditionMaximums | null
  onConditionsChange: (conditions: string[]) => void
  onConditionValuesChange: (values: ConditionValues) => void
}

export default function BuildOverviewScreen({
  conditions, conditionValues, conditionMaximums,
  onConditionsChange, onConditionValuesChange,
}: Props) {
  const [conditionsData, setConditionsData] = useState<Record<string, ConditionDef[]> | null>(null)

  useEffect(() => {
    api.getConditions().then(setConditionsData).catch(() => {})
  }, [])

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

  const numericActive =
    (conditionValues.tenacity_stacks > 0 ? 1 : 0) +
    (conditionValues.agility_stacks > 0 ? 1 : 0) +
    (conditionValues.focus_stacks > 0 ? 1 : 0) +
    (channeledMax > 0 && conditionValues.channeled_stacks < channeledMax ? 1 : 0)
  const activeCondCount = conditions.length + numericActive

  const condCategories = conditionsData ? Object.entries(conditionsData) : []
  const loading = conditionsData === null

  return (
    <div className="screen build-overview">
      <div className="cond-screen-header">
        <span>Conditionals</span>
        {activeCondCount > 0 && <span className="panel-header-badge">{activeCondCount} active</span>}
      </div>

      {loading && <div className="panel-empty">Loading…</div>}

      {!loading && (
        <div className="cond-grid">

          {/* Blessings card — stack counters */}
          <div className="cond-card">
            <div className="cond-card-header">Blessings</div>
            <div className="cond-card-body">
              {([
                { field: 'tenacity_stacks' as const, label: 'Tenacity', max: tenacityMax },
                { field: 'agility_stacks'  as const, label: 'Agility',  max: agilityMax },
                { field: 'focus_stacks'    as const, label: 'Focus',    max: focusMax },
              ]).map(({ field, label, max }) => (
                <div key={field} className="cond-stack-row">
                  <span className="cond-stack-label">{label}</span>
                  <div className="cond-stack-controls">
                    <button
                      className="cond-stack-btn"
                      onClick={() => setConditionValue(field, Math.max(0, conditionValues[field] - 1))}
                      disabled={conditionValues[field] <= 0}
                    >−</button>
                    <span className="cond-stack-value">
                      {conditionValues[field]}<span className="cond-stack-max">/{max}</span>
                    </span>
                    <button
                      className="cond-stack-btn"
                      onClick={() => setConditionValue(field, Math.min(max, conditionValues[field] + 1))}
                      disabled={conditionValues[field] >= max}
                    >+</button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Channeled Stacks card */}
          <div className="cond-card">
            <div className="cond-card-header">Channeled Stacks</div>
            <div className="cond-card-body">
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
              {channeledMax > 0 ? (
                <div className="cond-stack-row">
                  <span className="cond-stack-label">Current</span>
                  <div className="cond-stack-controls">
                    <button
                      className="cond-stack-btn"
                      onClick={() => setConditionValue('channeled_stacks', Math.max(0, conditionValues.channeled_stacks - 1))}
                      disabled={conditionValues.channeled_stacks <= 0}
                    >−</button>
                    <span className="cond-stack-value">
                      {conditionValues.channeled_stacks}<span className="cond-stack-max">/{channeledMax}</span>
                    </span>
                    <button
                      className="cond-stack-btn"
                      onClick={() => setConditionValue('channeled_stacks', Math.min(channeledMax, conditionValues.channeled_stacks + 1))}
                      disabled={conditionValues.channeled_stacks >= channeledMax}
                    >+</button>
                  </div>
                </div>
              ) : (
                <div className="cond-stack-hint">Set skill base max above to enable</div>
              )}
            </div>
          </div>

          {/* Boolean condition category cards */}
          {condCategories
            .filter(([cat]) => cat !== 'Blessings')
            .map(([cat, items]) => {
              const filtered = items.filter(c => !NUMERIC_CONDITION_KEYS.has(c.key))
              if (filtered.length === 0) return null
              return (
                <div key={cat} className="cond-card">
                  <div className="cond-card-header">{cat}</div>
                  <div className="cond-card-body">
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
                </div>
              )
            })}
        </div>
      )}
    </div>
  )
}
