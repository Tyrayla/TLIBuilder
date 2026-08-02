import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import SlateScreen from '../screens/SlateScreen'
import { useBuildStore } from '../store/buildStore'
import type { SlateTemplate } from '../api/client'

// Regression coverage for the stale-snapshot slate crash (lead URGENT dispatch 2026-08-02).
//
// BUG (fixed): rapid interleaved place+remove clicks on a legendary slate board could desync
// slots[idx] mid-render (four separate views of slate state — local `placed` useState, store
// `slates`, `dragSlate` snapshot, `editSnapshot` — going out of sync for a frame), so the modifier-
// slot map in SlateScreen.tsx's renderCreatorPanel() indexed `slots[idx]` past what was actually
// there. ModifierSlot then derefed `.selectedNodeId`/`.isCore`/`.canBeCore` on `undefined` and threw
// — with no error boundary anywhere in the app (before this fix), that blanked the ENTIRE React
// tree and lost all in-memory build progress.
//
// FIX (already landed, not re-diagnosed here): the map now does `const slot = slots[idx]; if
// (!slot) return null` before constructing <ModifierSlot>, skipping the hole instead of crashing.
//
// This test does NOT try to reproduce the exact timing race (rapid pointer-event interleaving
// across React's async effect scheduling) — that's inherently flaky to author deterministically.
// Instead it directly constructs the SAME undefined-slots[idx] condition ModifierSlot would have
// hit, through a genuinely reachable production code path: `placeFromTemplate()` (SlateScreen.tsx)
// copies a saved inventory template's `slots` array into the creator verbatim, with no
// reconciliation against SLOT_CONFIG's expected section/slot count for that kind. A template saved
// with fewer slots than its kind currently expects (e.g. from stale/legacy inventory data — the
// same class of "local view disagrees with what's actually needed" desync as the real bug) hits the
// exact guard being tested, deterministically, with no click-timing choreography required.
//
// 'corner_of_divinity' has ONE section, count: 2 (SLOT_CONFIG) → indices [0, 1]. The fixture below
// supplies only 1 slot, so slots[1] is undefined when renderCreatorPanel renders it.

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

// SlateScreen registers window click/pointerup/contextmenu listeners unconditionally on mount for
// its global drag/dismiss handling — irrelevant to this test (nothing here dispatches real browser
// events; handlers are invoked directly via test-renderer instance props), but `window` doesn't
// exist in this suite's 'node' vitest environment (no jsdom — see vitest.config.ts). Node's built-in
// EventTarget satisfies addEventListener/removeEventListener without pulling in a DOM.
//
// Every SlateScreen node also carries useFloatingTooltip's `ref: refs.setReference` (from
// @floating-ui/react). Floating-ui's own isElement()/isNode() checks short-circuit to `false` (no
// crash) when `typeof window === 'undefined'` — which is exactly why the earlier App.previewWiring
// TreeViewerScreen render needed no such stub. But defining `window` above to satisfy
// addEventListener flips that short-circuit off, so floating-ui proceeds to `value instanceof
// Element`, and a bare `Element` global doesn't exist without a real DOM. Minimal stub classes make
// that `instanceof` check evaluate to `false` (correctly — a react-test-renderer instance isn't a
// real Element) instead of throwing ReferenceError.
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

const _UNDERSIZED_TEMPLATE: SlateTemplate = {
  id: 'tpl-1',
  kind: 'corner_of_divinity',
  orientationIndex: 0,
  shapeIndex: 0,
  slots: [
    {
      slotType: 'legendary', maxType: 'legendary', canBeCore: false, isCore: false,
      selectedNodeId: 'node-1', selectedCoreKey: null, coreName: null, effects: ['some effect'],
    },
  ],
}

describe('SlateScreen stale-snapshot slots[idx] guard (regression)', () => {
  beforeEach(() => {
    useBuildStore.setState({ slates: [], slateInventory: [_UNDERSIZED_TEMPLATE] })
  })

  it('placing an undersized saved template does not throw when a later section index has no slot', async () => {
    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(<SlateScreen treeColors={{}} onBack={() => {}} />)
    })

    const placeTile = renderer.root.findAllByProps({ title: 'Click to place · right-click to delete' })
    expect(placeTile).toHaveLength(1)

    // This is the exact click that used to reach the unguarded `slots[idx]` deref: it enters
    // 'creating' mode with creator.slots = the undersized template's 1-element array, and
    // renderCreatorPanel immediately renders both of corner_of_divinity's 2 section indices.
    expect(() => {
      act(() => { placeTile[0].props.onClick() })
    }).not.toThrow()

    // Confirm we actually reached the guarded render path (not a no-op) — exactly one
    // ModifierSlot-shaped control rendered (index 0, real slot), not two, and not a crash.
    const slotControls = renderer.root.findAllByProps({ title: 'legendary (click to cycle)' })
    expect(slotControls.length).toBe(1)
  })
})
