import { describe, expect, it } from 'vitest'
import {
  buildSpiritEffects,
  type InstalledFate,
  type PactSpirit,
  type SelectedPactSpirit,
  type UndeterminedFate,
} from '../api/client'

const STAR_TRAIL: InstalledFate = {
  name: 'Kismet: Star Trail',
  shortName: 'Star Trail',
  kind: 'kismet',
  nodeTier: 'medium',
  effectText: '+45 % for the effects of Micro Fates in the same Pact Branch',
}

function microFate(shortName = 'Fire Resistance', effectText = '+(5–7) % Fire Resistance', rolledValues?: number[]): InstalledFate {
  return { name: 'Micro Fate: ' + shortName, shortName, kind: 'micro_fate', nodeTier: 'micro', effectText, rolledValues }
}

function spirit(itemId: string): PactSpirit {
  return {
    item_id: itemId,
    name: 'Pact ' + itemId,
    description: '',
    affinities: [],
    main_skill_name: '',
    main_skill_effect: '',
    upgrade_ranks: [],
    slots: [
      { name: 'Micro', effect: [], ring: 'inner' },
      ...Array.from({ length: 4 }, (_, i) => ({ name: 'Mid ' + i, effect: [], ring: 'mid' as const })),
    ],
    glossary: {},
  }
}

function selected(...itemIds: string[]): SelectedPactSpirit[] {
  return itemIds.map(itemId => ({ itemId, rank: 1 }))
}

function fateTexts(effects: ReturnType<typeof buildSpiritEffects>, shortName: string): string[] {
  return effects.filter(effect => effect.source === 'Fate: ' + shortName).map(effect => effect.text)
}

function oneTreeEffects(starTrailCount: number, micro = microFate()) {
  const fates: Record<string, InstalledFate> = { '0:0': micro }
  for (let i = 0; i < starTrailCount; i++) fates['0:' + (i + 1)] = STAR_TRAIL
  return buildSpiritEffects(selected('tree'), [spirit('tree')], fates, [{ extraMicro: 0, extraMedium: 0, slots: [] }])
}

