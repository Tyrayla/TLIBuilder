import { describe, it, expect } from 'vitest'
import { buildMemoryEffects, scaleSelValue, memoryRangeCount, memoryRangeBounds,
  type CreatedHeroMemory, type MemorySlotSelection } from '../api/client'
import { resolveMemoryEffect } from '../components/HeroTraitShared'

// Multi-range combo affix: two INDEPENDENT rolls on one line (owner-confirmed they roll separately in-game).
// rolledValues holds one value per "(lo–hi)" range in order; a null entry defaults to that range's max.
const COMBO = '+(10–12) % additional Attack and Cast Speed for Combo Starters +(31–40) % Critical Strike Damage for Combo Finishers'
const mem = (over: Partial<CreatedHeroMemory>): CreatedHeroMemory => ({
  id: 'm', memoryType: 'origin', rarity: 'ultimate', baseStat: null,
  fixedAffixes: [null, null], randomAffixes: [null, null], ...over,
} as CreatedHeroMemory)

describe('memoryRangeCount / memoryRangeBounds', () => {
  it('counts the ranges on a combo line', () => expect(memoryRangeCount(COMBO)).toBe(2))
  it('single-range affix → 1', () => expect(memoryRangeCount('+(20–30) % Damage')).toBe(1))
  it('extracts each range bounds in order', () =>
    expect(memoryRangeBounds(COMBO)).toEqual([{ min: 10, max: 12 }, { min: 31, max: 40 }]))
})

describe('multi-range combo affix resolution', () => {
  it('resolveMemoryEffect fills each range independently from rolledValues', () => {
    const sel: MemorySlotSelection = { modifier: COMBO, tier: 0, rolledValue: null, rolledValues: [11, 35] }
    expect(resolveMemoryEffect(sel)).toBe(
      '+11 % additional Attack and Cast Speed for Combo Starters +35 % Critical Strike Damage for Combo Finishers')
  })

  it('a null entry defaults to that range max (best roll)', () => {
    const sel: MemorySlotSelection = { modifier: COMBO, tier: 0, rolledValue: null, rolledValues: [null, 33] }
    expect(resolveMemoryEffect(sel)).toBe(
      '+12 % additional Attack and Cast Speed for Combo Starters +33 % Critical Strike Damage for Combo Finishers')
  })

  it('buildMemoryEffects emits the two-value text (engine payload)', () => {
    const m = mem({ randomAffixes: [{ modifier: COMBO, tier: 0, rolledValue: null, rolledValues: [10, 40] }, null] })
    const texts = buildMemoryEffects([m]).map(e => e.text)
    expect(texts).toContain(
      '+10 % additional Attack and Cast Speed for Combo Starters +40 % Critical Strike Damage for Combo Finishers')
  })

  it('scaleSelValue scales each independent roll (base-slot penalty)', () => {
    const scaled = scaleSelValue({ modifier: COMBO, tier: 0, rolledValue: null, rolledValues: [10, 40] }, 0.5)
    expect(scaled.rolledValues).toEqual([5, 20])
  })

  it('single-range affix is unaffected (rolledValue path)', () => {
    expect(resolveMemoryEffect({ modifier: '+(20–30) % Damage', tier: 1, rolledValue: 25 })).toBe('+25 % Damage')
  })
})
