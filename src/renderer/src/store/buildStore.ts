import { create } from 'zustand'
import { isEqual } from 'lodash-es'
import type {
  TreeSlot, SavedSlate, EquippedGearItem, EquippedSkill,
  CreatedHeroMemory, SelectedPactSpirit, StatSheetResponse, PactSpirit, SkillEngineInput,
} from '../api/client'
import { EMPTY_STAT_SHEET } from '../api/client'

// All fields that are loaded/reset atomically when opening a build
export interface LoadedBuild {
  buildId: string | null
  buildName: string
  activeSlot: number
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  conditionState: Record<string, number | boolean>
  gear: EquippedGearItem[]
  skills: EquippedSkill[]
  characterLevel: number
  hasPrism: boolean
  traitId: string | null
  traitSlotLevels: number[]
  advancedTraitSelections: string[]
  heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]
  pactSpirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]
  notes: string
  customMods: string[]
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
  setTraitId: (id: string | null) => void
  setTraitSlotLevels: (levels: number[]) => void
  setAdvancedTraitSelections: (sels: string[]) => void

  // Notes
  notes: string
  setNotes: (notes: string) => void

  // Compound trait setter — updates all three trait fields atomically (one buildVersion bump)
  setTraitData: (traitId: string | null, traitSlotLevels: number[], advancedTraitSelections: string[]) => void

  // Stats-relevant data fields
  slots: (TreeSlot | null)[]
  slates: SavedSlate[]
  conditionState: Record<string, number | boolean>
  gear: EquippedGearItem[]
  characterLevel: number
  hasPrism: boolean
  heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]
  pactSpirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]

  // Individual setters for stats-relevant fields (bump buildVersion)
  setSlots: (slots: (TreeSlot | null)[]) => void
  setSlates: (slates: SavedSlate[]) => void
  setConditionState: (state: Record<string, number | boolean>) => void
  setGear: (gear: EquippedGearItem[]) => void
  setCharacterLevel: (level: number) => void
  setHasPrism: (v: boolean) => void
  setHeroMemories: (memories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]) => void
  setPactSpirits: (spirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]) => void

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
  conditionState: {},
  gear: [],
  skills: [],
  characterLevel: 100,
  hasPrism: false,
  traitId: null,
  traitSlotLevels: [1, 1, 1, 1],
  advancedTraitSelections: [],
  heroMemories: [null, null, null],
  pactSpirits: [null, null, null],
  notes: '',
  customMods: [],
}

function deriveMainSkill(skills: EquippedSkill[]): SkillEngineInput | null {
  const slot1 = skills.find(sk => sk.slot === 1)
  return slot1 ? { skill_id: slot1.item_id, level: slot1.level ?? 1 } : null
}

export const useBuildStore = create<BuildStore>((set) => ({
  ...DEFAULT_BUILD,
  allSpirits: [],
  spiritsResolved: false,
  spiritsFetchFailed: false,
  mainSkill: null,
  computedStats: EMPTY_STAT_SHEET,
  statsLoading: false,
  statsError: '',
  buildVersion: 0,
  computedVersion: -1,

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

  // ── Notes ───────────────────────────────────────────────────────────────────
  setNotes: (notes) => set({ notes }),

  // ── Compound trait setter ────────────────────────────────────────────────────
  setTraitData: (traitId, traitSlotLevels, advancedTraitSelections) =>
    set((s) => ({ traitId, traitSlotLevels, advancedTraitSelections, buildVersion: s.buildVersion + 1 })),

  // ── Stats-relevant individual setters ───────────────────────────────────────
  setSlots: (slots) => set((s) => ({ slots, buildVersion: s.buildVersion + 1 })),
  setSlates: (slates) => set((s) => ({ slates, buildVersion: s.buildVersion + 1 })),
  setConditionState: (conditionState) => set((s) => ({ conditionState, buildVersion: s.buildVersion + 1 })),
  setGear: (gear) => set((s) => ({ gear, buildVersion: s.buildVersion + 1 })),
  setCharacterLevel: (characterLevel) => set((s) => ({ characterLevel, buildVersion: s.buildVersion + 1 })),
  setHasPrism: (hasPrism) => set((s) => ({ hasPrism, buildVersion: s.buildVersion + 1 })),
  setHeroMemories: (heroMemories) => set((s) => ({ heroMemories, buildVersion: s.buildVersion + 1 })),
  setPactSpirits: (pactSpirits) => set((s) => ({ pactSpirits, buildVersion: s.buildVersion + 1 })),

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

  // ── Computed output (MUST NOT bump buildVersion) ────────────────────────────
  setComputedStats: (computedStats, computedVersion) =>
    set({ computedStats, computedVersion, statsLoading: false, statsError: '' }),

  setStatsLoading: (statsLoading) => set({ statsLoading }),
  setStatsError: (statsError) => set({ statsError, statsLoading: false }),
}))
