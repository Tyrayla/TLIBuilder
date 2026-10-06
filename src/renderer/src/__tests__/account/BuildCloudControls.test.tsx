import React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import BuildCloudControls from '../../components/accounts/BuildCloudControls'
import type { CloudBuild } from '../../api/accounts'

vi.stubGlobal('window', new EventTarget())

let renderer: TestRenderer.ReactTestRenderer | null = null
afterEach(() => { act(() => { renderer?.unmount() }); renderer = null })

const cloud = (link: boolean): CloudBuild => ({
  cloudBuildId: 'cb', name: 'n', currentRevisionId: 'r', semanticHash: 'h', updatedAt: 1, dataVersion: 's',
  namedLink: link ? { urlPath: '/u/t-1/x', slug: 'x', listed: false, revisionId: 'r' } : null,
})

const text = () => JSON.stringify(renderer!.toJSON())
const labels = () => renderer!.root.findAllByType('button').map((b) => b.children.join(''))

function mount(status: string | undefined, link = false) {
  const h = { onUpload: vi.fn(), onDownload: vi.fn(), onLinkUpdate: vi.fn() }
  act(() => {
    renderer = TestRenderer.create(
      <BuildCloudControls status={status ? { status: status as never, cloud: status === 'not-uploaded' ? null : cloud(link) } : undefined} {...h} />,
    )
  })
  return h
}

describe('BuildCloudControls', () => {
  it('shows nothing until a status exists (guests and signed-out)', () => {
    mount(undefined)
    expect(renderer!.toJSON()).toBeNull()
  })

  it('not uploaded: indicator plus Upload only', () => {
    mount('not-uploaded')
    expect(text()).toContain('Not uploaded')
    expect(labels()).toEqual(['Upload to cloud'])
  })

  it('synced: indicator, Download available, Upload hidden', () => {
    mount('synced')
    expect(text()).toContain('Synced')
    expect(labels()).toEqual(['Download from cloud'])
  })

  it('local changes, newer cloud, and diverged use the plain-language indicators', () => {
    for (const [status, label] of [['local-changes', 'Local changes'], ['cloud-newer', 'Newer version in cloud'], ['diverged', 'Diverged']] as const) {
      mount(status)
      expect(text()).toContain(label)
      act(() => { renderer!.unmount() }); renderer = null
    }
  })

  it('offers Update shared link only when the cloud build has a named link', () => {
    mount('synced', true)
    expect(labels()).toContain('Update shared link')
    act(() => { renderer!.unmount() }); renderer = null
    mount('synced', false)
    expect(labels()).not.toContain('Update shared link')
  })

  it('clicks do not bubble to the card (which would open the build)', () => {
    const h = mount('local-changes')
    const stopPropagation = vi.fn()
    const button = renderer!.root.findAllByType('button')[0]
    act(() => { button.props.onClick({ stopPropagation }) })
    expect(stopPropagation).toHaveBeenCalled()
    expect(h.onUpload).toHaveBeenCalledTimes(1)
  })

  it('the indicator is a status, not a prompt: no dialog is rendered by it', () => {
    mount('diverged')
    expect(text()).not.toContain('modal-backdrop')
  })
})
