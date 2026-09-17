// staticCatalogLean.ts — minimal CDN catalog fetching for the share-link overview page.
//
// The full app boots the whole referenceStore/initApi machinery (many catalogs, Pyodide compute
// wiring, etc.) before it can resolve a single hero-trait icon. The overview page needs exactly
// two catalogs — hero traits (to resolve traitId -> hero/name/icon) and legendary gear (to
// rehydrate non-crafted/non-vorax gear items, see rehydrateGearLean.ts) — so it replicates just the
// fetch pattern api/client.ts already uses for the web build's static catalogs
// (manifest.json -> season, then <season>/<name>.json), without pulling in the rest of that module.

import type { HeroTrait, LegendaryGearItem } from '../api/client'

const STATIC_DATA_BASE = ((import.meta.env?.VITE_STATIC_DATA_BASE as string | undefined) || '').replace(/\/+$/, '')

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`)
  return res.json() as Promise<T>
}

// A plain `x ??= fetch(...)` memoizes the REJECTED promise too — one transient network blip on
// first load would permanently poison the catalog for the rest of the page's lifetime, since every
// later call just returns that same rejected promise instead of trying again. This clears the slot
// on failure so the next call retries fresh; only a successful result stays cached.
function memoizedRetry<T>(slot: { current: Promise<T> | null }, load: () => Promise<T>): Promise<T> {
  if (!slot.current) {
    slot.current = load().catch((e: unknown) => { slot.current = null; throw e })
  }
  return slot.current
}

const seasonSlot: { current: Promise<string> | null } = { current: null }
function getSeason(): Promise<string> {
  if (!STATIC_DATA_BASE) return Promise.reject(new Error('VITE_STATIC_DATA_BASE is not configured.'))
  return memoizedRetry(seasonSlot, () =>
    fetchJson<{ season: string }>(`${STATIC_DATA_BASE}/manifest.json`).then(m => m.season))
}

const heroTraitsSlot: { current: Promise<HeroTrait[]> | null } = { current: null }
export function getHeroTraitsLean(): Promise<HeroTrait[]> {
  return memoizedRetry(heroTraitsSlot, () => getSeason()
    .then(season => fetchJson<{ traits: HeroTrait[] }>(`${STATIC_DATA_BASE}/${season}/hero_traits.json`))
    .then(r => r.traits))
}

const legendaryGearSlot: { current: Promise<LegendaryGearItem[]> | null } = { current: null }
export function getLegendaryGearLean(): Promise<LegendaryGearItem[]> {
  return memoizedRetry(legendaryGearSlot, () => getSeason()
    .then(season => fetchJson<{ items: LegendaryGearItem[] }>(`${STATIC_DATA_BASE}/${season}/legendary_gear.json`))
    .then(r => r.items))
}

/** Mirrors api/client.ts's iconUrl(), but always resolves to the public CDN (never a local desktop
 *  backend host) — the only thing this page ever runs against. */
export function cdnIconUrl(category: string, iconRef: string | null | undefined): string | null {
  if (!iconRef || !STATIC_DATA_BASE) return null
  const clean = iconRef.split('?')[0].split('#')[0]
  const file = clean.substring(clean.lastIndexOf('/') + 1)
  return file ? `${STATIC_DATA_BASE}/icons/${category}/${file}` : null
}
