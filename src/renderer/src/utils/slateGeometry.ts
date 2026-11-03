export type SlateCell = [number, number]

import { BASE_SHAPES } from '../crosswalk/slateGeometry'

export { LEGENDARY_ORIENTATIONS } from '../crosswalk/slateGeometry'

// Keep the UI labels derived from the geometry table used by the import crosswalk.
export const BASE_SLATE_SHAPES = BASE_SHAPES.map((shape, index) => ({
  label: ['O', 'L', 'Z', 'T', 'J', 'S'][index]!,
  rotations: shape.rotations,
}))

// The 24 playable cells in the Builder's 6×6 divinity board. Shared by UI placement and log import.
export const SLATE_BOARD_VALID: boolean[][] = [
  [false, false, true, true, false, false],
  [false, true, true, true, true, false],
  [true, true, true, true, true, true],
  [true, true, true, true, true, true],
  [false, true, true, true, true, false],
  [false, false, true, true, false, false],
]
