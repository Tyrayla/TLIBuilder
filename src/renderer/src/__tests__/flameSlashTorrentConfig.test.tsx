import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BuildOverviewScreen from '../screens/BuildOverviewScreen'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs } from '../store/uiPrefsStore'

vi.mock('../components/CustomModsPanel', () => ({ default: () => null }))

const key = 'flame_slash_torrent_hits'
const label = 'Torrent Hits'

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

  it('uses the automatic count, shows Auto only for an override, and clears back to auto on blank commit', () => {
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const input = () => view.root.findAllByType('input').find(i => i.props.type === 'number')!
    const autoButton = () => view.root.findAllByType('button').find(button => button.children.join('') === 'Auto')
    expect(input().props.value).toBe('5')
    expect(input().props.min).toBe(1)
    expect(input().props.max).toBe(5)
    expect(autoButton()).toBeUndefined()
    expect(view.root.findAllByProps({ className: 'cond-derived-hint' })).toHaveLength(0)
    act(() => { input().props.onChange({ target: { value: '' } }) })
    act(() => { input().props.onBlur({ target: { value: '' } }) })
    expect(useBuildStore.getState().conditionState).toEqual({})
    expect(input().props.value).toBe('5')
    expect(autoButton()).toBeUndefined()
    act(() => { input().props.onChange({ target: { value: '1' } }) })
    act(() => { input().props.onBlur({ target: { value: '1' } }) })
    expect(useBuildStore.getState().conditionState[key]).toBe(1)
    expect(input().props.value).toBe('1')
    expect(autoButton()).toBeDefined()
    act(() => { input().props.onChange({ target: { value: '' } }) })
    act(() => { input().props.onBlur({ target: { value: '' } }) })
    expect(input().props.value).toBe('5')
    expect(useBuildStore.getState().conditionState).toEqual({})
    expect(autoButton()).toBeUndefined()
    act(() => { view.unmount() })
  })

  it('hides per-slot count helpers for Torrent Hits while keeping Auto visible inside the blank input', () => {
    useBuildStore.setState({ computedStats: {
      ...useBuildStore.getState().computedStats,
      auto_conditions: { [key]: { value: null, source: 'Flame Slash', slot_values: { '1': 3, '2': 5 } } },
    } as never })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const labelNode = view.root.findAllByProps({ className: 'cond-stack-label' }).find(item => item.children.join('') === label)
    expect(labelNode).toBeDefined()
    let row = labelNode!.parent
    while (row && row.props.className !== 'cond-stack-row') row = row.parent
    expect(row?.props.className).toBe('cond-stack-row')
    expect(row!.findAllByProps({ className: 'cond-derived-hint' })).toHaveLength(0)
    const torrentInput = row!.findByType('input')
    expect(torrentInput.props.value).toBe('')
    expect(torrentInput.props.placeholder).toBe('Auto')
    expect(row!.findAllByType('button').some(button => button.children.join('') === 'Auto')).toBe(false)
    act(() => { view.unmount() })
  })

  it('hides per-slot count helpers for Torrent Return Hits and uses Auto when slot values differ', () => {
    const otherKey = 'inverted_blaze_returns'
    useReferenceStore.setState({ conditions: { Skill: [
      { key: otherKey, label: 'Torrent Return Hits', category: 'Skill', value_type: 'numeric', source: 'auto', default_value: 0, numeric_min: 0 },
    ] } })
    useBuildStore.setState({ computedStats: {
      ...useBuildStore.getState().computedStats,
      referenced_conditions: [otherKey], condition_maximums: { [otherKey]: 5 },
      auto_conditions: { [otherKey]: { value: null, source: 'Flame Slash', slot_values: { '1': 3, '2': 5 } } },
    } as never })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const labelNode = view.root.findAllByProps({ className: 'cond-stack-label' }).find(item => item.children.join('') === 'Torrent Return Hits')
    expect(labelNode).toBeDefined()
    let row = labelNode!.parent
    while (row && row.props.className !== 'cond-stack-row') row = row.parent
    expect(row?.props.className).toBe('cond-stack-row')
    expect(row!.findAllByProps({ className: 'cond-derived-hint' })).toHaveLength(0)
    const returnInput = row!.findByType('input')
    expect(returnInput.props.value).toBe('')
    expect(returnInput.props.placeholder).toBe('Auto')
    expect(row!.findAllByType('button').some(button => button.children.join('') === 'Auto')).toBe(false)
    act(() => { view.unmount() })
  })

  it('also hides per-slot count text when auto conditions are locked', () => {
    const returnKey = 'inverted_blaze_returns'
    useUiPrefs.setState({ lockAutoConditions: true })
    useReferenceStore.setState({ conditions: { Skill: [
      { key, label, category: 'Skill', value_type: 'numeric', source: 'auto', default_value: 3, numeric_min: 1 },
      { key: returnKey, label: 'Torrent Return Hits', category: 'Skill', value_type: 'numeric', source: 'auto', default_value: 0, numeric_min: 0 },
    ] } })
    useBuildStore.setState({ conditionState: {}, computedStats: {
      ...useBuildStore.getState().computedStats,
      referenced_conditions: [key, returnKey], condition_maximums: { [key]: 5, [returnKey]: 5 },
      auto_conditions: {
        [key]: { value: null, source: 'Flame Slash', slot_values: { '1': 3, '2': 5 } },
        [returnKey]: { value: null, source: 'Flame Slash', slot_values: { '1': 3, '2': 5 } },
      },
    } as never })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const screen = JSON.stringify(view.toJSON())
    expect(screen).not.toContain('Slot 1: 3')
    expect(screen).not.toContain('Slot 2: 5')
    expect(screen).toContain('Torrent Hits')
    expect(screen).toContain('Torrent Return Hits')
    for (const text of [label, 'Torrent Return Hits']) {
      const node = view.root.findAllByProps({ className: 'cond-label' })
        .find(item => item.children.join('') === text)!
      let row = node.parent
      while (row && row.props.className !== 'cond-item cond-item--derived') row = row.parent
      expect(row?.findAllByProps({ className: 'cond-derived-hint' }).map(item => item.children.join('')))
        .toContain('Auto')
    }
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
