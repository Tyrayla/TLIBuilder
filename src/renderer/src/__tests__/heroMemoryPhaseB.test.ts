import { describe, it, expect } from 'vitest'
import { buildMemoryEffects, memoryTraitLevel, deriveTraitSlotLevels, waxBaseStat,
  parseBaseSlotEnabler, resolveBaseSlot, activeBaseSlotEnabler, rarityWithinCap, scaleSelValue,
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

// ── Base/Special slot (in-game-verified, owner 2026-08-08) ──────────────────────────────────────────────
// Enabler selections: T0 name-only "Artificial Moon" carries its text in `description`; T1/T2 in `modifier`.
const T0_ORIGIN: MemorySlotSelection = {
  modifier: 'Artificial Moon: Origin', tier: 0, rolledValue: null,
  description: 'Base Traits now have Special Memory slots that can be installed with an Ultimate or lower Origin Memory. Reduces the Base Stats and Random Affixes of Memories installed in this slot by 60%',
}
const T1_ORIGIN: MemorySlotSelection = {
  modifier: 'Base Traits now have Base Trait slots that can be installed with a Epic or lower Origin Memory. Base Stats and the value of Random Affixes of the Memory installed in this slot: (-60--55) %',
  tier: 1, rolledValue: -57,
}

describe('parseBaseSlotEnabler', () => {
  it('T0 Artificial Moon → origin, ultimate cap, −60% (factor 0.4), artificialMoon', () => {
    const e = parseBaseSlotEnabler(T0_ORIGIN)!
    expect(e).toMatchObject({ type: 'origin', rarityCap: 'ultimate', penaltyPct: 60, artificialMoon: true })
    expect(e.factor).toBeCloseTo(0.4)
  })
  it('T1 → epic cap, rolled −57% (factor 0.43), not artificialMoon', () => {
    const e = parseBaseSlotEnabler(T1_ORIGIN)!
    expect(e).toMatchObject({ type: 'origin', rarityCap: 'epic', artificialMoon: false })
    expect(e.factor).toBeCloseTo(0.43)
  })
  it('the base-slot type comes from the mod TEXT, not the host memory', () => {
    expect(parseBaseSlotEnabler(T0_ORIGIN)!.type).toBe('origin')
  })
  it('a normal revival mod is not an enabler', () => {
    expect(parseBaseSlotEnabler(sel('+10 % Damage'))).toBeNull()
  })
  it('Artificial Moon fails SAFE to −60% if its description text is missing (never unpenalized)', () => {
    // Name-only selection with NO description attached (e.g. an older build). Still a recognized AM enabler.
    const e = parseBaseSlotEnabler({ modifier: 'Artificial Moon: Discipline', tier: 0, rolledValue: null })!
    expect(e.type).toBe('discipline')
    expect(e.factor).toBeCloseTo(0.4)
    expect(e.penaltyPct).toBe(60)
  })
})

describe('rarityWithinCap', () => {
  it('respects the ordering', () => {
    expect(rarityWithinCap('epic', 'ultimate')).toBe(true)
    expect(rarityWithinCap('ultimate', 'epic')).toBe(false)
    expect(rarityWithinCap('rare', 'rare')).toBe(true)
  })
})

describe('resolveBaseSlot', () => {
  // Host a T0 Origin enabler on a (revived) PROGRESS memory — the base slot still accepts ORIGIN (text wins).
  const host = mem({ id: 'h', memoryType: 'progress', rarity: 'ultimate', revived: true, revivalMod: T0_ORIGIN })
  it('resolves when an enabler is equipped and type + rarity match', () => {
    const base = mem({ id: 'b', memoryType: 'origin', rarity: 'ultimate' })
    expect(resolveBaseSlot([host, null, null], base)?.memory.id).toBe('b')
  })
  it('is null when the base memory type mismatches the enabler', () => {
    expect(resolveBaseSlot([host, null, null], mem({ memoryType: 'discipline', rarity: 'rare' }))).toBeNull()
  })
  it('is null when no enabler is equipped', () => {
    expect(resolveBaseSlot([null, null, null], mem({ memoryType: 'origin' }))).toBeNull()
    expect(activeBaseSlotEnabler([null, null, null])).toBeNull()
  })
  it('is null when the base memory rarity exceeds the enabler cap (T1 = epic)', () => {
    const t1host = mem({ id: 'h', memoryType: 'progress', revived: true, revivalMod: T1_ORIGIN })
    expect(resolveBaseSlot([t1host, null, null], mem({ memoryType: 'origin', rarity: 'ultimate' }))).toBeNull()
    expect(resolveBaseSlot([t1host, null, null], mem({ memoryType: 'origin', rarity: 'epic' }))).not.toBeNull()
  })
})

describe('scaleSelValue (base-slot penalty)', () => {
  it('scales a rolled value by the factor (exact — display caps decimals downstream)', () =>
    expect(scaleSelValue(sel('+(50–100) Dexterity', 100), 0.4).rolledValue).toBe(40))
  it('caps a scaled text-value to ≤2 non-zero decimals (no floating-point tail like 75.60000000000001)', () =>
    expect(scaleSelValue(sel('+189 Max Mana'), 0.4).modifier).toBe('+75.6 Max Mana'))
  it('scales a text value and trims trailing zeros', () =>
    expect(scaleSelValue(sel('+100 Max Mana'), 0.43).modifier).toBe('+43 Max Mana'))
})

describe('buildMemoryEffects — base slot', () => {
  const host = mem({ id: 'h', memoryType: 'progress', rarity: 'ultimate', revived: true, revivalMod: T0_ORIGIN })
  const base = mem({
    id: 'b', memoryType: 'origin', rarity: 'ultimate', level: 50,
    baseStat: sel('+(50–100) Dexterity', 100),
    fixedAffixes: [sel('+5 Strength'), null],
    randomAffixes: [sel('+(10–20) % Damage', 20), null],
  })
  it('penalizes the base memory base + random values (×0.4) but not fixed', () => {
    const fx = buildMemoryEffects([host, null, null], base)
    expect(fx.some(e => e.text === '+40 Dexterity' && e.source.includes('Base'))).toBe(true)   // 100 × 0.4
    expect(fx.some(e => e.text === '+8 % Damage')).toBe(true)                                    // 20 × 0.4
    expect(fx.some(e => e.text === '+5 Strength')).toBe(true)                                    // fixed unscaled
  })
  it('contributes nothing when no enabler is equipped', () => {
    const fx = buildMemoryEffects([null, null, null], base)
    expect(fx.some(e => e.source.includes('Base'))).toBe(false)
  })
})

describe('deriveTraitSlotLevels — base slot', () => {
  const host = mem({ id: 'h', memoryType: 'progress', rarity: 'ultimate', revived: true, revivalMod: T0_ORIGIN })
  it('sets base [0] from the base memory when validly socketed (ultimate lv50 → 3)', () => {
    const base = mem({ memoryType: 'origin', rarity: 'ultimate', level: 50 })
    expect(deriveTraitSlotLevels([host, null, null], [1, 1, 1, 1], base)[0]).toBe(3)
  })
  it('leaves base [0] at its stored value when no enabler is equipped', () => {
    const base = mem({ memoryType: 'origin', rarity: 'ultimate', level: 50 })
    expect(deriveTraitSlotLevels([null, null, null], [1, 1, 1, 1], base)[0]).toBe(1)
  })
})
