import { describe, it, expect } from 'vitest'
import { createSyncRecordsFile } from './syncRecordsFile'

const rec = (id: string, over: Record<string, unknown> = {}) => ({
  localBuildId: id, accountUserId: 'user-A', cloudBuildId: 'cb', baseRevisionId: 'r', baseSemanticHash: 'h', ...over,
})

function setup(initial?: string) {
  let text: string | null = initial ?? null
  const file = createSyncRecordsFile({
    read: () => { if (text === null) throw new Error('ENOENT'); return text },
    write: (t) => { text = t },
  })
  return { file, text: () => text }
}

describe('sync records file', () => {
  it('reads empty when the file does not exist', () => {
    expect(setup().file.read()).toEqual([])
  })

  it('reads empty from a corrupt file instead of throwing', () => {
    expect(setup('{not json').file.read()).toEqual([])
  })

  it('puts and removes records, one per local build', () => {
    const { file } = setup()
    file.put(rec('a'))
    file.put(rec('b'))
    file.put(rec('a', { baseRevisionId: 'r2' }))
    expect(file.read().map((r) => [r.localBuildId, r.baseRevisionId]).sort()).toEqual([['a', 'r2'], ['b', 'r']])
    file.remove('a')
    expect(file.read().map((r) => r.localBuildId)).toEqual(['b'])
  })

  it('rejects records from the renderer that are malformed or carry extra fields', () => {
    const { file, text } = setup()
    expect(() => file.put({ localBuildId: 'a' } as never)).toThrow()
    expect(() => file.put('x' as never)).toThrow()
    file.put({ ...rec('a'), buildName: 'secret' } as never)
    expect(text()).not.toContain('secret')
  })

  it('drops malformed stored rows', () => {
    const { file } = setup(JSON.stringify({ version: 1, records: [rec('ok'), { localBuildId: 5 }] }))
    expect(file.read().map((r) => r.localBuildId)).toEqual(['ok'])
  })

  it('caps the number of records', () => {
    const seeded = Array.from({ length: 2000 }, (_, i) => rec('s' + i))
    const { file } = setup(JSON.stringify({ version: 1, records: seeded }))
    file.put(rec('new'))
    const ids = file.read().map((r) => r.localBuildId)
    expect(ids).toHaveLength(2000)
    expect(ids).toContain('new')
  })
})
