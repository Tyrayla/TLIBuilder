import type { ConditionValues, ConditionMaximums } from '../api/client'

export const NUMERIC_CONDITION_KEYS = new Set([
  'tenacity_active', 'agility_active', 'focus_active', 'channeled_not_capped',
])

export function deriveNumericConditions(
  values: ConditionValues,
  maximums: ConditionMaximums | null,
): string[] {
  const derived: string[] = []
  if (values.tenacity_stacks > 0) derived.push('tenacity_active')
  if (values.agility_stacks > 0) derived.push('agility_active')
  if (values.focus_stacks > 0) derived.push('focus_active')
  const channeledMax = values.channeled_base_max + (maximums?.channeled_max_bonus ?? 0)
  if (channeledMax > 0 && values.channeled_stacks < channeledMax) derived.push('channeled_not_capped')
  return derived
}

export function effectiveConditionsFrom(
  conditions: string[],
  conditionValues: ConditionValues,
): string[] {
  return [
    ...conditions.filter(c => !NUMERIC_CONDITION_KEYS.has(c)),
    ...deriveNumericConditions(conditionValues, null),
  ]
}
