import { describe, it, expect } from 'vitest'
import { MAX_TALENT_POINTS, slotPointTotal, totalAllocatedPoints } from '../utils/talentPoints'
import type { TreeSlot } from '../api/client'

describe('MAX_TALENT_POINTS', () => {
  it('is 115 (owner-asserted in-game max talent points)', () => {
    expect(MAX_TALENT_POINTS).toBe(115)
  })
})

describe('slotPointTotal', () => {
  it('sums multiple node entries for a normal slot', () => {
    const slot: TreeSlot = {
      treeName: 'tree_a',
      nodeStates: { node_1: 3, node_2: 5, node_3: 2 },
    }
    expect(slotPointTotal(slot)).toBe(10)
  })

  it('returns 0 for a null slot', () => {
    expect(slotPointTotal(null)).toBe(0)
  })

  it('returns 0 for an undefined slot', () => {
    expect(slotPointTotal(undefined)).toBe(0)
  })

  it('returns 0 for a slot with missing nodeStates (legacy slot)', () => {
    const legacySlot = { treeName: 'tree_a' } as unknown as TreeSlot
    expect(slotPointTotal(legacySlot)).toBe(0)
  })

  it('ignores coreTalentSelections when computing the total', () => {
    const slot: TreeSlot = {
      treeName: 'tree_a',
      nodeStates: { node_1: 4 },
      coreTalentSelections: { core_1: 'option_a', core_2: 'option_b' },
    }
    expect(slotPointTotal(slot)).toBe(4)
  })

  it('counts zero-point node entries without affecting the sum', () => {
    const slot: TreeSlot = {
      treeName: 'tree_a',
      nodeStates: { node_1: 0, node_2: 6, node_3: 0 },
    }
    expect(slotPointTotal(slot)).toBe(6)
  })

  it('returns 0 for an empty nodeStates object', () => {
    const slot: TreeSlot = { treeName: 'tree_a', nodeStates: {} }
    expect(slotPointTotal(slot)).toBe(0)
  })

  it('adds an Inverse Image prism boxAllocations sum on top of nodeStates', () => {
    const slot: TreeSlot = { treeName: 'tree_a', nodeStates: { node_1: 4 } }
    const prism = { kind: 'inverse_image' as const, boxAllocations: { '2,1': 3, '2,2': 5 } }
    expect(slotPointTotal(slot, prism)).toBe(12)
  })

  it('ignores box allocations on an Ethereal prism (only Inverse Image cells cost points)', () => {
    const slot: TreeSlot = { treeName: 'tree_a', nodeStates: { node_1: 4 } }
    const prism = { kind: 'ethereal_prism' as const, boxAllocations: { '2,1': 3 } }
    expect(slotPointTotal(slot, prism)).toBe(4)
  })

  it('ignores an undefined prism', () => {
    const slot: TreeSlot = { treeName: 'tree_a', nodeStates: { node_1: 4 } }
    expect(slotPointTotal(slot, undefined)).toBe(4)
  })
})

describe('totalAllocatedPoints', () => {
  it('returns 0 for an empty slot array', () => {
    expect(totalAllocatedPoints([])).toBe(0)
  })

  it('returns 0 when every slot is null', () => {
    expect(totalAllocatedPoints([null, null, null])).toBe(0)
  })

  it('sums across multiple slots, skipping nulls', () => {
    const slots: (TreeSlot | null)[] = [
      { treeName: 'tree_a', nodeStates: { node_1: 3, node_2: 5 } },
      null,
      { treeName: 'tree_b', nodeStates: { node_1: 7 } },
      undefined as unknown as TreeSlot | null,
    ]
    expect(totalAllocatedPoints(slots)).toBe(15)
  })

  it('computes a total exceeding MAX_TALENT_POINTS without clamping (display-only cap)', () => {
    const slots: TreeSlot[] = [
      { treeName: 'tree_a', nodeStates: { node_1: 60, node_2: 40 } },
      { treeName: 'tree_b', nodeStates: { node_1: 30 } },
    ]
    const total = totalAllocatedPoints(slots)
    expect(total).toBe(130)
    expect(total).toBeGreaterThan(MAX_TALENT_POINTS)
  })

  it('includes a placed Inverse Image prism boxAllocations, matched by treeName', () => {
    const slots: TreeSlot[] = [
      { treeName: 'tree_a', nodeStates: { node_1: 10 } },
      { treeName: 'tree_b', nodeStates: { node_1: 5 } },
    ]
    const prisms = [{ treeName: 'tree_a', kind: 'inverse_image' as const, boxAllocations: { '2,1': 3, '2,2': 4 } }]
    expect(totalAllocatedPoints(slots, prisms)).toBe(22)
  })

  it('does not add a prism whose treeName matches no slot', () => {
    const slots: TreeSlot[] = [{ treeName: 'tree_a', nodeStates: { node_1: 10 } }]
    const prisms = [{ treeName: 'tree_c', kind: 'inverse_image' as const, boxAllocations: { '2,1': 3 } }]
    expect(totalAllocatedPoints(slots, prisms)).toBe(10)
  })

  it('does not count stray box allocations on an Ethereal prism in the global total', () => {
    const slots: TreeSlot[] = [{ treeName: 'tree_a', nodeStates: { node_1: 10 } }]
    const prisms = [{ treeName: 'tree_a', kind: 'ethereal_prism' as const, boxAllocations: { '2,1': 3 } }]
    expect(totalAllocatedPoints(slots, prisms)).toBe(10)
  })

  it('is unaffected when prisms is omitted entirely', () => {
    const slots: TreeSlot[] = [{ treeName: 'tree_a', nodeStates: { node_1: 10 } }]
    expect(totalAllocatedPoints(slots)).toBe(10)
  })
})
