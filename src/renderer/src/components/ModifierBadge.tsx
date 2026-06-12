// Modifier badge + the status hooks that drive it. ONE 4-state taxonomy, consistent everywhere
// (gear, spirit, memory, talent nodes, slates, core talents, player stats). Every modifier resolves
// to engine stat key(s) via the unified resolver, then is classified against two sets the backend
// returns: the build's `consumed_stats` and the global `consumable_universe`:
//   - "working"      (green) : a mapped stat is in consumed_stats → actively contributing to this build
//   - "inactive"     (grey)  : a mapped stat is in the universe but NOT consumed → the engine models it,
//                              your selected skill just doesn't read it (would work on another build)
//   - "unused"       (yellow): mapped to a stat the engine never reads anywhere → recognized, not modeled
//   - "unrecognized" (red)   : the text maps to no engine stat at all (data/parse gap, NYI)
// Gear/vorax affixes carry stat keys locally; spirit/memory/talent/slate text resolves via the mapping
// store (which now calls the SAME unified resolver the engine uses — no recipe drift).
//
// Hooks come in singular and plural forms — use the PLURAL form when rendering a list of modifier
// lines (a hook may not be called inside a .map()).
import React, { useEffect, useMemo } from 'react'
import { useBuildStore } from '../store/buildStore'
import { useMappingStore, modifierKey } from '../store/mappingStore'
import { useUiPrefs } from '../store/uiPrefsStore'
import { affixStatKeys } from '../utils/affixText'
import type { ModifierSource } from '../api/client'

export type ModifierStatus = 'working' | 'inactive' | 'unused' | 'unrecognized'

type StatBearingAffix = Parameters<typeof affixStatKeys>[0] & { affix_kind?: string }
export interface TextModifier { text: string | null | undefined; source: ModifierSource; nodeId?: string }

// The stat keys the current build's compute consumed. Call once at a component's top level, then
// classify many affixes synchronously with gearModifierStatus (avoids a hook inside a .map()).
export function useConsumedStatSet(): Set<string> {
  const consumed = useBuildStore((s) => s.computedStats.consumed_stats)
  return useMemo(() => new Set(consumed ?? []), [consumed])
}
const useConsumedSet = useConsumedStatSet

// The maximal set of stats the engine can EVER read (all skills/tags). Splits "Inactive" (in here, not
// in consumed) from "Unconsumed" (not in here at all). Empty = not loaded yet → classifier fails open.
export function useConsumableUniverse(): Set<string> {
  const universe = useBuildStore((s) => s.computedStats.consumable_universe)
  return useMemo(() => new Set(universe ?? []), [universe])
}

// The set of gear affix/implicit raw texts the backend could NOT resolve (gear_mod_statuses,
// resolved:false). An affix without a local stat key is sent to the backend for resolution, so it's
// only genuinely "unrecognized" if it's in this set — otherwise it resolved server-side and works.
export function useGearUnresolvedTexts(): Set<string> {
  const statuses = useBuildStore((s) => s.computedStats.gear_mod_statuses)
  return useMemo(
    () => new Set((statuses ?? []).filter((st) => !st.resolved).map((st) => (st.text ?? '').trim())),
    [statuses],
  )
}

// ── Core 4-state classification ──────────────────────────────────────────────────
// Given the stat keys a modifier resolved to, classify against consumed_stats + the universe.
//   in consumed            → working   (green)
//   in universe, not consumed → inactive (grey)   — modeled, not for your selected skill
//   resolved, in neither    → unused    (yellow)  — engine never reads it
// Fail-open: if the universe set is empty (not loaded), a not-consumed stat shows 'inactive' (benign)
// rather than 'unused', so a load race never paints a false "engine never reads it".
function classifyKeys(keys: string[], consumed: Set<string>, universe: Set<string>): ModifierStatus {
  if (keys.some((k) => consumed.has(k))) return 'working'
  if (universe.size === 0) return 'inactive'
  if (keys.some((k) => universe.has(k))) return 'inactive'
  return 'unused'
}

