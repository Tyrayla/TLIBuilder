import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { useBuildStore, type LoadedBuild } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useDefaultHeroTrait } from '../store/useDefaultHeroTrait'
import type { HeroTrait } from '../api/client'

// bug-291 (new-build case): App.tsx's startNewBuild (~line 438) calls
// useBuildStore.getState().loadBuild({..., buildId: null, traitId: null, ...}) to hand the player a
// fresh build. useDefaultHeroTrait's latch (appliedForRef) is keyed on buildId — and the store's
// initial boot state is ALSO buildId===null/traitId===null. So the hook applies its default once at
// boot, latches on `null`, and then startNewBuild's loadBuild (still buildId===null) is silently
// ignored: the fresh build never gets a default trait. Two consecutive "New build" clicks hit the
// exact same gap.
//
// The fresh-build payload below mirrors what startNewBuild hands to loadBuild: a full LoadedBuild
// literal with buildId/traitId null, built off the store's own DEFAULT_BUILD shape (traitSlotLevels
// [1,1,1,1], no trait selected yet).
function freshBuildPayload(): LoadedBuild {
  return {
    buildId: null,
    buildName: '',
    activeSlot: 0,
    slots: [null, null, null, null],
    slates: [],
    slateInventory: [],
    prisms: [],
    prismInventory: [],
    conditionState: {},
    gear: [],
    skills: [],
    characterLevel: 100,
    traitId: null,
    traitSlotLevels: [1, 1, 1, 1],
    advancedTraitSelections: [],
    traitTreeAllocations: [],
    traitSkillSupports: [],
    licoricePreparedSkill: null,
    elixirIngredients: {},
    heroMemories: [null, null, null],
    baseMemory: null,
    memoryInventory: [],
    pactSpirits: [null, null, null],
    fates: {},
    undetermined: [null, null, null],
    notes: '',
    customMods: [],
    targetConfig: useBuildStore.getState().targetConfig,
    enemyConfig: useBuildStore.getState().enemyConfig,
    loadouts: useBuildStore.getState().loadouts,
    activeLoadoutId: useBuildStore.getState().activeLoadoutId,
  }
}

const TRAIT_A: HeroTrait = {
  trait_id: 'trait-a', hero: 'Selena', variant_name: 'Dance of the Deep', description: '',
  levels: [], artificial_moon: { description: '', effects: [] }, advanced_traits: [],
}
const TRAIT_B: HeroTrait = {
  trait_id: 'trait-b', hero: 'Rehan', variant_name: 'Boundless Fury', description: '',
  levels: [], artificial_moon: { description: '', effects: [] }, advanced_traits: [],
}
const TRAITS: HeroTrait[] = [TRAIT_A, TRAIT_B]

function Harness({ onApplied }: { onApplied: () => void }) {
  useDefaultHeroTrait(onApplied)
  return null
}

const initialBuildState = useBuildStore.getState()
const initialRefState = useReferenceStore.getState()

describe('useDefaultHeroTrait — new-build case (bug-291)', () => {
  beforeEach(() => {
    useBuildStore.setState(initialBuildState, true)
    useReferenceStore.setState(initialRefState, true)
  })

  it('applies the default again to a fresh loadBuild after the hook already latched on boot state', async () => {
    useReferenceStore.setState({ heroTraits: TRAITS })
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })

    // Latches on the boot state (buildId===null) exactly like the existing spec's first test.
    expect(useBuildStore.getState().traitId).toBe('trait-a')
    expect(onApplied).toHaveBeenCalledTimes(1)

    // startNewBuild() calls loadBuild with a fresh, trait-less payload — buildId is still null.
    await act(async () => { useBuildStore.getState().loadBuild(freshBuildPayload()) })

    expect(useBuildStore.getState().traitId).toBe('trait-a')
    expect(useBuildStore.getState().traitSlotLevels).toEqual([1, 1, 1, 1])
    expect(onApplied).toHaveBeenCalledTimes(2)
    renderer.unmount()
  })

  it('applies the default on each of two consecutive fresh loadBuild calls', async () => {
    useReferenceStore.setState({ heroTraits: TRAITS })
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })
    expect(onApplied).toHaveBeenCalledTimes(1)

    // First "New build".
    await act(async () => { useBuildStore.getState().loadBuild(freshBuildPayload()) })
    expect(useBuildStore.getState().traitId).toBe('trait-a')
    expect(onApplied).toHaveBeenCalledTimes(2)

    // Player picks a different trait on this fresh build.
    await act(async () => { useBuildStore.getState().setTraitData('trait-b', [1, 1, 1, 1], []) })
    expect(useBuildStore.getState().traitId).toBe('trait-b')

    // Second "New build" — must get the default again, not stay latched from the first.
    await act(async () => { useBuildStore.getState().loadBuild(freshBuildPayload()) })
    expect(useBuildStore.getState().traitId).toBe('trait-a')
    expect(onApplied).toHaveBeenCalledTimes(3)
    renderer.unmount()
  })

  it('still applies at most once per load — clearing the trait afterward does not re-trigger it', async () => {
    useReferenceStore.setState({ heroTraits: TRAITS })
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })

    await act(async () => { useBuildStore.getState().loadBuild(freshBuildPayload()) })
    expect(useBuildStore.getState().traitId).toBe('trait-a')
    expect(onApplied).toHaveBeenCalledTimes(2)

    await act(async () => { useBuildStore.getState().setTraitData(null, [1, 1, 1, 1], []) })

    expect(useBuildStore.getState().traitId).toBeNull()
    expect(onApplied).toHaveBeenCalledTimes(2)
    renderer.unmount()
  })

  it('never applies to a loaded saved build (buildId set, traitId null)', async () => {
    useReferenceStore.setState({ heroTraits: TRAITS })
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })
    expect(onApplied).toHaveBeenCalledTimes(1)

    await act(async () => {
      useBuildStore.getState().loadBuild({ ...freshBuildPayload(), buildId: 'saved-1', traitId: null })
    })

    expect(useBuildStore.getState().traitId).toBeNull()
    expect(onApplied).toHaveBeenCalledTimes(1)
    renderer.unmount()
  })
})
