import { create } from 'zustand'
import { isEqual } from 'lodash-es'
import type {
  TreeSlot, SavedSlate, EquippedGearItem,
  CreatedHeroMemory, SelectedPactSpirit, StatSheetResponse, PactSpirit,
} from '../api/client'
import { EMPTY_STAT_SHEET } from '../api/client'

// The stats-relevant subset of session fields. Non-stats fields (buildId,
// buildName, activeSlot, skills, traitId, traitSlotLevels,
// advancedTraitSelections, notes) stay in App.tsx session state only.
interface StatsInputs {
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  conditionState: Record<string, number | boolean>
  gear: EquippedGearItem[]
  characterLevel: number
  hasPrism: boolean
  heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]
  pactSpirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]
}

interface BuildStore extends StatsInputs {
  allSpirits: PactSpirit[]
  // "resolved" means the spirits fetch has settled (success OR failure).
  // The recalc hook bails until this is true so it never runs with an empty
  // spirit list mid-load. On failure it is set true with allSpirits: [] so
  // the build can still compute without spirit effects.
  spiritsResolved: boolean
  spiritsFetchFailed: boolean

  // Computed output — writing these MUST NOT bump buildVersion (infinite loop)
  computedStats: StatSheetResponse
  statsLoading: boolean
  statsError: string

  // Versioning — the single trigger for recalc
  buildVersion: number      // bumped on every genuine input change
  computedVersion: number   // version the cached stats were built from

  // Batch-sync from App.tsx during migration phase.
  // Guards with isEqual; only bumps buildVersion if something actually changed.
  syncStatsInputs: (inputs: StatsInputs) => void

  // Reference data — bumps buildVersion so first load triggers recalc
  setAllSpirits: (spirits: PactSpirit[]) => void
  setSpiritsFailure: () => void

  // Result write-back
  setComputedStats: (stats: StatSheetResponse, version: number) => void
  setStatsLoading: (v: boolean) => void
  setStatsError: (e: string) => void
}

const DEFAULT_INPUTS: StatsInputs = {
  slots: [null, null, null, null],
  slates: [],
  conditionState: {},
  gear: [],
  characterLevel: 100,
  hasPrism: false,
  heroMemories: [null, null, null],
  pactSpirits: [null, null, null],
}

export const useBuildStore = create<BuildStore>((set) => ({
  ...DEFAULT_INPUTS,
  allSpirits: [],
  spiritsResolved: false,
  spiritsFetchFailed: false,
  computedStats: EMPTY_STAT_SHEET,
  statsLoading: false,
  statsError: '',
  buildVersion: 0,
  computedVersion: -1,

  syncStatsInputs: (inputs) =>
    set((s) => {
      const changed = (Object.keys(inputs) as (keyof StatsInputs)[])
        .some(k => !isEqual(s[k], inputs[k]))
      if (!changed) return s
      return { ...inputs, buildVersion: s.buildVersion + 1 }
    }),

  setAllSpirits: (allSpirits) =>
    set((s) => {
      if (s.spiritsResolved && isEqual(s.allSpirits, allSpirits)) return s
      return { allSpirits, spiritsResolved: true, buildVersion: s.buildVersion + 1 }
    }),

  setSpiritsFailure: () =>
    set((s) => {
      if (s.spiritsResolved) return s
      return { spiritsResolved: true, spiritsFetchFailed: true, buildVersion: s.buildVersion + 1 }
    }),

  // CRITICAL: must NOT bump buildVersion — would cause infinite recalc loop
  setComputedStats: (computedStats, computedVersion) =>
    set({ computedStats, computedVersion, statsLoading: false, statsError: '' }),

  setStatsLoading: (statsLoading) => set({ statsLoading }),
  setStatsError: (statsError) => set({ statsError, statsLoading: false }),
}))
