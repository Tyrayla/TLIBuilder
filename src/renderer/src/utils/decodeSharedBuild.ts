import type { LegendaryGearItem } from '../api/client'
import { decodeBuildCodeLean, LeanBuildCodeError } from './decodeBuildCodeLean'
import { rehydrateGearItemLean } from './rehydrateGearLean'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Migrate and rehydrate already-decoded share data on the renderer thread. */
export function rehydrateSharedBuild(rawBuild: Record<string, unknown>, catalog: LegendaryGearItem[]): Record<string, unknown> {
  const build = { ...rawBuild }
  const version = build.v
  if (typeof version !== 'number' || !Number.isInteger(version) || version < 1) {
    throw new LeanBuildCodeError("This build code is from an older version and can't be imported.")
  }

  if (version < 2) {
    const oldConditions = build.conditions ?? []
    const oldValues = build.conditionValues ?? {}
    if (!Array.isArray(oldConditions) || !isRecord(oldValues)) {
      throw new LeanBuildCodeError('This older build code has invalid condition data.')
    }
    const conditionState: Record<string, boolean | number> = {}
    for (const key of oldConditions) if (typeof key === 'string') conditionState[key] = true
    for (const [key, value] of Object.entries(oldValues)) {
      if (typeof value === 'number' || (typeof value === 'string' && value.trim() !== '')) {
        const numeric = Number(value)
        if (Number.isNaN(numeric)) throw new LeanBuildCodeError('This older build code has invalid condition values.')
        conditionState[key] = numeric
      }
    }
    delete build.conditions
    delete build.conditionValues
    build.conditionState = conditionState
    build.v = 2
  }

  if ('gear' in build) {
    if (!Array.isArray(build.gear)) {
      throw new LeanBuildCodeError("Build code has an invalid 'gear' value — expected a list of gear items.")
    }
    build.gear = build.gear.map(item => {
      if (!isRecord(item)) throw new LeanBuildCodeError('Build code has an invalid gear entry — expected a gear item object.')
      return rehydrateGearItemLean(item, catalog)
    })
  }

  // A share is an unsaved copy; an id embedded in a hand-crafted code must never target a named save.
  delete build.id
  delete build.v
  return build
}

/** Decode and rehydrate a share code on the renderer thread without waiting for the Python worker. */
export async function decodeSharedBuildCode(code: string, catalog: LegendaryGearItem[]): Promise<Record<string, unknown>> {
  return rehydrateSharedBuild(await decodeBuildCodeLean(code), catalog)
}
