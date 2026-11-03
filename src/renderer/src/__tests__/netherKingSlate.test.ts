import { describe, expect, it } from 'vitest'
import { findNetherKingPlacement } from '../utils/netherKingSlate'
import { SLATE_BOARD_VALID } from '../utils/slateGeometry'

describe('findNetherKingPlacement', () => {
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
