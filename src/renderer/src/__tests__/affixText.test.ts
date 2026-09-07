import { describe, it, expect } from 'vitest'
import {
  decimalPlaces, rangeDecimals, midpoint, hasRangeValues, affixStatKeys,
  reconstructAffixText, tooltipAffixText, affixTypeLabel,
} from '../utils/affixText'
import type { LegendaryAffix, LegendaryNumericValue } from '../api/client'

// ── fixtures ──────────────────────────────────────────────────────────────────
function nv(o: Partial<LegendaryNumericValue> & Pick<LegendaryNumericValue, 'kind' | 'raw'>): LegendaryNumericValue {
  return { sign: null, ...o }
}
function affix(raw_text: string, numeric_values: LegendaryNumericValue[], extra: Partial<LegendaryAffix> = {}): LegendaryAffix {
  return { raw_text, modifier_id: null, expression: '', condition: null, affix_kind: 'numeric', numeric_values, ...extra }
}

describe('decimalPlaces', () => {
  it('counts fractional digits', () => {
    expect(decimalPlaces(5)).toBe(0)
    expect(decimalPlaces(100)).toBe(0)
    expect(decimalPlaces(5.5)).toBe(1)
    expect(decimalPlaces(5.25)).toBe(2)
  })
})

describe('rangeDecimals', () => {
  it('takes the max fractional precision of min and max', () => {
    expect(rangeDecimals(nv({ kind: 'range', min: 1, max: 2, raw: '' }))).toBe(0)
    expect(rangeDecimals(nv({ kind: 'range', min: 1.5, max: 2.25, raw: '' }))).toBe(2)
  })
})

describe('midpoint', () => {
  it('rounds an integer range to a whole number', () => {
    expect(midpoint(nv({ kind: 'range', min: 10, max: 20, raw: '' }))).toBe(15)
  })
  it('keeps the range precision for a fractional range', () => {
    expect(midpoint(nv({ kind: 'range', min: 1.5, max: 2.5, raw: '' }))).toBe(2)
    expect(midpoint(nv({ kind: 'range', min: 1.0, max: 1.5, raw: '' }))).toBe(1.3) // mid 1.25, dp 1 → toFixed(1) → 1.3
  })
  it('returns the value for a fixed number', () => {
    expect(midpoint(nv({ kind: 'fixed', value: 7, raw: '7' }))).toBe(7)
  })
})

describe('hasRangeValues', () => {
  it('is true only for a numeric affix carrying at least one range', () => {
    expect(hasRangeValues(affix('(10-20) Fire', [nv({ kind: 'range', min: 10, max: 20, raw: '(10-20)' })]))).toBe(true)
    expect(hasRangeValues(affix('7 Fire', [nv({ kind: 'fixed', value: 7, raw: '7' })]))).toBe(false)
    expect(hasRangeValues(affix('special', [nv({ kind: 'range', min: 1, max: 2, raw: '' })], { affix_kind: 'special' }))).toBe(false)
  })
})

describe('affixStatKeys', () => {
  it('collects keys from every stat-bearing field', () => {
    expect(affixStatKeys({ stat_key: 'a' })).toEqual(['a'])
    expect(affixStatKeys({ stat_keys: ['b', 'c'] })).toEqual(['b', 'c'])
    expect(affixStatKeys({ min_stat_keys: ['d'], max_stat_keys: ['e'] })).toEqual(['d', 'e'])
    expect(affixStatKeys({ dual_stat_groups: [{ stat_keys: ['f'] }, { stat_keys: ['g'] }] })).toEqual(['f', 'g'])
    expect(affixStatKeys({ stat_key: 'a', stat_keys: ['b'], max_stat_keys: ['e'] })).toEqual(['a', 'b', 'e'])
  })
})

