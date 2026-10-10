import React from 'react'
import { describe, it, expect } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import HeroTraitTree from '../screens/HeroTraitTree'
import type { HeroTrait } from '../api/client'

// Youga 3 layout (pixel positions of the in-game tree image, 836x713, normalized like the dataset).
const POS: Record<string, [number, number]> = {
  root: [430, 378], meet: [201, 326], measure: [321, 148], notlift: [319, 513], arrive: [562, 257],
  gather: [438, 214], command: [590, 383], hold: [555, 501], hunt: [657, 605], claim: [694, 189], doom: [220, 614],
}
const EDGES: [string, string][] = [
  ['root', 'meet'], ['root', 'hold'], ['root', 'arrive'], ['meet', 'measure'], ['meet', 'notlift'],
  ['arrive', 'gather'], ['arrive', 'command'], ['hold', 'hunt'], ['hunt', 'claim'], ['hunt', 'doom'],
]

function trait(pos: Record<string, [number, number]>, edges: [string, string][], dims: [number, number]): HeroTrait {
  return {
    trait_id: 't', hero: 'H', variant_name: 'T', description: '', levels: [], artificial_moon: { description: '', effects: [] },
    advanced_traits: [], allocation_mode: 'tree', tree_root_id: 'root',
    tree_nodes: Object.entries(pos).map(([id, [x, y]]) => ({
      node_id: id, name: id, column: 0, row: 0, effects: [],
      x: Number((x / dims[0]).toFixed(3)), y: Number((y / dims[1]).toFixed(3)),
    })),
    tree_connections: edges.map(([from, to]) => ({ from, to })),
  } as HeroTrait
}

function render(t: HeroTrait) {
  let r!: TestRenderer.ReactTestRenderer
  act(() => {
    r = TestRenderer.create(
      <HeroTraitTree trait={t} heroMemories={[null, null, null]} baseMemory={null} openMemoryCreator={() => {}}
        openBaseCreator={() => {}} traitTreeAllocations={[]} setTraitTreeAllocations={() => {}}
        characterLevel={100} resolveLevelAt={5} />)
  })
  return r
}

describe('HeroTraitTree ring', () => {
  it('draws one complete ring circle behind the connections and grows the viewBox to contain it', () => {
    const r = render(trait(POS, EDGES, [836, 713]))
    const ring = r.root.findByProps({ 'data-testid': 'htt-tree-ring' })
    const { cx, cy, r: rad } = ring.props
    expect(Math.round(rad)).toBe(339)
    expect(Math.round(cx)).toBe(553)
    expect(Math.round(cy)).toBe(475)
    const svg = r.root.findByType('svg')
    const [vx, vy, vw, vh] = svg.props.viewBox.split(' ').map(Number)
    expect(vx).toBeLessThanOrEqual(cx - rad)
    expect(vy).toBeLessThanOrEqual(cy - rad)
    expect(vx + vw).toBeGreaterThanOrEqual(cx + rad)
    expect(vy + vh).toBeGreaterThanOrEqual(cy + rad)   // bottom of the ring is not clipped
    // The ring is the first drawn child after <defs>, i.e. behind every connection and node.
    const kids = svg.children.filter(c => typeof c !== 'string') as TestRenderer.ReactTestInstance[]
    expect(kids[1].props['data-testid']).toBe('htt-tree-ring')
  })

  it('leaves a tree with no ring unchanged: no ring circle and the standard viewBox', () => {
    // Dance of the Deep layout (normalized 0..1 positions).
    const sel: Record<string, [number, number]> = {
      root: [0.5, 0.1], a: [0.72, 0.27], b: [0.87, 0.52], c: [0.28, 0.27], d: [0.13, 0.52],
      e: [0.67, 0.6], f: [0.5, 0.36], g: [0.38, 0.6], h: [0.5, 0.82],
    }
    const r = render(trait(sel, [['root', 'a'], ['a', 'b'], ['root', 'c'], ['c', 'd']], [1, 1]))
    expect(r.root.findAllByProps({ 'data-testid': 'htt-tree-ring' })).toHaveLength(0)
    expect(r.root.findByType('svg').props.viewBox).toBe('0 0 1000 800')
    expect(r.root.findByType('svg').props.style).toBeUndefined()
  })
})
