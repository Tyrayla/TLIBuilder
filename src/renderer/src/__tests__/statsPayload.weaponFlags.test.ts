import { describe, it, expect, beforeEach } from 'vitest'
import { isDualWielding, countUniqueWeaponTypes, wornWeaponFlags } from '../utils/statsPayload'
import { useReferenceStore } from '../store/referenceStore'
import type { EquippedGearItem } from '../api/client'

// Minimal EquippedGearItem factory — mirrors gearPayload.test.ts's factory.
function item(partial: Partial<EquippedGearItem>): EquippedGearItem {
  return {
    item_id: 'x', name: 'X', affixes: [], customizations: [], slot: null, base_type: '',
    is_crafted: false, implicit_count: 0, corrosion_type: 'none',
    ...partial,
  } as unknown as EquippedGearItem
}

describe('countUniqueWeaponTypes — unknown base types never dropped', () => {
  beforeEach(() => useReferenceStore.setState({ craftBaseItems: [
    { item_id: 'sword_class', name: 'Swords', base_items: [{ name: 'Battlefield Longsword' }] },
  ] as unknown as never }))

  it('a base_type absent from the craft-base catalog still counts as its own distinct type', () => {
    const known = item({ slot: 'weapon1', base_type: 'Battlefield Longsword' })
    const unknown = item({ slot: 'weapon2', base_type: 'Mystery Blade' })
    expect(countUniqueWeaponTypes([known, unknown])).toBe(2)
  })

  it('two unknown weapons with the SAME base_type collapse to one distinct type', () => {
    const u1 = item({ slot: 'weapon1', base_type: 'Mystery Blade' })
    const u2 = item({ slot: 'weapon2', base_type: 'Mystery Blade' })
    expect(countUniqueWeaponTypes([u1, u2])).toBe(1)
  })

  it('two unknown weapons with DIFFERENT base_types both count (never silently merged/dropped)', () => {
    const u1 = item({ slot: 'weapon1', base_type: 'Mystery Blade' })
    const u2 = item({ slot: 'weapon2', base_type: 'Odd Cleaver' })
    expect(countUniqueWeaponTypes([u1, u2])).toBe(2)
  })
})

describe('shield in weapon2 is excluded from dual-wield + weapon-class counting', () => {
  beforeEach(() => useReferenceStore.setState({ craftBaseItems: [
    { item_id: 'one_handed_sword', name: 'Swords', base_items: [{ name: 'Battlefield Longsword' }] },
  ] as unknown as never }))

  const weapon = item({ slot: 'weapon1', base_type: 'Battlefield Longsword' })
  const shield = item({ slot: 'weapon2', base_type: "Kite Shield" })

  it('isDualWielding is false when weapon2 holds a shield', () => {
    expect(isDualWielding([weapon, shield])).toBe(false)
  })

  it('countUniqueWeaponTypes ignores the shield entirely (counts only the real weapon)', () => {
    expect(countUniqueWeaponTypes([weapon, shield])).toBe(1)
  })

  it('wornWeaponFlags reports shield:true and dualWield:false', () => {
    const flags = wornWeaponFlags([weapon, shield])
    expect(flags.shield).toBe(true)
    expect(flags.dualWield).toBe(false)
    expect(flags.oneHanded).toBe(true)
  })
})
