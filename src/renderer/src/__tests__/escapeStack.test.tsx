import React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import SettingsOverlay from '../components/SettingsOverlay'
import ReportModal from '../components/ReportModal'

// Escape must close only the top-most modal. Settings' "Report a bug" opens ReportModal on top of Settings
// while Settings stays mounted; before this fix Escape closed the Settings card underneath and left the
// report form (which had no Escape handling) open on top.

vi.stubGlobal('window', new EventTarget())
// CoverageLegend relies on the app build's automatic JSX runtime, which this vitest setup doesn't provide.
vi.mock('../components/CoverageLegend', () => ({ CoverageLegend: () => null }))

function press(key: string) {
  window.dispatchEvent(Object.assign(new Event('keydown'), { key }))
}

describe('Escape closes only the top-most modal', () => {
  let settings: TestRenderer.ReactTestRenderer | null = null
  let report: TestRenderer.ReactTestRenderer | null = null
  afterEach(() => {
    act(() => { report?.unmount(); settings?.unmount() })
    settings = null; report = null
  })

  it('with the report form open over Settings, Escape closes the report form, not Settings', () => {
    const closeSettings = vi.fn(); const closeReport = vi.fn()
    act(() => { settings = TestRenderer.create(<SettingsOverlay onClose={closeSettings} />) })
    act(() => { report = TestRenderer.create(<ReportModal onClose={closeReport} />) })

    act(() => press('Escape'))

    expect(closeReport).toHaveBeenCalledTimes(1)
    expect(closeSettings).not.toHaveBeenCalled()
  })

  it('once the report form closes, the next Escape closes Settings', () => {
    const closeSettings = vi.fn(); const closeReport = vi.fn()
    act(() => { settings = TestRenderer.create(<SettingsOverlay onClose={closeSettings} />) })
    act(() => { report = TestRenderer.create(<ReportModal onClose={closeReport} />) })
    act(() => { report!.unmount() }); report = null

    act(() => press('Escape'))

    expect(closeSettings).toHaveBeenCalledTimes(1)
    expect(closeReport).not.toHaveBeenCalled()
  })

  it('uses the latest onClose after a re-render', () => {
    const first = vi.fn(); const second = vi.fn()
    act(() => { settings = TestRenderer.create(<SettingsOverlay onClose={first} />) })
    act(() => { settings!.update(<SettingsOverlay onClose={second} />) })

    act(() => press('Escape'))

    expect(second).toHaveBeenCalledTimes(1)
    expect(first).not.toHaveBeenCalled()
  })
})
