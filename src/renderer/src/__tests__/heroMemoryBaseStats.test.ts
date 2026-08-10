import { describe, it, expect } from 'vitest'
import { heroMemoryBaseStatValue, heroMemoryBaseStatText,
  type HeroMemoryBaseStatScaling } from '../api/client'

// Base-stat-by-level scaling (source: MinMaxedARPG). LINEAR per rarity from L1 to the rarity cap, with anchors
// captured every 10 levels; a consumer interpolates piecewise-linearly by memory level. See the
// hero-memory-base-stats verification entry.

const scaling: HeroMemoryBaseStatScaling = {
  stats: [
    { source: 'Discipline', affixTemplate: '+{value} Life',
      magic: { 1: 61, 10: 119, 20: 183 },
      epic: { 1: 110, 10: 161, 20: 217, 30: 274, 40: 330 } },
    { source: 'Origin', affixTemplate: '+{value} Strength',
      magic: { 1: 17, 10: 33, 20: 50 },
      epic: { 1: 30, 10: 44, 20: 59, 30: 75, 40: 90 } },
    { source: 'Origin', affixTemplate: '+{value} Damage',
      magic: { 1: 20, 10: 38.9, 20: 60 } },
    // The source's single MinionCastAttackSpeed row feeds BOTH our Minion Attack Speed and Minion Cast Speed.
    { source: 'Progress', affixTemplate: '+{value} MinionCastAttackSpeed',
      epic: { 1: 12, 10: 17.5, 20: 23.7, 30: 29.8, 40: 36 } },
  ],
}

describe('heroMemoryBaseStatValue', () => {
  it('returns the exact anchor at the rarity cap', () =>
    expect(heroMemoryBaseStatValue(scaling, 'discipline', 'Max Life', 'epic', 40)).toBe(330))

  it('returns the exact anchor at a 10-level mark', () =>
    expect(heroMemoryBaseStatValue(scaling, 'discipline', 'Max Life', 'epic', 20)).toBe(217))

  it('interpolates piecewise-linearly between anchors', () =>
    // between L10 (161) and L20 (217): 161 + (217-161)*(15-10)/10 = 189
    expect(heroMemoryBaseStatValue(scaling, 'discipline', 'Max Life', 'epic', 15)).toBe(189))

  it('clamps above the rarity cap to the cap value', () =>
    expect(heroMemoryBaseStatValue(scaling, 'origin', 'Strength', 'epic', 999)).toBe(90))

  it('clamps below level 1 to the L1 value', () =>
    expect(heroMemoryBaseStatValue(scaling, 'origin', 'Strength', 'epic', 0)).toBe(30))

  it('maps our "Damage" affix to the source Damage row', () =>
    expect(heroMemoryBaseStatValue(scaling, 'origin', 'Damage', 'magic', 20)).toBe(60))

  it('feeds BOTH Minion Attack Speed and Minion Cast Speed from the one source row', () => {
    expect(heroMemoryBaseStatValue(scaling, 'progress', 'Minion Attack Speed', 'epic', 40)).toBe(36)
    expect(heroMemoryBaseStatValue(scaling, 'progress', 'Minion Cast Speed', 'epic', 40)).toBe(36)
  })

  it('returns null for a stat not in the table', () =>
    expect(heroMemoryBaseStatValue(scaling, 'origin', 'Nonexistent', 'epic', 40)).toBeNull())

  it('returns null when the rarity has no anchors', () =>
    // Damage has no epic anchors in this fixture
    expect(heroMemoryBaseStatValue(scaling, 'origin', 'Damage', 'epic', 40)).toBeNull())

  it('returns null when the scaling table is missing', () =>
    expect(heroMemoryBaseStatValue(null, 'origin', 'Strength', 'epic', 40)).toBeNull())
})

describe('heroMemoryBaseStatText (crosswalk import recompute)', () => {
  it('recomputes the value into the affix text at rarity-max', () =>
    // Compendium exported "+30 Strength"; our epic L40 Strength = 90
    expect(heroMemoryBaseStatText(scaling, 'origin', '+30 Strength', 'epic', 40)).toBe('+90 Strength'))

  it('preserves the exact suffix format ("Max Life")', () =>
    expect(heroMemoryBaseStatText(scaling, 'discipline', '+37 Max Life', 'magic', 20)).toBe('+183 Max Life'))

  it('preserves a "% <stat>" suffix', () =>
    expect(heroMemoryBaseStatText(scaling, 'origin', '+10 % damage', 'magic', 20)).toBe('+60 % damage'))

  it('rounds to 1 decimal (source precision)', () =>
    // magic Damage L10 = 38.9 (an anchor)
    expect(heroMemoryBaseStatText(scaling, 'origin', '+10 % damage', 'magic', 10)).toBe('+38.9 % damage'))

  it('returns null (keep Compendium value) when the stat is not in the table', () =>
    expect(heroMemoryBaseStatText(scaling, 'origin', '+5 Foobar', 'epic', 40)).toBeNull())
})
