import { create } from 'zustand'
import { isEqual } from 'lodash-es'
import type {
  TreeSlot, SavedSlate, SlateTemplate, PlacedPrism, CraftedPrism, EquippedGearItem, EquippedSkill, EquippedSupportSkill,
  CreatedHeroMemory, SelectedPactSpirit, StatSheetResponse, PactSpirit, SkillEngineInput, InstalledFate, UndeterminedFate,
  Loadout,
} from '../api/client'
import { EMPTY_STAT_SHEET } from '../api/client'
import {
  ALL_AREAS, readArea, resolvedPatch, loadoutById, ownerLoadout, snapshotAllAreas,
  loadoutKeyFromResolved, loadoutKeyFromState,
} from '../utils/loadoutAreas'

const genLoadoutId = (): string =>
  (globalThis.crypto?.randomUUID?.() ?? `lo${Date.now()}${Math.floor(Math.random() * 1e6)}`)

// All fields that are loaded/reset atomically when opening a build
export interface LoadedBuild {
  buildId: string | null
  buildName: string
  activeSlot: number
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  slateInventory: SlateTemplate[]
  prisms: PlacedPrism[]
  prismInventory: CraftedPrism[]
  conditionState: Record<string, number | boolean>
  gear: EquippedGearItem[]
  skills: EquippedSkill[]
  characterLevel: number
  traitId: string | null
  traitSlotLevels: number[]
  advancedTraitSelections: string[]
  traitSkillSupports: EquippedSupportSkill[]
  heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]
  pactSpirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]
  fates: Record<string, InstalledFate>
  undetermined: (UndeterminedFate | null)[]
  notes: string
  customMods: string[]
  loadouts: Loadout[]
  activeLoadoutId: string
}

interface BuildStore {
  // Build identity
  buildId: string | null
  buildName: string
  setBuildId: (id: string | null) => void
  setBuildName: (name: string) => void

  // Navigation
  activeSlot: number
  setActiveSlot: (i: number) => void

  // Skills (also derives mainSkill)
  skills: EquippedSkill[]
  setSkills: (skills: EquippedSkill[]) => void

  // Trait / hero memories
  traitId: string | null
  traitSlotLevels: number[]
  advancedTraitSelections: string[]
  traitSkillSupports: EquippedSupportSkill[]   // supports socketed into the trait skill slot (Holy Domain)
  setTraitId: (id: string | null) => void
  setTraitSlotLevels: (levels: number[]) => void
  setAdvancedTraitSelections: (sels: string[]) => void
  setTraitSkillSupports: (supports: EquippedSupportSkill[]) => void

  // Notes
  notes: string
  setNotes: (notes: string) => void

  // Compound trait setter — updates all three trait fields atomically (one buildVersion bump)
  setTraitData: (traitId: string | null, traitSlotLevels: number[], advancedTraitSelections: string[]) => void

