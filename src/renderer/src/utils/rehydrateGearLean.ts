// rehydrateGearLean.ts — a lean, READ-ONLY TS port of backend/build_code.py's
// `_rehydrate_gear_item`, for the share-link overview page. A shared build code stores a stripped
// gear entry for ordinary legendary items (just item_id/slot/customizations — no affixes, to keep
// the code compact) and relies on the decoder to merge in the full item definition from the
// season's legendary-gear catalog. Crafted/Vorax items are the exception — the code already
// carries their affixes directly, since they have no catalog entry to rehydrate from.
//
// KEEP IN SYNC with `_rehydrate_gear_item` in backend/build_code.py — this mirrors its exact
// field-merge and variant/random-affix flattening logic. If that function changes, this needs a
// matching update or shared builds will render gear wrong on the overview page (the real app,
// which goes through the real Python backend, would be unaffected).

import type { EquippedGearItem, LegendaryGearItem } from '../api/client'

/**
 * Rehydrate one raw (decoded, not-yet-typed) gear entry from a build code into an
 * `EquippedGearItem` ready for `GearTooltipBody`. `legendaryItems` is the season's full
 * legendary-gear catalog (`legendary_gear.json`'s `.items`).
 */
export function rehydrateGearItemLean(
  raw: Record<string, unknown>,
  legendaryItems: LegendaryGearItem[],
): EquippedGearItem {
  if (raw.is_crafted || raw.is_vorax) {
    // Crafted/Vorax items carry their own affixes directly in the code — nothing to rehydrate.
    return raw as unknown as EquippedGearItem
  }

  const itemId = raw.item_id as string | undefined
  const full = itemId ? legendaryItems.find(i => i.item_id === itemId) : undefined
  if (!full) {
    // Unknown item (different game version, or not in this season's catalog) — pass through as-is
    // so the overview page can still show *something* rather than failing the whole page.
    return raw as unknown as EquippedGearItem
  }

  const rehydrated: Record<string, unknown> = { ...full }
  // Python falls back to the catalog record's own "slot" if the stripped entry lacks one — a
  // defensive branch that's effectively dead in practice (every equipped item's stripped entry
  // always carries `slot`; see build_code.py's `_strip_gear_item`), but mirrored here for parity.
  // `LegendaryGearItem` doesn't declare `slot` (equipped state isn't part of the catalog record),
  // hence the loose (full as Record<string, unknown>) read instead of a typed property access.
  rehydrated.slot = raw.slot ?? (full as unknown as Record<string, unknown>).slot
  rehydrated.customizations = raw.customizations ?? []
  if (raw.base_type) rehydrated.base_type = raw.base_type
  if (raw.displayName) rehydrated.displayName = raw.displayName

  const variants = full.variants ?? {}
  const randomAffixesMap = full.random_affixes ?? {}
  // Python's `next(iter(variants), "base")` takes the FIRST key of the (insertion-ordered) dict.
  // JSON.parse preserves source key order for string keys, so Object.keys matches it here.
  const variantKey = Object.keys(variants)[0] ?? 'base'
  const variant = variants[variantKey] ?? { implicits: [], explicits: [] }
  const implicits = variant.implicits ?? []
  const explicits = variant.explicits ?? []
  const affixes = [...implicits, ...explicits]

  for (const group of randomAffixesMap[variantKey] ?? []) {
    affixes.push({
      raw_text: group.placeholder,
      modifier_id: null,
      expression: group.placeholder,
      condition: null,
      affix_kind: 'placeholder',
      numeric_values: [],
    })
  }
  rehydrated.affixes = affixes
  rehydrated.implicit_count = implicits.length

  return rehydrated as unknown as EquippedGearItem
}
