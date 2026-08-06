import fs from 'node:fs'
import path from 'node:path'
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import TreeSelectorScreen from '../screens/TreeSelectorScreen'
import TreeViewerScreen from '../screens/TreeViewerScreen'
import { useBuildStore } from '../store/buildStore'
import { api } from '../api/client'
import type { TreeData } from '../api/client'

// Cases 2-4 of the preview-mode-redesign coverage (lead dispatch 2026-07-31, follow-up 2026-07-31
// REQUEST CHANGES). The literal preview call sites this targets live in App.tsx (screen ===
// 'preview-selector' / 'preview-viewer' branches), but App itself can't be rendered here: it touches
// `document.documentElement.style.zoom` unconditionally on mount (App.tsx:114), and this suite's
// vitest environment is 'node' (no DOM/jsdom — see vitest.config.ts and the SlotSidebar.preview.test.tsx
// comment on why hooks block plain-function invocation as an alternative). Extracting App's preview
// branches into a testable helper isn't an option either — the testing lane can't edit production
// source (CLAUDE.md). So this file combines:
//   - Case 2 (preview-selector side): a REAL behavioral render of TreeSelectorScreen, wired with the
//     exact literal no-op props App.tsx passes at its preview-selector call site, asserting a slot
//     click never reaches useBuildStore.
//   - Case 2 (preview-viewer side), the highest-risk store-mutation guards: a REAL behavioral render
//     of TreeViewerScreen with previewMode=true, exercising a node-allocate click (the interaction
//     path that normally calls updateSlotNodeStates/updateSlotCoreTalentSelections — the 5 `if
//     (!previewMode)` guard sites review-correctness flagged at lines 919/931/1081/1100/1884),
//     asserting the store is NOT mutated.
//   - Cases 3, 4 (App-internal screen-navigation state that isn't reachable via either child screen's
//     own props — previewSource/setScreen live only in App): covered as source-text pins against
//     App.tsx's exact call-site wiring — real regression coverage (a wiring change trips these), just
//     not exercised end-to-end via a renderer.

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    api: {
      ...actual.api,
      getTrees: vi.fn().mockResolvedValue([]),
      searchTrees: vi.fn().mockResolvedValue([]),
      getTree: vi.fn(),
      getEtherealPrism: vi.fn().mockResolvedValue({ season: null, items: [], base_affixes: [], random_affixes: [] }),
    },
  }
})

// A minimal single-node tree: column 0 (always unlocked), no connections/prereqs, so a left-click
// on it is a DIRECT allocate (tryLocalAllocate's `allowed: true` branch) — the simplest interaction
// path that reaches applyNodeStates' `if (!previewMode) updateSlotNodeStates(...)` guard.
const _MINIMAL_TREE: TreeData = {
  name: 'Test Tree',
  nodes: [{ id: 'n1', column: 0, row: 0, max_points: 3, node_type: 'Test Node', current_points: 0, effects: ['test effect'] }],
  connections: [],
  core_talent_slots: [],
  node_prefix: 'tt',
}

const APP_TSX = fs.readFileSync(path.resolve(__dirname, '../App.tsx'), 'utf-8')

function previewBranch(startMarker: string, endMarker: string): string {
  const start = APP_TSX.indexOf(startMarker)
  expect(start, `marker not found: ${startMarker}`).toBeGreaterThanOrEqual(0)
  const end = APP_TSX.indexOf(endMarker, start)
  expect(end, `end marker not found after start: ${endMarker}`).toBeGreaterThan(start)
  return APP_TSX.slice(start, end)
}

describe("App.tsx preview call-site wiring (source pin)", () => {
  const previewSelectorBranch = previewBranch(
    "screen === 'preview-selector'", "screen === 'preview-viewer'")
  const previewViewerBranch = previewBranch(
    "screen === 'preview-viewer'", "screen === 'import-export'")

  it('case 2: preview-selector passes literal no-op onSlotClick/onSlotReorder to TreeSelectorScreen', () => {
    expect(previewSelectorBranch).toContain('onSlotClick={() => {}}')
    expect(previewSelectorBranch).toContain('onSlotReorder={() => {}}')
  })

  it('case 2: preview-viewer passes literal no-op onSlotClick to TreeViewerScreen', () => {
    expect(previewViewerBranch).toContain('onSlotClick={() => {}}')
  })

  it('case 3: Exit Preview (onPreview) navigates to previewSource on both preview screens', () => {
    expect(previewSelectorBranch).toContain('onPreview={() => setScreen(previewSource)}')
    expect(previewViewerBranch).toContain('onPreview={() => setScreen(previewSource)}')
  })

  it("case 4: preview-viewer's Overview (onBack) stays within preview (goes to preview-selector, not build-overview)", () => {
    expect(previewViewerBranch).toContain("onBack={() => setScreen('preview-selector')}")
    expect(previewViewerBranch).not.toContain("onBack={() => setScreen('build-overview')}")
  })
})

