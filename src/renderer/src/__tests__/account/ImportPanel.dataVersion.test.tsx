import React from 'react'
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'

vi.stubGlobal('window', new EventTarget())

const resolveImportSource = vi.fn()
vi.mock('../../utils/resolveImportInput', async () => {
  const actual = await vi.importActual<typeof import('../../utils/resolveImportInput')>('../../utils/resolveImportInput')
  return { ...actual, resolveImportSource: (...args: unknown[]) => resolveImportSource(...args) }
})
vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client')
  return { ...actual, api: { ...actual.api, decodeBuildCode: vi.fn(async () => ({ build: { name: 'x', slots: [null, null, null, null], gear: [], skills: [] } })) } }
})
vi.mock('../../utils/buildCompat', () => ({ checkBuildCompatibility: () => [] }))

import ImportPanel from '../../components/ImportPanel'
import { useReferenceStore } from '../../store/referenceStore'
import { NamedLinkRemovedError } from '../../utils/resolveImportInput'

let renderer: TestRenderer.ReactTestRenderer | null = null
beforeEach(() => { resolveImportSource.mockReset(); useReferenceStore.setState({ season: 'SS13' }) })
afterEach(() => { act(() => { renderer?.unmount() }); renderer = null })

const text = () => JSON.stringify(renderer!.toJSON())
const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 20)) })

async function importCode(onImport = vi.fn()) {
  act(() => { renderer = TestRenderer.create(<ImportPanel onImport={onImport} />) })
  act(() => { renderer!.root.findByType('textarea').props.onChange({ target: { value: 'https://api.tlibuilder.com/u/tyra-4472/fire' } }) })
  const button = renderer!.root.findAllByType('button').find((b) => b.children.join('') === 'Import')!
  await act(async () => { await button.props.onClick() })
  await settle()
  return onImport
}

describe('ImportPanel — builds saved under another data version', () => {
  it('warns, naming the saved version, and waits for Import Anyway', async () => {
    resolveImportSource.mockResolvedValue({ code: 'tli1_x', dataVersion: 'SS12' })
    const onImport = await importCode()
    expect(text()).toContain('SS12')
    expect(text()).toContain('SS13')
    expect(onImport).not.toHaveBeenCalled()
    const anyway = renderer!.root.findAllByType('button').find((b) => b.children.join('') === 'Import Anyway')!
    act(() => { anyway.props.onClick() })
    expect(onImport).toHaveBeenCalledTimes(1)
  })

  it('imports straight away when the data version matches', async () => {
    resolveImportSource.mockResolvedValue({ code: 'tli1_x', dataVersion: 'SS13' })
    const onImport = await importCode()
    expect(onImport).toHaveBeenCalledTimes(1)
  })

  it('imports straight away for a raw code (no saved version known)', async () => {
    resolveImportSource.mockResolvedValue({ code: 'tli1_x', dataVersion: null })
    const onImport = await importCode()
    expect(onImport).toHaveBeenCalledTimes(1)
  })

  it('a removed named link says it was removed by its owner', async () => {
    resolveImportSource.mockRejectedValue(new NamedLinkRemovedError())
    const onImport = await importCode()
    expect(onImport).not.toHaveBeenCalled()
    expect(text()).toContain('This build was removed by its owner.')
  })
})
