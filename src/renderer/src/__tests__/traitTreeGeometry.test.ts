import { describe, it, expect } from 'vitest'
import { findRing, connectorPath } from '../utils/traitTreeGeometry'

// Render-space (1000 x 760, plus the 40px top pad) positions, derived like HeroTraitTree: x*1000, y*760+40.
const YOUGA_PX: Record<string, [number, number]> = {
  root: [430, 378], meet: [201, 326], measure: [321, 148], notlift: [319, 513], arrive: [562, 257],
  gather: [438, 214], command: [590, 383], hold: [555, 501], hunt: [657, 605], claim: [694, 189], doom: [220, 614],
}
const youga = Object.entries(YOUGA_PX).map(([id, [x, y]]) => ({
  id, x: Number((x / 836).toFixed(3)) * 1000, y: Number((y / 713).toFixed(3)) * 760 + 40,
}))
const at = (id: string) => youga.find(n => n.id === id)!

describe('traitTreeGeometry', () => {
  it('draws ring arcs between ring nodes and straight lines elsewhere (Youga 3 layout)', () => {
    const ring = findRing(youga, 'root')
    expect(ring).not.toBeNull()
    const kind = (a: string, b: string) => connectorPath(at(a), at(b), ring).kind
    expect(kind('meet', 'measure')).toBe('arc')
    expect(kind('hunt', 'claim')).toBe('arc')
    expect(kind('hunt', 'doom')).toBe('arc')
    expect(kind('root', 'meet')).toBe('line')
    expect(kind('root', 'arrive')).toBe('line')
    expect(kind('arrive', 'gather')).toBe('line')
    expect(kind('hold', 'hunt')).toBe('line')
  })

  it('emits an SVG arc command along the ring for on-ring points', () => {
    const ring = { cx: 0, cy: 0, r: 100 }
    const p = connectorPath({ x: 100, y: 0 }, { x: 0, y: 100 }, ring)
    expect(p.kind).toBe('arc')
    expect(p.d).toBe('M 100 0 A 100 100 0 0 1 0 100')
    expect(connectorPath({ x: 0, y: 100 }, { x: 100, y: 0 }, ring).d).toBe('M 0 100 A 100 100 0 0 0 100 0')
  })

  it('falls back to a straight line when a point is off the ring or there is no ring', () => {
    const ring = { cx: 0, cy: 0, r: 100 }
    expect(connectorPath({ x: 100, y: 0 }, { x: 0, y: 50 }, ring)).toEqual({ kind: 'line', d: 'M 100 0 L 0 50' })
    expect(connectorPath({ x: 100, y: 0 }, { x: 0, y: 100 }, null).kind).toBe('line')
  })

  it('finds no ring in Dance of the Deep (Selena 2), so its links stay straight', () => {
    const sel: Record<string, [number, number]> = {
      root: [0.5, 0.1], a: [0.72, 0.27], b: [0.87, 0.52], c: [0.28, 0.27], d: [0.13, 0.52],
      e: [0.67, 0.6], f: [0.5, 0.36], g: [0.38, 0.6], h: [0.5, 0.82],
    }
    const nodes = Object.entries(sel).map(([id, [x, y]]) => ({ id, x: x * 1000, y: y * 760 + 40 }))
    expect(findRing(nodes, 'root')).toBeNull()
  })

  it('returns no ring for empty or tiny layouts', () => {
    expect(findRing([], 'root')).toBeNull()
    expect(findRing([{ id: 'root', x: 0, y: 0 }, { id: 'a', x: 10, y: 0 }], 'root')).toBeNull()
  })

})