  // Stats-relevant data fields
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  slateInventory: SlateTemplate[]
  prisms: PlacedPrism[]
  prismInventory: CraftedPrism[]
  conditionState: Record<string, number | boolean>
  gear: EquippedGearItem[]
  characterLevel: number
  heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]
  pactSpirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]
  fates: Record<string, InstalledFate>            // pact fates keyed by "<spiritSlotIdx>:<nodeDataIdx>"
  undetermined: (UndeterminedFate | null)[]       // one per spirit slot (index 0–2)
  // Transient: never set on the real store — only by damage-delta `step`/`base` transforms to price a
  // single pact-spirit node (one occurrence of each listed effect line is removed before payload build).
  spiritEffectExclude?: string[]

  // Individual setters for stats-relevant fields (bump buildVersion)
  setSlots: (slots: (TreeSlot | null)[]) => void
  setSlates: (slates: SavedSlate[]) => void
  setSlateInventory: (slateInventory: SlateTemplate[]) => void
  setPrisms: (prisms: PlacedPrism[]) => void
  setPrismInventory: (prismInventory: CraftedPrism[]) => void
  setConditionState: (state: Record<string, number | boolean>) => void
  setGear: (gear: EquippedGearItem[]) => void
  setCharacterLevel: (level: number) => void
  // Uptime calc mode (global): 'max' (assume-max, default) | 'real' (compute ramp). Not part of the saved
  // build — a display/calc preference. Drives the engine's uptime_mode for ailment ramp (Numbed, …).
  uptimeMode: 'max' | 'real'
  setUptimeMode: (m: 'max' | 'real') => void
  setHeroMemories: (memories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]) => void
  setPactSpirits: (spirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]) => void
  setFates: (fates: Record<string, InstalledFate>) => void
  setUndetermined: (undetermined: (UndeterminedFate | null)[]) => void

  // Slot mutation actions (bump buildVersion)
  setSlot: (slotIndex: number, slot: TreeSlot | null) => void
  reorderSlots: (fromSlot: number, toSlot: number) => void
  shiftSlotUp: (fromSlot: number) => void
  updateSlotNodeStates: (slotIndex: number, nodeStates: Record<string, number>) => void
  updateSlotCoreTalentSelections: (slotIndex: number, selections: Record<string, string>) => void

  // Atomic build load — sets all fields at once, resets computedStats
  loadBuild: (data: LoadedBuild) => void

  // Reference data — bumps buildVersion so first load triggers recalc
  allSpirits: PactSpirit[]
  spiritsResolved: boolean
  spiritsFetchFailed: boolean
  setAllSpirits: (spirits: PactSpirit[]) => void
  setSpiritsFailure: () => void

  // Main skill for offense calculation
  mainSkill: SkillEngineInput | null
  setMainSkill: (skill: SkillEngineInput | null) => void

  // Custom mods — bump buildVersion on change
  customMods: string[]
  setCustomMods: (mods: string[]) => void
  addCustomMod: (text: string) => void
  removeCustomMod: (index: number) => void
  updateCustomMod: (index: number, text: string) => void

  // ── Loadouts ────────────────────────────────────────────────────────────────
  // Each loadout is a full variant of the swappable areas; the live store reflects the active loadout's resolved
  // view. `loadoutStatsCache` is transient (never persisted) — it lets unchanged loadouts swap with no recompute.
  loadouts: Loadout[]
  activeLoadoutId: string
  loadoutStatsCache: Record<string, { stats: StatSheetResponse; key: string }>
  // Structural edits (rename/create/delete/inheritance). Flushes the live store into the active loadout first (so
  // unsaved edits aren't lost), applies the mutator to a deep copy of the loadouts, re-syncs the active loadout's
  // resolved view into the store, and bumps buildVersion (marks dirty + recalc + cache refresh).
  editLoadouts: (mutator: (loadouts: Loadout[]) => Loadout[]) => void
  switchLoadout: (targetId: string) => void           // flush current → load target (one bump; cache-aware)
  flushActiveLoadout: () => void                       // write the live store back into the active loadout (pre-save)
  cacheActiveLoadoutStats: (stats: StatSheetResponse) => void  // called by useBuildCalculation when results land

  // Computed output — writing these MUST NOT bump buildVersion (infinite loop)
  computedStats: StatSheetResponse
  statsLoading: boolean
  statsError: string
  setComputedStats: (stats: StatSheetResponse, version: number) => void
  setStatsLoading: (v: boolean) => void
  setStatsError: (e: string) => void

  // Versioning — the single trigger for recalc
  buildVersion: number
  computedVersion: number
}

const DEFAULT_BUILD: LoadedBuild = {
  buildId: null,
  buildName: '',
  activeSlot: 0,
  slots: [null, null, null, null],
  slates: [],
  slateInventory: [],
  prisms: [],
  prismInventory: [],
  conditionState: {},
  gear: [],
  skills: [],
  characterLevel: 100,
  traitId: null,
  traitSlotLevels: [1, 1, 1, 1],
  advancedTraitSelections: [],
  traitSkillSupports: [],
  heroMemories: [null, null, null],
  pactSpirits: [null, null, null],
  fates: {},
  undetermined: [null, null, null],
  notes: '',
  customMods: [],
  loadouts: [],
  activeLoadoutId: '',
}

