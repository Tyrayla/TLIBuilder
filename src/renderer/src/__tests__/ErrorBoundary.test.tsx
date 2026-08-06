import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import ErrorBoundary from '../components/ErrorBoundary'
import { useBuildStore } from '../store/buildStore'
import { api } from '../api/client'

// Coverage for the safety net added alongside the stale-snapshot slate crash fix (lead URGENT
// dispatch 2026-08-02): before this fix, React 18 unmounted the ENTIRE tree on any uncaught
// render/effect throw, stranding the in-memory Zustand build with no way to save it. ErrorBoundary
// is a plain class component (no hooks) — trivially renderable/error-testable without the
// window/floating-ui stubbing SlateScreen.staleSnapshot.test.tsx needed.

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, api: { ...actual.api, encodeBuildCode: vi.fn() } }
})

function Bomb(): React.ReactElement {
  throw new Error('boom')
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    useBuildStore.setState({ buildName: 'My Test Build', characterLevel: 42 })
    vi.mocked(api.encodeBuildCode).mockResolvedValue({ code: 'tli1_recoverycode' })
  })

  it('renders children normally when nothing throws', () => {
    let renderer!: TestRenderer.ReactTestRenderer
    act(() => {
      renderer = TestRenderer.create(
        <ErrorBoundary><div className="fine">all good</div></ErrorBoundary>,
      )
    })
    expect(renderer.root.findAllByProps({ className: 'fine' })).toHaveLength(1)
  })

  it('catches a thrown render error instead of letting it unmount the whole tree', () => {
    let renderer!: TestRenderer.ReactTestRenderer
    // React logs the caught error to console.error as part of its own dev-mode reporting —
    // expected noise for this test, not a real failure.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => {
      act(() => {
        renderer = TestRenderer.create(
          <ErrorBoundary><Bomb /></ErrorBoundary>,
        )
      })
    }).not.toThrow()
    consoleError.mockRestore()

    expect(renderer.root.findAllByProps({ className: 'fine' })).toHaveLength(0)
    expect(renderer.root.findByType('h1').children.join('')).toBe('Something went wrong')
  })

  it('the recovery-code button reads the in-memory build via getBuildPayload/api.encodeBuildCode (data survives the crash)', async () => {
    let renderer!: TestRenderer.ReactTestRenderer
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    await act(async () => {
      renderer = TestRenderer.create(
        <ErrorBoundary><Bomb /></ErrorBoundary>,
      )
    })
    consoleError.mockRestore()

    const generateButton = renderer.root.findAllByType('button').find(b => b.children.join('').includes('Generate recovery code'))!
    await act(async () => { await generateButton.props.onClick() })

    // The build data (still in the plain-JS Zustand store, untouched by the crashed React tree)
    // was actually read and handed to the same encode path normal Import/Export uses.
    expect(vi.mocked(api.encodeBuildCode)).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(api.encodeBuildCode).mock.calls[0][0] as Record<string, unknown>
    expect(payload.name).toBe('My Test Build')
    expect(payload.characterLevel).toBe(42)

    const textarea = renderer.root.findByType('textarea')
    expect(textarea.props.value).toBe('tli1_recoverycode')
  })
})
