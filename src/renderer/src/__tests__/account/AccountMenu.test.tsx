import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import AccountMenu from '../../components/accounts/AccountMenu'
import { getAccountStore } from '../../store/accountStore'

let renderer: TestRenderer.ReactTestRenderer | null = null
afterEach(() => {
  act(() => { renderer?.unmount() })
  renderer = null
  vi.unstubAllGlobals()
})

function mount() {
  const input = new EventTarget()
  const select = new EventTarget()
  const outside = new EventTarget()
  const listeners = new Map<string, (event: { target: EventTarget | null }) => void>()
  const documentStub = {
    activeElement: null,
    addEventListener: vi.fn((name: string, listener: (event: { target: EventTarget | null }) => void) => listeners.set(name, listener)),
    removeEventListener: vi.fn((name: string) => listeners.delete(name)),
  }
  vi.stubGlobal('document', documentStub)
  getAccountStore().setState({
    status: 'signed-in',
    account: {
      userId: 'user-1',
      publicName: { name: 'Tyra', tag: '1234' },
      limits: { cloudBuilds: 20, profileBuilds: 10 },
      usage: { cloudBuilds: 1, profileBuilds: 0 },
    },
    signupOffer: null,
  })

  const rootNode = {
    contains: (target: EventTarget) => target === input || target === select,
    querySelector: () => ({ focus: vi.fn() }),
    querySelectorAll: () => [],
  }
  const triggerNode = { focus: vi.fn() }
  act(() => {
    renderer = TestRenderer.create(
      <AccountMenu onOpenProfile={vi.fn()} onOpenCloudLibrary={vi.fn()} />,
      { createNodeMock: element => element.props.className === 'account-menu' ? rootNode : triggerNode },
    )
  })
  const root = renderer!.root.findByProps({ className: 'account-menu' })
  const trigger = renderer!.root.findByProps({ 'aria-haspopup': 'menu' })
  act(() => { trigger.props.onClick() })
  return { root, outside, input, select, listeners }
}

describe('AccountMenu dismissal', () => {
  it('stays open through pointer leave and inside input/select interaction, but closes on outside pointerdown', () => {
    const { root, outside, input, select, listeners } = mount()
    const pointerDown = listeners.get('pointerdown')!

    expect(root.props.onBlur).toBeUndefined()
    expect(root.props.onPointerLeave).toBeUndefined()
    expect(root.props.onMouseLeave).toBeUndefined()
    expect(listeners.has('pointerleave')).toBe(false)

    act(() => { pointerDown({ target: input }) })
    expect(renderer!.root.findAllByProps({ role: 'menu' })).toHaveLength(1)
    act(() => { pointerDown({ target: select }) })
    expect(renderer!.root.findAllByProps({ role: 'menu' })).toHaveLength(1)

    act(() => { pointerDown({ target: outside }) })
    expect(renderer!.root.findAllByProps({ role: 'menu' })).toHaveLength(0)
  })

  it('still closes on Escape', () => {
    const { root } = mount()
    const stopPropagation = vi.fn()
    act(() => { root.props.onKeyDown({ key: 'Escape', stopPropagation }) })
    expect(stopPropagation).toHaveBeenCalledOnce()
    expect(renderer!.root.findAllByProps({ role: 'menu' })).toHaveLength(0)
  })
})
