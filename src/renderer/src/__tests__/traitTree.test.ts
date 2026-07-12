import { describe, it, expect } from 'vitest'
import {
  TREE_THRESHOLDS,
  availableThresholds,
  parentOf,
  descendantsOf,
  canAllocate,
  allocate,
  deallocate,
  reconcile,
  badgeFor,
} from '../utils/traitTree'
import type { TraitTreeConnection } from '../utils/traitTree'
import type { CreatedHeroMemory } from '../api/client'

// ── Fixture: real Dance of the Deep topology (data/seasons/SS13/_hero_traits.json) ─────────────
// dance_of_the_deep (root)
//   -> silencing_severance -> drenched_hem
//   -> the_paradise -> the_cycle
//   -> crimson_endless_dance
//   -> dreambreakers_gyre -> layered_hem -> lonely_ensemble
const ROOT = 'dance_of_the_deep'
const CONNECTIONS: TraitTreeConnection[] = [
  { from: 'dance_of_the_deep', to: 'silencing_severance' },
  { from: 'silencing_severance', to: 'drenched_hem' },
  { from: 'dance_of_the_deep', to: 'the_paradise' },
  { from: 'the_paradise', to: 'the_cycle' },
  { from: 'dance_of_the_deep', to: 'crimson_endless_dance' },
  { from: 'dance_of_the_deep', to: 'dreambreakers_gyre' },
  { from: 'dreambreakers_gyre', to: 'layered_hem' },
  { from: 'layered_hem', to: 'lonely_ensemble' },
]

function memory(): CreatedHeroMemory {
  return {
    memoryType: 'origin',
    rarity: 'normal',
    baseStat: null,
    fixedAffixes: [null, null],
    randomAffixes: [null, null],
  }
}

describe('availableThresholds', () => {
  it('no memories socketed -> [] (budget 0) even at high character level', () => {
    expect(availableThresholds(100, [null, null, null])).toEqual([])
    expect(availableThresholds(100, [])).toEqual([])
    expect(availableThresholds(100, null)).toEqual([])
    expect(availableThresholds(100, undefined)).toEqual([])
  })

  it('only origin(45) + progress(75) socketed -> [45, 75] (budget 2)', () => {
    expect(availableThresholds(100, [memory(), null, memory()])).toEqual([45, 75])
  })

  it('all three socketed at character level 90 -> [45, 60, 75]', () => {
    expect(availableThresholds(90, [memory(), memory(), memory()])).toEqual([45, 60, 75])
  })

  it('character level below a threshold excludes it even when the memory is socketed', () => {
    // Level 60: 45 and 60 reached, 75 not — even though all three slots are socketed.
    expect(availableThresholds(60, [memory(), memory(), memory()])).toEqual([45, 60])
    // Level 44: none reached yet.
    expect(availableThresholds(44, [memory(), memory(), memory()])).toEqual([])
  })

  it('TREE_THRESHOLDS is the frozen ascending triple', () => {
    expect(TREE_THRESHOLDS).toEqual([45, 60, 75])
  })
})

describe('parentOf', () => {
  it('root has no parent', () => {
    expect(parentOf(ROOT, CONNECTIONS, ROOT)).toBeNull()
  })

  it('direct child of root', () => {
    expect(parentOf('silencing_severance', CONNECTIONS, ROOT)).toBe(ROOT)
    expect(parentOf('crimson_endless_dance', CONNECTIONS, ROOT)).toBe(ROOT)
  })

  it('deeper chain', () => {
    expect(parentOf('drenched_hem', CONNECTIONS, ROOT)).toBe('silencing_severance')
    expect(parentOf('lonely_ensemble', CONNECTIONS, ROOT)).toBe('layered_hem')
  })

  it('unknown node id -> null', () => {
    expect(parentOf('not_a_real_node', CONNECTIONS, ROOT)).toBeNull()
  })
})

