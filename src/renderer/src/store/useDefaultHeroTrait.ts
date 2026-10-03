import { useEffect, useRef } from 'react'
import { useBuildStore } from './buildStore'
import { useReferenceStore } from './referenceStore'

// bug-291: a new build got no default hero trait if the player left the Hero Trait screen before the
// catalog had loaded — the old auto-select effect lived in HeroTraitScreen.tsx and only ran while that
// screen was mounted. This hook applies the default wherever/whenever the hero-traits catalog resolves,
// independent of which screen is showing, mirroring the old effect's own gate (a brand-new, never-saved,
// trait-less build) but no longer tied to that screen's lifecycle.
//
// Applies at most once per LOAD, not per buildId: the store's own boot state and a fresh
// (buildId===null) build from startNewBuild are otherwise indistinguishable by buildId alone, which
// let the hook latch on the boot state and then silently skip every subsequent "New build". The latch
// is keyed on buildStore's `loadGeneration` — a runtime-only counter bumped exclusively by loadBuild
// (including at boot, since the store's initial state counts as generation 0) — so each load gets its
// own chance to apply the default, while clearing the trait back out by hand (setTraitData, no
// loadGeneration bump) still does not re-trigger it.
export function useDefaultHeroTrait(onApplied: () => void): void {
  const buildId = useBuildStore((s) => s.buildId)
  const traitId = useBuildStore((s) => s.traitId)
  const loadGeneration = useBuildStore((s) => s.loadGeneration)
  const heroTraits = useReferenceStore((s) => s.heroTraits)
  const setTraitData = useBuildStore((s) => s.setTraitData)

  const appliedForRef = useRef<number>(-1)

  useEffect(() => {
    if (appliedForRef.current === loadGeneration) return
    if (buildId !== null) return
    if (traitId !== null) return
    if (!heroTraits || heroTraits.length === 0) return

    appliedForRef.current = loadGeneration
    setTraitData(heroTraits[0].trait_id, [1, 1, 1, 1], [])
    // This is a DEFAULT, not a user edit — let the caller re-baseline the dirty tracker so the fresh
    // build isn't flagged dirty by the auto-select's buildVersion bump.
    onApplied()
  }, [buildId, traitId, loadGeneration, heroTraits, setTraitData, onApplied])
}
