import { describe, expect, it } from 'vitest'
import { createCalculationSnapshot, getReportRuntimeContext } from '../reports/reporting'
import { useBuildStore } from '../store/buildStore'

describe('reporting snapshots', () => {
  it('contains engine inputs but excludes save identity, notes, and loadout management', () => {
    useBuildStore.setState({ buildName: 'Private build', notes: 'Do not send', buildId: 'local-build-id', characterLevel: 77 })
    const snapshot = createCalculationSnapshot()
    expect(snapshot.characterLevel).toBe(77)
    expect(snapshot).not.toHaveProperty('buildName')
    expect(snapshot).not.toHaveProperty('notes')
    expect(snapshot).not.toHaveProperty('buildId')
    expect(snapshot).not.toHaveProperty('loadouts')
    expect(snapshot).not.toHaveProperty('activeLoadoutId')
  })

  it('classifies an available runtime with safe viewport fields', () => {
    const runtime = getReportRuntimeContext()
    expect(['desktop-electron', 'web-browser']).toContain(runtime.runtime)
    expect(['desktop', 'mobile']).toContain(runtime.form_factor)
    expect(runtime.viewport.width).toBeGreaterThanOrEqual(0)
    expect(runtime.viewport.height).toBeGreaterThanOrEqual(0)
  })
})
