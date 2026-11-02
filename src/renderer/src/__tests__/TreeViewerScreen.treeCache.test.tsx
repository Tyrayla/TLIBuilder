import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import TreeViewerScreen from '../screens/TreeViewerScreen'
import { useBuildStore } from '../store/buildStore'
import { api } from '../api/client'
import type { TreeData } from '../api/client'
import { clearTreeCache } from '../api/treeCache'

// Re-opening a talent tree must not flash the loading state or refetch: trees are season-static and
// served from the session cache (api/treeCache). Previously every open cleared the tree and refetched it,
// which on web queued behind the serialized Pyodide worker (≈1s spinner on every tree click).

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    api: {
      ...actual.api,
      getTree: vi.fn(),
      getEtherealPrism: vi.fn().mockResolvedValue({ season: null, items: [], base_affixes: [], random_affixes: [] }),
    },
  }
})

const TREE: TreeData = {
  name: 'Test Tree',
  nodes: [{ id: 'n1', column: 0, row: 0, max_points: 3, node_type: 'Test Node', current_points: 0, effects: ['test effect'] }],
  connections: [],
  core_talent_slots: [],
  node_prefix: 'tt',
}

const viewer = (treeName = 'Test Tree') => (
  <TreeViewerScreen
    treeName={treeName}
    treeColor="#e94560"
    treeColors={{ [treeName]: '#e94560' }}
    treeIcons={{}}
    onBack={() => {}}
    onSlotClick={() => {}}
    onReselect={() => {}}
    onSlotReorder={() => {}}
    onPreview={() => {}}
    previewMode
  />
)

const texts = (r: TestRenderer.ReactTestRenderer) =>
  r.root.findAll(n => typeof n.type === 'string')
    .map(n => n.children.filter(c => typeof c === 'string').join(''))

describe('TreeViewerScreen — session tree cache', () => {
  beforeEach(() => {
    clearTreeCache()
    useBuildStore.setState({ activeSlot: 0, slots: [null, null, null, null] })
    vi.mocked(api.getTree).mockReset().mockResolvedValue(TREE)
    vi.mocked(api.getEtherealPrism).mockClear()
  })

  it('shows the loading state only on the first open; a re-open renders the tree immediately without refetching', async () => {
    let first!: TestRenderer.ReactTestRenderer
    act(() => { first = TestRenderer.create(viewer()) })
    expect(texts(first)).toContain('Loading Test Tree…')
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(texts(first)).toContain('0/3')
    act(() => first.unmount())

    // Second open: assert on the very first committed frame, before any promise can settle.
    let second!: TestRenderer.ReactTestRenderer
    act(() => { second = TestRenderer.create(viewer()) })
    expect(texts(second)).not.toContain('Loading Test Tree…')
    expect(texts(second)).toContain('0/3')

    expect(api.getTree).toHaveBeenCalledTimes(1)
    expect(api.getEtherealPrism).toHaveBeenCalledTimes(1)
    act(() => second.unmount())
  })

  it("a slow response for a tree the player already left never replaces the newer tree", async () => {
    const OTHER: TreeData = { ...TREE, name: 'Other Tree', nodes: [{ ...TREE.nodes[0], id: 'o1', max_points: 5 }] }
    let resolveSlow!: (t: TreeData) => void
    vi.mocked(api.getTree).mockImplementation(name =>
      name === 'Test Tree' ? new Promise<TreeData>(r => { resolveSlow = r }) : Promise.resolve(OTHER))

    let r!: TestRenderer.ReactTestRenderer
    act(() => { r = TestRenderer.create(viewer('Test Tree')) })
    act(() => { r.update(viewer('Other Tree')) })
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(texts(r)).toContain('0/5')

    await act(async () => { resolveSlow(TREE); await Promise.resolve(); await Promise.resolve() })
    expect(texts(r)).toContain('0/5')
    expect(texts(r)).not.toContain('0/3')
    act(() => r.unmount())
  })

  it('Retry after a failed load refetches and shows the tree', async () => {
    vi.mocked(api.getTree)
      .mockRejectedValueOnce(new Error('GET /tree/Test Tree failed (500)'))
      .mockResolvedValueOnce(TREE)

    let r!: TestRenderer.ReactTestRenderer
    act(() => { r = TestRenderer.create(viewer()) })
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(texts(r)).toContain('Failed to load Test Tree')

    const retry = r.root.findAllByType('button').find(b => b.children.join('').includes('Retry'))!
    await act(async () => { retry.props.onClick(); await Promise.resolve(); await Promise.resolve() })
    expect(texts(r)).toContain('0/3')
    expect(api.getTree).toHaveBeenCalledTimes(2)
    act(() => r.unmount())
  })
})
