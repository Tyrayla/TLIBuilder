import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import SlateScreen from '../screens/SlateScreen'
import { useBuildStore } from '../store/buildStore'
import type { SavedSlate } from '../api/client'

// Coverage for the owner-requested change (2026-08-08): the slate-inventory auto-sync effect no
// longer skips placed slates that have no modifiers, so empty base slates (and Moth/Prairie
// legendary slates, which have no node slots at all) now also land in the build's saved-slates
// inventory. Previously the effect did `if (!sl.slots.some(s => s.selectedNodeId || s.selectedCoreKey)) continue`,
// which kept empty/moth slates out of the inventory entirely. This test drives the real mount-time
// sync (placed initialized from store.slates → auto-sync effect upserts into slateInventory).

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

// Same window/Element/Node stubbing as the sibling SlateScreen tests (see SlateScreen.staleSnapshot
// for the full rationale): SlateScreen registers window listeners on mount, and floating-ui's
// isElement/isNode checks need Element/Node stand-ins once `window` exists.
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

// A placed base slate with a slot but NO modifier chosen (no selectedNodeId / selectedCoreKey) — the
// exact case the old skip filtered out of the inventory.
const _EMPTY_BASE_SLATE: SavedSlate = {
  id: 's-empty', templateId: 's-empty', kind: 'base',
  cells: [[0, 0]], anchor: [0, 0], orientationIndex: 0, shapeIndex: 0,
  treeType: 'Goddess of Knowledge',
  slots: [
    { slotType: 'legendary', maxType: 'legendary', canBeCore: false, isCore: false,
      selectedNodeId: null, selectedCoreKey: null, coreName: null, effects: [], nodeType: null },
  ],
}

describe('SlateScreen empty-slate inventory sync', () => {
  beforeEach(() => {
    useBuildStore.setState({ slates: [_EMPTY_BASE_SLATE], slateInventory: [] })
  })

  it('auto-saves a placed slate with no modifiers into the saved-slates inventory', async () => {
    await act(async () => {
      TestRenderer.create(<SlateScreen treeColors={{}} onBack={() => {}} />)
    })

    // The mount-time auto-sync effect should have upserted the empty slate (keyed by its templateId)
    // into slateInventory — previously it was skipped for having no selectedNodeId/selectedCoreKey.
    const inv = useBuildStore.getState().slateInventory
    expect(inv.map(t => t.id)).toContain('s-empty')
    const saved = inv.find(t => t.id === 's-empty')
    expect(saved?.kind).toBe('base')
    expect(saved?.slots.some(s => s.selectedNodeId || s.selectedCoreKey)).toBe(false) // still empty
  })
})
