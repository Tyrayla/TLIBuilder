// Loadout area registry + inheritance/snapshot helpers.
//
// A "loadout" is a full, independent variant of the build's swappable areas. Each AreaKey maps to a set of store
// fields; a loadout stores a per-area snapshot of just those fields (`Loadout.data[area] = { field: value, … }`).
// An area can inherit from another loadout (the "general") via `Loadout.inherit[area] = sourceId`; resolution
// follows the chain to the owner (the end of the chain) and uses the owner's snapshot. Editing an inherited area
// writes through to the owner (handled at flush time in `buildStore.switchLoadout`).
import type { AreaKey, Loadout } from '../api/client'
import { DEFAULT_TARGET_CONFIG } from './targetPresets'

export type AreaSnapshot = Record<string, unknown>
export type LoadoutData = Partial<Record<AreaKey, AreaSnapshot>>

// Each area → the store fields it owns. Field names match the buildStore keys 1:1.
export const AREA_FIELDS: Record<AreaKey, string[]> = {
  talents: ['slots', 'activeSlot'],
  slates: ['slates', 'slateInventory'],
  prisms: ['prisms'],
  gear: ['gear'],
  skills: ['skills'],
  trait: ['traitId', 'traitSlotLevels', 'advancedTraitSelections', 'traitTreeAllocations', 'traitSkillSupports', 'licoricePreparedSkill', 'elixirIngredients'],
  spirits: ['pactSpirits', 'fates', 'undetermined'],
  memories: ['heroMemories', 'memoryInventory'],
  conditions: ['conditionState'],
  level: ['characterLevel'],
  customMods: ['customMods'],
  notes: ['notes'],
  target: ['targetConfig'],
}

export const ALL_AREAS = Object.keys(AREA_FIELDS) as AreaKey[]

// Areas that feed the DPS engine — used for the per-loadout stats-cache fingerprint. Notes is display-only.
export const ENGINE_AREAS: AreaKey[] = ALL_AREAS.filter(a => a !== 'notes')

export const AREA_LABELS: Record<AreaKey, string> = {
  talents: 'Talents', slates: 'Slates', prisms: 'Prisms', gear: 'Gear', skills: 'Skills', trait: 'Hero Trait',
  spirits: 'Pact Spirits', memories: 'Hero Memories', conditions: 'Conditionals', level: 'Character Level',
  customMods: 'Custom Mods', notes: 'Notes', target: 'Target',
}

// Default (empty/"from scratch") snapshot per area — mirrors DEFAULT_BUILD in buildStore. Used when a loadout has
// no value for an area (e.g. a from-scratch loadout) so swaps + cache keys stay deterministic.
export const DEFAULT_AREA_SNAPSHOT: Record<AreaKey, AreaSnapshot> = {
  talents: { slots: [null, null, null, null], activeSlot: 0 },
  slates: { slates: [], slateInventory: [] },
  prisms: { prisms: [] },
  gear: { gear: [] },
  skills: { skills: [] },
  trait: { traitId: null, traitSlotLevels: [1, 1, 1, 1], advancedTraitSelections: [], traitTreeAllocations: [], traitSkillSupports: [], licoricePreparedSkill: null, elixirIngredients: {} },
  spirits: { pactSpirits: [null, null, null], fates: {}, undetermined: [null, null, null] },
  memories: { heroMemories: [null, null, null], memoryInventory: [] },
  conditions: { conditionState: {} },
  level: { characterLevel: 100 },
  customMods: { customMods: [] },
  notes: { notes: '' },
  target: { targetConfig: DEFAULT_TARGET_CONFIG },
}

const clone = <T,>(v: T): T => (v === undefined ? v : JSON.parse(JSON.stringify(v)))

// Snapshot one area's fields from a store-like state object (deep-cloned so the loadout never shares references).
export function readArea(state: Record<string, unknown>, area: AreaKey): AreaSnapshot {
  const out: AreaSnapshot = {}
  for (const f of AREA_FIELDS[area]) out[f] = clone(state[f])
  return out
}

// Snapshot every area from a state object — used to seed a loadout from the current build.
export function snapshotAllAreas(state: Record<string, unknown>): LoadoutData {
  const data: LoadoutData = {}
  for (const area of ALL_AREAS) data[area] = readArea(state, area)
  return data
}

export const loadoutById = (loadouts: Loadout[], id: string | null | undefined): Loadout | undefined =>
  loadouts.find(l => l.id === id)

// Follow the inherit chain for `area` from loadout `id` to the owner (the loadout that actually holds the value).
export function ownerLoadout(loadouts: Loadout[], id: string, area: AreaKey): Loadout | undefined {
  let cur = loadoutById(loadouts, id)
  const seen = new Set<string>()
  while (cur && cur.inherit?.[area] && !seen.has(cur.id)) {
    seen.add(cur.id)
    const next = loadoutById(loadouts, cur.inherit[area]!)
    if (!next) break
    cur = next
  }
  return cur
}

// Resolve an area's snapshot for a loadout (own or inherited), falling back to the default when unset.
export function resolveAreaSnapshot(loadouts: Loadout[], id: string, area: AreaKey): AreaSnapshot {
  const owner = ownerLoadout(loadouts, id, area)
  return clone(owner?.data?.[area]) ?? clone(DEFAULT_AREA_SNAPSHOT[area])
}

// Build a store patch (field → value) for the full resolved view of a loadout.
export function resolvedPatch(loadouts: Loadout[], id: string): Record<string, unknown> {
  const patch: Record<string, unknown> = {}
  for (const area of ALL_AREAS) Object.assign(patch, resolveAreaSnapshot(loadouts, id, area))
  return patch
}

// Fields that live inside an ENGINE area (for per-loadout scoping + persistence) but are DISPLAY-ONLY —
// the stats engine never reads them (see statsPayload.ts). They're stripped from the cache fingerprint so
// editing them doesn't force an avoidable recompute (same intent as excluding the `notes` area entirely).
// Area-level exclusion is too coarse: `slates`/`memories` also hold real engine inputs (slates/heroMemories).
const FINGERPRINT_EXCLUDED_FIELDS = new Set(['slateInventory', 'memoryInventory'])

function forFingerprint(snap: AreaSnapshot): AreaSnapshot {
  let out = snap
  for (const f of FINGERPRINT_EXCLUDED_FIELDS) {
    if (f in out) { if (out === snap) out = { ...snap }; delete out[f] }
  }
  return out
}

// Stable fingerprint of a loadout's RESOLVED engine inputs (+ global uptimeMode) — for the stats cache.
export function loadoutKeyFromResolved(loadouts: Loadout[], id: string, uptimeMode: string): string {
  return JSON.stringify({ a: ENGINE_AREAS.map(area => forFingerprint(resolveAreaSnapshot(loadouts, id, area))), u: uptimeMode })
}

// Same fingerprint computed from a live store state (the active loadout reflects unsaved edits here).
export function loadoutKeyFromState(state: Record<string, unknown>, uptimeMode: string): string {
  return JSON.stringify({ a: ENGINE_AREAS.map(area => forFingerprint(readArea(state, area))), u: uptimeMode })
}
