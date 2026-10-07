import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useUiPrefs } from '../../store/uiPrefsStore'
import { useReferenceStore } from '../../store/referenceStore'
import { useBuildStore } from '../../store/buildStore'
import { createAnalyticsClient } from '../../api/analytics'
import { startCompositionReporting, stopCompositionReporting, reportAfterCalculation } from '../../utils/compositionReporting'

// These tests drive the real reporter and the real analytics client and assert the literal request
// the service would receive. Only fetch is faked.

const BASE = 'https://api.example.test'
const flush = () => new Promise((r) => setTimeout(r, 0))

interface Sent { url: string; init: RequestInit; body: Record<string, unknown> }

function start() {
  const sent: Sent[] = []
  const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
    sent.push({ url, init, body: JSON.parse(String(init.body)) })
    return new Response(null, { status: 204 })
  }) as unknown as typeof fetch
  const client = createAnalyticsClient({ base: BASE, fetchImpl })
  startCompositionReporting({ send: (c, signal) => client.sendComposition(c, signal) })
  return { sent, fetchImpl }
}

const memory = (over: Record<string, unknown> = {}) => ({
  id: 'm', memoryType: 'origin', rarity: 'rare', fixedAffixes: [null, null], randomAffixes: [null, null],
  baseStat: null, revived: false, revivalMod: null, ...over,
})

beforeEach(() => {
  stopCompositionReporting()
  useUiPrefs.setState({ shareCompositionStats: true })
  useReferenceStore.setState({ season: 'SS13', heroMemories: { base_stats: [] }, memoryRevival: [] } as never)
  useBuildStore.setState({
    traitId: 'trait_x', name: 'My Secret Build', notes: 'private notes', customMods: ['custom text'],
    skills: [], gear: [], pactSpirits: [null, null, null], heroMemories: [null, null, null], baseMemory: null,
    slots: [null, null, null, null], slates: [], prisms: [], computedStats: {},
  } as never)
})

