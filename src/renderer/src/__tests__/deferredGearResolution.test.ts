import { describe, expect, it } from 'vitest'
import { resolveDeferredGear } from '../utils/deferredGearResolution'

describe('deferred shared-build gear resolution', () => {
  it('keeps resolving affixes after the build changes and preserves its dirty state', () => {
    const result = resolveDeferredGear(
      [{ name: 'Shared ring', affixes: [{ raw_text: '+100 % Skill Area', stat_key: null }] }],
      { '+100 % Skill Area': { stat_key: 'skill_area_inc', unit: '%' } },
      11,
      10,
      true,
    )

    expect(result.gear?.[0].affixes[0]).toMatchObject({
      raw_text: '+100 % Skill Area',
      stat_key: 'skill_area_inc',
      unit: '%',
    })
    expect(result.shouldRebaseline).toBe(false)
  })
})
