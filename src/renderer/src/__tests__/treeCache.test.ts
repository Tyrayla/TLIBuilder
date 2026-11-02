import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../api/client', () => ({
  api: {
    getTree: vi.fn(),
    getEtherealPrism: vi.fn(),
  },
}))

import { api, type TreeData } from '../api/client'
import {
  getTreeCached, peekTree, prefetchTrees, clearTreeCache, getEtherealPrismCached, peekEtherealPrism,
} from '../api/treeCache'

const tree = (name: string) => ({ name, nodes: [], connections: [], core_talent_slots: [] }) as unknown as TreeData

describe('treeCache', () => {
  beforeEach(() => {
    clearTreeCache()
    vi.mocked(api.getTree).mockReset()
    vi.mocked(api.getEtherealPrism).mockReset()
  })

  it('fetches a tree once and serves repeat opens from the cache', async () => {
    vi.mocked(api.getTree).mockImplementation(async name => tree(name))
    expect(peekTree('Warrior')).toBeUndefined()

    const [a, b] = await Promise.all([getTreeCached('Warrior'), getTreeCached('Warrior')])
    await getTreeCached('Warrior')

    expect(api.getTree).toHaveBeenCalledTimes(1)
    expect(a).toBe(b)
    expect(peekTree('Warrior')?.name).toBe('Warrior')
  })

  it('evicts a failed fetch so the next open retries', async () => {
    vi.mocked(api.getTree)
      .mockRejectedValueOnce(new Error('GET /tree/Warrior failed (500)'))
      .mockResolvedValueOnce(tree('Warrior'))

    await expect(getTreeCached('Warrior')).rejects.toThrow('failed (500)')
    expect(peekTree('Warrior')).toBeUndefined()

    expect((await getTreeCached('Warrior')).name).toBe('Warrior')
    expect(api.getTree).toHaveBeenCalledTimes(2)
  })

  it('prefetches sequentially and skips trees already cached', async () => {
    const order: string[] = []
    vi.mocked(api.getTree).mockImplementation(async name => { order.push(name); return tree(name) })
    await getTreeCached('The Brave')

    await prefetchTrees(['The Brave', 'Warlord', 'Onslaughter'])

    expect(order).toEqual(['The Brave', 'Warlord', 'Onslaughter'])
    expect(peekTree('Onslaughter')?.name).toBe('Onslaughter')
  })

  it('a clear (season change) drops cached trees and ignores responses from before the clear', async () => {
    let resolveOld!: (t: TreeData) => void
    vi.mocked(api.getTree)
      .mockImplementationOnce(() => new Promise<TreeData>(r => { resolveOld = r }))
      .mockResolvedValueOnce(tree('Warrior (new season)'))

    const stale = getTreeCached('Warrior')
    clearTreeCache()
    resolveOld(tree('Warrior (old season)'))
    await stale

    expect(peekTree('Warrior')).toBeUndefined()
    expect((await getTreeCached('Warrior')).name).toBe('Warrior (new season)')
  })

  it('caches the Ethereal Prism catalog for the session', async () => {
    vi.mocked(api.getEtherealPrism).mockResolvedValue({ season: 'SS13', items: [], catalog: null } as never)

    await getEtherealPrismCached()
    await getEtherealPrismCached()

    expect(api.getEtherealPrism).toHaveBeenCalledTimes(1)
    expect(peekEtherealPrism()?.season).toBe('SS13')
  })
})
