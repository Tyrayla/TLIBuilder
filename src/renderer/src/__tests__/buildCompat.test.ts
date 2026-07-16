import { describe, it, expect } from 'vitest'

import { checkBuildCompatibility } from '../utils/buildCompat'

describe('checkBuildCompatibility', () => {
  it('does not flag a current-format build containing traitTreeAllocations as an older format', () => {
    const build = {
      name: 'Test Build',
      id: 'abc123',
      slots: ['some_slot'],
      traitTreeAllocations: ['dreambreakers_gyre', 'layered_hem'],
    }
    const issues = checkBuildCompatibility(build)
    expect(issues.some(i => i.includes('Unrecognized fields'))).toBe(false)
    expect(issues.some(i => i.includes('traitTreeAllocations'))).toBe(false)
  })

  it('still flags a genuinely unknown top-level key (regression guard for the allowlist)', () => {
    const build = {
      name: 'Test Build',
      id: 'abc123',
      slots: ['some_slot'],
      traitTreeAllocations: ['dreambreakers_gyre', 'layered_hem'],
      bogusField: 'unexpected',
    }
    const issues = checkBuildCompatibility(build)
    const unrecognized = issues.find(i => i.includes('Unrecognized fields'))
    expect(unrecognized).toBeDefined()
    expect(unrecognized).toContain('bogusField')
    expect(unrecognized).not.toContain('traitTreeAllocations')
  })
})
