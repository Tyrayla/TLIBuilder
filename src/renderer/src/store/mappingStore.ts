// Per-data-version cache of raw modifier text -> engine stat key(s), for the inert-modifier
// badges. Spirit/memory/talent/slate modifiers render as raw strings with no stat info, so we
// resolve them via /api/map-modifiers (which reuses the engine's own resolvers). The mapping is
// deterministic per data version, so results are cached for the session and only cleared on a
// season change. Resolution is LAZY + batched: a render site asks for a text's keys; misses are
// queued and flushed together after a short debounce, then the cache update re-renders the site.
import { create } from 'zustand'
import { api, type ModifierSource, type ModifierMapItem } from '../api/client'

export function modifierKey(source: ModifierSource, text: string, nodeId?: string): string {
  return `${source}|${nodeId ?? ''}|${text}`
}

interface MappingStore {
  // key -> stat keys. Empty array = resolved-but-unrecognized. Missing = not yet resolved.
  cache: Record<string, string[]>
  request: (items: { text: string; source: ModifierSource; nodeId?: string }[]) => void
  clear: () => void
}

// Queue of distinct keys awaiting the next flush (module-level so the debounce survives renders).
let pending = new Map<string, ModifierMapItem>()
let flushTimer: ReturnType<typeof setTimeout> | null = null

async function flush() {
  flushTimer = null
  if (pending.size === 0) return
  const batch = Array.from(pending.values())
  pending = new Map()
  try {
    const res = await api.mapModifiers(batch)
    const next = { ...useMappingStore.getState().cache }
    for (const it of batch) next[it.key] = res.results[it.key]?.stat_keys ?? []
    useMappingStore.setState({ cache: next })
  } catch {
    // Leave keys unresolved on failure — the status hook fails open (no badge) for unknown keys.
  }
}

export const useMappingStore = create<MappingStore>((_set, get) => ({
  cache: {},
  request: (items) => {
    const { cache } = get()
    let added = false
    for (const it of items) {
      if (!it.text) continue
      const key = modifierKey(it.source, it.text, it.nodeId)
      if (key in cache || pending.has(key)) continue
      pending.set(key, { key, text: it.text, source: it.source, node_id: it.nodeId })
      added = true
    }
    if (!added) return
    if (flushTimer) clearTimeout(flushTimer)
    flushTimer = setTimeout(flush, 100)
  },
  clear: () => {
    pending = new Map()
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null }
    useMappingStore.setState({ cache: {} })
  },
}))
