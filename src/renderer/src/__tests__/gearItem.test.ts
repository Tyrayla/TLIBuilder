import { describe, expect, it } from 'vitest'
import type { LegendaryGearItem } from '../api/client'
import { getRandomAffixGroupForExplicit } from '../utils/gearItem'

describe('random affixes on equipped gear', () => {
  it('shows the selected corroded Broken Sun Ring option in the editor', () => {
    const placeholder = '<A Random Steep Strike, Demolisher, Shadow Strike Affix>'
    const affix = (raw_text: string, affix_kind: string) => ({
      raw_text, modifier_id: null, expression: raw_text, condition: null,
      affix_kind, numeric_values: [],
    })
    const selected = {
      raw_text: '+(40–52) % additional Steep Strike Damage',
      modifier_id: '51525130', expression: '+(#) % additional Steep Strike Damage',
      condition: null, affix_kind: 'numeric', numeric_values: [],
    }
    const catalog = {
      item_id: 'broken_sun_ring', name: 'Broken Sun Ring',
      variants: {
        base: { implicits: [], explicits: [affix('Max Life', 'numeric'), affix('Elemental Resistance', 'numeric'), affix(placeholder, 'placeholder')] },
        corroded: { implicits: [], explicits: [affix('Max Life', 'numeric'), affix('Elemental Resistance', 'numeric'), affix(placeholder, 'placeholder')] },
      },
      random_affixes: {
        base: [{ placeholder, options: [{ ...selected, modifier_id: '51525131' }] }],
        corroded: [{ placeholder: `${placeholder}Corroded`, options: [selected] }],
      },
    } as unknown as LegendaryGearItem
    const group = getRandomAffixGroupForExplicit(catalog, 2, [0, 2])

    expect(group?.options[0].raw_text).toBe('+(40–52) % additional Steep Strike Damage')
  })
})
