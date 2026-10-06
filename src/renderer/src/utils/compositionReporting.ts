// Wires the anonymous composition reporter to the app. Off until App starts it, so tests and any
// other shell never reach the network. The Privacy preference is read on every call.
import { createAnalyticsClient } from '../api/analytics'
import { createCompositionReporter, type CompositionBuild, type CompositionReporter } from './buildComposition'
import type { Composition } from './buildComposition'
import { useUiPrefs } from '../store/uiPrefsStore'
import { useReferenceStore } from '../store/referenceStore'
import { useBuildStore } from '../store/buildStore'

let reporter: CompositionReporter | null = null

/**
 * Development servers and automated browsers (Playwright sets navigator.webdriver) must never add
 * to the production counters, so only a real production build reports.
 */
export function isReportingRuntime(env: { prod: boolean; webdriver: boolean }): boolean {
  return env.prod && !env.webdriver
}

export function startCompositionReporting(opts: { send?: (composition: Composition) => Promise<void> } = {}): void {
  const send = opts.send ?? ((composition: Composition) => createAnalyticsClient().sendComposition(composition))
  reporter = createCompositionReporter({
    send,
    isEnabled: () => useUiPrefs.getState().shareCompositionStats,
  })
}

export function stopCompositionReporting(): void {
  reporter = null
}

/** Call after a successful, changed calculation. Fire and forget; never throws. */
export function reportAfterCalculation(): void {
  if (!reporter || !useUiPrefs.getState().shareCompositionStats) return
  const dataVersion = useReferenceStore.getState().season
  if (!dataVersion) return
  const s = useBuildStore.getState()
  const build: CompositionBuild = {
    traitId: s.traitId,
    skills: s.skills,
    gear: s.gear,
    pactSpirits: s.pactSpirits,
    heroMemories: s.heroMemories,
    slots: s.slots,
    slates: s.slates,
    prisms: s.prisms,
  }
  void reporter.onCalculated({ ok: true, build, dataVersion })
}
