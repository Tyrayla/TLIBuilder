import { describe, it, expect } from 'vitest'
import { nodeThreshold, diffAdded, diffRemoved, nodeStatesSignature } from '../utils/passiveTreeDiff'

describe('nodeThreshold', () => {
  it('is 1 for a Legendary Medium Talent', () => {
    expect(nodeThreshold({ node_type: 'Legendary Medium Talent' })).toBe(1)
  })

  it('is 3 for a Medium Talent', () => {
    expect(nodeThreshold({ node_type: 'Medium Talent' })).toBe(3)
  })

  it('is 3 for a Micro Talent', () => {
    expect(nodeThreshold({ node_type: 'Micro Talent' })).toBe(3)
  })

  it('is 3 for an unrecognized node_type (falls to the else branch)', () => {
    expect(nodeThreshold({ node_type: 'something-unexpected' })).toBe(3)
  })

  // Pins the exact finding that started the fix round: threshold is derived from node_type ALONE and
  // must stay independent of max_points. Mirrors backend/tests/test_passive_tree.py's
  // test_deallocate_source_above_threshold_ok (max_points=5, threshold=3) — no shipped tree has a node
  // like this today, which is exactly why this needs its own test rather than trusting live data to
  // exercise it. A node whose max_points equals its own threshold would let `thr === max_points` quietly
  // pass; this one diverges on purpose so that false invariant can never sneak back in.
  it('is independent of max_points — a divergent node (max_points=5) still gets threshold 3, not 5', () => {
    const divergent = { node_type: 'Medium Talent', max_points: 5 }
    expect(nodeThreshold(divergent)).toBe(3)
    expect(nodeThreshold(divergent)).not.toBe(divergent.max_points)
  })

  it('is independent of max_points on the legendary branch too — max_points=1 does not make threshold 1 "by coincidence" of matching', () => {
    // Legendary nodes are max_points=1 in every shipped tree, so threshold(1) === max_points(1) here.
    // This case exists to document that the equality is coincidental to shipped data, not derived from
    // max_points — the function reads node_type only and never inspects max_points at all.
    const legendary = { node_type: 'Legendary Medium Talent', max_points: 1 }
    expect(nodeThreshold(legendary)).toBe(1)
    const divergentLegendary = { node_type: 'Legendary Medium Talent', max_points: 4 }
    expect(nodeThreshold(divergentLegendary)).toBe(1)
  })
})

describe('diffAdded', () => {
  it('returns empty for an empty before and empty after (true no-op)', () => {
    expect(diffAdded({}, {})).toEqual({})
  })

  it('returns empty when before and after are identical non-empty maps (no-op diff)', () => {
    const state = { node_a: 2, node_b: 3 }
    expect(diffAdded(state, { ...state })).toEqual({})
  })

  it('treats a key present only in before (absent from after) as not added', () => {
    // after[id] is undefined -> a is undefined -> `a > b` is false for any b, so it's excluded, not NaN'd in.
    expect(diffAdded({ node_a: 3 }, {})).toEqual({})
  })

  it('treats a key present only in after (absent from before) as fully added, defaulting before to 0', () => {
    expect(diffAdded({}, { node_a: 2 })).toEqual({ node_a: 2 })
  })

  it('reports only the positive delta for a key present in both, increased', () => {
    expect(diffAdded({ node_a: 1 }, { node_a: 3 })).toEqual({ node_a: 2 })
  })

  it('omits a key present in both but decreased (that is diffRemoved\'s job)', () => {
    expect(diffAdded({ node_a: 3 }, { node_a: 1 })).toEqual({})
  })

  it('handles a mixed map: added, removed, unchanged, and after-only keys together', () => {
    const before = { grew: 1, shrank: 3, same: 2 }
    const after = { grew: 2, shrank: 1, same: 2, brandNew: 1 }
    expect(diffAdded(before, after)).toEqual({ grew: 1, brandNew: 1 })
  })
})

