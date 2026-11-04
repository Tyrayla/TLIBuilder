// Session cache for talent-tree data and the Ethereal Prism catalog.
//
// Trees and the prism catalog are season-static, but they aren't part of the reference store, and
// TreeViewerScreen used to refetch both on EVERY tree open. On web that request goes through the
// serialized Pyodide worker, so a tree click could sit behind an in-flight stats recompute and show the
// loading spinner for about a second, even for a tree already viewed. This module keeps one promise per tree
// (deduping concurrent callers), exposes the resolved value synchronously so a cached tree renders on
// the first frame, and supports a background prefetch. A failed fetch is evicted so a retry refetches.
// Cleared on season change (App's DevTools onSeasonChange), alongside the reference/mapping stores.
// Every caller shares the same cached TreeData / catalog objects: treat them as READ-ONLY (copy before mutating).
import { api, type TreeData } from './client'

type PrismCatalog = Awaited<ReturnType<typeof api.getEtherealPrism>>

const treePromises = new Map<string, Promise<TreeData>>()
const treeValues = new Map<string, TreeData>()
let prismPromise: Promise<PrismCatalog> | null = null
let prismValue: PrismCatalog | null = null
// Bumped by clearTreeCache so a fetch started before a season change can't repopulate the new season's cache.
let generation = 0

export function getTreeCached(name: string): Promise<TreeData> {
  const existing = treePromises.get(name)
  if (existing) return existing
  const gen = generation
  const p = api.getTree(name).then(
    data => {
      if (gen === generation) treeValues.set(name, data)
      return data
    },
    err => {
      if (gen === generation && treePromises.get(name) === p) treePromises.delete(name)
      throw err
    },
  )
  treePromises.set(name, p)
  return p
}

/** The already-resolved tree, if any — lets a screen render a cached tree without a loading frame. */
export function peekTree(name: string): TreeData | undefined {
  return treeValues.get(name)
}

export function getEtherealPrismCached(): Promise<PrismCatalog> {
  if (prismPromise) return prismPromise
  const gen = generation
  const p = api.getEtherealPrism().then(
    data => {
      if (gen === generation) prismValue = data
      return data
    },
    err => {
      if (gen === generation && prismPromise === p) prismPromise = null
      throw err
    },
  )
  prismPromise = p
  return p
}

export function peekEtherealPrism(): PrismCatalog | null {
  return prismValue
}

/**
 * Warm the cache for the given trees, one request at a time so the prefetch never floods the single
 * backend / Pyodide worker queue ahead of user-driven requests. `shouldContinue` is re-checked before each
 * fetch so a caller can stop a long prefetch (e.g. when the player edits and a recalc starts). Failures are
 * swallowed (a real open retries).
 */
export async function prefetchTrees(names: string[], shouldContinue: () => boolean = () => true): Promise<void> {
  const gen = generation
  for (const name of names) {
    if (gen !== generation || !shouldContinue()) return
    if (treeValues.has(name)) continue
    await getTreeCached(name).catch(() => {})
  }
}

export function clearTreeCache(): void {
  generation++
  treePromises.clear()
  treeValues.clear()
  prismPromise = null
  prismValue = null
}
