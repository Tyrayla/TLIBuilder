import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import SlotSidebar from '../components/SlotSidebar'
import type { TreeSlot } from '../api/client'

// Case 1 of the preview-mode-redesign coverage (see lead dispatch 2026-07-31): SlotSidebar renders
// EMPTY_SLOTS + "Exit Preview" when inPreview=true, vs real slots + "Preview" otherwise. Rendered via
// react-test-renderer (no DOM/jsdom needed) since SlotSidebar uses useState and can't be invoked as a
// plain function outside a reconciler.
const EMPTY_SLOTS: (TreeSlot | null)[] = [null, null, null, null]
const REAL_SLOTS: (TreeSlot | null)[] = [
  { treeName: 'God of Might', nodeStates: {} },
  null,
  null,
  null,
]

function renderSidebar(props: Partial<React.ComponentProps<typeof SlotSidebar>> = {}) {
  let renderer!: TestRenderer.ReactTestRenderer
  act(() => {
    renderer = TestRenderer.create(
      <SlotSidebar
        slots={REAL_SLOTS}
        activeSlot={0}
        treeColors={{}}
        onOverview={() => {}}
        onSlotClick={() => {}}
        {...props}
      />,
    )
  })
  return renderer
}

function previewButtonText(renderer: TestRenderer.ReactTestRenderer): string {
  const btn = renderer.root.findAllByType('button').find(b =>
    (b.props.className as string).includes('slot-sidebar-preview'))
  if (!btn) throw new Error('preview button not found')
  return btn.children.join('')
}

describe('SlotSidebar preview-mode rendering', () => {
  it('renders EMPTY_SLOTS + "Exit Preview" (active) when inPreview=true', () => {
    const renderer = renderSidebar({ slots: EMPTY_SLOTS, activeSlot: -1, inPreview: true, onPreview: () => {} })
    const slotButtons = renderer.root.findAllByType('button').filter(b =>
      (b.props.className as string).includes('slot-sidebar-btn'))
    expect(slotButtons).toHaveLength(4)
    // Every slot is empty; the fallback label in preview mode is "Preview Mode", not "Empty".
    for (const btn of slotButtons) {
      expect(btn.findByProps({ className: 'slot-sidebar-name' }).children.join('')).toBe('Preview Mode')
    }
    expect(previewButtonText(renderer)).toBe('Exit Preview')
    const previewBtn = renderer.root.findAllByType('button').find(b =>
      (b.props.className as string).includes('slot-sidebar-preview'))!
    expect(previewBtn.props.className).toContain('active')
  })

  it('renders real slots + "Preview" (inactive) when inPreview is false/absent', () => {
    const renderer = renderSidebar({ slots: REAL_SLOTS, activeSlot: 0, onPreview: () => {} })
    const slotButtons = renderer.root.findAllByType('button').filter(b =>
      (b.props.className as string).includes('slot-sidebar-btn'))
    expect(slotButtons[0].findByProps({ className: 'slot-sidebar-name' }).children.join('')).toBe('God of Might')
    expect(previewButtonText(renderer)).toBe('Preview')
    const previewBtn = renderer.root.findAllByType('button').find(b =>
      (b.props.className as string).includes('slot-sidebar-preview'))!
    expect(previewBtn.props.className).not.toContain('active')
  })

  it('onPreview click handler is invoked when the Preview/Exit Preview button is clicked', () => {
    const onPreview = vi.fn()
    const renderer = renderSidebar({ slots: EMPTY_SLOTS, inPreview: true, onPreview })
    const previewBtn = renderer.root.findAllByType('button').find(b =>
      (b.props.className as string).includes('slot-sidebar-preview'))!
    act(() => { previewBtn.props.onClick() })
    expect(onPreview).toHaveBeenCalledTimes(1)
  })
})