describe('descendantsOf', () => {
  it('leaf has no descendants', () => {
    expect(descendantsOf('drenched_hem', CONNECTIONS, ROOT)).toEqual(new Set())
    expect(descendantsOf('crimson_endless_dance', CONNECTIONS, ROOT)).toEqual(new Set())
  })

  it('mid-chain node includes everything below it, not itself', () => {
    const desc = descendantsOf('dreambreakers_gyre', CONNECTIONS, ROOT)
    expect(desc).toEqual(new Set(['layered_hem', 'lonely_ensemble']))
    expect(desc.has('dreambreakers_gyre')).toBe(false)
  })

  it('root includes the whole tree', () => {
    const desc = descendantsOf(ROOT, CONNECTIONS, ROOT)
    expect(desc).toEqual(new Set([
      'silencing_severance', 'drenched_hem',
      'the_paradise', 'the_cycle',
      'crimson_endless_dance',
      'dreambreakers_gyre', 'layered_hem', 'lonely_ensemble',
    ]))
  })
})

describe('canAllocate', () => {
  it('rejects a node whose parent is not yet allocated', () => {
    expect(canAllocate('drenched_hem', [], CONNECTIONS, ROOT, 3)).toBe(false)
    expect(canAllocate('lonely_ensemble', [], CONNECTIONS, ROOT, 3)).toBe(false)
    expect(canAllocate('lonely_ensemble', ['dreambreakers_gyre'], CONNECTIONS, ROOT, 3)).toBe(false)
  })

  it('accepts a direct child of root', () => {
    expect(canAllocate('silencing_severance', [], CONNECTIONS, ROOT, 3)).toBe(true)
    expect(canAllocate('crimson_endless_dance', [], CONNECTIONS, ROOT, 3)).toBe(true)
  })

  it('accepts a child of an already-allocated node', () => {
    expect(canAllocate('drenched_hem', ['silencing_severance'], CONNECTIONS, ROOT, 3)).toBe(true)
    expect(canAllocate('lonely_ensemble', ['dreambreakers_gyre', 'layered_hem'], CONNECTIONS, ROOT, 3)).toBe(true)
  })

  it('rejects the root itself', () => {
    expect(canAllocate(ROOT, [], CONNECTIONS, ROOT, 3)).toBe(false)
  })

  it('rejects when budget is exhausted', () => {
    expect(canAllocate('the_paradise', ['silencing_severance', 'crimson_endless_dance'], CONNECTIONS, ROOT, 2)).toBe(false)
  })

  it('rejects an already-allocated node', () => {
    expect(canAllocate('silencing_severance', ['silencing_severance'], CONNECTIONS, ROOT, 3)).toBe(false)
  })
})

describe('allocate', () => {
  it('appends in order', () => {
    let list: string[] = []
    list = allocate('silencing_severance', list, CONNECTIONS, ROOT, 3)
    list = allocate('drenched_hem', list, CONNECTIONS, ROOT, 3)
    expect(list).toEqual(['silencing_severance', 'drenched_hem'])
  })

  it('respects the budget cap — no-op past it', () => {
    let list: string[] = ['silencing_severance', 'crimson_endless_dance']
    list = allocate('the_paradise', list, CONNECTIONS, ROOT, 2)
    expect(list).toEqual(['silencing_severance', 'crimson_endless_dance'])
  })

  it('no-op when the node cannot be allocated (parent gate)', () => {
    const list = allocate('drenched_hem', [], CONNECTIONS, ROOT, 3)
    expect(list).toEqual([])
  })
})

