import { IS_WEB } from '../api/client'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import type { TliErrorPayload } from '../errors/tliError'

export type ReportCategory = 'wrong_calculation' | 'visual_layout' | 'data_content' | 'import_save_share' | 'app_behavior' | 'other'

export interface ReportRuntimeContext {
  runtime: 'desktop-electron' | 'web-browser'
  form_factor: 'desktop' | 'mobile'
  transport: 'electron-ipc' | 'browser-http' | 'web-pyodide'
  viewport: { width: number, height: number }
  touch: boolean
}

export function getReportRuntimeContext(): ReportRuntimeContext {
  const touch = typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0)
  const mobile = typeof window !== 'undefined' && (touch && Math.min(window.innerWidth, window.innerHeight) < 768)
  return {
    runtime: IS_WEB ? 'web-browser' : 'desktop-electron',
    form_factor: mobile ? 'mobile' : 'desktop',
    transport: IS_WEB ? 'web-pyodide' : 'electron-ipc',
    viewport: { width: typeof window === 'undefined' ? 0 : window.innerWidth, height: typeof window === 'undefined' ? 0 : window.innerHeight },
    touch,
  }
}

// Deliberately construct a new object rather than reusing getBuildPayload():
// normal saves contain name, notes and loadout-management records, which are
// not needed to reproduce an engine result and must never be report defaults.
export function createCalculationSnapshot(): Record<string, unknown> {
  const s = useBuildStore.getState()
  s.flushActiveLoadout()
  return {
    characterLevel: s.characterLevel,
    slots: s.slots,
    slates: s.slates,
    slateInventory: s.slateInventory,
    prisms: s.prisms,
    prismInventory: s.prismInventory,
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
    heroMemories: s.heroMemories,
    baseMemory: s.baseMemory,
    pactSpirits: s.pactSpirits,
    fates: s.fates,
    undetermined: s.undetermined,
    customMods: s.customMods,
    targetConfig: s.targetConfig,
    enemyConfig: s.enemyConfig,
  }
}

export function createDiagnostics(error?: TliErrorPayload): Record<string, unknown> {
  const runtime = getReportRuntimeContext()
  return {
    error: error ? {
      code: error.code, title: error.title, operation: error.operation,
      fingerprint: error.fingerprint, requestId: error.requestId,
    } : undefined,
    runtime,
  }
}

export function currentSeason(): string | undefined {
  return useReferenceStore.getState().season ?? undefined
}

export const REPORT_CATEGORIES: Array<{ value: ReportCategory, label: string }> = [
  { value: 'wrong_calculation', label: 'Wrong calculation' },
  { value: 'visual_layout', label: 'Visual/layout issue' },
  { value: 'data_content', label: 'Data/content issue' },
  { value: 'import_save_share', label: 'Import/save/share issue' },
  { value: 'app_behavior', label: 'App behavior' },
  { value: 'other', label: 'Other' },
]
