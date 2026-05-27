import type { ConditionDef } from '../api/client'

// Migrates old split conditions list + conditionValues dict → unified conditionState map.
// Used when loading builds saved before the conditionState unification (SCHEMA_VERSION < 2).
export function migrateOldConditions(
  conditions?: string[] | null,
  conditionValues?: Record<string, number> | null,
): Record<string, number | boolean> {
  const state: Record<string, number | boolean> = {}
  for (const k of conditions ?? []) state[k] = true
  for (const [k, v] of Object.entries(conditionValues ?? {})) state[k] = Number(v)
  return state
}

// Builds the default conditionState from condition definitions.
export function buildDefaultConditionState(
  defs: ConditionDef[],
): Record<string, number | boolean> {
  const state: Record<string, number | boolean> = {}
  for (const def of defs) {
    state[def.key] = def.value_type === 'boolean'
      ? (def.default_bool ?? false)
      : (def.default_value ?? 0)
  }
  return state
}
