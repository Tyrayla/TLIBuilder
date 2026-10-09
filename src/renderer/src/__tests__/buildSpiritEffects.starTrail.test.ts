import { describe, expect, it } from 'vitest'
import {
  buildSpiritEffects,
  fateRangeRegex,
  fateRanges,
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
    // Additive stacking (1 + 0.45n) is modeled, unverified; no in-game measurement exists.
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

  it('shares one signed roll-range pattern between fateRanges and the roll editor', () => {
    const text = '(-36–-30) % additional Ignite Damage taken +(5–7) % Fire Resistance'
    const matches = Array.from(text.matchAll(fateRangeRegex())).map(m => m[0])

    expect(matches).toEqual(['(-36–-30)', '(5–7)'])
    expect(fateRanges(text)).toEqual([{ lo: -36, hi: -30, dp: 0 }, { lo: 5, hi: 7, dp: 0 }])
  })

  it('does not emit the Star Trail effect line itself', () => {
    expect(fateTexts(oneTreeEffects(1), 'Star Trail')).toEqual([])
  })

  it('does not count a Star Trail in a micro-ring slot or in another tree', () => {
    const effects = buildSpiritEffects(
      selected('tree-a', 'tree-b'),
      [spirit('tree-a'), spirit('tree-b')],
      { '0:0': microFate(), '1:0': STAR_TRAIL, '1:1': microFate('Attack Damage', '+(14–18) % Attack Damage') },
      [null, null],
    )

    // Tree A has no mid-ring Trail (the only Trail is in tree B's inner slot), so its roll stays 7.
    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+7 % Fire Resistance'])
    expect(fateTexts(effects, 'Attack Damage')).toEqual(['+18 % Attack Damage'])
  })

  it('does not count an Undetermined Star Trail sitting in a micro slot', () => {
    const effects = buildSpiritEffects(
      selected('tree'),
      [spirit('tree')],
      { '0:0': microFate() },
      [{ extraMicro: 1, extraMedium: 0, slots: [STAR_TRAIL] }],
    )

    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+7 % Fire Resistance'])
  })

  it('adds native and Undetermined Star Trails in one tree, capped at three in total', () => {
    const fates: Record<string, InstalledFate> = { '0:0': microFate(), '0:1': STAR_TRAIL, '0:2': STAR_TRAIL }
    const effects = buildSpiritEffects(
      selected('tree'),
      [spirit('tree')],
      fates,
      [{ extraMicro: 0, extraMedium: 2, slots: [STAR_TRAIL, STAR_TRAIL] }],
    )

    // Four Trails total; assumed cap of three (unverified) gives 7 * 2.35 = 16.45, rounded to 16.
    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+16 % Fire Resistance'])
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
    // The +45 % factor is game text; 2 * 1.45 = 2.9 rounds to 3 (whole-number rounding is an unverified assumption).
    expect(fateTexts(oneTreeEffects(1, microFate('Two Percent', '+2 % Damage')), 'Two Percent')).toEqual(['+3 % Damage'])
  })

  it('rounds a positive half value away from zero', () => {
    // 10 * 1.45 = 14.5, which rounds half away from zero to 15 (unverified assumption).
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

    // The default roll is the range's upper bound, -30; applying 1.45 gives -43.5, rounded half away from zero to -44.
    expect(fateTexts(effects, 'Ignite Damage Mitigation')).toEqual(['-44 % additional Ignite Damage taken'])
  })
})
