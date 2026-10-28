import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BuildOverviewScreen from '../screens/BuildOverviewScreen'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs } from '../store/uiPrefsStore'

vi.mock('../components/CustomModsPanel', () => ({ default: () => null }))

describe('Config condition search', () => {
  beforeEach(() => {
    useReferenceStore.setState({
      conditions: {
        Character: [{ key: 'character_level', label: 'Character Level', category: 'Character', value_type: 'numeric' }],
        Enemy: [{ key: 'enemy_is_ignited', label: 'Enemy is Ignited', category: 'Enemy', value_type: 'boolean' }],
      },
      referenceResolved: true,
    })
    useUiPrefs.setState({ lockAutoConditions: false, collapsiblePanels: false })
    useBuildStore.setState({
      conditionState: {},
      traitId: '',
      skills: [],
      mainSkill: null,
      computedStats: {
        ...useBuildStore.getState().computedStats,
        condition_maximums: {}, clamp_report: {}, referenced_conditions: [], auto_conditions: {}, main_skill_slot: null,
      } as never,
    })
  })

  it('shows the empty-result message when fixed Character and Enemy panels have no matching conditions', () => {
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })

    const search = view.root.findByProps({ 'aria-label': 'Search config conditions' })
    act(() => { search.props.onChange({ target: { value: 'no-such-condition' } }) })

    expect(view.root.findAll(node => node.props.className === 'panel-empty'
      && node.children.join('') === 'No conditions match “no-such-condition”.')).toHaveLength(1)
    expect(view.root.findAllByProps({ className: 'cond-label' })).toHaveLength(0)

    act(() => { view.unmount() })
  })
})
