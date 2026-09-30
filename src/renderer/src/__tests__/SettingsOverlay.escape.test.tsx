import React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import SettingsOverlay from '../components/SettingsOverlay'

// bug-285: the Settings modal couldn't be closed with Escape (and in a short window its Close button was
// off-screen). The 'node' vitest environment has no DOM, so `window` is a bare EventTarget and the key
// press is a plain Event carrying a `key` field — the same shape the overlay's listener reads.

vi.stubGlobal('window', new EventTarget())

// CoverageLegend relies on the app build's automatic JSX runtime (no React import), which this vitest
// setup doesn't provide; it's unrelated to closing the modal, so render nothing in its place.
vi.mock('../components/CoverageLegend', () => ({ CoverageLegend: () => null }))

function press(key: string) {
  window.dispatchEvent(Object.assign(new Event('keydown'), { key }))
}

describe('SettingsOverlay — Escape closes it (bug-285)', () => {
  let renderer: TestRenderer.ReactTestRenderer | null = null
  afterEach(() => { act(() => { renderer?.unmount() }); renderer = null })

  it('calls onClose once on Escape', () => {
    const onClose = vi.fn()
    act(() => { renderer = TestRenderer.create(<SettingsOverlay onClose={onClose} />) })
    act(() => press('Escape'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('ignores other keys', () => {
    const onClose = vi.fn()
    act(() => { renderer = TestRenderer.create(<SettingsOverlay onClose={onClose} />) })
    act(() => press('Enter'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('stops listening once closed (unmounted)', () => {
    const onClose = vi.fn()
    act(() => { renderer = TestRenderer.create(<SettingsOverlay onClose={onClose} />) })
    act(() => { renderer!.unmount() })
    renderer = null
    act(() => press('Escape'))
    expect(onClose).not.toHaveBeenCalled()
  })
})
