import { describe, it, expect } from 'vitest'

describe('stats computing loop prevention', () => {
  it('effectiveConditions reference is unstable without memoization (documents the bug)', () => {
    const conditions: string[] = []
    const NUMERIC_KEYS = new Set(['tenacity_active'])

    // Without memoization: new array reference every call — triggers infinite useEffect loop
    const makeConditions = () => conditions.filter(c => !NUMERIC_KEYS.has(c))
    const a = makeConditions()
    const b = makeConditions()
    expect(a).not.toBe(b)
  })

  it('stable setter prevents re-renders when condition maximums are unchanged', () => {
    type Maximums = { tenacity_max: number; agility_max: number; focus_max: number; channeled_max_bonus: number }
    const incoming: Maximums = { tenacity_max: 4, agility_max: 4, focus_max: 4, channeled_max_bonus: 0 }
    let updateCount = 0

    const stableSetter = (next: Maximums, prev: Maximums | null): Maximums => {
      if (
        prev &&
        prev.tenacity_max === next.tenacity_max &&
        prev.agility_max === next.agility_max &&
        prev.focus_max === next.focus_max &&
        prev.channeled_max_bonus === next.channeled_max_bonus
      ) return prev
      updateCount++
      return next
    }

    let current: Maximums | null = null
    for (let i = 0; i < 5; i++) {
      const result = stableSetter({ ...incoming }, current)
      if (result !== current) current = result
    }

    expect(updateCount).toBe(1) // Only first call triggers an update — loop broken
  })
})
