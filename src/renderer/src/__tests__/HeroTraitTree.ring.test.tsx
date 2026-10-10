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
  it('draws the ring links as arcs (no full circle) and grows the viewBox so the bottom arc is not clipped', () => {
    const r = render(trait(POS, EDGES, [836, 713]))
    expect(r.root.findAllByType('circle').some(c => c.props.className === 'htt-tree-ring')).toBe(false)
    const arcs = r.root.findAllByType('path').map(p => p.props.d as string).filter(d => d.includes(' A '))
    expect(arcs).toHaveLength(3)   // Meet-Measure, Hunt-Claim, Hunt-Doomsday
    // The Hunt-Doomsday arc runs along the bottom of the ring, down to about y=813 (render units), past the
    // 800-tall node area; the viewBox must grow to hold it.
    const [vx, vy, vw, vh] = r.root.findByType('svg').props.viewBox.split(' ').map(Number)
    expect(vy + vh).toBeGreaterThan(813)
    expect([vx, vy, vw]).toEqual([0, 0, 1000])
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