describe('diffRemoved', () => {
  it('returns empty for an empty before and empty after (true no-op)', () => {
    expect(diffRemoved({}, {})).toEqual({})
  })

  it('returns empty when before and after are identical non-empty maps (no-op diff)', () => {
    const state = { node_a: 2, node_b: 3 }
    expect(diffRemoved(state, { ...state })).toEqual({})
  })

  it('treats a key present only in before (absent from after) as fully removed, defaulting after to 0', () => {
    expect(diffRemoved({ node_a: 3 }, {})).toEqual({ node_a: 3 })
  })

  it('treats a key present only in after (absent from before) as not removed', () => {
    // before[id] is undefined here since we iterate before's keys only, so an after-only key never
    // appears in the output at all.
    expect(diffRemoved({}, { node_a: 2 })).toEqual({})
  })

  it('reports only the negative delta for a key present in both, decreased', () => {
    expect(diffRemoved({ node_a: 3 }, { node_a: 1 })).toEqual({ node_a: 2 })
  })

  it('omits a key present in both but increased (that is diffAdded\'s job)', () => {
    expect(diffRemoved({ node_a: 1 }, { node_a: 3 })).toEqual({})
  })

  it('handles a mixed map: added, removed, unchanged, and before-only keys together', () => {
    const before = { grew: 1, shrank: 3, same: 2, droppedEntirely: 4 }
    const after = { grew: 2, shrank: 1, same: 2 }
    expect(diffRemoved(before, after)).toEqual({ shrank: 2, droppedEntirely: 4 })
  })
})

describe('nodeStatesSignature', () => {
  it('is stable regardless of key insertion order (order-independent)', () => {
    const a = { node_b: 2, node_a: 1 }
    const b = { node_a: 1, node_b: 2 }
    expect(nodeStatesSignature(a)).toBe(nodeStatesSignature(b))
  })

  it('produces an empty-map signature that is distinct from any populated one', () => {
    expect(nodeStatesSignature({})).toBe('')
    expect(nodeStatesSignature({ node_a: 1 })).not.toBe('')
  })

  it('differs when a single node value differs', () => {
    const s1 = nodeStatesSignature({ node_a: 1, node_b: 2 })
    const s2 = nodeStatesSignature({ node_a: 1, node_b: 3 })
    expect(s1).not.toBe(s2)
  })

  // Pins bug-tree-hover-preview-cost-keyed-cache-collision: the whole reason this function exists is that
  // two distinct paths/cascades can cost the SAME total points while landing on different node-state maps.
  // A signature keyed on cost (or any point-total-derived value) would collide these two states; the real
  // fix keys on the full per-node map instead.
  it('produces different signatures for two states with the same total point cost but different allocations', () => {
    // Same total (3 points) split across the map two different ways.
    const pathA = { node_1: 3, node_2: 0 }
    const pathB = { node_1: 1, node_2: 2 }
    const totalA = Object.values(pathA).reduce((a, b) => a + b, 0)
    const totalB = Object.values(pathB).reduce((a, b) => a + b, 0)
    expect(totalA).toBe(totalB) // same cost by construction
    expect(nodeStatesSignature(pathA)).not.toBe(nodeStatesSignature(pathB))
  })

  it('produces different signatures for equal-cost states that share some allocated nodes but not others', () => {
    // Two 4-point states: one an even 2/2/0 split, one a lopsided 0/3/1 split across the same three ids.
    const stateA = { a: 2, b: 2, c: 0 }
    const stateB = { a: 0, b: 3, c: 1 }
    const totalA = Object.values(stateA).reduce((x, y) => x + y, 0)
    const totalB = Object.values(stateB).reduce((x, y) => x + y, 0)
    expect(totalA).toBe(totalB)
    expect(nodeStatesSignature(stateA)).not.toBe(nodeStatesSignature(stateB))
  })

  it('treats a key entirely absent from the map differently from the same key present at 0', () => {
    const withZero = { node_a: 0, node_b: 1 }
    const without = { node_b: 1 }
    // Not asserting a specific direction of behavior beyond "the function is well-defined and doesn't throw" —
    // this documents the actual (order-independent join over Object.keys) behavior so a future refactor can see
    // whether it changed: an explicit 0 entry IS included in the signature, unlike a missing key.
    expect(nodeStatesSignature(withZero)).toBe('node_a:0,node_b:1')
    expect(nodeStatesSignature(without)).toBe('node_b:1')
    expect(nodeStatesSignature(withZero)).not.toBe(nodeStatesSignature(without))
  })
})
