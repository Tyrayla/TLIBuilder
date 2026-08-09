import { describe, it, expect } from 'vitest'
import { buildMemoryEffects, memoryTraitLevel, deriveTraitSlotLevels, waxBaseStat,
  type CreatedHeroMemory, type MemorySlotSelection } from '../api/client'

// Phase B (in-game-verified): memory→trait-level SET formula, Wax & Wane ×1.3 base stat, revival-mod emission,
// and exclusion of the "+N to Hero Trait Level" fixed mod from DPS effects.

const sel = (modifier: string, rolledValue: number | null = null, tier = 1): MemorySlotSelection =>
  ({ modifier, tier, rolledValue })
const mem = (over: Partial<CreatedHeroMemory>): CreatedHeroMemory => ({
  id: 'm', memoryType: 'origin', rarity: 'epic', baseStat: null,
  fixedAffixes: [null, null], randomAffixes: [null, null], ...over,
} as CreatedHeroMemory)

describe('memoryTraitLevel (SET, clamped 1..5)', () => {
  it('unleveled memory → 1', () => expect(memoryTraitLevel(mem({ level: 1 }))).toBe(1))
  it('+2 fixed at level 1 → 3', () =>
    expect(memoryTraitLevel(mem({ level: 1, fixedAffixes: [sel('+2 to Hero Trait Level'), null] }))).toBe(3))
  it('lv50 ultimate + 2 fixed → 5 (clamped)', () =>
    expect(memoryTraitLevel(mem({ rarity: 'ultimate', level: 50, fixedAffixes: [sel('+2 to Hero Trait Level'), null] }))).toBe(5))
  it('epic max (40) + 2 fixed → 4', () =>
    expect(memoryTraitLevel(mem({ rarity: 'epic', level: 40, fixedAffixes: [sel('+2 to Hero Trait Level'), null] }))).toBe(4))
  it('defaults level to the rarity max when undefined (ultimate → lv50 → +3)', () =>
    expect(memoryTraitLevel(mem({ rarity: 'ultimate' }))).toBe(3))
})

describe('deriveTraitSlotLevels', () => {
  it('sets slots 1-3 from memories, 0 for an empty slot, and preserves base [0]', () => {
    const origin = mem({ memoryType: 'origin', rarity: 'epic', level: 40 })          // 1 + 1(≥30) = 2
    const progress = mem({ memoryType: 'progress', rarity: 'ultimate', level: 50, fixedAffixes: [sel('+2 to Hero Trait Level'), null] }) // 5
    expect(deriveTraitSlotLevels([origin, null, progress], [3, 1, 1, 1])).toEqual([3, 2, 0, 5])
  })
})

describe('waxBaseStat (shared by the preview card AND the engine effect)', () => {
  it('×1.3 on a rolled value (rounded)', () =>
    expect(waxBaseStat(sel('+(50–100) Dexterity', 90)).rolledValue).toBe(117))
  it('×1.3 on a leading text value when there is no rolled value', () =>
    expect(waxBaseStat(sel('+90 Dexterity')).modifier).toBe('+117 Dexterity'))
})

describe('buildMemoryEffects', () => {
  it('applies Wax & Wane ×1.3 to the base stat on a revived memory', () => {
    const m = mem({ revived: true, waxAndWane: true, baseStat: sel('+(50–100) Dexterity', 90) })
    expect(buildMemoryEffects([m]).some(e => e.text === '+117 Dexterity')).toBe(true)
  })
  it('does NOT wax when not revived', () => {
    const m = mem({ revived: false, waxAndWane: true, baseStat: sel('+(50–100) Dexterity', 90) })
    expect(buildMemoryEffects([m]).some(e => e.text === '+90 Dexterity')).toBe(true)
  })
  it('emits the revival mod on a revived memory', () => {
    const m = mem({ revived: true, revivalMod: sel('+10 % Damage') })
    expect(buildMemoryEffects([m]).some(e => e.text.includes('Damage'))).toBe(true)
  })
  it('does not emit the revival mod when not revived', () => {
    const m = mem({ revived: false, revivalMod: sel('+10 % Damage') })
    expect(buildMemoryEffects([m]).some(e => e.text.includes('Damage'))).toBe(false)
  })
  it('excludes the "+N to Hero Trait Level" fixed mod but keeps a normal fixed affix', () => {
    const m = mem({ fixedAffixes: [sel('+2 to Hero Trait Level'), sel('+(10–20) % Max Life', 15)] })
    const fx = buildMemoryEffects([m])
    expect(fx.some(e => e.text.includes('Hero Trait Level'))).toBe(false)
    expect(fx.some(e => e.text.includes('Max Life'))).toBe(true)
  })
})
