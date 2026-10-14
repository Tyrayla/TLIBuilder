import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useUiPrefs } from '../../store/uiPrefsStore'
import { useReferenceStore } from '../../store/referenceStore'
import { useBuildStore } from '../../store/buildStore'
import {
  isReportingRuntime,
  startCompositionReporting,
  stopCompositionReporting,
  reportAfterCalculation,
} from '../../utils/compositionReporting'

const flush = () => new Promise((r) => setTimeout(r, 0))

beforeEach(() => {
  stopCompositionReporting()
  useUiPrefs.setState({ shareCompositionStats: true })
  useReferenceStore.setState({ season: 'season-9' })
  useBuildStore.setState({ traitId: 'trait_berserker', name: 'secret name' } as never)
})

describe('composition reporting', () => {
  it('is off until the app starts it (no network from tests or other shells)', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    reportAfterCalculation()
    await flush()
    expect(send).not.toHaveBeenCalled()
  })

  it('sends canonical ids with the data version after a calculation', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    startCompositionReporting({ send })
    reportAfterCalculation()
    await flush()
    expect(send).toHaveBeenCalledTimes(1)
    const sent = send.mock.calls[0][0]
    expect(sent.dataVersion).toBe('season-9')
    expect(sent.entities).toContainEqual({ type: 'hero_trait', id: 'trait_berserker' })
    expect(JSON.stringify(sent)).not.toContain('secret name')
  })

  it('stops reporting the moment the user turns it off in Privacy settings', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    startCompositionReporting({ send })
    useUiPrefs.setState({ shareCompositionStats: false })
    reportAfterCalculation()
    await flush()
    expect(send).not.toHaveBeenCalled()
  })

  it('sends the engine-proven mechanic flags from the latest calculation', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    startCompositionReporting({ send })
    useBuildStore.setState({
      computedStats: { offense: { supported: true, tangle_count: 2, damage_rows: [{ kind: 'dot' }] }, reservation: { per_skill: [{}] } },
    } as never)
    reportAfterCalculation()
    await flush()
    expect(send.mock.calls[0][0].mechanics).toEqual(['damage_over_time', 'reservation', 'tangle'])
    useBuildStore.setState({ computedStats: {} } as never)
  })

  it('identifies a Hero Memory base stat by catalog uuid and a named revival mod by its catalog name', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    startCompositionReporting({ send })
    useReferenceStore.setState({
      heroMemories: { base_stats: [{ modifier: '+90 Strength', tier: 1, uuid: 'a65f0fbf-bc8f-5e90-a594-7b70b6fb7a63', source: 'Memory of Origin' }] },
      memoryRevival: [
        { modifier: 'Furious Roar', tier: 0 },
        { modifier: '-20 % All Stats +(98–100) to All Stats', tier: 1 },
      ],
    } as never)
    useBuildStore.setState({
      heroMemories: [{ memoryType: 'origin', rarity: 'ultimate', baseStat: { modifier: '+90 Strength', tier: 1, rolledValue: null }, revived: true, revivalMod: { modifier: 'Furious Roar', tier: 0, rolledValue: null }, fixedAffixes: [null, null], randomAffixes: [null, null], id: 'm' }, null, null],
    } as never)
    reportAfterCalculation()
    await flush()
    const entities = send.mock.calls[0][0].entities
    expect(entities).toContainEqual({ type: 'memory_base_stat', id: 'a65f0fbf-bc8f-5e90-a594-7b70b6fb7a63' })
    expect(entities).toContainEqual({ type: 'memory_revival', id: 'furious_roar' })
    useBuildStore.setState({ heroMemories: [null, null, null] } as never)
  })

  it('identifies a level-scaled base stat (text no catalog row has) by its stat family within the memory type', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    startCompositionReporting({ send })
    useReferenceStore.setState({
      heroMemories: { base_stats: [
        { modifier: '+90 Strength', tier: 1, uuid: 'uuid-origin-strength', source: 'Memory of Origin' },
        { modifier: '+88 Strength', tier: 2, uuid: 'uuid-origin-strength', source: 'Memory of Origin' },
        { modifier: '+90 Strength', tier: 1, uuid: 'uuid-discipline-strength', source: 'Memory of Discipline' },
        { modifier: '+(10–12) % Movement Speed', tier: 1, uuid: 'uuid-origin-move', source: 'Memory of Origin' },
      ] },
      memoryRevival: [],
    } as never)
    const memory = (type: string, modifier: string) => ({ memoryType: type, rarity: 'rare', baseStat: { modifier, tier: 3, rolledValue: null }, fixedAffixes: [null, null], randomAffixes: [null, null], id: 'm' })
    useBuildStore.setState({ heroMemories: [memory('origin', '+93.5 Strength'), memory('discipline', '+41.2 Strength'), null] } as never)
    reportAfterCalculation()
    await flush()
    const ids = send.mock.calls[0][0].entities.filter((e: { type: string }) => e.type === 'memory_base_stat').map((e: { id: string }) => e.id).sort()
    expect(ids).toEqual(['uuid-discipline-strength', 'uuid-origin-strength'])
    useBuildStore.setState({ heroMemories: [null, null, null] } as never)
  })

  it('reports nothing for a base stat whose family the catalog does not know', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    startCompositionReporting({ send })
    useReferenceStore.setState({ heroMemories: { base_stats: [{ modifier: '+90 Strength', tier: 1, uuid: 'u', source: 'Memory of Origin' }] }, memoryRevival: [] } as never)
    useBuildStore.setState({ heroMemories: [{ memoryType: 'origin', rarity: 'rare', baseStat: { modifier: '+5 Typed By Hand', tier: 3, rolledValue: null }, fixedAffixes: [null, null], randomAffixes: [null, null], id: 'm' }, null, null] } as never)
    reportAfterCalculation()
    await flush()
    expect(send.mock.calls[0][0].entities.some((e: { type: string }) => e.type === 'memory_base_stat')).toBe(false)
    useBuildStore.setState({ heroMemories: [null, null, null] } as never)
  })

  it('does not identify a tiered revival row, which the catalog gives no identifier', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    startCompositionReporting({ send })
    useReferenceStore.setState({ memoryRevival: [{ modifier: '-20 % All Stats +(98–100) to All Stats', tier: 1 }] } as never)
    useBuildStore.setState({
      heroMemories: [{ memoryType: 'origin', rarity: 'ultimate', baseStat: null, revived: true, revivalMod: { modifier: '-20 % All Stats +(98–100) to All Stats', tier: 1, rolledValue: null }, fixedAffixes: [null, null], randomAffixes: [null, null], id: 'm' }, null, null],
    } as never)
    reportAfterCalculation()
    await flush()
    expect(send.mock.calls[0][0].entities.some((e: { type: string }) => e.type === 'memory_revival')).toBe(false)
    useBuildStore.setState({ heroMemories: [null, null, null] } as never)
  })

  it('turning reporting off aborts a report that is still in flight', async () => {
    let signal: AbortSignal | undefined
    const send = vi.fn((_c: unknown, s?: AbortSignal) => new Promise<void>((_res, rej) => {
      signal = s
      s?.addEventListener('abort', () => rej(new Error('aborted')))
    }))
    startCompositionReporting({ send: send as never })
    reportAfterCalculation()
    await flush()
    expect(send).toHaveBeenCalledTimes(1)
    useUiPrefs.getState().setShareCompositionStats(false)
    expect(signal?.aborted).toBe(true)
  })

  it('does not report without a known data version', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    startCompositionReporting({ send })
    useReferenceStore.setState({ season: null })
    reportAfterCalculation()
    await flush()
    expect(send).not.toHaveBeenCalled()
  })

  it('only a production build driven by a person reports', () => {
    expect(isReportingRuntime({ prod: true, webdriver: false })).toBe(true)
    expect(isReportingRuntime({ prod: false, webdriver: false })).toBe(false)
    expect(isReportingRuntime({ prod: true, webdriver: true })).toBe(false)
  })

  it('reporting is on by default for a fresh install', () => {
    expect(useUiPrefs.getInitialState().shareCompositionStats).toBe(true)
  })
})
