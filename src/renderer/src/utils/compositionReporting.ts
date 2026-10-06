// Wires the anonymous composition reporter to the app. Off until App starts it, so tests and any
// other shell never reach the network. The Privacy preference is read on every call, and turning it
// off also aborts any report still in flight.
import { createAnalyticsClient } from '../api/analytics'
import {
  createCompositionReporter,
  mechanicsFromStats,
  type CompositionBuild,
  type CompositionReporter,
  type MemoryResolver,
  type StatsLike,
} from './buildComposition'
import type { Composition } from './buildComposition'
import { useUiPrefs } from '../store/uiPrefsStore'
import { useReferenceStore } from '../store/referenceStore'
import { useBuildStore } from '../store/buildStore'

let reporter: CompositionReporter | null = null
let unsubscribe: (() => void) | null = null

/**
 * Development servers and automated browsers (Playwright sets navigator.webdriver) must never add
 * to the production counters, so only a real production build reports.
 */
export function isReportingRuntime(env: { prod: boolean; webdriver: boolean }): boolean {
  return env.prod && !env.webdriver
}

export function startCompositionReporting(opts: { send?: (composition: Composition, signal?: AbortSignal) => Promise<void> } = {}): void {
  stopCompositionReporting()
  const send = opts.send ?? ((composition: Composition, signal?: AbortSignal) => createAnalyticsClient().sendComposition(composition, signal))
  const created = createCompositionReporter({
    send,
    isEnabled: () => useUiPrefs.getState().shareCompositionStats,
  })
  reporter = created
  // Opting out stops what is already on its way, not only what would start later.
  unsubscribe = useUiPrefs.subscribe((state, previous) => {
    if (previous.shareCompositionStats && !state.shareCompositionStats) created.cancelAll()
  })
}

export function stopCompositionReporting(): void {
  unsubscribe?.()
  unsubscribe = null
  reporter?.cancelAll()
  reporter = null
}

// Catalog rows as served at runtime. Base-stat rows carry the catalog `uuid` of the stat (the same
// uuid for every tier of that stat); revival rows have no identifier, but a tier-0 revival mod is a
// named catalog entry such as "Furious Roar".
interface CatalogRow { modifier: string; tier: number; uuid?: string; source?: string }

const SLUG_SOURCE = /[^A-Za-z0-9]+/g
const MEMORY_SOURCE: Record<string, string> = {
  origin: 'Memory of Origin', discipline: 'Memory of Discipline', progress: 'Memory of Progress',
}

/**
 * The stat a base-stat text belongs to, with the value removed. Mirrors HeroTraitScreen's getAffixName,
 * which the memory creator uses to group every tier of one stat. The creator rewrites the leading value
 * when it scales a base stat to the memory level, so the saved text often matches no catalog row exactly;
 * the stat family is what stays the same.
 */
export function statFamilyName(modifier: string): string {
  const name = modifier
    .replace(/^\+?(?:\d+(?:\.\d+)?|\([^)]+\))\s*%?\s*/, '')
    .replace(/\+?\(\d+(?:\.\d+)?[–-]\d+(?:\.\d+)?\)\s*%?\s*/g, '')
    .replace(/\+\d+(?:\.\d+)?\s*%?\s*/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return name ? name[0].toUpperCase() + name.slice(1) : name
}

export function memoryResolverFromCatalog(
  baseStats: CatalogRow[] | null | undefined,
  revival: CatalogRow[] | null | undefined,
): MemoryResolver {
  return {
    baseStat: (selection, memoryType) => {
      const source = MEMORY_SOURCE[memoryType]
      const family = statFamilyName(selection.modifier)
      if (!source || !family) return null
      // Every tier of one stat shares a catalog uuid; require exactly one so a clash is never guessed.
      const ids = new Set(
        (baseStats ?? [])
          .filter((r) => r.source === source && r.uuid && statFamilyName(r.modifier) === family)
          .map((r) => r.uuid as string),
      )
      return ids.size === 1 ? [...ids][0] : null
    },
    revival: (selection) => {
      // Only a named (tier 0) catalog entry is identifiable. Tiered rows are long effect text with no id.
      const row = (revival ?? []).find((r) => r.tier === 0 && r.modifier === selection.modifier)
      if (!row) return null
      const slug = row.modifier.toLowerCase().replace(SLUG_SOURCE, '_').replace(/^_+|_+$/g, '')
      return slug || null
    },
  }
}

/** Call after a successful, changed calculation. Fire and forget; never throws. */
export function reportAfterCalculation(): void {
  if (!reporter || !useUiPrefs.getState().shareCompositionStats) return
  const reference = useReferenceStore.getState()
  const dataVersion = reference.season
  if (!dataVersion) return
  const s = useBuildStore.getState()
  const build: CompositionBuild = {
    traitId: s.traitId,
    skills: s.skills,
    gear: s.gear,
    pactSpirits: s.pactSpirits,
    heroMemories: s.heroMemories,
    baseMemory: s.baseMemory,
    slots: s.slots,
    slates: s.slates,
    prisms: s.prisms,
  }
  void reporter.onCalculated({
    ok: true,
    build,
    dataVersion,
    mechanics: mechanicsFromStats(s.computedStats as unknown as StatsLike),
    memory: memoryResolverFromCatalog(
      reference.heroMemories?.base_stats as unknown as CatalogRow[] | undefined,
      reference.memoryRevival as unknown as CatalogRow[] | null,
    ),
  })
}
