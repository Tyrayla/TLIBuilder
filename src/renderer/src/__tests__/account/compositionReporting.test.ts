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
