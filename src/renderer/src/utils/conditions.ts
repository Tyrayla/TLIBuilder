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
// Character level is now driven solely by the `level` condition (no separate skills-screen control).
// Defaults to 90 when unset (e.g. older builds whose conditionState predates the condition).
export function characterLevelFrom(conditionState: Record<string, number | boolean | string>): number {
  const v = conditionState?.['level']
  return typeof v === 'number' && v > 0 ? Math.round(v) : 90
}

export function buildDefaultConditionState(
  defs: ConditionDef[],
): Record<string, number | boolean | string> {
  const state: Record<string, number | boolean | string> = {}
  for (const def of defs) {
    if (def.value_type === 'boolean') state[def.key] = def.default_bool ?? false
    else if (def.value_type === 'enum') state[def.key] = def.default_enum ?? (def.enum_values?.[0] ?? '')
    else state[def.key] = def.default_value ?? 0
  }
  return state
}
