import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import { useReferenceStore } from '../store/referenceStore'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}

describe('reference catalog loading', () => {
  beforeEach(() => {
    useReferenceStore.getState().clearReferenceData()
    vi.spyOn(api, 'getLegendaryGearIndex').mockResolvedValue({ items: [] } as never)
    vi.spyOn(api, 'getLegendaryGear').mockResolvedValue({ items: [] } as never)
    vi.spyOn(api, 'getCraftBaseItems').mockResolvedValue({ base_types: [] } as never)
    vi.spyOn(api, 'getCraftBaseTypes').mockResolvedValue({ base_types: [] } as never)
    vi.spyOn(api, 'getGrafts').mockResolvedValue({ grafts: [] } as never)
    vi.spyOn(api, 'getHeroMemories').mockResolvedValue({
      memory_types: [], base_stats: [], fixed_affixes: [], random_affixes: [],
    } as never)
    vi.spyOn(api, 'getMemoryRevival').mockResolvedValue({ affixes: [] } as never)
    vi.spyOn(api, 'getConditions').mockResolvedValue({} as never)
    vi.spyOn(api, 'getSkills').mockResolvedValue({ skills: [] } as never)
    vi.spyOn(api, 'getBeltBlends').mockResolvedValue({ blends: [] } as never)
  })

  afterEach(() => vi.restoreAllMocks())

  it('publishes a catalog as soon as it resolves without marking the full load complete', async () => {
    const traits = deferred<{ traits: never[]; season: string }>()
    const skills = deferred<{ skills: never[] }>()
    vi.spyOn(api, 'getHeroTraits').mockReturnValue(traits.promise as never)
    vi.spyOn(api, 'getSkills').mockReturnValue(skills.promise as never)
    const load = useReferenceStore.getState().loadReferenceData()
    traits.resolve({ traits: [{ trait_id: 'early-trait' }] as never[], season: 'SS13' })

    await vi.waitFor(() => expect(useReferenceStore.getState().heroTraits).toEqual([{ trait_id: 'early-trait' }]))
    expect(useReferenceStore.getState().season).toBe('SS13')
    expect(useReferenceStore.getState().referenceResolved).toBe(false)
    expect(useReferenceStore.getState().loadDone).toBeGreaterThan(0)

    skills.resolve({ skills: [] })
    await load
    expect(useReferenceStore.getState().referenceResolved).toBe(true)
    expect(useReferenceStore.getState().failedCatalogs.size).toBe(0)
  })

  it('retains the failed catalog name after every request settles', async () => {
    vi.spyOn(api, 'getHeroTraits').mockRejectedValue(new Error('catalog unavailable'))
    await useReferenceStore.getState().loadReferenceData()

    expect(useReferenceStore.getState().referenceResolved).toBe(true)
    expect([...useReferenceStore.getState().failedCatalogs]).toEqual(['heroTraits'])
    expect(useReferenceStore.getState().heroTraits).toBeNull()
  })
})