describe('TreeSelectorScreen in preview mode (behavioral)', () => {
  beforeEach(() => {
    useBuildStore.setState({ activeSlot: 0, slots: [null, null, null, null] })
  })

  it('respects a no-op onSlotClick prop without bypassing it to call the store directly', async () => {
    // NOTE: this renders TreeSelectorScreen directly with its own onSlotClick={() => {}} prop — it does
    // NOT render or read App.tsx. It proves TreeSelectorScreen passes through whatever onSlotClick it's
    // given rather than reaching into useBuildStore itself; that App.tsx's real preview wiring supplies
    // this exact no-op end to end is covered separately by the source-text pin above.
    const setActiveSlot = vi.spyOn(useBuildStore.getState(), 'setActiveSlot')
    const setSlot = vi.spyOn(useBuildStore.getState(), 'setSlot')
    const setSlots = vi.spyOn(useBuildStore.getState(), 'setSlots')

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(
        <TreeSelectorScreen
          treeColors={{}}
          treeIcons={{}}
          onSelectTree={() => {}}
          onRemoveTree={() => {}}
          onSlotClick={() => {}}
          onSlotReorder={() => {}}
          onGoToSelector={() => {}}
          onShiftUp={() => {}}
          onPreview={() => {}}
          previewMode
        />,
      )
    })

    const slotButtons = renderer.root.findAllByType('button').filter(b =>
      (b.props.className as string).includes('slot-sidebar-btn'))
    expect(slotButtons).toHaveLength(4)

    act(() => { slotButtons[0].props.onClick() })

    expect(setActiveSlot).not.toHaveBeenCalled()
    expect(setSlot).not.toHaveBeenCalled()
    expect(setSlots).not.toHaveBeenCalled()
    expect(useBuildStore.getState().slots).toEqual([null, null, null, null])
  })

  it('preview mode disables slot drag-and-drop entirely (dragDropEnabled=false reaches SlotSidebar)', async () => {
    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(
        <TreeSelectorScreen
          treeColors={{}}
          treeIcons={{}}
          onSelectTree={() => {}}
          onRemoveTree={() => {}}
          onSlotClick={() => {}}
          onSlotReorder={() => {}}
          onGoToSelector={() => {}}
          onShiftUp={() => {}}
          onPreview={() => {}}
          previewMode
        />,
      )
    })
    const slotButtons = renderer.root.findAllByType('button').filter(b =>
      (b.props.className as string).includes('slot-sidebar-btn'))
    for (const btn of slotButtons) {
      expect(btn.props.draggable).toBe(false)
      expect(btn.props.onDragStart).toBeUndefined()
      expect(btn.props.onDrop).toBeUndefined()
    }
  })
})

describe('TreeViewerScreen in preview mode (behavioral) — store-mutation guards', () => {
  beforeEach(() => {
    useBuildStore.setState({ activeSlot: 0, slots: [null, null, null, null] })
    vi.mocked(api.getTree).mockResolvedValue(_MINIMAL_TREE)
  })

  it('allocating a node in preview mode updates local view state but never calls updateSlotNodeStates/updateSlotCoreTalentSelections', async () => {
    const updateSlotNodeStates = vi.spyOn(useBuildStore.getState(), 'updateSlotNodeStates')
    const updateSlotCoreTalentSelections = vi.spyOn(useBuildStore.getState(), 'updateSlotCoreTalentSelections')

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(
        <TreeViewerScreen
          treeName="Test Tree"
          treeColor="#e94560"
          treeColors={{ 'Test Tree': '#e94560' }}
          treeIcons={{}}
          onBack={() => {}}
          onSlotClick={() => {}}
          onReselect={() => {}}
          onSlotReorder={() => {}}
          onPreview={() => {}}
          previewMode
        />,
      )
      // Let the mocked api.getTree()/getEtherealPrism() promises resolve and flush the resulting setState.
      await Promise.resolve()
      await Promise.resolve()
    })

    // Find the allocatable node's SVG group — the one carrying the node click handler (TreeNodeG's
    // onClick, wired to handleClick('n1', 'allocate') via onInteract). Filtered by onClick presence
    // since the canvas SVG contains other <g> wrapper elements with no click handler.
    const nodeGroups = renderer.root.findAllByType('g').filter(g => typeof g.props.onClick === 'function')
    expect(nodeGroups.length).toBeGreaterThan(0)

    act(() => { nodeGroups[0].props.onClick({ preventDefault: () => {} }) })

    // The click should have actually allocated (local nodeStates), or this test would trivially pass
    // for the wrong reason. Confirmed via the node's rendered point count text "1/3".
    const pointTexts = renderer.root.findAllByType('text').map(t => (t.children ?? []).join(''))
    expect(pointTexts).toContain('1/3')

    // The whole point of previewMode: the local allocate above must NEVER reach the real build's store.
    expect(updateSlotNodeStates).not.toHaveBeenCalled()
    expect(updateSlotCoreTalentSelections).not.toHaveBeenCalled()
    expect(useBuildStore.getState().slots).toEqual([null, null, null, null])
  })
})