describe('reconstructAffixText', () => {
  it('substitutes a chosen value for a range token', () => {
    const a = affix('Adds (10-20) Fire Damage', [nv({ kind: 'range', min: 10, max: 20, raw: '(10-20)' })])
    expect(reconstructAffixText(a, { 0: 15 })).toBe('Adds 15 Fire Damage')
  })
  it('prepends the sign', () => {
    const a = affix('(5-10)% increased Damage', [nv({ kind: 'range', sign: '+', min: 5, max: 10, raw: '(5-10)' })])
    expect(reconstructAffixText(a, { 0: 7 })).toBe('+7% increased Damage')
  })
  it('falls back to the midpoint when a value is not chosen', () => {
    const a = affix('(10-20) Life', [nv({ kind: 'range', min: 10, max: 20, raw: '(10-20)' })])
    expect(reconstructAffixText(a, {})).toBe('15 Life')
  })
  it('formats to the range decimal precision', () => {
    const a = affix('(1.5-2.5)x Multiplier', [nv({ kind: 'range', min: 1.5, max: 2.5, raw: '(1.5-2.5)' })])
    expect(reconstructAffixText(a, { 0: 2 })).toBe('2.0x Multiplier')
  })
  it('leaves fixed values untouched', () => {
    const a = affix('10 Mana', [nv({ kind: 'fixed', value: 10, raw: '10' })])
    expect(reconstructAffixText(a, { 0: 99 })).toBe('10 Mana')
  })
  it('substitutes multiple distinct range tokens independently', () => {
    const a = affix('(10-20) Fire, (5-15) Cold', [
      nv({ kind: 'range', min: 10, max: 20, raw: '(10-20)' }),
      nv({ kind: 'range', min: 5, max: 15, raw: '(5-15)' }),
    ])
    expect(reconstructAffixText(a, { 0: 12, 1: 8 })).toBe('12 Fire, 8 Cold')
  })
})

describe('tooltipAffixText', () => {
  const rangeAffix = affix('(10-20) Fire Damage', [nv({ kind: 'range', min: 10, max: 20, raw: '(10-20)' })])

  it('returns raw_text verbatim when the affix has no ranges', () => {
    const fixed = affix('+7 Fire Damage', [nv({ kind: 'fixed', value: 7, raw: '7' })])
    expect(tooltipAffixText(fixed, 0, undefined)).toBe('+7 Fire Damage')
  })
  it('reconstructs from the matching customization by affix_index', () => {
    const custs = [{ affix_index: 3, chosen_values: { 0: 18 }, chosen_placeholder_key: null }]
    expect(tooltipAffixText(rangeAffix, 3, custs)).toBe('18 Fire Damage')
  })
  it('falls back to midpoints when no customization matches the index', () => {
    const custs = [{ affix_index: 99, chosen_values: { 0: 18 }, chosen_placeholder_key: null }]
    expect(tooltipAffixText(rangeAffix, 3, custs)).toBe('15 Fire Damage')
  })
})

describe('affixTypeLabel', () => {
  it('maps the known affix types', () => {
    expect(affixTypeLabel('Base')).toBe('Base Affix')
    expect(affixTypeLabel('Base Affix')).toBe('Base Affix')
    expect(affixTypeLabel('Legendary')).toBe('Legendary Affix')
    expect(affixTypeLabel('Advanced Affix')).toBe('Advanced Affix')
    expect(affixTypeLabel('Ultimate')).toBe('Ultimate Affix')
  })
  it('prefixes the roll tier when present and > 0', () => {
    expect(affixTypeLabel('Advanced Affix', 2)).toBe('T2 Advanced Affix')
    expect(affixTypeLabel('Advanced Affix', '3')).toBe('T3 Advanced Affix')
    expect(affixTypeLabel('Advanced Affix', 0)).toBe('Advanced Affix') // tier 0 not prefixed
    expect(affixTypeLabel('Legendary', 2)).toBe('T2 Legendary Affix')
  })
  it('returns undefined for an unknown or missing type', () => {
    expect(affixTypeLabel(undefined)).toBeUndefined()
    expect(affixTypeLabel('Something Else')).toBeUndefined()
  })
})
