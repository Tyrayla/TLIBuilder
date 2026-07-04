// Pure gear-shape helpers shared by GearScreen and the damage-delta hook.
// (GearScreen keeps its own local copies for now; this is the reusable surface for code
// outside that screen — notably converting a catalog item into a priceable equipped item.)
import type {
  LegendaryGearItem, EquippedGearItem, GearSlot, LegendaryAffix, CustomizedAffix,
} from '../api/client'

export function getItemSlots(item: EquippedGearItem): GearSlot[] {
  if (!item.slot) return []
  return Array.isArray(item.slot) ? item.slot : [item.slot]
}

export function itemHasSlot(item: EquippedGearItem, slot: GearSlot): boolean {
  return getItemSlots(item).includes(slot)
}

// Item-quality colors (mirror the .quality-* CSS): legendaries get their OWN gold; crafted/Vorax gear is
// colored by its explicit-mod count (the standardized rarity system). Shared so the gear labels, the gear
// tooltip, and the stat-breakdown source colors all agree.
const QUALITY_COLORS = {
  legendary: '#c8a050', normal: '#cccccc', magic: '#6699ff', rare: '#aa66ff', unique: '#ff66bb',
} as const

export function gearQualityColor(item: EquippedGearItem): string {
  if (!item.is_crafted) return QUALITY_COLORS.legendary
  const n = item.affixes.length - (item.implicit_count ?? 0)
  if (n === 0) return QUALITY_COLORS.normal
  if (n <= 2) return QUALITY_COLORS.magic
  if (n <= 5) return QUALITY_COLORS.rare
  return QUALITY_COLORS.unique
}

export function isLegendaryGearItem(item: LegendaryGearItem | EquippedGearItem): item is LegendaryGearItem {
  return 'variants' in item
}

// Which slot(s) a base type can occupy. Mirrors GearScreen.getValidSlots.
export function getValidSlots(baseType: string, slotMap?: Record<string, GearSlot[]>): GearSlot[] {
  if (slotMap?.[baseType]?.length) return slotMap[baseType]
  const b = (baseType ?? '').toLowerCase()
  if (/belt|girdle|waistguard/.test(b)) return ['belt']
  if (/necklace|pendant|amulet/.test(b)) return ['amulet']
  if (/\bring\b/.test(b)) return ['ring1', 'ring2']
  if (/crown|helmet|mask|miter|headdress|headscarf|hood/.test(b)) return ['helmet']
  if (/robe|coat|chestguard|chest armor|outerwear|armor|vest|skin|protection|body/.test(b)) return ['chest']
  if (/gloves|handguards|gauntlets|wristband|wrists|wristguard|grip/.test(b)) return ['gloves']
  if (/boots|sabatons|slippers|treads|greaves|shoes|feet/.test(b)) return ['boots']
  if (/shield/.test(b)) return ['weapon2']
  if (/sword|axe|hammer|bow|crossbow|dagger|claw|wand|staff|scepter|musket|pistol|cannon|rod|spear|mace|cudgel|cane/.test(b)) return ['weapon1', 'weapon2']
  return []
}

export function getItemImplicits(item: LegendaryGearItem): LegendaryAffix[] {
  const variantKey = Object.keys(item.variants)[0] ?? 'base'
  return item.variants[variantKey]?.implicits ?? []
}

// Implicits + explicits (with unfilled random-affix placeholders appended). Matches
// GearScreen.getItemAffixes for catalog items; for equipped items returns item.affixes.
export function getItemAffixes(item: LegendaryGearItem | EquippedGearItem): LegendaryAffix[] {
  if ('customizations' in item) return item.affixes
  const variantKey = Object.keys(item.variants)[0] ?? 'base'
  const variant = item.variants[variantKey]
  if (!variant) return []
  const affixes: LegendaryAffix[] = [...variant.implicits, ...variant.explicits]
  const existingCounts: Record<string, number> = {}
  for (const a of variant.explicits) {
    if (a.affix_kind === 'placeholder') existingCounts[a.raw_text] = (existingCounts[a.raw_text] ?? 0) + 1
  }
  const consumed: Record<string, number> = {}
  for (const group of (item.random_affixes[variantKey] ?? [])) {
    const ph = group.placeholder
    const used = consumed[ph] ?? 0
    if (used < (existingCounts[ph] ?? 0)) { consumed[ph] = used + 1 } else {
      affixes.push({ raw_text: ph, modifier_id: null, expression: ph, condition: null, affix_kind: 'placeholder', numeric_values: [] })
    }
  }
  return affixes
}

