import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BuildOverviewScreen from '../screens/BuildOverviewScreen'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs } from '../store/uiPrefsStore'

vi.mock('../components/CustomModsPanel', () => ({ default: () => null }))

const key = 'flame_slash_torrent_hits'
const label = 'Steep Strike Torrent Hits (Flame Slash)'

describe('Flame Slash torrent hits in Config', () => {
  beforeEach(() => {
    useReferenceStore.setState({ conditions: { Skill: [{
      key, label, category: 'Skill', value_type: 'numeric', source: 'auto',
      default_value: 3, numeric_min: 1,
    }] }, referenceResolved: true })
    useUiPrefs.setState({ lockAutoConditions: false })
    useBuildStore.setState({ conditionState: {}, computedStats: {
      ...useBuildStore.getState().computedStats,
      condition_maximums: { [key]: 5 }, clamp_report: {}, referenced_conditions: [key],
      auto_conditions: { [key]: { value: 5, source: 'Flame Slash', slot_values: { '1': 5 } } },
    } as never })
  })

  it('uses the automatic count and max, accepts one hit, and restores Auto', () => {
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const input = () => view.root.findAllByType('input').find(i => i.props.type === 'number')!
    expect(input().props.value).toBe('5')
    expect(input().props.min).toBe(1)
    expect(input().props.max).toBe(5)
    act(() => { input().props.onChange({ target: { value: '1' } }) })
    act(() => { input().props.onBlur({ target: { value: '1' } }) })
    expect(useBuildStore.getState().conditionState[key]).toBe(1)
    expect(input().props.value).toBe('1')
    act(() => { input().props.onChange({ target: { value: '' } }) })
    act(() => { input().props.onBlur({ target: { value: '' } }) })
    expect(input().props.value).toBe('5')
    expect(useBuildStore.getState().conditionState).toEqual({})
    act(() => { view.unmount() })
  })

  it('hides a stale saved setting after Flame Slash leaves the build', () => {
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    expect(JSON.stringify(view.toJSON())).toContain(label)
    act(() => {
      useBuildStore.setState({ conditionState: { [key]: 1 }, computedStats: {
        ...useBuildStore.getState().computedStats,
        referenced_conditions: [], auto_conditions: {}, condition_maximums: {},
      } as never })
    })
    expect(JSON.stringify(view.toJSON())).not.toContain(label)
    act(() => { view.unmount() })
  })
})
