import { describe, it, expect } from 'vitest'
import { seasonLabel, isPreSeason } from '../utils/seasonLabel'

describe('seasonLabel / isPreSeason', () => {
  it('uses the file label and falls back to the season name', () => {
    expect(seasonLabel({ name: 'SS14', label: 'SS14 Pre-Season' })).toBe('SS14 Pre-Season')
    expect(seasonLabel({ name: 'SS13' })).toBe('SS13')
    expect(seasonLabel({ name: 'SS13', label: '  ' })).toBe('SS13')
  })

  it('flags only pre-season status', () => {
    expect(isPreSeason({ status: 'pre-season' })).toBe(true)
    expect(isPreSeason({ status: 'Pre-Season' })).toBe(true)
    expect(isPreSeason({ status: null })).toBe(false)
    expect(isPreSeason({})).toBe(false)
  })
})