describe('badgeFor — "down the middle" chain', () => {
  const CHAIN = ['dreambreakers_gyre', 'layered_hem', 'lonely_ensemble']

  it('3 points, all thresholds available -> 45/60/75 in allocation order', () => {
    expect(badgeFor('dreambreakers_gyre', CHAIN, [45, 60, 75])).toBe(45)
    expect(badgeFor('layered_hem', CHAIN, [45, 60, 75])).toBe(60)
    expect(badgeFor('lonely_ensemble', CHAIN, [45, 60, 75])).toBe(75)
  })

  it('only [45, 75] available -> two allocations badge 45 then 75 (NOT 45/60)', () => {
    const twoAllocated = ['dreambreakers_gyre', 'layered_hem']
    expect(badgeFor('dreambreakers_gyre', twoAllocated, [45, 75])).toBe(45)
    expect(badgeFor('layered_hem', twoAllocated, [45, 75])).toBe(75)
  })

  it('unallocated node -> null', () => {
    expect(badgeFor('lonely_ensemble', ['dreambreakers_gyre'], [45, 60, 75])).toBeNull()
  })

  it('allocation index beyond the thresholds array -> null (stale data before a reconcile)', () => {
    expect(badgeFor('lonely_ensemble', CHAIN, [45])).toBeNull()
  })
})

describe('deallocate cascade', () => {
  it('removing a mid-chain node cascades to remove every allocated descendant', () => {
    const allocated = ['dreambreakers_gyre', 'layered_hem', 'lonely_ensemble']
    const result = deallocate('dreambreakers_gyre', allocated, CONNECTIONS, ROOT)
    expect(result).toEqual([])
  })

  it('removing a leaf removes only the leaf', () => {
    const allocated = ['dreambreakers_gyre', 'layered_hem', 'lonely_ensemble']
    const result = deallocate('lonely_ensemble', allocated, CONNECTIONS, ROOT)
    expect(result).toEqual(['dreambreakers_gyre', 'layered_hem'])
  })

  it('unrelated branches are untouched by a cascade elsewhere', () => {
    const allocated = ['silencing_severance', 'dreambreakers_gyre', 'layered_hem']
    const result = deallocate('dreambreakers_gyre', allocated, CONNECTIONS, ROOT)
    expect(result).toEqual(['silencing_severance'])
  })

  it('no-op if the node is not allocated', () => {
    const allocated = ['silencing_severance']
    expect(deallocate('drenched_hem', allocated, CONNECTIONS, ROOT)).toEqual(allocated)
  })
})

describe('reconcile', () => {
  it('trims from the end (last-allocated first) when budget shrinks, no orphans to cascade', () => {
    const allocated = ['silencing_severance', 'crimson_endless_dance', 'the_paradise']
    const result = reconcile(allocated, CONNECTIONS, ROOT, 2)
    expect(result).toEqual(['silencing_severance', 'crimson_endless_dance'])
  })

  it('trimming the last-allocated node cascades its own orphaned descendants', () => {
    // Allocated down the middle chain, budget shrinks from 3 to 2: the last-allocated
    // (lonely_ensemble) is trimmed; its removal has no descendants so nothing else cascades.
    const allocated = ['dreambreakers_gyre', 'layered_hem', 'lonely_ensemble']
    const result = reconcile(allocated, CONNECTIONS, ROOT, 2)
    expect(result).toEqual(['dreambreakers_gyre', 'layered_hem'])
  })

  it('trimming a node whose descendants were allocated OUT OF chain order cascades them too', () => {
    // last-allocated is the mid node (layered_hem allocated after lonely_ensemble is impossible by
    // adjacency, so instead exercise: dreambreakers_gyre allocated last, but with a descendant
    // present — impossible under normal allocate() ordering, but reconcile must be robust to any
    // allocations array, e.g. one rehydrated from an edited/older build).
    const allocated = ['layered_hem', 'lonely_ensemble', 'dreambreakers_gyre']
    const result = reconcile(allocated, CONNECTIONS, ROOT, 2)
    // last element is 'dreambreakers_gyre' -> removing it orphans layered_hem + lonely_ensemble too
    expect(result).toEqual([])
  })

  it('drops disconnected nodes (parent no longer present) regardless of budget', () => {
    // drenched_hem's parent (silencing_severance) isn't in the list at all — malformed/edited data.
    const allocated = ['drenched_hem', 'crimson_endless_dance']
    const result = reconcile(allocated, CONNECTIONS, ROOT, 3)
    expect(result).toEqual(['crimson_endless_dance'])
  })

  it('re-badging after reconcile reflects the new available thresholds', () => {
    const allocated = ['dreambreakers_gyre', 'layered_hem', 'lonely_ensemble']
    const reconciled = reconcile(allocated, CONNECTIONS, ROOT, 2)
    const newThresholds = [45, 75] // e.g. the lv60 memory got un-socketed
    expect(badgeFor('dreambreakers_gyre', reconciled, newThresholds)).toBe(45)
    expect(badgeFor('layered_hem', reconciled, newThresholds)).toBe(75)
  })

  it('budget of 0 empties the list entirely', () => {
    const allocated = ['silencing_severance', 'drenched_hem']
    expect(reconcile(allocated, CONNECTIONS, ROOT, 0)).toEqual([])
  })

  it('no-op when already within budget and fully connected', () => {
    const allocated = ['silencing_severance', 'drenched_hem']
    expect(reconcile(allocated, CONNECTIONS, ROOT, 3)).toEqual(allocated)
  })
})

