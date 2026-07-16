import { describe, it, expect } from 'vitest'
import { coverageRank, passesModeledOnly } from '../utils/coverage'
import type { Coverage } from '../utils/coverage'

describe('coverageRank', () => {
  it('orders full < partial < none < undefined', () => {
    expect(coverageRank('full')).toBeLessThan(coverageRank('partial'))
    expect(coverageRank('partial')).toBeLessThan(coverageRank('none'))
    expect(coverageRank('none')).toBeLessThan(coverageRank(undefined))
  })

  it('exact rank values', () => {
    expect(coverageRank('full')).toBe(0)
    expect(coverageRank('partial')).toBe(1)
    expect(coverageRank('none')).toBe(2)
    expect(coverageRank(undefined)).toBe(3)
  })

  it('sorts a mixed list into full, partial, none, undefined order', () => {
    const items: { id: string; coverage?: Coverage }[] = [
      { id: 'a', coverage: 'none' },
      { id: 'b', coverage: undefined },
      { id: 'c', coverage: 'full' },
      { id: 'd', coverage: 'partial' },
    ]
    const sorted = [...items].sort((x, y) => coverageRank(x.coverage) - coverageRank(y.coverage))
    expect(sorted.map((i) => i.id)).toEqual(['c', 'd', 'a', 'b'])
  })
})

describe('passesModeledOnly', () => {
  it('modeledOnly=false: everything passes regardless of coverage', () => {
    expect(passesModeledOnly('full', false)).toBe(true)
    expect(passesModeledOnly('partial', false)).toBe(true)
    expect(passesModeledOnly('none', false)).toBe(true)
    expect(passesModeledOnly(undefined, false)).toBe(true)
  })

  it('modeledOnly=true: none is hidden', () => {
    expect(passesModeledOnly('none', true)).toBe(false)
  })

  it('modeledOnly=true: full and partial pass', () => {
    expect(passesModeledOnly('full', true)).toBe(true)
    expect(passesModeledOnly('partial', true)).toBe(true)
  })

  it('modeledOnly=true: undefined coverage ALWAYS passes (no hiding on a load race / stale cache)', () => {
    expect(passesModeledOnly(undefined, true)).toBe(true)
  })
})