// ── Pure classifiers ────────────────────────────────────────────────────────────
export function gearModifierStatus(
  affix: StatBearingAffix | null | undefined, consumed: Set<string>, universe: Set<string>, unresolved?: Set<string>,
): ModifierStatus | null {
  return gearStatus(affix, consumed, universe, unresolved)
}
function gearStatus(
  affix: StatBearingAffix | null | undefined, consumed: Set<string>, universe: Set<string>, unresolved?: Set<string>,
): ModifierStatus | null {
  if (!affix) return null
  const kind = affix.affix_kind
  if (kind === 'placeholder') return null // unfilled random-affix slot — never flagged
  const keys = affixStatKeys(affix)
  if (keys.length === 0) {
    // No local stat key — the backend attempts to resolve the raw text. Flag as unrecognized only if
    // the backend also couldn't (in the unresolved set); otherwise it resolved server-side → no badge.
    const raw = (affix as { raw_text?: string }).raw_text?.trim()
    return raw && unresolved?.has(raw) ? 'unrecognized' : null
  }
  return classifyKeys(keys, consumed, universe)
}

function textStatus(keys: string[] | undefined, consumed: Set<string>, universe: Set<string>): ModifierStatus | null {
  if (keys === undefined) return null // not resolved yet → fail open (no badge)
  if (keys.length === 0) return 'unrecognized'
  return classifyKeys(keys, consumed, universe)
}

// ── Gear/vorax affixes (synchronous, local stat keys) ────────────────────────────
export function useGearModifierStatus(affix: StatBearingAffix | null | undefined): ModifierStatus | null {
  const consumed = useConsumedSet()
  const universe = useConsumableUniverse()
  const unresolved = useGearUnresolvedTexts()
  return gearStatus(affix, consumed, universe, unresolved)
}
export function useGearModifierStatuses(affixes: (StatBearingAffix | null | undefined)[]): (ModifierStatus | null)[] {
  const consumed = useConsumedSet()
  const universe = useConsumableUniverse()
  const unresolved = useGearUnresolvedTexts()
  return affixes.map((a) => gearStatus(a, consumed, universe, unresolved))
}

// ── Raw-text sources (lazy mapping store) ────────────────────────────────────────
export function useTextModifierStatuses(items: TextModifier[]): (ModifierStatus | null)[] {
  const consumed = useConsumedSet()
  const universe = useConsumableUniverse()
  const enabled = useUiPrefs((s) => s.showModifierBadges)
  const cache = useMappingStore((s) => s.cache)
  const request = useMappingStore((s) => s.request)

  const keysJoined = items.map((it) => (it.text ? modifierKey(it.source, it.text, it.nodeId) : '')).join('§')

  useEffect(() => {
    if (!enabled) return
    const missing = items.filter(
      (it) => it.text && cache[modifierKey(it.source, it.text, it.nodeId)] === undefined,
    )
    if (missing.length) request(missing.map((it) => ({ text: it.text!, source: it.source, nodeId: it.nodeId })))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, keysJoined, cache])

  return items.map((it) => {
    if (!it.text) return null
    return textStatus(cache[modifierKey(it.source, it.text, it.nodeId)], consumed, universe)
  })
}
export function useTextModifierStatus(text: string | null | undefined, source: ModifierSource, nodeId?: string): ModifierStatus | null {
  return useTextModifierStatuses([{ text, source, nodeId }])[0]
}

// ── Badge ────────────────────────────────────────────────────────────────────────
const LABEL: Record<ModifierStatus, string> = {
  working: 'Consumed',
  inactive: 'Inactive',
  unused: 'Unconsumed',
  unrecognized: 'Unrecognized (NYI)',
}
const TITLE: Record<ModifierStatus, string> = {
  working: 'Resolved to an engine stat that this build actively consumes.',
  inactive: "The engine models this stat, but your selected skill/calculation doesn't read it (it would work on another build).",
  unused: "Resolves to a stat the engine doesn't read anywhere yet — recognized, not modeled.",
  unrecognized: "This modifier doesn't map to any stat the engine models yet.",
}

// Renders nothing for null status or when the toggle is off. Every resolved state (incl. green
// "Consumed") is badged so nothing silently passes as working.
export function ModifierBadge({ status }: { status: ModifierStatus | null }) {
  const show = useUiPrefs((s) => s.showModifierBadges)
  if (!show || !status) return null
  return (
    <span className={`nyi-tag nyi-tag--${status}`} title={TITLE[status]}>
      {LABEL[status]}
    </span>
  )
}
