import { describe, expect, it } from 'vitest'
import { minionOffenseForSlot } from '../utils/minionOffense'

describe('minion offense slot lookup', () => {
  it('selects the matching slot when duplicate Magi share an item id', () => {
    const results = {
      'summon_rock_magus@slot1': { owner_slot: 1, total_dps: 100 },
      'summon_rock_magus@slot2': { owner_slot: 2, total_dps: 240 },
    }

    expect(minionOffenseForSlot(results, 'summon_rock_magus', 2)?.total_dps).toBe(240)
  })

  it('keeps the bare item-id result for a unique Magus', () => {
    const results = { summon_rock_magus: { owner_slot: 1, total_dps: 100 } }

    expect(minionOffenseForSlot(results, 'summon_rock_magus', 1)?.total_dps).toBe(100)
  })
})
