// Inert-modifier badge + the status hooks that drive it.
//
// A modifier is "working" if its mapped engine stat is in the build's consumed_stats (the stats the
// offense/defense/derive passes actually read). The badge flags the two non-working cases:
//   - "Inactive"     (unused): recognized stat, but the current build's skill/calc doesn't read it
//   - "Unrecognized" : the text maps to no engine stat at all (data/parse gap)
// Gear/vorax affixes carry stat keys locally; spirit/memory/talent/slate text resolves via the
// mapping store. See plan v3 (Flag Inert Modifiers).
//
// Hooks come in singular and plural forms — use the PLURAL form when rendering a list of modifier
// lines (a hook may not be called inside a .map()).
import React, { useEffect, useMemo } from 'react'
import { useBuildStore } from '../store/buildStore'
import { useMappingStore, modifierKey } from '../store/mappingStore'
import { useUiPrefs } from '../store/uiPrefsStore'
import { affixStatKeys } from '../utils/affixText'
import type { ModifierSource } from '../api/client'

export type ModifierStatus = 'working' | 'unused' | 'unrecognized'

type StatBearingAffix = Parameters<typeof affixStatKeys>[0] & { affix_kind?: string }
export interface TextModifier { text: string | null | undefined; source: ModifierSource; nodeId?: string }

// The stat keys the current build's compute consumed. Call once at a component's top level, then
// classify many affixes synchronously with gearModifierStatus (avoids a hook inside a .map()).
export function useConsumedStatSet(): Set<string> {
  const consumed = useBuildStore((s) => s.computedStats.consumed_stats)
  return useMemo(() => new Set(consumed ?? []), [consumed])
}
const useConsumedSet = useConsumedStatSet

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

// node_ids of allocated talent nodes / slate slots with at least one effect line the backend could not
// resolve (node_mod_statuses, resolved:false) — drives the NYI badge on tree nodes. 'deduped' is resolved.
export function useUnresolvedNodeIds(): Set<string> {
  const statuses = useBuildStore((s) => s.computedStats.node_mod_statuses)
  return useMemo(
    () => new Set((statuses ?? []).filter((st) => !st.resolved).map((st) => st.node_id)),
    [statuses],
  )
}

// ── Pure classifiers ────────────────────────────────────────────────────────────
export function gearModifierStatus(
  affix: StatBearingAffix | null | undefined, consumed: Set<string>, unresolved?: Set<string>,
): ModifierStatus | null {
  return gearStatus(affix, consumed, unresolved)
}
function gearStatus(
  affix: StatBearingAffix | null | undefined, consumed: Set<string>, unresolved?: Set<string>,
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
  return keys.some((k) => consumed.has(k)) ? 'working' : 'unused'
}

function textStatus(keys: string[] | undefined, consumed: Set<string>): ModifierStatus | null {
  if (keys === undefined) return null // not resolved yet → fail open (no badge)
  if (keys.length === 0) return 'unrecognized'
  return keys.some((k) => consumed.has(k)) ? 'working' : 'unused'
}

// ── Gear/vorax affixes (synchronous, local stat keys) ────────────────────────────
export function useGearModifierStatus(affix: StatBearingAffix | null | undefined): ModifierStatus | null {
  const consumed = useConsumedSet()
  const unresolved = useGearUnresolvedTexts()
  return gearStatus(affix, consumed, unresolved)
}
export function useGearModifierStatuses(affixes: (StatBearingAffix | null | undefined)[]): (ModifierStatus | null)[] {
  const consumed = useConsumedSet()
  const unresolved = useGearUnresolvedTexts()
  return affixes.map((a) => gearStatus(a, consumed, unresolved))
}

// ── Raw-text sources (lazy mapping store) ────────────────────────────────────────
export function useTextModifierStatuses(items: TextModifier[]): (ModifierStatus | null)[] {
  const consumed = useConsumedSet()
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
    return textStatus(cache[modifierKey(it.source, it.text, it.nodeId)], consumed)
  })
}
export function useTextModifierStatus(text: string | null | undefined, source: ModifierSource, nodeId?: string): ModifierStatus | null {
  return useTextModifierStatuses([{ text, source, nodeId }])[0]
}

// ── Badge ────────────────────────────────────────────────────────────────────────
const LABEL: Record<Exclude<ModifierStatus, 'working'>, string> = {
  unused: 'Inactive',
  unrecognized: 'Unrecognized (NYI)',
}
const TITLE: Record<Exclude<ModifierStatus, 'working'>, string> = {
  unused: "Recognized stat, but the current build's skill/calculation doesn't use it.",
  unrecognized: "This modifier doesn't map to any stat the engine models yet.",
}

// Renders nothing for working/null status or when the toggle is off.
export function ModifierBadge({ status }: { status: ModifierStatus | null }) {
  const show = useUiPrefs((s) => s.showModifierBadges)
  if (!show || !status || status === 'working') return null
  return (
    <span className={`nyi-tag nyi-tag--${status}`} title={TITLE[status]}>
      {LABEL[status]}
    </span>
  )
}
