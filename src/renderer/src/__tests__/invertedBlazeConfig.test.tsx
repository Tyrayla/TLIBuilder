import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BuildOverviewScreen from '../screens/BuildOverviewScreen'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs } from '../store/uiPrefsStore'

vi.mock('../components/CustomModsPanel', () => ({ default: () => null }))

const key = 'inverted_blaze_returns'

describe('Inverted Blaze Config automatic returns', () => {
  beforeEach(() => {
    useReferenceStore.setState({ conditions: { Skill: [{
      key, label: 'Torrent Return Hits', category: 'Skill', value_type: 'numeric',
      source: 'auto', default_value: 3, numeric_min: 0,
    }] }, referenceResolved: true })
    useUiPrefs.setState({ lockAutoConditions: false })
    useBuildStore.setState({ conditionState: {}, computedStats: {
      ...useBuildStore.getState().computedStats,
      condition_maximums: {}, clamp_report: {}, referenced_conditions: [key],
      auto_conditions: { [key]: { value: 5, source: 'Inverted Blaze', slot_values: { '1': 5 } } },
    } as never })
  })

  it('shows five, retains explicit zero, and clearing deletes the override', () => {
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const input = () => view.root.findAllByType('input').find(i => i.props.type === 'number')!
    expect(input().props.value).toBe('5')
    act(() => { input().props.onChange({ target: { value: '0' } }) })
    act(() => { input().props.onBlur({ target: { value: '0' } }) })
    expect(useBuildStore.getState().conditionState[key]).toBe(0)
    act(() => { input().props.onChange({ target: { value: '' } }) })
    act(() => { input().props.onBlur({ target: { value: '' } }) })
    expect(useBuildStore.getState().conditionState).toEqual({})
    expect(input().props.value).toBe('5')
    act(() => { view.unmount() })
  })

  it('displays and stores a fractional return-hit override as a whole count', () => {
    useBuildStore.setState({ conditionState: { [key]: 2.9 } })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const input = () => view.root.findAllByType('input').find(i => i.props.type === 'number')!
    expect(input().props.value).toBe('2')
    expect(input().props.step).toBe(1)
    act(() => { input().props.onChange({ target: { value: '2.9' } }) })
    act(() => { input().props.onBlur({ target: { value: '2.9' } }) })
    expect(useBuildStore.getState().conditionState[key]).toBe(2)
    expect(input().props.value).toBe('2')
    act(() => { view.unmount() })
  })

  it('shows differing automatic slot counts without choosing a global default', () => {
    useBuildStore.setState({ computedStats: {
      ...useBuildStore.getState().computedStats,
      auto_conditions: { [key]: { value: null, source: 'Inverted Blaze', slot_values: { '1': 5, '2': 7 } } },
    } as never })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const input = view.root.findAllByType('input').find(i => i.props.type === 'number')!
    expect(input.props.value).toBe('')
    expect(JSON.stringify(view.toJSON())).toContain('Slot 1: 5 · Slot 2: 7')
    act(() => { input.props.onBlur({ target: { value: '' } }) })
    expect(useBuildStore.getState().conditionState).toEqual({})
    act(() => { view.unmount() })
  })
})