function deriveMainSkill(skills: EquippedSkill[]): SkillEngineInput | null {
  // The main skill drives the headline "DPS vs Target". Prefer slot 1, but fall back to the first
  // populated ACTIVE slot (1-5) so a build with its damage skill parked outside slot 1 still has a main
  // skill instead of a blank DPS. (Disabled skills are skipped.)
  const actives = skills
    .filter(sk => sk.slot <= 5 && sk.enabled !== false)
    .sort((a, b) => a.slot - b.slot)
  const main = actives.find(sk => sk.slot === 1) ?? actives[0]
  return main ? { skill_id: main.item_id, level: main.level ?? 1 } : null
}

export const useBuildStore = create<BuildStore>((set, get) => ({
  ...DEFAULT_BUILD,
  uptimeMode: 'max',   // global calc pref (not per-build) — persists across build loads
  allSpirits: [],
  spiritsResolved: false,
  spiritsFetchFailed: false,
  mainSkill: null,
  computedStats: EMPTY_STAT_SHEET,
  statsLoading: false,
  statsError: '',
  buildVersion: 0,
  computedVersion: -1,
  loadoutStatsCache: {},

  // ── Build identity ──────────────────────────────────────────────────────────
  setBuildId: (buildId) => set({ buildId }),
  setBuildName: (buildName) => set({ buildName }),

  // ── Navigation ──────────────────────────────────────────────────────────────
  setActiveSlot: (activeSlot) => set({ activeSlot }),

  // ── Skills ──────────────────────────────────────────────────────────────────
  setSkills: (skills) =>
    set((s) => ({ skills, mainSkill: deriveMainSkill(skills), buildVersion: s.buildVersion + 1 })),

  // ── Trait / memories ────────────────────────────────────────────────────────
  setTraitId: (traitId) => set((s) => ({ traitId, buildVersion: s.buildVersion + 1 })),
  setTraitSlotLevels: (traitSlotLevels) => set((s) => ({ traitSlotLevels, buildVersion: s.buildVersion + 1 })),
  setAdvancedTraitSelections: (advancedTraitSelections) =>
    set((s) => ({ advancedTraitSelections, buildVersion: s.buildVersion + 1 })),
  setTraitSkillSupports: (traitSkillSupports) =>
    set((s) => ({ traitSkillSupports, buildVersion: s.buildVersion + 1 })),

  // ── Notes ───────────────────────────────────────────────────────────────────
  setNotes: (notes) => set({ notes }),

  // ── Compound trait setter ────────────────────────────────────────────────────
  setTraitData: (traitId, traitSlotLevels, advancedTraitSelections) =>
    set((s) => ({ traitId, traitSlotLevels, advancedTraitSelections, buildVersion: s.buildVersion + 1 })),

  // ── Stats-relevant individual setters ───────────────────────────────────────
  setSlots: (slots) => set((s) => ({ slots, buildVersion: s.buildVersion + 1 })),
  setSlates: (slates) => set((s) => ({ slates, buildVersion: s.buildVersion + 1 })),
  // Inventory is display/library only (not engine-relevant) — bump version just to mark the build dirty.
  setSlateInventory: (slateInventory) => set((s) => ({ slateInventory, buildVersion: s.buildVersion + 1 })),
  // Prisms: placed prisms drive tree placement/visuals (no DPS yet in Plan 1); inventory is library-only.
  setPrisms: (prisms) => set((s) => ({ prisms, buildVersion: s.buildVersion + 1 })),
  setPrismInventory: (prismInventory) => set((s) => ({ prismInventory, buildVersion: s.buildVersion + 1 })),
  setConditionState: (conditionState) => set((s) => ({ conditionState, buildVersion: s.buildVersion + 1 })),
  setGear: (gear) => set((s) => ({ gear, buildVersion: s.buildVersion + 1 })),
  setCharacterLevel: (characterLevel) => set((s) => ({ characterLevel, buildVersion: s.buildVersion + 1 })),
  setUptimeMode: (uptimeMode) => set((s) => ({ uptimeMode, buildVersion: s.buildVersion + 1 })),
  setHeroMemories: (heroMemories) => set((s) => ({ heroMemories, buildVersion: s.buildVersion + 1 })),
  setPactSpirits: (pactSpirits) => set((s) => ({ pactSpirits, buildVersion: s.buildVersion + 1 })),
  setFates: (fates) => set((s) => ({ fates, buildVersion: s.buildVersion + 1 })),
  setUndetermined: (undetermined) => set((s) => ({ undetermined, buildVersion: s.buildVersion + 1 })),

  // ── Slot mutation actions ────────────────────────────────────────────────────
  setSlot: (slotIndex, slot) =>
    set((s) => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      slots[slotIndex] = slot
      return { slots, buildVersion: s.buildVersion + 1 }
    }),

  reorderSlots: (fromSlot, toSlot) =>
    set((s) => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      const moving = slots[fromSlot]
      slots[fromSlot] = slots[toSlot]
      slots[toSlot] = moving
      return { slots, buildVersion: s.buildVersion + 1 }
    }),

  shiftSlotUp: (fromSlot) =>
    set((s) => {
      if (fromSlot === 0) return s
      const slots = [...s.slots] as (TreeSlot | null)[]
      const moving = slots[fromSlot]
      slots[fromSlot] = slots[fromSlot - 1]
      slots[fromSlot - 1] = moving
      return { slots, buildVersion: s.buildVersion + 1 }
    }),

  updateSlotNodeStates: (slotIndex, nodeStates) =>
    set((s) => {
      const slot = s.slots[slotIndex]
      if (!slot) return s
      const slots = [...s.slots] as (TreeSlot | null)[]
      slots[slotIndex] = { ...slot, nodeStates }
      return { slots, buildVersion: s.buildVersion + 1 }
    }),

  updateSlotCoreTalentSelections: (slotIndex, coreTalentSelections) =>
    set((s) => {
      const slot = s.slots[slotIndex]
      if (!slot) return s
      const slots = [...s.slots] as (TreeSlot | null)[]
      slots[slotIndex] = { ...slot, coreTalentSelections }
      return { slots, buildVersion: s.buildVersion + 1 }
    }),

  // ── Atomic build load ───────────────────────────────────────────────────────
  loadBuild: (data) =>
    set((s) => ({
      ...data,
      mainSkill: deriveMainSkill(data.skills),
      computedStats: EMPTY_STAT_SHEET,
      loadoutStatsCache: {},
      buildVersion: s.buildVersion + 1,
    })),

  // ── Reference data ──────────────────────────────────────────────────────────
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

  // ── Main skill (kept for backward compat; prefer setSkills which auto-derives) ─
  setMainSkill: (mainSkill) =>
    set((s) => {
      if (isEqual(s.mainSkill, mainSkill)) return s
      return { mainSkill, buildVersion: s.buildVersion + 1 }
    }),

  // ── Custom mods ─────────────────────────────────────────────────────────────
  setCustomMods: (customMods) =>
    set((s) => {
      if (isEqual(s.customMods, customMods)) return s
      return { customMods, buildVersion: s.buildVersion + 1 }
    }),

  addCustomMod: (text) =>
    set((s) => ({ customMods: [...s.customMods, text], buildVersion: s.buildVersion + 1 })),

  removeCustomMod: (index) =>
    set((s) => {
      const customMods = s.customMods.filter((_, i) => i !== index)
      return { customMods, buildVersion: s.buildVersion + 1 }
    }),

  updateCustomMod: (index, text) =>
    set((s) => {
      const customMods = s.customMods.map((m, i) => (i === index ? text : m))
      return { customMods, buildVersion: s.buildVersion + 1 }
    }),

  // ── Loadouts ─────────────────────────────────────────────────────────────────
  // Structural edits only (rename, create, delete, inheritance links). Does NOT touch the live store fields or
  // trigger a recalc — the active loadout's resolved view is unchanged. Callers that change the active loadout's
  // resolved value (e.g. removing an inherited link) should follow with switchLoadout to re-sync the store.
  editLoadouts: (mutator) => {
    get().flushActiveLoadout()
    set((s) => {
      const loadouts = mutator(JSON.parse(JSON.stringify(s.loadouts)) as Loadout[])
      const activeLoadoutId = loadoutById(loadouts, s.activeLoadoutId) ? s.activeLoadoutId : (loadouts[0]?.id ?? '')
      const patch = activeLoadoutId ? resolvedPatch(loadouts, activeLoadoutId) : {}
      return {
        loadouts,
        activeLoadoutId,
        ...patch,
        mainSkill: deriveMainSkill((patch.skills as EquippedSkill[] | undefined) ?? s.skills),
        buildVersion: s.buildVersion + 1,
      }
    })
  },

  // Write the live store's area values back into the active loadout's owner snapshots. No version bump (structural).
  // Used before saving/exporting and after loading, to keep the active loadout's data in sync with the store.
  flushActiveLoadout: () =>
    set((s) => {
      const state = s as unknown as Record<string, unknown>
      if (!loadoutById(s.loadouts, s.activeLoadoutId)) {
        const id = genLoadoutId()
        return { loadouts: [{ id, name: 'New Loadout', data: snapshotAllAreas(state), inherit: {} }], activeLoadoutId: id }
      }
      const loadouts = s.loadouts.map(l => ({ ...l, data: { ...l.data } }))
      const cur = loadoutById(loadouts, s.activeLoadoutId)!
      for (const area of ALL_AREAS) {
        const owner = ownerLoadout(loadouts, cur.id, area) ?? cur
        owner.data = { ...owner.data, [area]: readArea(state, area) }
      }
      return { loadouts }
    }),

  cacheActiveLoadoutStats: (stats) =>
    set((s) => {
      if (!s.activeLoadoutId) return s
      const key = loadoutKeyFromState(s as unknown as Record<string, unknown>, s.uptimeMode)
      return { loadoutStatsCache: { ...s.loadoutStatsCache, [s.activeLoadoutId]: { stats, key } } }
    }),

  switchLoadout: (targetId) =>
    set((s) => {
      if (targetId === s.activeLoadoutId) return s
      const target = loadoutById(s.loadouts, targetId)
      if (!target) return s

      // 1. Flush the current active loadout: write each area's live store values into its OWNER loadout's snapshot
      //    (owner = end of the inherit chain), so edits to inherited areas update the general.
      const loadouts = s.loadouts.map(l => ({ ...l, data: { ...l.data } }))
      const cur = loadoutById(loadouts, s.activeLoadoutId)
      if (cur) {
        for (const area of ALL_AREAS) {
          const owner = ownerLoadout(loadouts, cur.id, area) ?? cur
          owner.data = { ...owner.data, [area]: readArea(s as unknown as Record<string, unknown>, area) }
        }
      }

      // 2. Load the target's resolved view into the store.
      const patch = resolvedPatch(loadouts, targetId)
      const nextVersion = s.buildVersion + 1

      // 3. Cache: if the target's resolved engine inputs match its cached fingerprint, apply the cached stats and
      //    mark them current (computedVersion = nextVersion) so useBuildCalculation skips the recompute.
      const key = loadoutKeyFromResolved(loadouts, targetId, s.uptimeMode)
      const cached = s.loadoutStatsCache[targetId]
      const hit = cached && cached.key === key

      return {
        ...patch,
        loadouts,
        activeLoadoutId: targetId,
        mainSkill: deriveMainSkill((patch.skills as EquippedSkill[] | undefined) ?? s.skills),
        buildVersion: nextVersion,
        ...(hit
          ? { computedStats: cached!.stats, computedVersion: nextVersion, statsLoading: false, statsError: '' }
          : {}),
      }
    }),

  // ── Computed output (MUST NOT bump buildVersion) ────────────────────────────
  setComputedStats: (computedStats, computedVersion) =>
    set({ computedStats, computedVersion, statsLoading: false, statsError: '' }),

  setStatsLoading: (statsLoading) => set({ statsLoading }),
  setStatsError: (statsError) => set({ statsError, statsLoading: false }),
}))
