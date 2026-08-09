import { useBuildStore } from '../store/buildStore'

// The same curated, save-relevant subset of store state used by App.tsx's normal save/export
// path — shared so the crash-recovery fallback (ErrorBoundary) produces an identical, clean
// payload instead of dumping the whole store (which also holds ephemeral UI-only fields).
export function getBuildPayload(): Record<string, unknown> {
  useBuildStore.getState().flushActiveLoadout()
  const s = useBuildStore.getState()
  return {
    name: s.buildName,
    loadouts: s.loadouts,
    activeLoadoutId: s.activeLoadoutId,
    characterLevel: s.characterLevel,
    slots: s.slots,
    slates: s.slates, slateInventory: s.slateInventory,
    prisms: s.prisms, prismInventory: s.prismInventory,
    conditionState: s.conditionState,
    gear: s.gear,
    skills: s.skills,
    traitId: s.traitId,
    traitSlotLevels: s.traitSlotLevels,
    advancedTraitSelections: s.advancedTraitSelections,
    traitTreeAllocations: s.traitTreeAllocations,
    traitSkillSupports: s.traitSkillSupports,
    licoricePreparedSkill: s.licoricePreparedSkill,
    elixirIngredients: s.elixirIngredients,
    heroMemories: s.heroMemories, baseMemory: s.baseMemory, memoryInventory: s.memoryInventory,
    pactSpirits: s.pactSpirits,
    fates: s.fates,
    undetermined: s.undetermined,
    notes: s.notes,
    customMods: s.customMods,
    targetConfig: s.targetConfig,
  }
}