describe('defensive / malformed input', () => {
  it('null/empty connections do not throw', () => {
    expect(() => parentOf('silencing_severance', null, ROOT)).not.toThrow()
    expect(() => parentOf('silencing_severance', undefined, ROOT)).not.toThrow()
    expect(() => parentOf('silencing_severance', [], ROOT)).not.toThrow()
    expect(parentOf('silencing_severance', [], ROOT)).toBeNull()
    expect(descendantsOf(ROOT, null, ROOT)).toEqual(new Set())
    expect(canAllocate('silencing_severance', [], null, ROOT, 3)).toBe(false)
    expect(allocate('silencing_severance', [], undefined, ROOT, 3)).toEqual([])
    expect(deallocate('silencing_severance', [], null, ROOT)).toEqual([])
    expect(reconcile([], null, ROOT, 3)).toEqual([])
  })

  it('unknown node ids do not throw and behave as disconnected', () => {
    expect(() => canAllocate('totally_unknown', [], CONNECTIONS, ROOT, 3)).not.toThrow()
    expect(canAllocate('totally_unknown', [], CONNECTIONS, ROOT, 3)).toBe(false)
    expect(parentOf('totally_unknown', CONNECTIONS, ROOT)).toBeNull()
    expect(descendantsOf('totally_unknown', CONNECTIONS, ROOT)).toEqual(new Set())
    expect(deallocate('totally_unknown', ['silencing_severance'], CONNECTIONS, ROOT)).toEqual(['silencing_severance'])
  })

  it('root passed as a node argument does not throw and is never allocatable', () => {
    expect(() => canAllocate(ROOT, [ROOT as string], CONNECTIONS, ROOT, 3)).not.toThrow()
    expect(canAllocate(ROOT, [], CONNECTIONS, ROOT, 3)).toBe(false)
    expect(allocate(ROOT, [], CONNECTIONS, ROOT, 3)).toEqual([])
    expect(parentOf(ROOT, CONNECTIONS, ROOT)).toBeNull()
  })

  it('malformed connection entries (missing from/to) are ignored, not thrown', () => {
    const badConns = [
      { from: 'dance_of_the_deep', to: 'silencing_severance' },
      { from: 'silencing_severance' } as unknown as TraitTreeConnection,
      null as unknown as TraitTreeConnection,
      { to: 'nowhere' } as unknown as TraitTreeConnection,
    ]
    expect(() => canAllocate('silencing_severance', [], badConns, ROOT, 3)).not.toThrow()
    expect(canAllocate('silencing_severance', [], badConns, ROOT, 3)).toBe(true)
  })

  it('empty allocations array with badgeFor on an unallocated node returns null, not a crash', () => {
    expect(badgeFor('silencing_severance', [], [45, 60, 75])).toBeNull()
  })
})