// Convert a catalog item into an equippable item assigned to `slot`, using default rolls (no
// customization/corrosion) — enough to price a hypothetical equip. Mirrors the add-to-build
// conversion in GearScreen.handleAddFromCatalog.
export function legendaryToEquipped(item: LegendaryGearItem, slot: GearSlot): EquippedGearItem {
  return {
    item_id: item.item_id,
    name: item.name,
    required_level: item.required_level,
    affixes: getItemAffixes(item),
    customizations: [],
    slot,
    base_type: item.base_type,
    implicit_count: getItemImplicits(item).length,
  }
}

// Build an equipped item from a catalog item + the user's staged customization/corrosion. Affixes are the
// CURRENT catalog's base affixes with the corroded ("T0") variants swapped in for the desecrated explicit
// indices and any chosen random-affix options applied by index. The rolled VALUES live separately in
// `customizations` (applied downstream), so the affixes here are the templates. Shared by GearScreen (add /
// edit / preview) and the build-load migration below. `corrosionBaseAffixes` (the base-type's corrosion pool)
// is only consulted to resolve a mutation affix; pass [] when it isn't needed.
export function makeCatalogItem(
  catalogItem: LegendaryGearItem, customizations: CustomizedAffix[],
  corrosionType: 'none' | 'desecration' | 'mutation', corrodedExplicitIndices: number[],
  selectedRandomAffixes: Record<number, string>,
  corrosionBaseAffixes: Array<LegendaryAffix & { modifier_text: string }>, mutationAffixText: string | null,
): EquippedGearItem {
  const baseAffixes = getItemAffixes(catalogItem)
  const implCount = getItemImplicits(catalogItem).length
  const affixes = [...baseAffixes]
  if (corrodedExplicitIndices.length > 0 && catalogItem.variants.corroded) {
    for (const idx of corrodedExplicitIndices) {
      const corroded = catalogItem.variants.corroded.explicits[idx]
      if (corroded) affixes[implCount + idx] = corroded
    }
  }
  const allRandomOptions = Object.values(catalogItem.random_affixes).flat().flatMap(g => g.options)
  for (const [explicitIdxStr, modifierId] of Object.entries(selectedRandomAffixes)) {
    const explicitIdx = Number(explicitIdxStr)
    const opt = allRandomOptions.find(o => o.modifier_id === modifierId)
    if (opt) affixes[implCount + explicitIdx] = opt
  }
  const mutationResolvedAffix = corrosionType === 'mutation' && mutationAffixText
    ? (corrosionBaseAffixes.find(a => a.modifier_text === mutationAffixText) ?? null)
    : null
  return {
    item_id: catalogItem.item_id,
    name: catalogItem.name,
    required_level: catalogItem.required_level,
    affixes,
    customizations,
    slot: null,
    base_type: catalogItem.base_type,
    implicit_count: implCount,
    corrosion_type: corrosionType,
    corroded_explicit_indices: corrodedExplicitIndices,
    mutation_affix_text: mutationAffixText,
    mutation_resolved_affix: mutationResolvedAffix,
    selected_random_affixes: Object.keys(selectedRandomAffixes).length ? selectedRandomAffixes : undefined,
  }
}

// Migrate an OLD saved legendary item to the CURRENT catalog: re-derive its affix array + implicit_count from
// the catalog (matched by item_id) so index-based desecration/corrosion aligns again (old saves can carry a
// stale affix layout from a prior app/catalog version, which made the corrosion toggle swap the wrong slot or
// no-op). The user's rolls (customizations), corrosion state, slot, enable flag, and stored mutation-resolved
// affix are all preserved. Only for real legendaries (skip crafted/Vorax items — they have no catalog entry).
export function migrateLegendaryItem(saved: EquippedGearItem, catalogItem: LegendaryGearItem): EquippedGearItem {
  const derived = makeCatalogItem(
    catalogItem, saved.customizations ?? [], saved.corrosion_type ?? 'none',
    saved.corroded_explicit_indices ?? [], saved.selected_random_affixes ?? {}, [], saved.mutation_affix_text ?? null,
  )
  return {
    ...saved, ...derived, slot: saved.slot,
    // corrosionBaseAffixes is [] above, so a mutation's resolved affix isn't recomputed here — keep the saved one.
    mutation_resolved_affix: saved.mutation_resolved_affix ?? derived.mutation_resolved_affix,
  }
}
