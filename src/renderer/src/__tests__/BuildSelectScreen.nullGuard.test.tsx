import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import BuildSelectScreen from '../screens/BuildSelectScreen'
import { api } from '../api/client'

// bug-290: BuildSelectScreen crashed to the error boundary (TLI-UI-001, "TypeError: Cannot read
// properties of null (reading 'filter')") when api.getBuilds() resolved null — main's api-request can
// hand back `{ ok: true, data: null }` when a 200 body fails to parse. loadAll's setBuilds/setManifest
// have no null guard, so the very next render's useMemo (builds.filter / manifest.folders.filter)
// throws immediately. This drives a guard that treats a null response as empty instead.

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, api: { ...actual.api, getBuilds: vi.fn(), getBuildFolders: vi.fn() } }
})

// BuildSelectScreen's version-check effect reads `window.api` unconditionally on mount (unlike its own
// openExternal helper, which guards with `window.api?.`) — a bare `window` stub keeps that effect from
// throwing for an unrelated reason (`window is not defined`) in this DOM-less 'node' vitest environment.
vi.stubGlobal('window', new EventTarget())

const EMPTY_MANIFEST = { folders: [], assignments: {}, order: {}, folderOrder: {} }

describe('BuildSelectScreen — null catalog responses do not crash (bug-290)', () => {
  beforeEach(() => {
    vi.mocked(api.getBuilds).mockReset()
    vi.mocked(api.getBuildFolders).mockReset()
  })

  it('does not crash when getBuilds() resolves null — shows the normal empty-state UI', async () => {
    vi.mocked(api.getBuilds).mockResolvedValue(null as unknown as Awaited<ReturnType<typeof api.getBuilds>>)
    vi.mocked(api.getBuildFolders).mockResolvedValue(EMPTY_MANIFEST)

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(<BuildSelectScreen onNewBuild={() => {}} onOpenBuild={() => {}} />)
      await new Promise((r) => setTimeout(r, 0))
    })

    // Without an error boundary, React unmounts silently (dev console.error only) on an error thrown
    // during this kind of post-mount re-render — `.root` then throws its OWN "unmounted" error, which
    // would masquerade as the failure reason. `.toJSON()` doesn't throw either way: null means the
    // crash actually happened; a real tree means the screen's normal chrome rendered instead of the
    // app's error-boundary recovery screen.
    expect(renderer.toJSON()).not.toBeNull()
    expect(JSON.stringify(renderer.toJSON())).toContain('build-select-import')
    renderer.unmount()
  })

  it('does not crash when getBuildFolders() resolves null — shows the normal empty-state UI', async () => {
    vi.mocked(api.getBuilds).mockResolvedValue([])
    vi.mocked(api.getBuildFolders).mockResolvedValue(null as unknown as Awaited<ReturnType<typeof api.getBuildFolders>>)

    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(<BuildSelectScreen onNewBuild={() => {}} onOpenBuild={() => {}} />)
      await new Promise((r) => setTimeout(r, 0))
    })

    expect(renderer.toJSON()).not.toBeNull()
    expect(JSON.stringify(renderer.toJSON())).toContain('build-select-import')
    renderer.unmount()
  })
})
