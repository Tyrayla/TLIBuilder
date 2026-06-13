// Layer 3 content body for gear items (legendary or crafted). Ported from the old
// ItemTooltip.tsx. Renders its own multi-line header (type / name / base / level) because
// gear's header is richer than TooltipShell's title/subtitle slots — so this body does NOT
// wrap in TooltipShell; it renders the full chrome itself and reuses DamageDeltaBand.
// The caller supplies the positioned container: <div className="tooltip tooltip--gear">.
import React from 'react'
import type {
  LegendaryGearItem, LegendaryAffix, EquippedGearItem,
} from '../../../api/client'
import { tooltipAffixText, affixTypeLabel } from '../../../utils/affixText'
import { TooltipContributions } from '../TooltipContributions'
import type { DamageDelta, LabeledDelta } from '../useDamageDelta'
import { ModifierBadge, useGearModifierStatus, useGearModifierStatuses } from '../../ModifierBadge'

export type GearTooltipItem = LegendaryGearItem | EquippedGearItem

function isLegendaryGearItem(item: GearTooltipItem): item is LegendaryGearItem {
  return 'variants' in item
}

// Map a base-type string to a slot label. Fragile regex — must be extended for new base
// types (flagged as a maintenance hazard in the revamp handoff).
function getGearTypeLabel(baseType: string): string {
  const b = (baseType ?? '').toLowerCase()
  if (/belt|girdle|waistguard/.test(b)) return 'Belt'
  if (/necklace|pendant|amulet/.test(b)) return 'Amulet'
  if (/\bring\b/.test(b)) return 'Ring'
  if (/crown|helmet|mask|miter|headdress|headscarf|hood/.test(b)) return 'Helmet'
  if (/robe|coat|chestguard|chest armor|outerwear|armor|vest|skin|protection|body/.test(b)) return 'Chest Armor'
  if (/gloves|handguards|gauntlets|wristband|wrists|wristguard|grip/.test(b)) return 'Gloves'
  if (/boots|sabatons|slippers|treads|greaves|shoes|feet/.test(b)) return 'Boots'
  if (/shield/.test(b)) return 'Shield'
  if (/sword|axe|hammer|bow|crossbow|dagger|claw|wand|staff|scepter|musket|pistol|cannon|rod|spear|mace|cudgel|cane/.test(b)) return 'Weapon'
  return ''
}

function getItemImplicits(item: LegendaryGearItem): LegendaryAffix[] {
  const variantKey = Object.keys(item.variants)[0] ?? 'base'
  return item.variants[variantKey]?.implicits ?? []
}

function getItemExplicits(item: LegendaryGearItem): LegendaryAffix[] {
  const variantKey = Object.keys(item.variants)[0] ?? 'base'
  const variant = item.variants[variantKey]
  if (!variant) return []
  const affixes: LegendaryAffix[] = [...variant.explicits]
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

export function GearTooltipBody({ item, delta, deltas }: { item: GearTooltipItem; delta?: DamageDelta; deltas?: LabeledDelta[] }) {
  const customizations = 'customizations' in item ? item.customizations : undefined
  const baseType = ('base_type' in item ? item.base_type : undefined) ?? ''
  const typeLabel = getGearTypeLabel(baseType)
  const lgItem = isLegendaryGearItem(item) ? item : null
  const craftItem = lgItem ? null : (item as EquippedGearItem)
  const implCount = craftItem ? (craftItem.implicit_count ?? 0) : 0
  // Implicit/explicit affix objects are structurally the same for legendary and crafted items —
  // both carry the resolved stat keys the inert-modifier badge needs.
  const implicits = lgItem ? getItemImplicits(lgItem) : (craftItem ? craftItem.affixes.slice(0, implCount) : [])
  const explicits = lgItem ? getItemExplicits(lgItem) : (craftItem ? craftItem.affixes.slice(implCount) : [])
  const mutText = craftItem && craftItem.corrosion_type === 'mutation' ? craftItem.mutation_affix_text : null

  const implicitStatuses = useGearModifierStatuses(implicits)
  const explicitStatuses = useGearModifierStatuses(explicits)
  const mutStatus = useGearModifierStatus(craftItem?.mutation_resolved_affix ?? null)

  return (
    <>
      {typeLabel && <div className="gear-tooltip-type">{typeLabel}</div>}
      <div className="gear-tooltip-name">{item.name}</div>
      {baseType && <div className="gear-tooltip-base">Base: {baseType}</div>}
      <div className="gear-tooltip-level">Required Level: {item.required_level}</div>
      <div className="gear-tooltip-divider" />
      {mutText && (
        <div className="gear-tooltip-affix gear-tooltip-affix--corroded">
          {mutText}<ModifierBadge status={mutStatus} />
        </div>
      )}
      {implicits.map((affix, i) => (
        <div key={`imp-${i}`} className="gear-tooltip-affix gear-tooltip-affix--implicit">
          {affix.raw_text}<ModifierBadge status={implicitStatuses[i]} />
        </div>
      ))}
      {implicits.length > 0 && explicits.length > 0 && (
        <div className="gear-preview-section-dashes" style={{ margin: '5px 0' }} />
      )}
      {explicits.map((affix, i) => (
        <div key={`exp-${i}`} className="gear-tooltip-affix">
          {tooltipAffixText(affix, implicits.length + i, customizations)}
          {affixTypeLabel(affix.affix_type) && <span className="gear-affix-label">({affixTypeLabel(affix.affix_type)})</span>}
          <ModifierBadge status={explicitStatuses[i]} />
        </div>
      ))}
      {/* Contributions live at the bottom and grow downward. `deltas` (one band per slot) takes
          precedence over the single `delta` when present. */}
      <TooltipContributions delta={delta} deltas={deltas} />
    </>
  )
}
