import { describe, expect, it } from 'vitest'
import { findNetherKingPlacement, isNetherKingBrandNodeForVariant, netherKingOrientationCells } from '../utils/netherKingSlate'
import { SLATE_BOARD_VALID } from '../utils/slateGeometry'

describe('findNetherKingPlacement', () => {
  it('uses variant-specific geometry for template orientations', () => {
    expect(netherKingOrientationCells('contamination', 0)).toEqual([[0, 0], [1, 0], [2, 0]])
    expect(netherKingOrientationCells('banishment', 0)).toEqual([[0, 2], [1, 1], [2, 0]])
    expect(netherKingOrientationCells('banishment', 1)).toEqual([[0, 0], [1, 1], [2, 2]])
  })

  it('anchors Judgment on each allowed middle corner using the shared orientation order', () => {
    const cases = [
      { primary: [1, 1] as [number, number], orientationIndex: 1, cells: [[1, 1], [4, 1], [4, 4]] },
      { primary: [1, 4] as [number, number], orientationIndex: 0, cells: [[1, 4], [4, 1], [4, 4]] },
      { primary: [4, 1] as [number, number], orientationIndex: 2, cells: [[1, 1], [1, 4], [4, 1]] },
      { primary: [4, 4] as [number, number], orientationIndex: 3, cells: [[1, 1], [1, 4], [4, 4]] },
    ]

    for (const { primary, orientationIndex, cells } of cases) {
      const placement = findNetherKingPlacement('judgment', primary, new Map(), (row, col) => !!SLATE_BOARD_VALID[row]?.[col])
      expect(placement).toMatchObject({ orientationIndex, cells })
      expect(placement?.cells).toContainEqual(primary)
    }
  })

  it('does not allow Judgment outside the four middle corners', () => {
    expect(findNetherKingPlacement('judgment', [2, 2], new Map(), () => true)).toBeNull()
  })
})

describe('Nether King branded talent filtering', () => {
  it('offers variant-tagged branded nodes only for their active variant', () => {
    // These phrases match the SS14 Nether King catalog and the supplied in-game screenshots.
    const judgment = ['When Judgment is active, +5 % Effect Increase Multiplier for Divinity Slate along the connecting line']
    const contamination = ['When Contamination is active, +12 % Projection Effect for all Divinity Slate (Max Divinity Effect: 1)']
    const banishment = ['When Banishment is active, for every 1 adjacent Divinity Slate, gains: +3 % Aura Effect']

    expect(isNetherKingBrandNodeForVariant(judgment, 'judgment')).toBe(true)
    expect(isNetherKingBrandNodeForVariant(judgment, 'contamination')).toBe(false)
    expect(isNetherKingBrandNodeForVariant(contamination, 'contamination')).toBe(true)
    expect(isNetherKingBrandNodeForVariant(contamination, 'banishment')).toBe(false)
    expect(isNetherKingBrandNodeForVariant(banishment, 'banishment')).toBe(true)
    expect(isNetherKingBrandNodeForVariant(banishment, 'judgment')).toBe(false)
    expect(isNetherKingBrandNodeForVariant(['+9 % damage'], 'judgment')).toBe(true)
    expect(isNetherKingBrandNodeForVariant(['When Judgment is discussed, When Banishment is active, +3 % Aura Effect'], 'judgment')).toBe(false)
  })
})
