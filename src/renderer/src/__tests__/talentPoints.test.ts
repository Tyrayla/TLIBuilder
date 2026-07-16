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
})
