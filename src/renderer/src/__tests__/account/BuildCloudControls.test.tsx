import React from 'react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import BuildCloudControls from '../../components/accounts/BuildCloudControls'
import type { CloudBuild } from '../../api/accounts'

vi.stubGlobal('window', new EventTarget())

let renderer: TestRenderer.ReactTestRenderer | null = null
afterEach(() => { act(() => { renderer?.unmount() }); renderer = null })

const cloud = (link: boolean): CloudBuild => ({
  cloudBuildId: 'cb', name: 'n', currentRevisionId: 'rev_internal_123', semanticHash: 'h',
  updatedAt: Date.UTC(2026, 9, 6) / 1000, dataVersion: 'SS13',
  namedLink: link ? { urlPath: '/u/t-1/x', slug: 'x', listed: false, revisionId: 'r' } : null,
})

function renderedText(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(renderedText).join('')
  if (node && typeof node === 'object' && 'children' in node) return renderedText((node as { children?: unknown }).children)
  return ''
}
const text = () => renderedText(renderer!.toJSON())
const labels = () => renderer!.root.findAllByType('button').map((b) => renderedText(b.children))

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

  it('synced: readable status with one date and no internal identifiers or duplicate local date', () => {
    mount('synced')
    const date = new Date(cloud(false).updatedAt * 1000).toLocaleDateString()
    const status = renderer!.root.findByProps({ className: 'build-cloud-status' })
    expect(status.children.join('')).toBe(`Synced - ${date}`)
    expect(text().match(new RegExp(date, 'g'))).toHaveLength(1)
    expect(text()).not.toContain('rev_internal_123')
    expect(text()).not.toContain('SS13')
    expect(text()).not.toContain('Local ')
    expect(labels()).toEqual([])
  })

  it('offers the action for each actionable cloud status', () => {
    for (const [status, label] of [
      ['local-changes', 'Sync'], ['cloud-newer', 'Update from cloud'], ['diverged', 'Review conflict'],
    ] as const) {
      mount(status)
      expect(labels()).toEqual([label])
      act(() => { renderer!.unmount() }); renderer = null
    }
  })

  it('keeps a useful cloud update detail and the explicit update action', () => {
    mount('cloud-newer')
    const date = new Date(cloud(false).updatedAt * 1000).toLocaleDateString()
    expect(text()).toContain(`Cloud copy updated ${date}`)
    expect(labels()).toContain('Update from cloud')
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
