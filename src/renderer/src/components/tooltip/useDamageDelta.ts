// Damage-delta data hook + UI shape.
//
// A tooltip describes a hypothetical build change as two state transforms:
//   step = the build WITH the hovered thing, base = the build with the alternative.
// The delta is dps(step) - dps(base). One side is usually `undefined` (= the current build),
// which is free when the store result is up to date; the other costs one engine recompute.
//   - Node:           step = node at cur±1,            base = current  → marginal gain/loss
//   - Equipped item:  step = current,                  base = slot emptied → +contribution
//   - Catalog gear:   step = current occupant swapped, base = current  → +/- swap result
//   - Memory/spirit/slate: step = current, base = that thing removed → +contribution
//
// Both DPS numbers come from the Python engine (the renderer holds no combat logic); we only
// diff them. When the DPS doesn't move we diff the stat maps to tell "not yet supported"
// (a damage-relevant mod the engine ignores) from a genuine "no damage change".

import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { StatEntry, StatSheetResponse, EquippedSupportSkill, SkillItem } from '../../api/client'
import { useBuildStore } from '../../store/buildStore'
import { buildEngineStatsPayload, type BuildState } from '../../utils/statsPayload'

export type DamageDelta =
  | { state: 'loading' }
  | { state: 'value'; absolute: number; percent: number; direction: 'gain' | 'loss' | 'neutral' }
  | { state: 'nyi'; reason: string }     // engine doesn't model this skill / mod yet
  | { state: 'error'; message: string }

export type StateTransform = (s: BuildState) => BuildState

// A delta paired with the slot/row label it should display under (multi-slot gear previews).
export interface LabeledDelta { label: string; delta: DamageDelta }

export interface DeltaRequest {
  key: string                // cache key (combined with buildVersion, unless `stable`)
  step?: StateTransform      // build WITH the hovered thing (default: current build)
  base?: StateTransform      // the alternative build (default: current build)
  // When true, the result is cached in a version-INDEPENDENT cache keyed solely by `key`. The caller
  // must make `key` capture every input the result depends on (e.g. a signature of the relevant build
  // slice). Used for support-pick deltas, which are independent of the equipped support's roll/rank/tier
  // so they must not recompute when those change. See SkillsScreen's pickBaseSig.
  stable?: boolean
  // Which skill slot's DPS to measure the delta on. Defaults to the headline (main) offense; set this to
  // the focused slot so a support on a non-main slot diffs THAT slot's offense (slot_offense[slot]).
  measureSlot?: number
}

const COMING_SOON: DamageDelta = { state: 'nyi', reason: 'coming soon' }
const SKILL_NYI: DamageDelta = { state: 'nyi', reason: 'skill not modeled' }
const NOT_MODELED: DamageDelta = { state: 'nyi', reason: 'not yet supported' }
const NO_CHANGE: DamageDelta = { state: 'value', absolute: 0, percent: 0, direction: 'neutral' }
const EPS = 0.5 // dps; below this the change is treated as "no DPS movement"

// Stat categories that never contribute to hit damage. A changed stat outside this set is
// treated as damage-relevant (we err toward "not yet supported" over a misleading 0).
const NON_DAMAGE_CATEGORIES = new Set([
  'Character', 'Life', 'Mana', 'Energy Shield', 'Defence', 'Defense', 'Damage Taken', 'Utility', 'Gear',
])

type StatMap = Record<string, StatEntry>
interface Stats { dps: number | null; supported: boolean; stats: StatMap }

// Set a passive node to a specific point count in a slot (<=0 removes it). Exported so the tree
// can build its `step` transform.
export function withNodePoints(s: BuildState, slotIdx: number, nodeId: string, points: number): BuildState {
  const slots = s.slots.map((slot, i) => {
    if (i !== slotIdx || !slot) return slot
    const nodeStates = { ...slot.nodeStates }
    if (points <= 0) delete nodeStates[nodeId]
    else nodeStates[nodeId] = points
    return { ...slot, nodeStates }
  })
  return { ...s, slots }
}

