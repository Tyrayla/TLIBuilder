// Pure gear-shape helpers shared by GearScreen and the damage-delta hook.
// (GearScreen keeps its own local copies for now; this is the reusable surface for code
// outside that screen — notably converting a catalog item into a priceable equipped item.)
import type {
  LegendaryGearItem, EquippedGearItem, GearSlot, LegendaryAffix,
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
