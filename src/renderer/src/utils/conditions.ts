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