// Set/replace (or remove, when `support` is null) a support at `supportIndex` on the skill in `slot`.
// Exported so the skills screen can build support `step`/`base` transforms for ANY focused slot:
//   pick  → step = withSupport(slot, idx, hypothetical), base = current  → swap-in result
//   tune  → step = current, base = withSupport(slot, idx, null)          → +contribution
// Swap the skill equipped in `slot` for `item` at `level` (or empty the slot when item is null), keeping the
// slot's existing supports. Used by the passive-skill catalog to preview each candidate's DPS contribution:
//   pick → step = withSkill(slot, candidate), base = current → swap-in result (measured on the MAIN skill,
//   since a passive/aura buffs the whole build rather than dealing its own hit damage).
export function withSkill(s: BuildState, slot: number, item: SkillItem | null, level: number): BuildState {
  const others = s.skills.filter(sk => sk.slot !== slot)
  if (!item) return { ...s, skills: others }
  const existing = s.skills.find(sk => sk.slot === slot)
  return {
    ...s,
    skills: [...others, {
      ...existing,
      slot,
      item_id: item.item_id,
      name: item.name,
      level,
      skill_tags: item.skill_tags,
      description_lines: item.description_lines,
      supports: existing?.supports ?? [],
    }],
  }
}

export function withSupport(s: BuildState, slot: number, supportIndex: number, support: EquippedSupportSkill | null): BuildState {
  return {
    ...s,
    skills: s.skills.map(sk => {
      if (sk.slot !== slot) return sk
      const supports = (sk.supports ?? []).filter(x => x.support_index !== supportIndex)
      if (support) supports.push({ ...support, support_index: supportIndex })
      return { ...sk, supports }
    }),
  }
}

function toStats(r: StatSheetResponse, measureSlot?: number): Stats {
  // Measure the headline offense by default; for a specific slot, diff that slot's per-slot offense so a
  // change on a non-main skill registers (the headline only reflects the main slot).
  const o = measureSlot != null ? (r.slot_offense?.[String(measureSlot)] ?? null) : (r.offense ?? null)
  return { dps: o?.total_dps_vs_target ?? null, supported: !!o?.supported, stats: r.stats ?? {} }
}

// True if the change touched any damage-relevant stat (so a 0 DPS delta means "not modeled"
// rather than "genuinely no damage change").
function changedTouchesDamage(a: StatMap, b: StatMap): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  for (const k of keys) {
    if ((a[k]?.total ?? 0) !== (b[k]?.total ?? 0)) {
      const cat = (b[k] ?? a[k])?.category ?? ''
      if (!NON_DAMAGE_CATEGORIES.has(cat)) return true
    }
  }
  return false
}

// The current build's RAW stats response, shared across all hovers at a given version (free when the
// store result is current; otherwise computed fresh and deduped per version). Kept raw — not reduced to a
// single dps — so each request can measure its own slot via toStats(measureSlot).
let identityCache: { version: number; promise: Promise<StatSheetResponse> } | null = null
function identityStats(s: BuildState, version: number): Promise<StatSheetResponse> {
  if (s.computedVersion === version && s.computedStats?.offense) {
    return Promise.resolve(s.computedStats)
  }
  if (identityCache && identityCache.version === version) return identityCache.promise
  const promise = api.engineStats(buildEngineStatsPayload(s))
  identityCache = { version, promise }
  return promise
}

function sideStats(transform: StateTransform | undefined, s: BuildState, version: number): Promise<StatSheetResponse> {
  if (!transform) return identityStats(s, version)
  return api.engineStats(buildEngineStatsPayload(transform(s)))
}

// Memoized delta results per (version, request key) so re-hovering is instant.
let resultCacheVersion = -1
const resultCache = new Map<string, DamageDelta>()

// Version-INDEPENDENT cache for `stable` requests whose key fully captures their inputs (it survives
// buildVersion bumps; correctness comes from the caller's signature-bearing key). Bounded LRU-ish.
const stableCache = new Map<string, DamageDelta>()
const STABLE_CACHE_CAP = 500

