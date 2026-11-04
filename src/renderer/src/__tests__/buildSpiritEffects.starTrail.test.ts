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

function fateTrailMetadata(effects: ReturnType<typeof buildSpiritEffects>, shortName: string) {
  return effects
    .filter(effect => effect.source === 'Fate: ' + shortName)
    .map(({ microFateGroup, microFateMultiplierPercent }) => [microFateGroup, microFateMultiplierPercent])
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

  it('passes the one-Trail multiplier with the unscaled Micro Fate roll', () => {
    // +45% per Trail gives a 145% multiplier; the raw +7% roll is tagged for backend aggregation.
    const effects = oneTreeEffects(1)
    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+7 % Fire Resistance'])
    expect(fateTrailMetadata(effects, 'Fire Resistance')).toEqual([['0', 145]])
  })

  it('passes the capped three-Trail multiplier with the unscaled Micro Fate roll', () => {
    // Two-Trail additive stacking is in-game verified; three Trails continue the same observed per-Trail model.
    // Three Trails give a 235% multiplier; the raw +7% roll stays unchanged in the renderer payload.
    const effects = oneTreeEffects(3)
    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+7 % Fire Resistance'])
    expect(fateTrailMetadata(effects, 'Fire Resistance')).toEqual([['0', 235]])
  })

  it('tags the fates-only regression inputs with one branch and multiplier', () => {
    const effects = buildSpiritEffects(
      selected('tree'),
      [spirit('tree')],
      {
        '0:0': microFate('Fire Resistance', '+2 % Fire Resistance'),
        '0:1': STAR_TRAIL,
        '0:2': STAR_TRAIL,
      },
      [{ extraMicro: 3, extraMedium: 0, slots: [
        microFate('Fire Resistance', '+2 % Fire Resistance'),
        microFate('Fire Resistance', '+2 % Fire Resistance'),
        null,
      ] }],
    )

    // Owner's in-game result: these three 2% rolls combine to 6%; two Trails scale that to 11.4%,
    // which displays as 11%. The separate talent contribution is intentionally not in this case.
    const fatesOnly = effects.filter(effect => effect.source === 'Fate: Fire Resistance')
    expect(fatesOnly.map(effect => effect.text)).toEqual([
      '+2 % Fire Resistance',
      '+2 % Fire Resistance',
      '+2 % Fire Resistance',
    ])
    expect(fatesOnly.map(effect => [effect.microFateGroup, effect.microFateMultiplierPercent])).toEqual([
      ['0', 190],
      ['0', 190],
      ['0', 190],
    ])
  })

  it('caps the branch multiplier at three Star Trails', () => {
    // Assumed cap of three (unverified; no source; owner has never seen more than three used).
    // The assumed three-Trail cap yields 235%; the raw +7% roll stays unchanged.
    const effects = oneTreeEffects(4)
    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+7 % Fire Resistance'])
    expect(fateTrailMetadata(effects, 'Fire Resistance')).toEqual([['0', 235]])
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

  it('keeps both Micro Fate modifier values raw for backend scaling', () => {
    const effects = oneTreeEffects(1, microFate('Spell Damage', '+(14–18) % Spell Damage +(14–18) % Minion Damage'))

    // Both selected 18% rolls stay raw; the branch multiplier metadata applies to both resolved stats.
    expect(fateTexts(effects, 'Spell Damage')).toEqual(['+18 % Spell Damage +18 % Minion Damage'])
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

    // Four Trails total use the assumed cap of three; the installed +7% Micro Fate value stays raw.
    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+7 % Fire Resistance'])
  })

  it('tags a Star Trail in a same-tree Undetermined medium slot', () => {
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

    // Tree A's Micro Fate carries a 145% multiplier; tree B has no Trail and keeps a raw +7% value.
    expect(fateTexts(effects, 'Fire Resistance')).toEqual(['+7 % Fire Resistance', '+7 % Fire Resistance'])
  })

  it('tags an Undetermined Micro Fate only in the tree with Star Trail', () => {
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

    // Same-tree fate is tagged for scaling; the different-tree fate remains untagged.
    expect(fateTexts(effects, 'Attack Damage')).toEqual(['+18 % Attack Damage', '+18 % Attack Damage'])
  })

  it('keeps the raw two-percent Micro Fate roll in the renderer payload', () => {
    // The backend needs the raw +2% value to combine all matching branch fates first.
    expect(fateTexts(oneTreeEffects(1, microFate('Two Percent', '+2 % Damage')), 'Two Percent')).toEqual(['+2 % Damage'])
  })

  it('keeps the raw ten-percent roll for backend aggregation', () => {
    // Star Trail applies after same-stat Micro Fate contributions have been grouped by the backend.
    expect(fateTexts(oneTreeEffects(1, microFate('Ten Percent', '+10 % Damage')), 'Ten Percent')).toEqual(['+10 % Damage'])
  })

  it('preserves raw Micro Fate contributions for backend aggregation', () => {
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

    // Raw Fate values remain intact; backend metadata applies the multiplier after same-stat grouping.
    expect(fateTexts(effects, 'First One Percent')).toEqual(['+1 % Damage'])
    expect(fateTexts(effects, 'Second One Percent')).toEqual(['+1 % Minion Damage'])
  })

  it('preserves the raw fractional Micro Fate roll', () => {
    const micro = microFate('Life Restored on Defeat', 'Restores (0.1–0.2) % of Life on defeat', [0.13])
    const effects = oneTreeEffects(1, micro)

    // The rolled value remains 0.13 in the payload; Star Trail metadata carries the factor separately.
    expect(fateTexts(effects, 'Life Restored on Defeat')).toEqual(['Restores 0.13 % of Life on defeat'])
  })

  it('preserves the selected negative Micro Fate roll for backend scaling', () => {
    const effects = oneTreeEffects(1, microFate('Ignite Damage Mitigation', '(-36–-30) % additional Ignite Damage taken'))

    // The default roll is -30; its sign and value remain intact in the renderer payload.
    expect(fateTexts(effects, 'Ignite Damage Mitigation')).toEqual(['-30 % additional Ignite Damage taken'])
  })
})
