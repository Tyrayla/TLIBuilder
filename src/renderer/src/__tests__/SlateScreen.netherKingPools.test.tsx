import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import SlateScreen from '../screens/SlateScreen'
import { useBuildStore } from '../store/buildStore'
import type { SavedSlate } from '../api/client'
import { initSlateSlots } from '../crosswalk/slateGeometry'

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return {
    ...actual,
    api: {
      ...actual.api,
      getSlatePoolAll: vi.fn().mockResolvedValue({
        magic: [], rare: [],
        legendary: [{ nodeId: 'unrelated_legendary', game_id: '1', treeName: 'Ranger', nodeType: 'Legendary Medium Talent', effects: ['+99% Unrelated Damage'] }],
        core: [{ key: 'nether-fixed', game_id: '2', treeName: 'Nether King', nodeType: 'Legendary Medium Nether King Talent Node',
          name: 'Fixed Nether King Talent', effects: ['+18% Fixed Damage'] }],
      }),
      getSlatePool: vi.fn().mockResolvedValue({ magic: [], rare: [], legendary: [], core: [] }),
    },
  }
})

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

const template: SavedSlate = {
  id: 'nk-template', templateId: 'nk-template', kind: 'nether_kings_divinity',
  cells: [[0, 3], [3, 0], [3, 3]], anchor: [1, 1], orientationIndex: 0, shapeIndex: 0,
  treeType: 'Nether King', slots: initSlateSlots('nether_kings_divinity'), netherKingVariant: 'judgment',
}

describe('SlateScreen Nether King fixed pool', () => {
  beforeEach(() => useBuildStore.setState({ slates: [], slateInventory: [template] }))

  it('offers fixed Nether King choices without ordinary legendary modifiers', async () => {
    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(<SlateScreen treeColors={{}} onBack={() => {}} />)
    })
    const place = renderer.root.findByProps({ title: 'Click to place · right-click to delete' })
    await act(async () => {
      place.props.onClick()
      await Promise.resolve()
      await Promise.resolve()
    })
    const fixedBadge = renderer.root.findAllByProps({ title: 'Fixed talent node pool' })[0]!
    const emptyFixedSlot = fixedBadge.parent!.findAll(node => node.props.onClick && node.props.title === undefined)
      .find(node => node !== fixedBadge)!
    await act(async () => { emptyFixedSlot.props.onClick() })

    const renderedText = renderer.root.findAll(node => typeof node.children?.[0] === 'string')
      .map(node => node.children.join('')).join('\n')
    expect(renderedText).toContain('Fixed Nether King Nodes')
    expect(renderedText).toContain('Fixed Nether King Talent')
    expect(renderedText).not.toContain('Modifiers')
    expect(renderedText).not.toContain('+99% Unrelated Damage')
  })
})
