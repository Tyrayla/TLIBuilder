import { describe, it, expect } from 'vitest'
import { affixIdentity } from '../utils/affixIdentity'

// Parity anchor: these identities are produced by backend/engine/affix_identity.py on the real CL
// support lines (verified). If either side changes, this test (and/or the Python one) fails — keep
// affixIdentity.ts in sync with affix_identity.py so explicit-roll keys line up across the wire.
describe('affixIdentity parity with backend affix_identity', () => {
  const cases: [string, string][] = [
    ['+(13–15) % additional damage for the supported skill', 'additional damage for the supported skill'],
    ['(-16.0–-15.0) % additional damage for the supported skill', 'additional damage for the supported skill'],
    ['+(16-18) % additional damage for the supported skill', 'additional damage for the supported skill'],
    [
      '+(4.9–5.2) % additional damage for every 1 Jump(s) remaining of the supported skill (multiplies)',
      'additional damage for every jump s remaining of the supported skill multiplies',
    ],
  ]
  it.each(cases)('%s', (input, expected) => {
    expect(affixIdentity(input)).toBe(expected)
  })
})
