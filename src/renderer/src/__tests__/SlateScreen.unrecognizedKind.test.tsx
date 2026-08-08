import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import SlateScreen from '../screens/SlateScreen'
import { useBuildStore } from '../store/buildStore'
import type { SavedSlate } from '../api/client'

// Regression coverage for editing an existing slate whose `kind` is not a key in LEGENDARY_META
// (lead URGENT follow-up, 2026-08-02) — simulating a stale export, a future legendary-kind
// rename/removal, or any other data desync. Distinct from SlateScreen.staleSnapshot.test.tsx (which
// covers an undersized modifier-slots array on a RECOGNIZED kind); this one targets the
// LEGENDARY_META[kind]/LEGENDARY_ORIENTATIONS[kind] lookups themselves being handed a kind that was
// never a real key at all.
//
// ui-ux's parallel fix guarded all 9 LEGENDARY_META[...] indexing sites in this file (verified via
// grep sweep below) with the same `?.x ?? fallback` pattern already used elsewhere. This test drives
// the actual edit-entry path (the pointerdown+pointerup interaction that sets creator.kind =
// slate.kind at SlateScreen.tsx:1196) rather than asserting on source text, so it exercises
// renderCreatorPanel + ShapePanel for real.

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    api: {
      ...actual.api,
      getSlatePoolAll: vi.fn().mockResolvedValue({ magic: [], rare: [], legendary: [], core: [] }),
      getSlatePool: vi.fn().mockResolvedValue({ magic: [], rare: [], legendary: [], core: [] }),
    },
  }
})

// Same window/Element/Node stubbing as SlateScreen.staleSnapshot.test.tsx (see that file's comment
// for why): SlateScreen needs a `window` for its global click/pointerup/contextmenu listeners (this
// test specifically NEEDS the pointerup listener live, to drive the edit-entry interaction), which
// in turn requires Element/Node stand-ins so @floating-ui/react's isElement()/isNode() checks
// degrade to `false` instead of throwing once `window` exists.
if (typeof (globalThis as unknown as { window?: unknown }).window === 'undefined') {
  class FakeNode {}
  class FakeElement extends FakeNode {}
  class FakeHTMLElement extends FakeElement {}
  const fakeWindow = Object.assign(new EventTarget(), { Node: FakeNode, Element: FakeElement, HTMLElement: FakeHTMLElement })
  const g = globalThis as unknown as { Node: unknown; Element: unknown; HTMLElement: unknown; window: unknown }
  g.Node = FakeNode
  g.Element = FakeElement
  g.HTMLElement = FakeHTMLElement
  g.window = fakeWindow
}

// A slate kind that was never a real LEGENDARY_META/LEGENDARY_ORIENTATIONS key — e.g. a legendary
// kind renamed or removed after this slate was exported, or any other kind-vs-config desync.
const _UNRECOGNIZED_KIND_SLATE: SavedSlate = {
  id: 's1',
  templateId: 's1',
  kind: 'a_future_legendary_kind_not_yet_known_to_this_build',
  cells: [[0, 0]],
  anchor: [0, 0],
  orientationIndex: 0,
  shapeIndex: 0,
  slots: [],
}

describe('SlateScreen unrecognized-kind edit (regression)', () => {
  beforeEach(() => {
    useBuildStore.setState({ slates: [_UNRECOGNIZED_KIND_SLATE], slateInventory: [] })
  })

  it('opening an existing placed slate with an unrecognized kind for edit does not throw', async () => {
    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(<SlateScreen treeColors={{}} onBack={() => {}} />)
    })

    // Board CELL divs are the only ones with className "slate-cell". (We used to filter on the
    // onClick+onContextMenu+onPointerDown handler trio, but saved-slate InventoryTiles now share that
    // signature since empty slates auto-save to the inventory too — the className is the precise
    // selector.) Cells render row-major (row 0 col 0..5, row 1 col 0..5, ...), so index 0 is
    // (row 0, col 0) — where the fixture slate's single cell sits.
    const cellDivs = renderer.root.findAll(n => n.props.className === 'slate-cell')
    expect(cellDivs.length).toBe(36) // BOARD_ROWS(6) * BOARD_COLS(6), not exported from SlateScreen.tsx

    expect(() => {
      act(() => { cellDivs[0].props.onPointerDown() })
      // Press+release without moving = open for edit (SlateScreen.tsx's global pointerup handler,
      // ~line 1194) — this is the exact interaction that sets creator.kind = slate.kind.
      act(() => { window.dispatchEvent(new Event('pointerup')) })
    }).not.toThrow()

    // Confirm we actually reached editing mode (not a silent no-op that would make the assertion
    // above vacuous) — the header's edit-mode hint text only renders while creator is set.
    const hintText = renderer.root.findAll(n =>
      Array.isArray(n.children) && n.children.join('') === 'Right-click or Done to finish')
    expect(hintText.length).toBeGreaterThan(0)
  })
})
