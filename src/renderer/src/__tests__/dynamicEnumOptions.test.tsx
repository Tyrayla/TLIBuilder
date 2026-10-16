import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BuildOverviewScreen from '../screens/BuildOverviewScreen'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs } from '../store/uiPrefsStore'

vi.mock('../components/CustomModsPanel', () => ({ default: () => null }))

describe('dynamic condition enum options', () => {
  beforeEach(() => {
    useReferenceStore.setState({
      conditions: { 'Hero Trait': [{
        key: 'vigilant_breeze_merged_slot', label: 'Merged Magus', category: 'Hero Trait',
        value_type: 'enum', enum_values: [], default_enum: '', options_source: 'spirit_magus_slots',
        trait_id: 'vigilant_breeze',
      }] },
      referenceResolved: true,
    })
    useUiPrefs.setState({ lockAutoConditions: false, collapsiblePanels: false })
    useBuildStore.setState({
      conditionState: { vigilant_breeze_merged_slot: '9' }, traitId: 'vigilant_breeze',
      skills: [
        { slot: 1, item_id: 'summon_rock_magus', name: 'Rock Magus', level: 20, enabled: true,
          skill_tags: ['Spirit Magus'], description_lines: [], supports: [] },
        { slot: 2, item_id: 'summon_rock_magus', name: 'Rock Magus', level: 20, enabled: true,
          skill_tags: ['Spirit Magus'], description_lines: [], supports: [] },
        { slot: 3, item_id: 'summon_erosion_magus', name: 'Erosion Magus', level: 20, enabled: true,
          skill_tags: ['Spirit Magus'], description_lines: [], supports: [] },
        { slot: 5, item_id: 'summon_rock_magus', name: 'Disabled Magus', level: 20, enabled: false,
          skill_tags: ['Spirit Magus'], description_lines: [], supports: [] },
      ] as never,
      mainSkill: null,
      computedStats: {
        ...useBuildStore.getState().computedStats,
        condition_maximums: {}, clamp_report: {}, referenced_conditions: [], auto_conditions: {}, main_skill_slot: null,
      } as never,
    })
  })

  it('offers enabled Spirit Magi by slot, replaces stale selections, and stores the chosen slot', () => {
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })

    const item = view.root.findAllByProps({ className: 'cond-item' }).find(node =>
      node.findAllByProps({ className: 'cond-label' }).some(label => label.children.join('') === 'Merged Magus'),
    )!
    const select = item.findByType('select')
    expect(select.props.value).toBe('1')
    expect(select.findAllByType('option').map(option => option.props.children)).toEqual([
      'Rock Magus · Slot 1', 'Rock Magus · Slot 2', 'Erosion Magus · Slot 3',
    ])
    act(() => { select.props.onChange({ target: { value: '2' } }) })
    expect(useBuildStore.getState().conditionState.vigilant_breeze_merged_slot).toBe('2')
    act(() => { view.unmount() })
  })
})
