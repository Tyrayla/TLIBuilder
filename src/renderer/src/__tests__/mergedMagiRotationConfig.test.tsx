import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BuildOverviewScreen from '../screens/BuildOverviewScreen'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs } from '../store/uiPrefsStore'

vi.mock('../components/CustomModsPanel', () => ({ default: () => null }))

const traitConditions = [
  { key: 'vigilant_breeze_active', label: 'Vigilant (Iris Merged)', value_type: 'boolean' as const },
  { key: 'vigilant_breeze_stacks', label: 'Current Breeze Stacks', value_type: 'numeric' as const },
  { key: 'vigilant_breeze_life_consumed_pct', label: 'Warmest Vigilance Max Life Consumed', value_type: 'numeric' as const },
  { key: 'vigilant_breeze_enemies_defeated', label: 'Warmest Vigilance Enemies Defeated', value_type: 'numeric' as const },
  { key: 'vigilant_breeze_whisper_bonus_stacks', label: "Breeze's Whisper Temporary Bonus Max Breeze", value_type: 'numeric' as const },
]
const rotationConditions = [
  { key: 'vigilant_breeze_spam_base', label: 'Base Skill', default_bool: false },
  { key: 'vigilant_breeze_spam_ultimate', label: 'Ultimate', default_bool: true },
  { key: 'vigilant_breeze_spam_empower', label: 'Empower', default_bool: true },
].map(condition => ({ ...condition, value_type: 'boolean' as const }))

describe('Merged Magi Rotation in Config', () => {
  beforeEach(() => {
    useReferenceStore.setState({
      conditions: { 'Hero Trait': [
        ...traitConditions.map(condition => ({ ...condition, category: 'Hero Trait', trait_id: 'vigilant_breeze' })),
        ...rotationConditions.map(condition => ({ ...condition, category: 'Hero Trait', trait_id: 'vigilant_breeze' })),
      ] },
      referenceResolved: true,
    })
    useUiPrefs.setState({ lockAutoConditions: false, collapsiblePanels: false })
    useBuildStore.setState({ conditionState: {}, traitId: 'vigilant_breeze', computedStats: {
      ...useBuildStore.getState().computedStats,
      condition_maximums: {}, clamp_report: {}, referenced_conditions: [], auto_conditions: {},
    } as never })
  })

  it('keeps Vigilant-only conditions out of another trait and shows the merged rotation only for Vigilant Breeze', () => {
    useBuildStore.setState({ traitId: 'another_trait' })
    let otherTraitView!: TestRenderer.ReactTestRenderer
    act(() => { otherTraitView = TestRenderer.create(<BuildOverviewScreen />) })
    expect(otherTraitView.root.findAllByProps({ className: 'cond-label' })).toHaveLength(0)
    expect(otherTraitView.root.findAll(node => node.type === 'span' && node.children.join('') === 'Merged Magi Rotation')).toHaveLength(0)
    const showAll = otherTraitView.root.findAllByType('input').find(input => input.props.type === 'checkbox')!
    act(() => { showAll.props.onChange({ target: { checked: true } }) })
    expect(otherTraitView.root.findAllByProps({ className: 'cond-label' })).toHaveLength(0)
    act(() => { otherTraitView.unmount() })

    useBuildStore.setState({ traitId: 'vigilant_breeze' })
    let vigilantView!: TestRenderer.ReactTestRenderer
    act(() => { vigilantView = TestRenderer.create(<BuildOverviewScreen />) })
    const labels = vigilantView.root.findAllByProps({ className: 'cond-label' }).map(node => node.children.join(''))
    expect(labels).toContain('Vigilant (Iris Merged)')
    const rotationHeader = vigilantView.root.findAllByProps({
      className: 'cond-card-header cond-card-header--clickable',
    }).find(node => node.findAllByType('span').some(span => span.children.join('') === 'Merged Magi Rotation'))
    expect(rotationHeader?.props['aria-expanded']).toBe(false)
    act(() => { vigilantView.unmount() })
  })

  it('opens the collapsed checklist with Base off and Ultimate plus Empower on, and stores a change', () => {
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const header = view.root.findAllByProps({
      className: 'cond-card-header cond-card-header--clickable',
    }).find(node => node.findAllByType('span').some(span => span.children.join('') === 'Merged Magi Rotation'))!
    expect(header.props['aria-expanded']).toBe(false)
    const rotationPanel = header.parent!
    expect(rotationPanel.findAllByType('label').map(label => label.children.join(''))).toEqual([])

    act(() => { header.props.onClick() })
    expect(header.props['aria-expanded']).toBe(true)
    const checks = rotationPanel.findAllByProps({ className: 'cond-check' })
    expect(checks.map(input => input.props.checked)).toEqual([false, true, true])
    act(() => { checks[0].props.onChange({ target: { checked: true } }) })
    expect(useBuildStore.getState().conditionState.vigilant_breeze_spam_base).toBe(true)
    act(() => { view.unmount() })
  })
})
