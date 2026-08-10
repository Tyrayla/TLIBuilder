import { describe, it, expect } from 'vitest'
import { sharedRollGroups } from '../utils/affixText'
import type { LegendaryNumericValue } from '../api/client'

// sharedRollGroups: numeric_value indices on ONE affix line that are ONE in-game roll must be grouped so the
// roll editor drives them with a single control. With rawText, grouping requires BOTH an identical range AND
// the same underlying stat (player/minion mirror or same-stat conditional split) — two DISTINCT stats that
// merely share a range are NOT grouped (owner: narrow to genuine combined lines). Without rawText the stat
// check is skipped (range-only grouping, back-compat).
const range = (min: number, max: number, sign: string | null = '+'): LegendaryNumericValue => ({
  kind: 'range', sign, min, max, raw: `${sign ?? ''}(${min}-${max})`,
})
const fixed = (value: number): LegendaryNumericValue => ({
  kind: 'fixed', sign: null, value, raw: String(value),
})

describe('sharedRollGroups — range-only (no rawText, back-compat)', () => {
  it('two identical ranges → one group', () => {
    expect(sharedRollGroups([range(109, 122), range(109, 122)])).toEqual([[0, 1]])
  })
  it('two different ranges → two groups', () => {
    expect(sharedRollGroups([range(1, 5), range(6, 10)])).toEqual([[0], [1]])
  })
  it('three identical ranges → one group', () => {
    expect(sharedRollGroups([range(2, 4), range(2, 4), range(2, 4)])).toEqual([[0, 1, 2]])
  })
  it('mixed range + fixed + range(same as first) → same ranges group, fixed is its own', () => {
    expect(sharedRollGroups([range(3, 7), fixed(10), range(3, 7)])).toEqual([[0, 2], [1]])
  })
  it('empty → no groups', () => {
    expect(sharedRollGroups([])).toEqual([])
  })
  it('single → one singleton group', () => {
    expect(sharedRollGroups([range(1, 9)])).toEqual([[0]])
  })
  it('different sign does not group', () => {
    expect(sharedRollGroups([range(1, 5, '+'), range(1, 5, '-')])).toEqual([[0], [1]])
  })
})

describe('sharedRollGroups — narrow (with rawText: same range AND same stat)', () => {
  it('player/minion mirror (Minion prefix) → grouped', () => {
    const nvs = [range(10, 20), range(10, 20)]
    const raw = '+(10-20) % Attack and Cast Speed +(10-20) % Minion Attack and Cast Speed'
    expect(sharedRollGroups(nvs, raw)).toEqual([[0, 1]])
  })
  it('player/minion mirror (for Minions suffix) → grouped', () => {
    const nvs = [range(6, 8), range(6, 8)]
    const raw = '+(6-8) % Resistance Penetration +(6-8) % Resistance Penetration for Minions'
    expect(sharedRollGroups(nvs, raw)).toEqual([[0, 1]])
  })
  it('same stat with a trailing condition clause → grouped', () => {
    const nvs = [range(1, 5), range(1, 5)]
    const raw = '+(1-5) % Damage +(1-5) % Damage when Ignited'
    expect(sharedRollGroups(nvs, raw)).toEqual([[0, 1]])
  })
  it('two DISTINCT stats that share a range → NOT grouped', () => {
    const nvs = [range(40, 60), range(40, 60)]
    const raw = '+(40-60) % Ignite damage +(40-60) % chance to Ignite targets'
    expect(sharedRollGroups(nvs, raw)).toEqual([[0], [1]])
  })
  it('distinct resistances that share a range → NOT grouped', () => {
    const nvs = [range(1, 5), range(1, 5)]
    const raw = '+(1-5) % Elemental Resistance +(1-5) % Erosion Resistance'
    expect(sharedRollGroups(nvs, raw)).toEqual([[0], [1]])
  })
})
