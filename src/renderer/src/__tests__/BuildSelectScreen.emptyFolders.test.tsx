import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import BuildSelectScreen from '../screens/BuildSelectScreen'
import { api } from '../api/client'
import type { FolderManifest } from '../api/client'

// bug-284: with zero saved builds, a folder the player just created was saved to the manifest but never
// shown — the "No saved builds yet" empty state replaced the whole list, folders included.

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, api: { ...actual.api, getBuilds: vi.fn(), getBuildFolders: vi.fn() } }
})

// The version-check effect reads `window.api`; a bare stub keeps it from throwing in the 'node' environment.
vi.stubGlobal('window', new EventTarget())

const ONE_FOLDER: FolderManifest = {
  folders: [{ id: 'f1', name: 'Season Starters', parentId: null }],
  assignments: {}, order: {}, folderOrder: {},
}
const NO_FOLDERS: FolderManifest = { folders: [], assignments: {}, order: {}, folderOrder: {} }

async function renderWith(manifest: FolderManifest): Promise<string> {
  vi.mocked(api.getBuilds).mockResolvedValue([])
  vi.mocked(api.getBuildFolders).mockResolvedValue(manifest)
  let renderer!: TestRenderer.ReactTestRenderer
  await act(async () => {
    renderer = TestRenderer.create(<BuildSelectScreen onNewBuild={() => {}} onOpenBuild={() => {}} />)
    await new Promise((r) => setTimeout(r, 0))
  })
  const text = JSON.stringify(renderer.toJSON())
  renderer.unmount()
  return text
}

describe('BuildSelectScreen — folders show with zero saved builds (bug-284)', () => {
  beforeEach(() => {
    vi.mocked(api.getBuilds).mockReset()
    vi.mocked(api.getBuildFolders).mockReset()
  })

  it('lists a root folder when there are no builds, instead of the "No saved builds yet" state', async () => {
    const text = await renderWith(ONE_FOLDER)
    expect(text).toContain('Season Starters')
    expect(text).not.toContain('No saved builds yet.')
  })

  it('still shows "No saved builds yet" when there are no builds and no folders', async () => {
    const text = await renderWith(NO_FOLDERS)
    expect(text).toContain('No saved builds yet.')
  })

  it('keeps Import Code above the paired create actions with the centered brand and account control', async () => {
    vi.mocked(api.getBuilds).mockResolvedValue([])
    vi.mocked(api.getBuildFolders).mockResolvedValue(NO_FOLDERS)
    let renderer!: TestRenderer.ReactTestRenderer
    await act(async () => {
      renderer = TestRenderer.create(<BuildSelectScreen onNewBuild={() => {}} onOpenBuild={() => {}} />)
      await new Promise((r) => setTimeout(r, 0))
    })

    const cluster = renderer.root.findByProps({ className: 'build-select-actions build-select-create-cluster' })
    const [importAction, createRow] = cluster.children
    if (typeof importAction === 'string' || typeof createRow === 'string') throw new Error('Expected action containers.')
    expect(importAction.props.className).toContain('build-select-import')
    expect(createRow.props.className).toBe('build-select-create-row')
    expect(cluster.findAllByType('button').map(button => button.children.join(''))).toEqual(['Import Code', '+ New Folder', '+ New Build'])
    expect(renderer.root.findByProps({ className: 'build-select-center' })).toBeTruthy()
    expect(renderer.root.findByProps({ className: 'build-select-account-control' })).toBeTruthy()
    const discordCta = renderer.root.findByProps({ className: 'btn btn-sm build-select-discord' })
    expect(discordCta.findByType('svg').props['aria-hidden']).toBe('true')
    expect(discordCta.findByType('span').children.join('')).toContain('Join the Discord')
    renderer.unmount()
  })
})
