import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useDefaultHeroTrait } from '../store/useDefaultHeroTrait'
import type { HeroTrait } from '../api/client'

// bug-291: a new build got no default hero trait if the player left the Hero Trait screen before the
// catalog had loaded — HeroTraitScreen.tsx's auto-select effect only ran while that screen was
// mounted. useDefaultHeroTrait (new: src/renderer/src/store/useDefaultHeroTrait.ts) applies the
// default wherever/whenever the catalog resolves, independent of which screen is showing, and applies
// it at most once per loaded build.
//
// This module doesn't exist yet — every test below fails to import until it's created. That's the
// intended RED: the test code itself is the contract the implementing lane builds against.

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

describe('useDefaultHeroTrait (bug-291)', () => {
  beforeEach(() => {
    useBuildStore.setState(initialBuildState, true)
    useReferenceStore.setState(initialRefState, true)
  })

  it('applies the first catalog trait for a fresh build (no buildId, no traitId) once the catalog is non-empty', async () => {
    useReferenceStore.setState({ heroTraits: TRAITS })
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })

    expect(useBuildStore.getState().traitId).toBe('trait-a')
    expect(useBuildStore.getState().traitSlotLevels).toEqual([1, 1, 1, 1])
    expect(useBuildStore.getState().advancedTraitSelections).toEqual([])
    expect(onApplied).toHaveBeenCalledTimes(1)
    renderer.unmount()
  })

  it('works when the catalog arrives AFTER the hook mounts (cold start)', async () => {
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })
    expect(useBuildStore.getState().traitId).toBeNull()
    expect(onApplied).not.toHaveBeenCalled()

    await act(async () => { useReferenceStore.setState({ heroTraits: TRAITS }) })

    expect(useBuildStore.getState().traitId).toBe('trait-a')
    expect(onApplied).toHaveBeenCalledTimes(1)
    renderer.unmount()
  })

  it('applies at most once per loaded build — clearing the trait afterward does not re-trigger it', async () => {
    useReferenceStore.setState({ heroTraits: TRAITS })
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })
    expect(useBuildStore.getState().traitId).toBe('trait-a')
    expect(onApplied).toHaveBeenCalledTimes(1)

    // Player clears the trait by hand. buildId is still null (an unsaved build), so the raw gate
    // (buildId===null && traitId===null) is true again — the once-per-load latch must stop a re-apply.
    await act(async () => { useBuildStore.getState().setTraitData(null, [1, 1, 1, 1], []) })

    expect(useBuildStore.getState().traitId).toBeNull()
    expect(onApplied).toHaveBeenCalledTimes(1)
    renderer.unmount()
  })

  it('never touches a build that already has a buildId', async () => {
    useBuildStore.setState({ buildId: 'saved-build-1' })
    useReferenceStore.setState({ heroTraits: TRAITS })
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })

    expect(useBuildStore.getState().traitId).toBeNull()
    expect(onApplied).not.toHaveBeenCalled()
    renderer.unmount()
  })

  it('never touches a build whose traitId is already set', async () => {
    useBuildStore.setState({ traitId: 'trait-b' })
    useReferenceStore.setState({ heroTraits: TRAITS })
    const onApplied = vi.fn()

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => { renderer = TestRenderer.create(<Harness onApplied={onApplied} />) })

    expect(useBuildStore.getState().traitId).toBe('trait-b')
    expect(onApplied).not.toHaveBeenCalled()
    renderer.unmount()
  })
})
