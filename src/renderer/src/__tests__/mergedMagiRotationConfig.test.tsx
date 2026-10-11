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
  { key: 'vigilant_breeze_merged_slot', label: 'Merged Magus', value_type: 'enum' as const,
    enum_values: [], default_enum: '', options_source: 'spirit_magus_slots' },
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
      condition_maximums: {}, clamp_report: {}, referenced_conditions: [], auto_conditions: {}, main_skill_slot: null,
    } as never })
  })

  it('keeps Vigilant-only conditions out of another trait and shows the merged rotation only for Vigilant Breeze', () => {
    useBuildStore.setState({ traitId: 'another_trait', skills: [{
      slot: 2, item_id: 'summon_rock_magus', name: 'Rock Magus', level: 20,
      skill_tags: ['Spirit Magus'], description_lines: [], supports: [],
    }] as never })
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
    const rotationButton = vigilantView.root.findAllByType('button')
      .find(node => node.findAllByType('span').some(span => span.children.join('') === 'Merged Magi Rotation'))
    expect(rotationButton?.props['aria-expanded']).toBe(false)
    expect(rotationButton?.parent?.props.className).toBe('merged-magi-rotation')
    const containingCards = vigilantView.root.findAllByProps({ className: 'cond-card' })
      .filter(card => card.findAllByType('button').includes(rotationButton!))
    expect(containingCards).toHaveLength(1)
    act(() => { vigilantView.unmount() })
  })

  it('opens the collapsed checklist with Base off and Ultimate plus Empower on, and stores a change', () => {
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const button = view.root.findAllByType('button')
      .find(node => node.findAllByType('span').some(span => span.children.join('') === 'Merged Magi Rotation'))!
    expect(button.props['aria-expanded']).toBe(false)
    expect(button.parent?.props.className).toBe('merged-magi-rotation')
    expect(view.root.findAllByProps({ className: 'cond-card' }).filter(card =>
      card.findAllByType('button').includes(button),
    )).toHaveLength(1)

    act(() => { button.props.onClick() })
    expect(button.props['aria-expanded']).toBe(true)
    const checks = button.parent!.findAllByProps({ className: 'cond-check' })
    expect(checks.map(input => input.props.checked)).toEqual([false, true, true])
    act(() => { checks[0].props.onChange({ target: { checked: true } }) })
    expect(useBuildStore.getState().conditionState.vigilant_breeze_spam_base).toBe(true)
    act(() => { view.unmount() })
  })

  it('lists Magus options by slot, defaults to the first slotted Magus, and stores the chosen slot', () => {
    const equipped = (slot: number, item_id: string, name: string, enabled = true) => ({
      slot, item_id, name, level: 20, enabled, skill_tags: ['Spirit Magus'], description_lines: [], supports: [],
    })
    useBuildStore.setState({
      skills: [
        equipped(1, 'summon_rock_magus', 'Rock Magus'),
        equipped(2, 'summon_rock_magus', 'Rock Magus'),
        equipped(3, 'summon_erosion_magus', 'Erosion Magus'),
        equipped(5, 'summon_rock_magus', 'Disabled Rock Magus', false),
        equipped(6, 'summon_rock_magus', 'Passive Rock Magus'),
      ] as never,
      conditionState: { vigilant_breeze_merged_slot: '9' },
    })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })

    const select = view.root.findAllByType('select').find(node =>
      node.findAllByType('option').some(option => option.props.children === 'Rock Magus · Slot 1'),
    )!
    expect(select.props.value).toBe('1')
    expect(select.findAllByType('option').map(option => option.props.children)).toEqual([
      'Rock Magus · Slot 1', 'Rock Magus · Slot 2', 'Erosion Magus · Slot 3',
    ])
    act(() => { select.props.onChange({ target: { value: '2' } }) })
    expect(useBuildStore.getState().conditionState.vigilant_breeze_merged_slot).toBe('2')
    act(() => { view.unmount() })
  })

  it('hides the selector when the build has no slotted Spirit Magi', () => {
    useBuildStore.setState({ skills: [] })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    expect(view.root.findAllByProps({ className: 'cond-label' }).map(node => node.children.join('')))
      .not.toContain('Merged Magus')
    act(() => { view.unmount() })
  })

  it('defaults to the main skill when it is a Magus in a later active slot', () => {
    const equipped = (slot: number, item_id: string, name: string) => ({
      slot, item_id, name, level: 20, skill_tags: ['Spirit Magus'], description_lines: [], supports: [],
    })
    useBuildStore.setState({
      skills: [
        equipped(2, 'summon_rock_magus', 'Rock Magus'),
        equipped(4, 'summon_erosion_magus', 'Erosion Magus'),
      ] as never,
      mainSkill: { skill_id: 'summon_erosion_magus', level: 20 } as never,
      conditionState: {},
    })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const select = view.root.findAllByType('select').find(node =>
      node.findAllByType('option').some(option => option.props.children === 'Erosion Magus · Slot 4'),
    )!
    expect(select.props.value).toBe('4')
    act(() => { view.unmount() })
  })

  it('uses the engine-selected main slot when duplicate Magi share the same item id', () => {
    const equipped = (slot: number) => ({
      slot, item_id: 'summon_rock_magus', name: 'Rock Magus', level: 20,
      skill_tags: ['Spirit Magus'], description_lines: [], supports: [],
    })
    useBuildStore.setState({
      skills: [equipped(1), equipped(2)] as never,
      mainSkill: { skill_id: 'summon_rock_magus', level: 20 } as never,
      computedStats: { ...useBuildStore.getState().computedStats, main_skill_slot: 2 },
      conditionState: {},
    })
    let view!: TestRenderer.ReactTestRenderer
    act(() => { view = TestRenderer.create(<BuildOverviewScreen />) })
    const select = view.root.findAllByType('select').find(node =>
      node.findAllByType('option').some(option => option.props.children === 'Rock Magus · Slot 2'),
    )!
    expect(select.props.value).toBe('2')
    act(() => { view.unmount() })
  })
})
