// Pure allocation logic for a "tree" allocation_mode Hero Trait (currently only Selena's Dance of the
// Deep). Unlike every other Hero Trait — a fixed base node + three pick-1-of-2 tiers at levels 45/60/75 —
// this is a connected allocatable tree: the level-15 base node is the root (always active, never spendable),
// and the player earns ONE allocation point at each of character levels 45/60/75 — but ONLY when the Hero
// Memory socketed at that slot is present (matching the in-game rule; character level alone is not enough).
//
// Every function here is pure/total and defensive against malformed input (absent tree data, an
// out-of-order or partial `connections` list, an allocations array referencing an unknown node) — this
// module has no React and is imported directly by renderer tests.
import type { CreatedHeroMemory } from '../api/client'

export interface TraitTreeConnection {
  from: string
  to: string
}

// The three allocation-point character-level thresholds, in order.
export const TREE_THRESHOLDS = [45, 60, 75] as const

// Threshold → Hero Memory slot index. Mirrors HeroTraitScreen's THRESHOLD_TO_MEMORY_SLOT
// (0 = origin/lv45, 1 = discipline/lv60, 2 = progress/lv75) — kept as its own small constant here so this
// module stays a self-contained, independently-testable unit (no import from the screen).
const THRESHOLD_TO_MEMORY_SLOT: Record<number, number> = { 45: 0, 60: 1, 75: 2 }

/**
 * The subset of [45, 60, 75] where the character has reached that level AND the Hero Memory socketed at
 * that threshold's slot is present. Order preserved (ascending). The allocation-point BUDGET is this
 * array's length (0–3).
 */
export function availableThresholds(
  characterLevel: number,
  heroMemories: (CreatedHeroMemory | null | undefined)[] | null | undefined,
): number[] {
  const memories = Array.isArray(heroMemories) ? heroMemories : []
  return TREE_THRESHOLDS.filter(t => {
    if (!(characterLevel >= t)) return false
    const slot = THRESHOLD_TO_MEMORY_SLOT[t]
    return !!memories[slot]
  })
}

// Build an undirected adjacency + a root-anchored parent/children map. Direction-agnostic on purpose —
// authored `connections` are expected root→leaf ("from" closer to root), but a BFS from the root makes
// parentOf/descendantsOf correct even if a connection is ever authored the other way round.
function buildTreeMaps(
  connections: TraitTreeConnection[] | null | undefined,
  rootId: string | null | undefined,
): { parent: Map<string, string>; children: Map<string, string[]> } {
  const adj = new Map<string, Set<string>>()
  const conns = Array.isArray(connections) ? connections : []
  const touch = (id: string) => { if (!adj.has(id)) adj.set(id, new Set()) }
  for (const c of conns) {
    if (!c || typeof c.from !== 'string' || typeof c.to !== 'string') continue
    touch(c.from); touch(c.to)
    adj.get(c.from)!.add(c.to)
    adj.get(c.to)!.add(c.from)
  }
  const parent = new Map<string, string>()
  const children = new Map<string, string[]>()
  if (typeof rootId !== 'string' || !rootId) return { parent, children }
  const seen = new Set<string>([rootId])
  const queue: string[] = [rootId]
  while (queue.length) {
    const cur = queue.shift() as string
    for (const next of adj.get(cur) ?? []) {
      if (seen.has(next)) continue
      seen.add(next)
      parent.set(next, cur)
      if (!children.has(cur)) children.set(cur, [])
      children.get(cur)!.push(next)
      queue.push(next)
    }
  }
  return { parent, children }
}

/**
 * The neighbor toward the root ("parent") of `nodeId`, or null for the root itself / an unconnected or
 * unknown node. A node is allocatable only when its parent is the root or is itself allocated.
 */
export function parentOf(
  nodeId: string,
  connections: TraitTreeConnection[] | null | undefined,
  rootId: string,
): string | null {
  if (!nodeId || nodeId === rootId) return null
  return buildTreeMaps(connections, rootId).parent.get(nodeId) ?? null
}

