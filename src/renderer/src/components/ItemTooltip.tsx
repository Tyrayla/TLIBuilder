import React from 'react'
import { createPortal } from 'react-dom'
import type {
  LegendaryGearItem, LegendaryAffix, LegendaryNumericValue,
  EquippedGearItem, CustomizedAffix,
} from '../api/client'

export interface ItemTooltipState {
  item: LegendaryGearItem | EquippedGearItem
  x: number
  y: number
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function isLegendaryGearItem(item: LegendaryGearItem | EquippedGearItem): item is LegendaryGearItem {
  return 'variants' in item
}

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

function hasRangeValues(affix: LegendaryAffix): boolean {
  return affix.affix_kind === 'numeric' && affix.numeric_values.some(v => v.kind === 'range')
}

function decimalPlaces(n: number): number {
  const s = String(n)
  const dot = s.indexOf('.')
  return dot === -1 ? 0 : s.length - dot - 1
}

function rangeDecimals(nv: LegendaryNumericValue): number {
  return Math.max(decimalPlaces(nv.min ?? 0), decimalPlaces(nv.max ?? 0))
}

function midpoint(v: LegendaryNumericValue): number {
  if (v.kind === 'range') {
    const mid = ((v.min ?? 0) + (v.max ?? 0)) / 2
    const dp = rangeDecimals(v)
    return dp > 0 ? parseFloat(mid.toFixed(dp)) : Math.round(mid)
  }
  return v.value ?? 0
}

function reconstructAffixText(affix: LegendaryAffix, chosenValues: Record<number, number>): string {
  let text = affix.raw_text
  for (let i = affix.numeric_values.length - 1; i >= 0; i--) {
    const nv = affix.numeric_values[i]
    if (nv.kind !== 'range') continue
    const chosen = chosenValues[i] ?? midpoint(nv)
    const sign = nv.sign ?? ''
    const dp = rangeDecimals(nv)
    const formatted = dp > 0 ? chosen.toFixed(dp) : String(chosen)
    text = text.replace(nv.raw, `${sign}${formatted}`)
  }
  return text
}

function affixTypeLabel(affixType: string | undefined): string | undefined {
  if (!affixType) return undefined
  if (affixType === 'Base' || affixType === 'Base Affix') return 'Base Affix'
  if (affixType === 'Legendary') return 'Legendary Affix'
  const match = affixType.match(/^(Basic|Advanced|Ultimate)/i)
  return match ? `${match[1]} Affix` : undefined
}

function tooltipAffixText(affix: LegendaryAffix, affixIdx: number, customizations: CustomizedAffix[] | undefined): string {
  if (!hasRangeValues(affix)) return affix.raw_text
  const cust = customizations?.find(c => c.affix_index === affixIdx)
  return reconstructAffixText(affix, cust?.chosen_values ?? {})
}

// ── Component ──────────────────────────────────────────────────────────────────

export function ItemTooltip({ state }: { state: ItemTooltipState }) {
  const customizations = 'customizations' in state.item ? state.item.customizations : undefined
  const baseType = ('base_type' in state.item ? state.item.base_type : undefined) ?? ''
  const typeLabel = getGearTypeLabel(baseType)
  const lgItem = isLegendaryGearItem(state.item) ? state.item : null
  const implicits = lgItem ? getItemImplicits(lgItem) : []
  const explicits = lgItem ? getItemExplicits(lgItem) : []

  const tooltipWidth = 316
  const tooltipLeft = state.x + 16 + tooltipWidth > window.innerWidth ? Math.max(8, state.x - tooltipWidth - 8) : state.x + 16
  const tooltipTop = Math.min(Math.max(8, state.y - 10), window.innerHeight - 360)

  return createPortal(
    <div className="gear-tooltip-portal" style={{ left: tooltipLeft, top: tooltipTop }}>
      {typeLabel && <div className="gear-tooltip-type">{typeLabel}</div>}
      <div className="gear-tooltip-name">{state.item.name}</div>
      {baseType && <div className="gear-tooltip-base">Base: {baseType}</div>}
      <div className="gear-tooltip-level">Required Level: {state.item.required_level}</div>
      <div className="gear-tooltip-divider" />
      {lgItem ? (
        <>
          {implicits.map((affix, i) => (
            <div key={i} className="gear-tooltip-affix gear-tooltip-affix--implicit">{affix.raw_text}</div>
          ))}
          {implicits.length > 0 && explicits.length > 0 && (
            <div className="gear-preview-section-dashes" style={{ margin: '5px 0' }} />
          )}
          {explicits.map((affix, i) => (
            <div key={i} className="gear-tooltip-affix">
              {tooltipAffixText(affix, implicits.length + i, customizations)}
            </div>
          ))}
        </>
      ) : (() => {
        const craftItem = state.item as EquippedGearItem
        const implCount = craftItem.implicit_count ?? 0
        const craftImplicits = craftItem.affixes.slice(0, implCount)
        const craftExplicits = craftItem.affixes.slice(implCount)
        const mutText = craftItem.corrosion_type === 'mutation' ? craftItem.mutation_affix_text : null
        return (
          <>
            {mutText && (
              <div className="gear-tooltip-affix gear-tooltip-affix--corroded">{mutText}</div>
            )}
            {craftImplicits.map((affix, i) => (
              <div key={i} className="gear-tooltip-affix gear-tooltip-affix--implicit">
                {affix.raw_text}
              </div>
            ))}
            {craftImplicits.length > 0 && craftExplicits.length > 0 && (
              <div className="gear-preview-section-dashes" style={{ margin: '5px 0' }} />
            )}
            {craftExplicits.map((affix, i) => (
              <div key={i} className="gear-tooltip-affix">
                {tooltipAffixText(affix, implCount + i, customizations)}
                {affixTypeLabel(affix.affix_type) && <span className="gear-affix-label">({affixTypeLabel(affix.affix_type)})</span>}
              </div>
            ))}
          </>
        )
      })()}
    </div>,
    document.body
  )
}