describe('literal composition payload', () => {
  it('sends exactly the four documented fields, no credentials, no auth header, no referrer', async () => {
    const { sent } = start()
    reportAfterCalculation()
    await flush()
    expect(sent).toHaveLength(1)
    expect(sent[0].url).toBe(`${BASE}/v1/stats/composition`)
    expect(Object.keys(sent[0].body).sort()).toEqual(['data_version', 'entities', 'mechanics', 'relations'])
    expect(sent[0].body).toEqual({
      data_version: 'SS13', entities: [{ type: 'hero_trait', id: 'trait_x' }], relations: [], mechanics: [],
    })
    expect(sent[0].init.credentials).toBe('omit')
    expect(sent[0].init.referrerPolicy).toBe('no-referrer')
    expect(Object.keys(sent[0].init.headers as Record<string, string>).map((k) => k.toLowerCase())).toEqual(['content-type'])
    const raw = String(sent[0].init.body)
    for (const leak of ['My Secret Build', 'private notes', 'custom text']) expect(raw).not.toContain(leak)
  })

  it('reports saved Vorax graft catalog IDs and omits unsupported graft identifiers', async () => {
    useBuildStore.setState({ gear: [
      { item_id: 'vorax_aberrant_limb_digits', is_vorax: true, name: 'Private display name' },
      { item_id: 'Typed graft name / not an ID', is_vorax: true, name: 'Another private name' },
      { item_id: '', is_vorax: true, name: 'Missing ID' },
      { item_id: 'vorax_aberrant_limb_digits', is_vorax: true, name: 'Duplicate' },
      { item_id: 'some_legendary', is_vorax: false, name: 'Ordinary gear' },
    ] } as never)
    const { sent } = start()
    reportAfterCalculation()
    await flush()
    expect(sent[0].body.entities).toEqual([
      { type: 'hero_trait', id: 'trait_x' },
      { type: 'graft', id: 'vorax_aberrant_limb_digits' },
      { type: 'legendary_item', id: 'some_legendary' },
    ])
    const raw = String(sent[0].init.body)
    expect(raw).not.toContain('Private display name')
    expect(raw).not.toContain('Typed graft name')
  })

  it('reports a base stat only when exactly one catalog uuid matches its family in the memory type', async () => {
    useReferenceStore.setState({
      heroMemories: { base_stats: [
        { modifier: '+90 Strength', tier: 1, uuid: 'uuid-str-origin', source: 'Memory of Origin' },
        { modifier: '+88 Strength', tier: 2, uuid: 'uuid-str-origin', source: 'Memory of Origin' },
        // Two different uuids for one family in the same type: ambiguous, so it must be omitted.
        { modifier: '+10 Dexterity', tier: 1, uuid: 'uuid-dex-a', source: 'Memory of Origin' },
        { modifier: '+9 Dexterity', tier: 2, uuid: 'uuid-dex-b', source: 'Memory of Origin' },
      ] },
    } as never)
    useBuildStore.setState({ heroMemories: [
      memory({ baseStat: { modifier: '+93.5 Strength', tier: 3, rolledValue: null } }),
      memory({ memoryType: 'origin', rarity: 'magic', baseStat: { modifier: '+12 Dexterity', tier: 3, rolledValue: null } }),
      memory({ memoryType: 'progress', rarity: 'epic', baseStat: { modifier: '+50 Strength', tier: 3, rolledValue: null } }),
    ] } as never)
    const { sent } = start()
    reportAfterCalculation()
    await flush()
    const baseStats = (sent[0].body.entities as { type: string; id: string }[]).filter((e) => e.type === 'memory_base_stat')
    expect(baseStats).toEqual([{ type: 'memory_base_stat', id: 'uuid-str-origin' }])
  })

  it('omits an unknown stat family and never sends the typed text', async () => {
    useReferenceStore.setState({ heroMemories: { base_stats: [{ modifier: '+90 Strength', tier: 1, uuid: 'u1', source: 'Memory of Origin' }] } } as never)
    useBuildStore.setState({ heroMemories: [memory({ baseStat: { modifier: '+5 Totally Made Up Stat', tier: 3, rolledValue: 5 } }), null, null] } as never)
    const { sent } = start()
    reportAfterCalculation()
    await flush()
    const raw = String(sent[0].init.body)
    expect(raw).not.toContain('Made Up')
    expect(raw).not.toContain('memory_base_stat')
  })

  it('a revival slug comes from the current season catalog row, never from the saved text', async () => {
    useReferenceStore.setState({ memoryRevival: [{ modifier: 'Furious Roar', tier: 0 }] } as never)
    useBuildStore.setState({ heroMemories: [
      memory({ revived: true, revivalMod: { modifier: 'Furious Roar', tier: 0, rolledValue: null } }),
      memory({ memoryType: 'discipline', revived: true, revivalMod: { modifier: 'Furious Roar!! (typed)', tier: 0, rolledValue: null } }),
      memory({ memoryType: 'progress', revived: true, revivalMod: { modifier: 'furious roar', tier: 0, rolledValue: null } }),
    ] } as never)
    const { sent } = start()
    reportAfterCalculation()
    await flush()
    const revivals = (sent[0].body.entities as { type: string; id: string }[]).filter((e) => e.type === 'memory_revival')
    expect(revivals).toEqual([{ type: 'memory_revival', id: 'furious_roar' }])
  })

  it('a revival mod absent from this season\'s catalog is not reported', async () => {
    useReferenceStore.setState({ season: 'SS14', memoryRevival: [{ modifier: 'Other Mod', tier: 0 }] } as never)
    useBuildStore.setState({ heroMemories: [memory({ revived: true, revivalMod: { modifier: 'Furious Roar', tier: 0, rolledValue: null } }), null, null] } as never)
    const { sent } = start()
    reportAfterCalculation()
    await flush()
    expect(sent[0].body.data_version).toBe('SS14')
    expect((sent[0].body.entities as { type: string }[]).some((e) => e.type === 'memory_revival')).toBe(false)
  })

  it('a tiered revival row is never reported', async () => {
    useReferenceStore.setState({ memoryRevival: [{ modifier: '-20 % All Stats +(98–100) to All Stats', tier: 1 }] } as never)
    useBuildStore.setState({ heroMemories: [memory({ revived: true, revivalMod: { modifier: '-20 % All Stats +(98–100) to All Stats', tier: 1, rolledValue: 99 } }), null, null] } as never)
    const { sent } = start()
    reportAfterCalculation()
    await flush()
    expect(String(sent[0].init.body)).not.toContain('memory_revival')
    expect(String(sent[0].init.body)).not.toContain('All Stats')
  })

  it('sends the eight baseline mechanics from the engine result and no other flag', async () => {
    useBuildStore.setState({
      computedStats: {
        offense: { supported: true, spell_burst_count: 2, tangle_count: 1, shadow_count: 1, channeled_max_stacks: 5, trigger_interval: 1, damage_rows: [{ kind: 'dot' }] },
        minion_offense: { owner: { supported: true } },
        reservation: { per_skill: [{}] },
      },
    } as never)
    const { sent } = start()
    reportAfterCalculation()
    await flush()
    expect(sent[0].body.mechanics).toEqual(['channeling', 'damage_over_time', 'minion', 'reservation', 'shadow_strike', 'spell_burst', 'tangle', 'trigger'])
  })
})

describe('opting out', () => {
  it('stops every later send, including a changed composition, and attaches no credentials to anything sent before', async () => {
    const { sent, fetchImpl } = start()
    reportAfterCalculation()
    await flush()
    expect(sent).toHaveLength(1)
    expect(sent[0].init.credentials).toBe('omit')

    useUiPrefs.getState().setShareCompositionStats(false)
    useBuildStore.setState({ traitId: 'trait_changed' } as never)
    reportAfterCalculation()
    useBuildStore.setState({ traitId: 'trait_changed_again' } as never)
    reportAfterCalculation()
    await flush()
    expect(fetchImpl).toHaveBeenCalledTimes(1)
  })

  it('aborts a report still in flight, and does not retry it after turning back on', async () => {
    let aborted = false
    const fetchImpl = vi.fn((_url: string, init: RequestInit) => new Promise<Response>((_res, rej) => {
      ;(init.signal as AbortSignal).addEventListener('abort', () => { aborted = true; rej(new DOMException('aborted', 'AbortError')) })
    })) as unknown as typeof fetch
    const client = createAnalyticsClient({ base: BASE, fetchImpl })
    startCompositionReporting({ send: (c, signal) => client.sendComposition(c, signal) })
    reportAfterCalculation()
    await flush()
    expect(fetchImpl).toHaveBeenCalledTimes(1)
    useUiPrefs.getState().setShareCompositionStats(false)
    await flush()
    expect(aborted).toBe(true)
    useUiPrefs.getState().setShareCompositionStats(true)
    await flush()
    expect(fetchImpl).toHaveBeenCalledTimes(1) // nothing was queued behind the abort
  })
})
