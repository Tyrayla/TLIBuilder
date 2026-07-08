import { describe, it, expect } from 'vitest'
import { migrateOldConditions, characterLevelFrom, buildDefaultConditionState } from '../utils/conditions'
import type { ConditionDef } from '../api/client'

describe('migrateOldConditions', () => {
  it('overlapping keys: conditionValues wins over the legacy conditions string[]', () => {
    // 'b' is present in BOTH the old boolean-list and the new numeric map — the numeric map must win
    // (conditionValues is applied AFTER the conditions loop in the source).
    const state = migrateOldConditions(['a', 'b'], { b: 5 })
    expect(state).toEqual({ a: true, b: 5 })
  })

  it('non-numeric conditionValues become NaN (Number() coercion, not silently dropped)', () => {
    const state = migrateOldConditions(null, { c: 'not-a-number' as unknown as number })
    expect(Number.isNaN(state.c)).toBe(true)
  })

  it('both args null → empty state', () => {
    expect(migrateOldConditions(null, null)).toEqual({})
  })

  it('both args undefined → empty state', () => {
    expect(migrateOldConditions(undefined, undefined)).toEqual({})
  })

  it('conditions-only (no conditionValues) → every key becomes boolean true', () => {
    expect(migrateOldConditions(['x', 'y'], null)).toEqual({ x: true, y: true })
  })
})

describe('characterLevelFrom', () => {
  it('level 0 → defaults to 90 (not > 0)', () => {
    expect(characterLevelFrom({ level: 0 })).toBe(90)
  })

  it('negative level → defaults to 90', () => {
    expect(characterLevelFrom({ level: -5 })).toBe(90)
  })

  it('non-number string level → defaults to 90', () => {
    expect(characterLevelFrom({ level: '50' })).toBe(90)
  })

  it('missing level key → defaults to 90', () => {
    expect(characterLevelFrom({})).toBe(90)
  })

  it('valid positive level is rounded', () => {
    expect(characterLevelFrom({ level: 45.6 })).toBe(46)
  })
})

describe('buildDefaultConditionState', () => {
  function def(partial: Partial<ConditionDef>): ConditionDef {
    return { key: 'k', label: 'K', value_type: 'numeric', ...partial }
  }

  it('boolean branch: default_bool true is honored', () => {
    const state = buildDefaultConditionState([def({ key: 'b1', value_type: 'boolean', default_bool: true })])
    expect(state.b1).toBe(true)
  })

  it('boolean branch: missing default_bool defaults to false', () => {
    const state = buildDefaultConditionState([def({ key: 'b2', value_type: 'boolean' })])
    expect(state.b2).toBe(false)
  })

  it('enum branch: default_enum is honored', () => {
    const state = buildDefaultConditionState([
      def({ key: 'e1', value_type: 'enum', enum_values: ['a', 'b', 'c'], default_enum: 'b' }),
    ])
    expect(state.e1).toBe('b')
  })

  it('enum branch: no default_enum falls back to enum_values[0]', () => {
    const state = buildDefaultConditionState([
      def({ key: 'e2', value_type: 'enum', enum_values: ['first', 'second'] }),
    ])
    expect(state.e2).toBe('first')
  })

  it('enum branch: empty enum_values and no default_enum → empty string', () => {
    const state = buildDefaultConditionState([def({ key: 'e3', value_type: 'enum', enum_values: [] })])
    expect(state.e3).toBe('')
  })

  it('enum branch: no enum_values at all and no default_enum → empty string', () => {
    const state = buildDefaultConditionState([def({ key: 'e4', value_type: 'enum' })])
    expect(state.e4).toBe('')
  })

  it('numeric branch: default_value is honored', () => {
    const state = buildDefaultConditionState([def({ key: 'n1', value_type: 'numeric', default_value: 42 })])
    expect(state.n1).toBe(42)
  })

  it('numeric branch: missing default_value defaults to 0', () => {
    const state = buildDefaultConditionState([def({ key: 'n2', value_type: 'numeric' })])
    expect(state.n2).toBe(0)
  })
})