describe('Star Trail Micro Fate effectiveness', () => {
  it('leaves Micro Fate rolls unchanged with no Star Trail', () => {
    // Canonical Micro Fate roll is 7%; with factor 1.00, 7 * 1.00 = 7.
    expect(fateTexts(oneTreeEffects(0), 'Fire Resistance')).toEqual(['+7 % Fire Resistance'])
  })

  it('adds 45 percentage points for one Star Trail', () => {
    // Factor is 1 + 0.45 * 1 = 1.45 (+45 % per Star Trail, per game text); canonical roll 7 * 1.45 = 10.15, rounded to 10.
    expect(fateTexts(oneTreeEffects(1), 'Fire Resistance')).toEqual(['+10 % Fire Resistance'])
  })

  it('stacks three Star Trails additively', () => {
    // Factor is 1 + 0.45 * 3 = 2.35; canonical roll 7 * 2.35 = 16.45, rounded to 16.
    expect(fateTexts(oneTreeEffects(3), 'Fire Resistance')).toEqual(['+16 % Fire Resistance'])
  })

  it('caps effectiveness at three Star Trails', () => {
    // Assumed cap of three (unverified; no source; owner has never seen more than three used).
    // A fourth Star Trail is above the assumed cap, so 7 * 2.35 = 16.45, still rounded to 16.
    expect(fateTexts(oneTreeEffects(4), 'Fire Resistance')).toEqual(['+16 % Fire Resistance'])
  })

  it('does not scale a Medium Fate alongside the Micro Fates', () => {
    const mediumFate: InstalledFate = {
      name: 'Medium Fate: Attack Damage',
      shortName: 'Medium Damage',
      kind: 'medium_fate',
      nodeTier: 'medium',
      effectText: '+18 % Damage',
    }
    const effects = buildSpiritEffects(
      selected('tree'),
      [spirit('tree')],
      { '0:0': microFate(), '0:1': STAR_TRAIL, '0:2': mediumFate },
      [{ extraMicro: 0, extraMedium: 0, slots: [] }],
    )

    expect(fateTexts(effects, 'Medium Damage')).toEqual(['+18 % Damage'])
  })

  it('scales both modifiers on a Micro Fate', () => {
    const effects = oneTreeEffects(1, microFate('Spell Damage', '+(14–18) % Spell Damage +(14–18) % Minion Damage'))

    // The selected 18% roll is scaled for each modifier: 18 * 1.45 = 26.1, rounded to 26.
    expect(fateTexts(effects, 'Spell Damage')).toEqual(['+26 % Spell Damage +26 % Minion Damage'])
  })
  it('counts a Star Trail in a same-tree Undetermined medium slot', () => {
    const undetermined: (UndeterminedFate | null)[] = [
      { extraMicro: 1, extraMedium: 1, slots: [microFate(), STAR_TRAIL] },
      { extraMicro: 1, extraMedium: 0, slots: [microFate()] },
    ]
    const effects = buildSpiritEffects(
      selected('tree-a', 'tree-b'),
      [spirit('tree-a'), spirit('tree-b')],
      {},
      undetermined,
    )

    // Tree A's Undetermined medium slot supplies one Trail: 7 * 1.45 = 10.15, rounded to 10; tree B stays at 7.
    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+10 % Fire Resistance', '+7 % Fire Resistance'])
  })

  it('scales an Undetermined Micro Fate only in the tree with Star Trail', () => {
    const undetermined: (UndeterminedFate | null)[] = [
      { extraMicro: 1, extraMedium: 0, slots: [microFate('Attack Damage', '+(14–18) % Attack Damage')] },
      { extraMicro: 1, extraMedium: 0, slots: [microFate('Attack Damage', '+(14–18) % Attack Damage')] },
    ]
    const effects = buildSpiritEffects(
      selected('tree-a', 'tree-b'),
      [spirit('tree-a'), spirit('tree-b')],
      { '0:1': STAR_TRAIL },
      undetermined,
    )

    // Same-tree: 18 * 1.45 = 26.1, rounded to 26. Different-tree: no Star Trail there, so the 18% roll stays 18.
    expect(fateTexts(effects, 'Attack Damage')).toEqual(['+26 % Attack Damage', '+18 % Attack Damage'])
  })

  it('rounds a two-percent Micro Fate result of 2.9 up to 3', () => {
    // Owner-approved factor gives 2 * 1.45 = 2.9, which rounds to 3.
    expect(fateTexts(oneTreeEffects(1, microFate('Two Percent', '+2 % Damage')), 'Two Percent')).toEqual(['+3 % Damage'])
  })

  it('rounds a half value up to the next integer', () => {
    // Owner-approved factor gives 10 * 1.45 = 14.5, which rounds half up to 15.
    expect(fateTexts(oneTreeEffects(1, microFate('Ten Percent', '+10 % Damage')), 'Ten Percent')).toEqual(['+15 % Damage'])
  })

  it('rounds each Micro Fate source before summing their results', () => {
    const effects = buildSpiritEffects(
      selected('tree'),
      [spirit('tree')],
      { '0:1': STAR_TRAIL },
      [{
        extraMicro: 2,
        extraMedium: 0,
        slots: [
          microFate('First One Percent', '+1 % Damage'),
          microFate('Second One Percent', '+1 % Minion Damage'),
        ],
      }],
    )

    // Each source gives 1 * 1.45 = 1.45, rounded down to 1: total 2. Aggregate rounding would give 2.9, rounded to 3.
    expect(fateTexts(effects, 'First One Percent')).toEqual(['+1 % Damage'])
    expect(fateTexts(effects, 'Second One Percent')).toEqual(['+1 % Minion Damage'])
  })

  it('rounds the exact decimal product once to the nearest integer', () => {
    const micro = microFate('Life Restored on Defeat', 'Restores (0.1–0.2) % of Life on defeat', [0.13])
    const effects = oneTreeEffects(1, micro)

    // Existing fate roll is 0.13; factor is 1.45, so the 0.1885 rounds down to 0.
    expect(fateTexts(effects, 'Life Restored on Defeat')).toEqual(['Restores 0 % of Life on defeat'])
  })

  it('scales the selected negative Micro Fate roll without losing its sign', () => {
    const effects = oneTreeEffects(1, microFate('Ignite Damage Mitigation', '(-36–-30) % additional Ignite Damage taken'))

    // Existing best-roll behavior selects -30; applying 1.45 gives -43.5, rounded half up to -44.
    expect(fateTexts(effects, 'Ignite Damage Mitigation')).toEqual(['-44 % additional Ignite Damage taken'])
  })
})