/** Every node in `nodeId`'s subtree (its children, grandchildren, …) — NOT including `nodeId` itself. */
export function descendantsOf(
  nodeId: string,
  connections: TraitTreeConnection[] | null | undefined,
  rootId: string,
): Set<string> {
  const { children } = buildTreeMaps(connections, rootId)
  const out = new Set<string>()
  const stack: string[] = [...(children.get(nodeId) ?? [])]
  while (stack.length) {
    const id = stack.pop() as string
    if (out.has(id)) continue
    out.add(id)
    stack.push(...(children.get(id) ?? []))
  }
  return out
}

/** Whether `nodeId` can be allocated right now: not the root, not already allocated, budget remains, and
 * its parent (toward the root) is either the root or already allocated. */
export function canAllocate(
  nodeId: string,
  allocations: string[],
  connections: TraitTreeConnection[] | null | undefined,
  rootId: string,
  budget: number,
): boolean {
  if (!nodeId || nodeId === rootId) return false
  const list = Array.isArray(allocations) ? allocations : []
  if (list.includes(nodeId)) return false
  if (list.length >= budget) return false
  const parent = parentOf(nodeId, connections, rootId)
  if (parent === null) return false   // not connected to the tree (root has parent null, handled above)
  return parent === rootId || list.includes(parent)
}

/** Allocate `nodeId`, appending it to the ordered list. No-op (returns `allocations` unchanged) if
 * `canAllocate` is false. */
export function allocate(
  nodeId: string,
  allocations: string[],
  connections: TraitTreeConnection[] | null | undefined,
  rootId: string,
  budget: number,
): string[] {
  const list = Array.isArray(allocations) ? allocations : []
  if (!canAllocate(nodeId, list, connections, rootId, budget)) return list
  return [...list, nodeId]
}

/** Deallocate `nodeId`, cascading to every descendant that would become disconnected from the root
 * (i.e. every allocated node in `nodeId`'s subtree). No-op if `nodeId` isn't allocated. */
export function deallocate(
  nodeId: string,
  allocations: string[],
  connections: TraitTreeConnection[] | null | undefined,
  rootId: string,
): string[] {
  const list = Array.isArray(allocations) ? allocations : []
  if (!list.includes(nodeId)) return list
  const orphaned = descendantsOf(nodeId, connections, rootId)
  return list.filter(id => id !== nodeId && !orphaned.has(id))
}

// Drop any allocated node whose chain back to the root isn't fully intact within the CURRENT allocation
// set — a fixed-point filter so a break partway up a chain also drops everything above it.
function pruneDisconnected(
  allocations: string[],
  connections: TraitTreeConnection[] | null | undefined,
  rootId: string,
): string[] {
  const list = Array.isArray(allocations) ? allocations : []
  const kept = new Set(list)
  let changed = true
  while (changed) {
    changed = false
    for (const id of kept) {
      const parent = parentOf(id, connections, rootId)
      if (parent !== rootId && !(parent !== null && kept.has(parent))) {
        kept.delete(id)
        changed = true
      }
    }
  }
  return list.filter(id => kept.has(id))
}

/**
 * Re-validate an allocation list against a (possibly shrunken) budget and/or changed topology — called
 * whenever Hero Memories change. Drops any node no longer connected to the root, then trims from the
 * END (highest allocation-index / most-recently-allocated first) until the list fits `budget`, cascading
 * any orphaned descendants at each trim.
 */
export function reconcile(
  allocations: string[],
  connections: TraitTreeConnection[] | null | undefined,
  rootId: string,
  budget: number,
): string[] {
  let list = pruneDisconnected(allocations, connections, rootId)
  while (list.length > Math.max(0, budget)) {
    const last = list[list.length - 1]
    const next = deallocate(last, list, connections, rootId)
    // deallocate is a no-op if `last` isn't found (shouldn't happen) — guard against an infinite loop.
    if (next.length === list.length) { list = list.slice(0, -1); continue }
    list = next
  }
  return list
}

/** The threshold (45/60/75) badge for an allocated node — the threshold GRANTED by the point at its
 * allocation index, or null if `nodeId` isn't allocated or has no corresponding threshold (e.g. stale data
 * from before a budget shrink, prior to the next reconcile()). */
export function badgeFor(
  nodeId: string,
  allocations: string[],
  thresholds: number[],
): number | null {
  const list = Array.isArray(allocations) ? allocations : []
  const idx = list.indexOf(nodeId)
  if (idx < 0) return null
  return thresholds[idx] ?? null
}