// Synchronous cache peek. Stable keys (self-validating) win; otherwise the version-gated cache, whose
// stale entries are ignored so a re-hover after a build edit recomputes instead of flashing old data.
function peekCache(key: string, version: number): DamageDelta | null {
  const stable = stableCache.get(key)
  if (stable) return stable
  if (resultCacheVersion !== version) return null
  return resultCache.get(key) ?? null
}

// Compute (and cache) one request's delta. Both sides resolve through sideStats, which dedupes
// the shared identity recompute across every request at a given version.
async function computeDelta(req: DeltaRequest, s: BuildState, version: number): Promise<DamageDelta> {
  if (resultCacheVersion !== version) { resultCache.clear(); resultCacheVersion = version }
  const cache = req.stable ? stableCache : resultCache
  const cached = cache.get(req.key)
  if (cached) return cached
  const [stepRaw, baseRaw] = await Promise.all([
    sideStats(req.step, s, version),
    sideStats(req.base, s, version),
  ])
  const step = toStats(stepRaw, req.measureSlot)
  const base = toStats(baseRaw, req.measureSlot)
  let result: DamageDelta
  if (!step.supported || step.dps == null || !base.supported || base.dps == null) {
    result = SKILL_NYI
  } else {
    const absolute = step.dps - base.dps
    if (Math.abs(absolute) < EPS) {
      result = changedTouchesDamage(base.stats, step.stats) ? NOT_MODELED : NO_CHANGE
    } else {
      const percent = base.dps > 0 ? (absolute / base.dps) * 100 : 0
      result = { state: 'value', absolute, percent, direction: absolute > 0 ? 'gain' : 'loss' }
    }
  }
  cache.set(req.key, result)
  if (req.stable && stableCache.size > STABLE_CACHE_CAP) {
    stableCache.delete(stableCache.keys().next().value as string)
  }
  return result
}

export function useDamageDelta(req: DeltaRequest | null, enabled = false): DamageDelta {
  const buildVersion = useBuildStore(s => s.buildVersion)
  const [delta, setDelta] = useState<DamageDelta>(COMING_SOON)

  const key = req?.key ?? null

  useEffect(() => {
    if (!enabled || !req) { setDelta(COMING_SOON); return }

    const cached = peekCache(req.key, buildVersion)
    if (cached) { setDelta(cached); return }

    setDelta({ state: 'loading' })
    let cancelled = false
    const s = useBuildStore.getState()
    const timer = setTimeout(async () => {
      try {
        const result = await computeDelta(req, s, buildVersion)
        if (!cancelled) setDelta(result)
      } catch {
        if (!cancelled) setDelta({ state: 'error', message: 'Failed to compute damage delta' })
      }
    }, 120)

    return () => { cancelled = true; clearTimeout(timer) }
  }, [enabled, key, buildVersion])

  return delta
}

// Multi-request variant: prices several hypothetical changes at once (e.g. a catalog ring previewed
// into both ring slots), returning one DamageDelta per request in order. The shared identity side
// is computed once across all of them. Used when a single hovered item maps to more than one slot.
export function useDamageDeltaList(reqs: DeltaRequest[] | null, enabled = false): DamageDelta[] {
  const buildVersion = useBuildStore(s => s.buildVersion)
  const [deltas, setDeltas] = useState<DamageDelta[]>([])

  const keysJoined = (reqs ?? []).map(r => r.key).join('|')

  useEffect(() => {
    if (!enabled || !reqs || reqs.length === 0) { setDeltas([]); return }

    const initial = reqs.map(r => peekCache(r.key, buildVersion) ?? ({ state: 'loading' } as DamageDelta))
    setDeltas(initial)
    if (initial.every(d => d.state !== 'loading')) return // all cached → no recompute

    let cancelled = false
    const s = useBuildStore.getState()
    const timer = setTimeout(async () => {
      try {
        const results = await Promise.all(reqs.map(r => computeDelta(r, s, buildVersion)))
        if (!cancelled) setDeltas(results)
      } catch {
        if (!cancelled) setDeltas(reqs.map(() => ({ state: 'error', message: 'Failed to compute damage delta' })))
      }
    }, 120)

    return () => { cancelled = true; clearTimeout(timer) }
  }, [enabled, keysJoined, buildVersion])

  return deltas
}
