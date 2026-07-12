// Small shared helpers for the build-independent `coverage`/`coverage_detail` fields the backend
// attaches to skills, hero traits, and legendary-gear-index entries. See components/CoverageBadge.tsx
// for the rendered pill and components/CoverageLegend.tsx for the explainer.

export type Coverage = 'full' | 'partial' | 'none'

// Sort rank: Full first, then Partial, then None, then unknown (older backend / not loaded) last.
export function coverageRank(coverage?: Coverage): number {
  if (coverage === 'full') return 0
  if (coverage === 'partial') return 1
  if (coverage === 'none') return 2
  return 3
}

// The "Modeled only" filter predicate — hides entries the engine doesn't model at all. Entries with no
// `coverage` (older backend / catalog not loaded yet) pass through rather than being hidden, so a load
// race or stale cache never silently drops items.
export function passesModeledOnly(coverage: Coverage | undefined, modeledOnly: boolean): boolean {
  if (!modeledOnly) return true
  return coverage !== 'none'
}
