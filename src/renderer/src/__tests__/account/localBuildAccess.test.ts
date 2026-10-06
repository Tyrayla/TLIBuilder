import { describe, it, expect, vi } from 'vitest'
import zlib from 'node:zlib'
import { createLocalBuildAccess } from '../../utils/localBuildAccess'

function codeOf(obj: unknown): string {
  const deflated = zlib.deflateSync(Buffer.from(JSON.stringify(obj), 'utf-8'), { level: 9 })
  return `tli1_${deflated.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}`
}

function setup() {
  const stored = new Map<string, Record<string, unknown>>([
    ['L1', { id: 'L1', name: 'Fire', slots: [], createdAt: 1, updatedAt: 2 }],
  ])
  let next = 100
  const api = {
    getBuilds: vi.fn(async () => [...stored.values()]),
    postBuild: vi.fn(async (b: Record<string, unknown>) => {
      const id = (b.id as string | undefined) ?? `L${++next}`
      stored.set(id, { ...b, id })
      return { ...b, id }
    }),
    // The real encoder strips technical fields; the fake mirrors that.
    encodeBuildCode: vi.fn(async (b: Record<string, unknown>) => {
      const { id: _id, createdAt: _c, updatedAt: _u, ...rest } = b
      return { code: codeOf({ v: 2, ...rest }) }
    }),
    decodeBuildCode: vi.fn(async (code: string) => {
      const json = JSON.parse(zlib.inflateSync(Buffer.from(code.slice(5).replace(/-/g, '+').replace(/_/g, '/'), 'base64')).toString())
      return { build: json }
    }),
  }
  return { api, stored, access: createLocalBuildAccess(api) }
}

describe('local build access', () => {
  it('reads a saved build as its code, name and semantic hash', async () => {
    const { access } = setup()
    const read = await access.read('L1')
    expect(read.name).toBe('Fire')
    expect(read.code.startsWith('tli1_')).toBe(true)
    expect(read.hash).toMatch(/^[0-9a-f]{64}$/)
  })

  it('keeps the hash stable across a save that only changes technical fields', async () => {
    const { access, stored } = setup()
    const before = (await access.read('L1')).hash
    stored.set('L1', { ...stored.get('L1')!, updatedAt: 999 })
    expect((await access.read('L1')).hash).toBe(before)
  })

  it('changes the hash when the build content changes', async () => {
    const { access, stored } = setup()
    const before = (await access.read('L1')).hash
    stored.set('L1', { ...stored.get('L1')!, notes: 'edited' })
    expect((await access.read('L1')).hash).not.toBe(before)
  })

  it('reports a missing build instead of guessing', async () => {
    const { access } = setup()
    await expect(access.read('nope')).rejects.toThrow(/not found/i)
  })

  it('renames by saving the same build with the new name', async () => {
    const { access, stored, api } = setup()
    await access.rename('L1', 'Short')
    expect(stored.get('L1')!.name).toBe('Short')
    expect(api.postBuild).toHaveBeenCalledWith(expect.objectContaining({ id: 'L1', name: 'Short' }))
  })

  it('creates a new local build from cloud content with no id (never overwrites)', async () => {
    const { access, stored, api } = setup()
    const id = await access.createFromCloud(codeOf({ v: 2, name: 'From cloud', slots: [] }), 'Cloud name')
    expect(api.postBuild).toHaveBeenLastCalledWith(expect.objectContaining({ id: undefined, name: 'Cloud name' }))
    expect(id).not.toBe('L1')
    expect(stored.get(id)!.name).toBe('Cloud name')
    expect(stored.get('L1')!.name).toBe('Fire')
  })

  it('replaces a specific local build from cloud content', async () => {
    const { access, stored } = setup()
    await access.replaceFromCloud('L1', codeOf({ v: 2, name: 'Cloud', slots: [], notes: 'n' }), 'Cloud')
    expect(stored.get('L1')).toMatchObject({ id: 'L1', name: 'Cloud', notes: 'n' })
  })
})
