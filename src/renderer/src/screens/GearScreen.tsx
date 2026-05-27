import React, { useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  LegendaryGearItem, LegendaryGearIndexItem, LegendaryAffix, LegendaryNumericValue,
  EquippedGearItem, CustomizedAffix, GearSlot, CraftBaseType, CraftAffix, CraftBaseItem, CraftBaseItemGroup,
  Graft, GraftAffix,
} from '../api/client'
import { useReferenceStore } from '../store/referenceStore'

// ── Constants ─────────────────────────────────────────────────────────────────

const SLOT_ORDER: { id: GearSlot; label: string }[] = [
  { id: 'helmet',  label: 'Helmet'   },
  { id: 'amulet',  label: 'Amulet'   },
  { id: 'chest',   label: 'Chest'    },
  { id: 'gloves',  label: 'Gloves'   },
  { id: 'belt',    label: 'Belt'     },
  { id: 'boots',   label: 'Boots'    },
  { id: 'ring1',   label: 'Ring 1'   },
  { id: 'ring2',   label: 'Ring 2'   },
  { id: 'weapon1', label: 'Weapon 1' },
  { id: 'weapon2', label: 'Weapon 2' },
]

// ── Affix helpers ─────────────────────────────────────────────────────────────

// Maps craft base type item_id to valid gear slots. Used to build a name→slot lookup
// from the craft_base_types data, covering legendary base type names like "Imperishable Touch".
const ITEM_ID_TO_SLOTS: Record<string, GearSlot[]> = {
  belt: ['belt'], ring: ['ring1', 'ring2'], spirit_ring: ['ring1', 'ring2'],
  necklace: ['amulet'],
  dex_boots: ['boots'], str_boots: ['boots'], int_boots: ['boots'],
  dex_gloves: ['gloves'], str_gloves: ['gloves'], int_gloves: ['gloves'],
  dex_helmet: ['helmet'], str_helmet: ['helmet'], int_helmet: ['helmet'],
  dex_chest_armor: ['chest'], str_chest_armor: ['chest'], int_chest_armor: ['chest'],
  dex_shield: ['weapon2'], str_shield: ['weapon2'], int_shield: ['weapon2'],
  bow: ['weapon1', 'weapon2'], crossbow: ['weapon1', 'weapon2'],
  two_handed_sword: ['weapon1'], two_handed_axe: ['weapon1'], two_handed_hammer: ['weapon1'],
  musket: ['weapon1'], fire_cannon: ['weapon1'], tin_staff: ['weapon1'],
  one_handed_sword: ['weapon1', 'weapon2'], one_handed_axe: ['weapon1', 'weapon2'],
  one_handed_hammer: ['weapon1', 'weapon2'], dagger: ['weapon1', 'weapon2'],
  claw: ['weapon1', 'weapon2'], wand: ['weapon1', 'weapon2'], scepter: ['weapon1', 'weapon2'],
  pistol: ['weapon1', 'weapon2'], cane: ['weapon1', 'weapon2'], rod: ['weapon1', 'weapon2'],
  cudgel: ['weapon1', 'weapon2'],
}

// Maps an item's base_type name to the GearSlot(s) it's valid for.
// slotMap (built from craftBases.base_items) is tried first to handle unusual names
// like "Imperishable Touch" (gloves) that don't match keyword patterns.
function getValidSlots(baseType: string, slotMap?: Record<string, GearSlot[]>): GearSlot[] {
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

function getItemSlots(item: EquippedGearItem): GearSlot[] {
  if (!item.slot) return []
  return Array.isArray(item.slot) ? item.slot : [item.slot]
}

function itemHasSlot(item: EquippedGearItem, slot: GearSlot): boolean {
  return getItemSlots(item).includes(slot)
}

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
  for (const group of (item.random_affixes[variantKey] ?? [])) {
    affixes.push({
      raw_text: group.placeholder,
      modifier_id: null,
      expression: group.placeholder,
      condition: null,
      affix_kind: 'placeholder',
      numeric_values: [],
    })
  }
  return affixes
}

function getItemAffixes(item: LegendaryGearItem | EquippedGearItem): LegendaryAffix[] {
  if ('customizations' in item) return item.affixes
  const variantKey = Object.keys(item.variants)[0] ?? 'base'
  const variant = item.variants[variantKey]
  if (!variant) return []
  const affixes: LegendaryAffix[] = [...variant.implicits, ...variant.explicits]
  for (const group of (item.random_affixes[variantKey] ?? [])) {
    affixes.push({
      raw_text: group.placeholder,
      modifier_id: null,
      expression: group.placeholder,
      condition: null,
      affix_kind: 'placeholder',
      numeric_values: [],
    })
  }
  return affixes
}

function hasRangeValues(affix: LegendaryAffix): boolean {
  return affix.affix_kind === 'numeric' &&
    affix.numeric_values.some(v => v.kind === 'range')
}

function getRangeIndices(affix: LegendaryAffix): number[] {
  return affix.numeric_values
    .map((v, i) => (v.kind === 'range' ? i : -1))
    .filter(i => i >= 0)
}

function decimalPlaces(n: number): number {
  const s = String(n)
  const dot = s.indexOf('.')
  return dot === -1 ? 0 : s.length - dot - 1
}

// Returns midpoints between each consecutive snap position, for datalist tick marks.
// n steps → n ticks. Empty array when range is trivial or too dense.
function buildTicks(sliderMin: number, sliderMax: number, step: number): number[] {
  if (step <= 0) return []
  const n = Math.round((sliderMax - sliderMin) / step)
  if (n <= 1 || n > 200) return []
  const ticks: number[] = []
  for (let i = 0; i < n; i++) {
    const v = sliderMin + i * step
    const next = sliderMin + (i + 1) * step
    ticks.push(+(((v + next) / 2).toFixed(10)))
  }
  return ticks
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

// ── Tooltip ────────────────────────────────────────────────────────────────────

interface TooltipState {
  item: LegendaryGearItem | EquippedGearItem
  x: number
  y: number
}

function tooltipAffixText(affix: LegendaryAffix, affixIdx: number, customizations: CustomizedAffix[] | undefined): string {
  if (!hasRangeValues(affix)) return affix.raw_text
  const cust = customizations?.find(c => c.affix_index === affixIdx)
  return reconstructAffixText(affix, cust?.chosen_values ?? {})
}

function GearTooltip({ state }: { state: TooltipState }) {
  const customizations = 'customizations' in state.item ? state.item.customizations : undefined
  const baseType = ('base_type' in state.item ? state.item.base_type : undefined) ?? ''
  const typeLabel = getGearTypeLabel(baseType)
  const lgItem = isLegendaryGearItem(state.item) ? state.item : null
  const implicits = lgItem ? getItemImplicits(lgItem) : []
  const explicits = lgItem ? getItemExplicits(lgItem) : []

  return createPortal(
    <div className="gear-tooltip-portal" style={{ left: state.x + 16, top: state.y - 10 }}>
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

// ── Slot Dropdown Portal ───────────────────────────────────────────────────────

interface SlotDropdownProps {
  slotId: GearSlot
  rect: DOMRect
  equippedItems: EquippedGearItem[]
  currentIdx: number
  slotMap: Record<string, GearSlot[]>
  weapon1Is2H: boolean
  onSelect: (slot: GearSlot, idx: number | null) => void
  onClose: () => void
}

function SlotDropdownPortal({ slotId, rect, equippedItems, currentIdx, slotMap, weapon1Is2H, onSelect, onClose }: SlotDropdownProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  const slot2HBlocked = slotId === 'weapon2' && weapon1Is2H

  return createPortal(
    <div
      ref={ref}
      className="gear-slot-menu"
      style={{ position: 'fixed', left: rect.left, top: rect.bottom + 4, minWidth: rect.width }}
    >
      {slot2HBlocked ? (
        <div className="gear-slot-menu-option gear-slot-menu-option--incompatible" style={{ cursor: 'default' }}>
          Blocked — 2H weapon in Weapon 1
        </div>
      ) : (
        <>
          <div
            className="gear-slot-menu-option gear-slot-menu-empty"
            onClick={() => onSelect(slotId, null)}
          >
            — Empty —
          </div>
          {equippedItems.map((item, i) => {
            const validSlots = item.base_type ? getValidSlots(item.base_type, slotMap) : []
            const slotCompatible = validSlots.length === 0 || validSlots.includes(slotId)
            // Only show items that can go in this slot type; always show currently equipped item
            if (!slotCompatible && i !== currentIdx) return null
            // 2H conflict: item is slot-compatible but weapon1 has 2H
            const is2HConflict = slotCompatible && slotId === 'weapon2' && weapon1Is2H && i !== currentIdx
            return (
              <div
                key={i}
                className={`gear-slot-menu-option${i === currentIdx ? ' gear-slot-menu-option--current' : ''}${is2HConflict ? ' gear-slot-menu-option--incompatible' : ''}`}
                onClick={() => !is2HConflict ? onSelect(slotId, i) : undefined}
                title={is2HConflict ? `Cannot equip in this slot — 2H weapon in Weapon 1` : undefined}
              >
                {item.name}
              </div>
            )
          })}
        </>
      )}
    </div>,
    document.body
  )
}

// ── Customization Panel ───────────────────────────────────────────────────────

interface CustomizePanelProps {
  item: LegendaryGearItem | EquippedGearItem | null
  customizations: CustomizedAffix[]
  isEditing: boolean
  onCustomizationChange: (customizations: CustomizedAffix[]) => void
  onConfirm: () => void
  onCancel: () => void
  baseItemImplicits: Record<string, string[]>
  previewName: string | null
  previewLines: PreviewLine[] | null
  catalogItem: LegendaryGearItem | null
  corrosionBaseAffixes: Array<LegendaryAffix & { modifier_text: string }>
  corrosionType: 'none' | 'desecration' | 'mutation'
  corrodedExplicitIndices: number[]
  mutationAffixText: string | null
  onCorrosionChange: (
    type: 'none' | 'desecration' | 'mutation',
    indices: number[],
    mutationText: string | null,
    updatedAffixes: LegendaryAffix[] | null
  ) => void
}

function CustomizePanel({ item, customizations, isEditing, onCustomizationChange, onConfirm, onCancel, baseItemImplicits, previewName, previewLines, catalogItem, corrosionBaseAffixes, corrosionType, corrodedExplicitIndices, mutationAffixText, onCorrosionChange }: CustomizePanelProps) {
  const [hoveredAffix, setHoveredAffix] = useState<{ idx: number; x: number; y: number } | null>(null)
  const [baseHoverPos, setBaseHoverPos] = useState<{ x: number; y: number } | null>(null)
  const custPanelId = useId()

  if (!item) {
    return (
      <div className="gear-customize-panel gear-customize-empty">
        <span>Select an item to customize</span>
      </div>
    )
  }

  const setChosenValue = (affixIdx: number, valIdx: number, val: number) => {
    const next = customizations.filter(c => c.affix_index !== affixIdx)
    const existing = customizations.find(c => c.affix_index === affixIdx)
    next.push({
      affix_index: affixIdx,
      chosen_values: { ...(existing?.chosen_values ?? {}), [valIdx]: val },
      chosen_placeholder_key: existing?.chosen_placeholder_key ?? null,
    })
    onCustomizationChange(next)
  }

  const getChosenMap = (affixIdx: number): Record<number, number> => {
    const cust = customizations.find(c => c.affix_index === affixIdx)
    return cust?.chosen_values ?? {}
  }

  const isLegendary = isLegendaryGearItem(item)
  const baseType = ('base_type' in item ? item.base_type : undefined) ?? ''
  const typeLabel = getGearTypeLabel(baseType || (isLegendary ? '' : ''))
  const implicits = isLegendary ? getItemImplicits(item) : []
  const baseExplicits = isLegendary ? getItemExplicits(item) : []
  // For catalog view: show corroded affix text for toggled explicits
  const explicits = isLegendary
    ? baseExplicits.map((affix, i) =>
        corrodedExplicitIndices.includes(i) && catalogItem?.variants?.corroded?.explicits[i]
          ? catalogItem.variants.corroded.explicits[i]
          : affix
      )
    : []

  const hasCorroded = !!(catalogItem?.variants?.corroded)
  // Show corrosion controls for legendary items (both catalog view and equipped view)
  const showCorrosion = !!catalogItem && hasCorroded

  const getImplicitCount = (): number => {
    if (isLegendaryGearItem(item)) return implicits.length
    return (item as EquippedGearItem).implicit_count ?? 0
  }

  const handleToggleCorroded = (explicitIndex: number) => {
    if (!catalogItem?.variants?.corroded) return
    const baseVariant = catalogItem.variants.base
    const corrodedVariant = catalogItem.variants.corroded
    const isCurrentlyCorroded = corrodedExplicitIndices.includes(explicitIndex)

    let newIndices: number[]
    if (isCurrentlyCorroded) {
      newIndices = corrodedExplicitIndices.filter(i => i !== explicitIndex)
    } else if (corrodedExplicitIndices.length < 2) {
      newIndices = [...corrodedExplicitIndices, explicitIndex]
    } else {
      return
    }

    const implCount = getImplicitCount()
    const affixArrayIndex = implCount + explicitIndex

    let currentAffixes: LegendaryAffix[]
    if (isLegendaryGearItem(item)) {
      currentAffixes = getItemAffixes(item)
    } else {
      currentAffixes = [...(item as EquippedGearItem).affixes]
    }
    const updatedAffixes = [...currentAffixes]

    if (isCurrentlyCorroded) {
      const baseAffix = baseVariant?.explicits[explicitIndex]
      if (baseAffix) updatedAffixes[affixArrayIndex] = baseAffix
    } else {
      const corrodedAffix = corrodedVariant.explicits[explicitIndex]
      if (corrodedAffix) updatedAffixes[affixArrayIndex] = corrodedAffix
    }

    // Clear stale customization for the toggled explicit
    const newCustomizations = customizations.filter(c => c.affix_index !== affixArrayIndex)
    onCustomizationChange(newCustomizations)

    onCorrosionChange('desecration', newIndices, null, updatedAffixes)
  }

  const handleCorrosionTypeChange = (newType: 'none' | 'desecration' | 'mutation') => {
    if (!catalogItem?.variants?.base) return
    const baseVariant = catalogItem.variants.base
    const implCount = getImplicitCount()

    let updatedAffixes: LegendaryAffix[] | null = null
    if (corrodedExplicitIndices.length > 0) {
      let currentAffixes: LegendaryAffix[]
      if (isLegendaryGearItem(item)) {
        currentAffixes = getItemAffixes(item)
      } else {
        currentAffixes = [...(item as EquippedGearItem).affixes]
      }
      updatedAffixes = [...currentAffixes]
      for (const idx of corrodedExplicitIndices) {
        const baseAffix = baseVariant.explicits[idx]
        if (baseAffix) updatedAffixes[implCount + idx] = baseAffix
      }
      // Clear stale customizations for all formerly corroded explicits
      const staleIndices = new Set(corrodedExplicitIndices.map(i => implCount + i))
      onCustomizationChange(customizations.filter(c => !staleIndices.has(c.affix_index)))
    }

    onCorrosionChange(newType, [], newType === 'mutation' ? mutationAffixText : null, updatedAffixes)
  }

  const renderAffixRow = (affix: LegendaryAffix, affixIdx: number, explicitIndex?: number) => {
    const isCorroded = explicitIndex !== undefined && corrodedExplicitIndices.includes(explicitIndex)
    const showToggle = corrosionType === 'desecration' && showCorrosion && explicitIndex !== undefined
    const toggleDisabled = !isCorroded && corrodedExplicitIndices.length >= 2

    if (affix.affix_kind === 'placeholder') {
      return (
        <div key={affixIdx} className="gear-affix-row gear-affix-placeholder">
          <div className="gear-affix-label gear-affix-label--dim">{affix.raw_text}</div>
          <select className="gear-placeholder-select" disabled>
            <option>— Select affix —</option>
          </select>
        </div>
      )
    }
    if (!hasRangeValues(affix)) {
      return (
        <div key={affixIdx} className={`gear-affix-row${isCorroded ? ' gear-affix-row--corroded' : ''}`}>
          <div className="gear-affix-label">{affix.raw_text}</div>
          {showToggle && (
            <button
              className={`gear-corrosion-toggle${isCorroded ? ' active' : ''}`}
              disabled={toggleDisabled}
              onClick={() => handleToggleCorroded(explicitIndex!)}
              title={isCorroded ? 'Remove desecration' : toggleDisabled ? 'Max 2 desecrated mods' : 'Desecrate this modifier'}
            >C</button>
          )}
        </div>
      )
    }
    const rangeIndices = getRangeIndices(affix)
    const chosenMap = getChosenMap(affixIdx)
    const displayText = reconstructAffixText(affix, {
      ...Object.fromEntries(rangeIndices.map(i => [i, midpoint(affix.numeric_values[i])])),
      ...chosenMap,
    })
    return (
      <div key={affixIdx} className={`gear-affix-row gear-affix-range-row${isCorroded ? ' gear-affix-row--corroded' : ''}`}
        onMouseMove={e => setHoveredAffix({ idx: affixIdx, x: e.clientX, y: e.clientY })}
        onMouseLeave={() => setHoveredAffix(null)}
      >
        <div className="gear-affix-label">{displayText}</div>
        {showToggle && (
          <button
            className={`gear-corrosion-toggle${isCorroded ? ' active' : ''}`}
            disabled={toggleDisabled}
            onClick={() => handleToggleCorroded(explicitIndex!)}
            title={isCorroded ? 'Remove desecration' : toggleDisabled ? 'Max 2 desecrated mods' : 'Desecrate this modifier'}
          >C</button>
        )}
        {rangeIndices.map(valIdx => {
          const nv = affix.numeric_values[valIdx]
          const nvSign = nv.sign ?? ''
          const rawMin = nv.min ?? 0
          const rawMax = nv.max ?? 0
          const dp = rangeDecimals(nv)
          const step = dp > 0 ? parseFloat((1 / Math.pow(10, dp)).toFixed(dp)) : 1
          const sMin = nvSign === '-' ? -rawMin : rawMin
          const sMax = nvSign === '-' ? -rawMax : rawMax
          const actualMin = Math.min(sMin, sMax)
          const actualMax = Math.max(sMin, sMax)
          const ticks = buildTicks(actualMin, actualMax, step)
          const listId = `${custPanelId}-${affixIdx}-${valIdx}`
          const unsignedChosen = chosenMap[valIdx] ?? midpoint(nv)
          const signedChosen = nvSign === '-' ? -unsignedChosen : unsignedChosen
          const displayChosen = dp > 0 ? signedChosen.toFixed(dp) : signedChosen
          return (
            <div key={valIdx} className="gear-slider-row">
              <input
                type="range"
                className="gear-affix-slider"
                list={ticks.length > 0 ? listId : undefined}
                min={actualMin}
                max={actualMax}
                step={step}
                value={signedChosen}
                onChange={e => {
                  const signed = Number(e.target.value)
                  setChosenValue(affixIdx, valIdx, nvSign === '-' ? -signed : signed)
                }}
              />
              {ticks.length > 0 && (
                <datalist id={listId}>
                  {ticks.map((t, ti) => <option key={ti} value={t} />)}
                </datalist>
              )}
              <span className="gear-affix-value">{displayChosen}</span>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className="gear-customize-panel">
      <div className="gear-customize-header">
        {typeLabel && <div className="gear-customize-type">{typeLabel}</div>}
        <div className="gear-customize-name">{item.name}</div>
        {baseType && (() => {
          const baseStats = baseItemImplicits[baseType] ?? []
          const hasStats = baseStats.length > 0
          return (
            <div
              className={`gear-customize-base${hasStats ? ' gear-customize-base--hoverable' : ''}`}
              onMouseEnter={hasStats ? e => setBaseHoverPos({ x: e.clientX, y: e.clientY }) : undefined}
              onMouseMove={hasStats ? e => setBaseHoverPos({ x: e.clientX, y: e.clientY }) : undefined}
              onMouseLeave={hasStats ? () => setBaseHoverPos(null) : undefined}
            >
              Base: {baseType}
            </div>
          )
        })()}
        <div className="gear-customize-level">Required Level: {item.required_level}</div>
      </div>
      {baseHoverPos && (() => {
        const baseStats = baseItemImplicits[baseType] ?? []
        if (!baseStats.length) return null
        return createPortal(
          <div
            className="gear-base-stat-tooltip"
            style={{
              left: Math.min(baseHoverPos.x + 16, window.innerWidth - 260),
              top: Math.min(baseHoverPos.y - 10, window.innerHeight - 150),
            }}
          >
            <div className="gear-base-stat-tooltip-name">{baseType}</div>
            {baseStats.map((line, i) => (
              <div key={i} className="gear-base-stat-tooltip-stat">{line}</div>
            ))}
          </div>,
          document.body
        )
      })()}
      <div className="gear-customize-divider" />

      {showCorrosion && (
        <div className="gear-corrosion-section">
          <div className="gear-corrosion-row">
            <span className="gear-corrosion-label">Corruption</span>
            <select
              className="gear-corrosion-select"
              value={corrosionType}
              onChange={e => handleCorrosionTypeChange(e.target.value as 'none' | 'desecration' | 'mutation')}
            >
              <option value="none">None</option>
              <option value="desecration">Desecration</option>
              <option value="mutation">Mutation</option>
            </select>
          </div>
          {corrosionType === 'mutation' && (
            corrosionBaseAffixes.length > 0 ? (
              <select
                className="gear-mutation-select"
                value={mutationAffixText ?? ''}
                onChange={e => onCorrosionChange('mutation', [], e.target.value || null, null)}
              >
                <option value="">— select mutation —</option>
                {corrosionBaseAffixes.map((a, i) => (
                  <option key={i} value={a.modifier_text}>{a.modifier_text}</option>
                ))}
              </select>
            ) : (
              <div className="gear-mutation-unavailable">
                Mutation data not available — re-import craft data from DevTools.
              </div>
            )
          )}
        </div>
      )}

      <div className="gear-customize-affixes">
        {isLegendary ? (
          <>
            {showCorrosion && corrosionType === 'mutation' && mutationAffixText && (
              <div className="gear-affix-row gear-affix-row--corroded">
                <div className="gear-affix-label">{mutationAffixText}</div>
              </div>
            )}
            {implicits.map((affix, i) => renderAffixRow(affix, i))}
            {implicits.length > 0 && explicits.length > 0 && (
              <div className="gear-affix-section-divider" />
            )}
            {explicits.map((affix, i) => renderAffixRow(affix, implicits.length + i, i))}
          </>
        ) : (() => {
          const craftItem = item as EquippedGearItem
          const implCount = craftItem.implicit_count ?? 0
          const craftImplicits = craftItem.affixes.slice(0, implCount)
          const craftExplicits = craftItem.affixes.slice(implCount)
          return (
            <>
              {showCorrosion && corrosionType === 'mutation' && mutationAffixText && (
                <div className="gear-affix-row gear-affix-row--corroded">
                  <div className="gear-affix-label">{mutationAffixText}</div>
                </div>
              )}
              {craftImplicits.map((affix, i) => renderAffixRow(affix, i))}
              {craftImplicits.length > 0 && craftExplicits.length > 0 && (
                <div className="gear-affix-section-divider" />
              )}
              {craftExplicits.map((affix, i) => renderAffixRow(affix, implCount + i, catalogItem ? i : undefined))}
            </>
          )
        })()}
      </div>

      <ItemPreviewCard name={previewName} lines={previewLines} />
      <div className="gear-customize-actions">
        <button className="btn btn-sm btn-primary gear-confirm-btn" onClick={onConfirm}>
          {isEditing ? 'Save' : 'Add to Build'}
        </button>
        <button className="btn btn-sm" onClick={onCancel}>Cancel</button>
      </div>
      {hoveredAffix && item && (() => {
        const hAffix = getItemAffixes(item)[hoveredAffix.idx]
        if (!hAffix || !hasRangeValues(hAffix)) return null
        const text = tooltipAffixText(hAffix, hoveredAffix.idx, customizations)
        return createPortal(
          <div className="gear-slider-tooltip" style={{ left: hoveredAffix.x + 16, top: Math.min(hoveredAffix.y - 10, window.innerHeight - 80) }}>
            {text}
          </div>,
          document.body
        )
      })()}
    </div>
  )
}

// ── Craft metadata ────────────────────────────────────────────────────────────

const CRAFT_CLASSIFICATIONS: Record<string, string> = {
  bow: 'Two-Handed', crossbow: 'Two-Handed', two_handed_sword: 'Two-Handed',
  two_handed_axe: 'Two-Handed', two_handed_hammer: 'Two-Handed',
  musket: 'Two-Handed', fire_cannon: 'Two-Handed', tin_staff: 'Two-Handed',
  one_handed_sword: 'One-Handed', one_handed_axe: 'One-Handed',
  one_handed_hammer: 'One-Handed', dagger: 'One-Handed', claw: 'One-Handed',
  wand: 'One-Handed', scepter: 'One-Handed', pistol: 'One-Handed',
  cane: 'One-Handed', rod: 'One-Handed', cudgel: 'One-Handed',
  str_shield: 'Shield', dex_shield: 'Shield', int_shield: 'Shield',
}

const TWO_HANDED_IDS = new Set(
  Object.entries(CRAFT_CLASSIFICATIONS)
    .filter(([, v]) => v === 'Two-Handed')
    .map(([k]) => k)
)

function isTwoHandedBaseType(baseType: string, baseTypeToItemId: Record<string, string>): boolean {
  const bt = baseType ?? ''
  const typeId = baseTypeToItemId[bt] ?? bt.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
  return TWO_HANDED_IDS.has(typeId)
}

// Fixed crit + attack speed shared by all weapons of a type
const CRAFT_WEAPON_STATS: Record<string, { crit: number; speed: number }> = {
  bow: { crit: 500, speed: 1.5 }, crossbow: { crit: 500, speed: 1.5 },
  two_handed_sword: { crit: 500, speed: 1.5 }, two_handed_axe: { crit: 500, speed: 1.5 },
  two_handed_hammer: { crit: 500, speed: 1.5 }, musket: { crit: 500, speed: 1.5 },
  fire_cannon: { crit: 500, speed: 1.5 }, tin_staff: { crit: 500, speed: 1.5 },
  one_handed_sword: { crit: 500, speed: 1.5 }, one_handed_axe: { crit: 500, speed: 1.5 },
  one_handed_hammer: { crit: 500, speed: 1.5 }, dagger: { crit: 500, speed: 1.5 },
  claw: { crit: 500, speed: 1.5 }, pistol: { crit: 500, speed: 1.5 },
  cudgel: { crit: 500, speed: 1.5 },
  wand: { crit: 500, speed: 1.2 }, scepter: { crit: 500, speed: 1.2 },
  cane: { crit: 500, speed: 1.2 }, rod: { crit: 500, speed: 1.2 },
}

// ── Craft helpers ─────────────────────────────────────────────────────────────

interface CraftSlotState {
  expression: string | null
  affix: CraftAffix | null
  chosenValues: Record<number, number>
}

const emptyCraftSlot = (): CraftSlotState => ({ expression: null, affix: null, chosenValues: {} })

interface VoraxInitialState {
  baseSlots: [VoraxAffixSlot, VoraxAffixSlot]
  prefixSlots: [VoraxAffixSlot, VoraxAffixSlot, VoraxAffixSlot]
  suffixSlots: [VoraxAffixSlot, VoraxAffixSlot, VoraxAffixSlot]
  legSourceName: string | null
  legSourceItem: LegendaryGearItem | null
}

function reconstructCraftSlots(item: EquippedGearItem, baseType: CraftBaseType): CraftSlotState[] {
  const implicitCount = item.implicit_count ?? 0
  const explicits = item.affixes.slice(implicitCount).filter(
    a => a.affix_kind === 'numeric' || a.affix_kind === 'special'
  )
  const slots: CraftSlotState[] = Array.from({ length: 8 }, emptyCraftSlot)
  const positions = item.craft_slot_positions
  explicits.forEach((aff, i) => {
    const slotIdx = positions ? (positions[i] ?? i) : i
    if (slotIdx >= 8) return
    const poolAffix = baseType.affixes.find(pa => pa.raw_text === aff.raw_text) ?? null
    const cust = item.customizations.find(c => c.affix_index === implicitCount + i)
    slots[slotIdx] = { expression: poolAffix ? normalizeExpression(poolAffix.expression) : null, affix: poolAffix, chosenValues: cust?.chosen_values ?? {} }
  })
  return slots
}

function reconstructVoraxSlots(
  item: EquippedGearItem,
  graft: Graft,
  catalog: LegendaryGearItem[],
): VoraxInitialState {
  const toSlot = (aff: LegendaryAffix, custIdx: number): VoraxAffixSlot => {
    const chosen = item.customizations.find(c => c.affix_index === custIdx)?.chosen_values ?? {}
    if (aff.affix_type === 'Legendary') {
      return { expression: normalizeExpression(aff.expression), affix: aff as unknown as LegendaryAffix, chosenValues: chosen, isLegendary: true }
    }
    const poolAffix = graft.affixes.find(pa => pa.raw_text === aff.raw_text) ?? null
    return { expression: poolAffix ? normalizeExpression(poolAffix.expression) : null, affix: poolAffix, chosenValues: chosen, isLegendary: false }
  }
  const baseSlots: [VoraxAffixSlot, VoraxAffixSlot] = [emptyVoraxSlot(), emptyVoraxSlot()]
  const prefixSlots: [VoraxAffixSlot, VoraxAffixSlot, VoraxAffixSlot] = [emptyVoraxSlot(), emptyVoraxSlot(), emptyVoraxSlot()]
  const suffixSlots: [VoraxAffixSlot, VoraxAffixSlot, VoraxAffixSlot] = [emptyVoraxSlot(), emptyVoraxSlot(), emptyVoraxSlot()]
  const positions = item.craft_slot_positions
  item.affixes.forEach((aff, affixIdx) => {
    // Slot indices: 0-1 = base, 2-4 = prefix, 5-7 = suffix
    const slotIdx = positions ? (positions[affixIdx] ?? affixIdx) : affixIdx
    const slot = toSlot(aff, affixIdx)
    if (slotIdx < 2) {
      baseSlots[slotIdx] = slot
    } else if (slotIdx < 5) {
      prefixSlots[slotIdx - 2] = slot
    } else if (slotIdx < 8) {
      suffixSlots[slotIdx - 5] = slot
    }
  })
  const legSourceName = item.legendary_source ?? null
  const legSourceItem = legSourceName ? catalog.find(c => c.name === legSourceName) ?? null : null
  return { baseSlots, prefixSlots, suffixSlots, legSourceName, legSourceItem }
}

type AffixWithTier = { expression: string; affix_type: string; tier: string }

function normalizeExpression(expr: string): string {
  return expr.replace(/\(#\)|\d+(\.\d+)?/g, '#')
}

function tiersForModifier<T extends AffixWithTier>(pool: T[], expression: string): T[] {
  const norm = normalizeExpression(expression)
  return pool.filter(a => normalizeExpression(a.expression) === norm)
}

function parseTierNum(tier: string): number {
  const s = (tier ?? '').trim()
  if (s.endsWith('+')) return parseFloat(s.slice(0, -1)) - 0.5
  return parseFloat(s) || 0
}

function sortedTiers<T extends AffixWithTier>(tiers: T[]): T[] {
  return [...tiers].sort((a, b) => parseTierNum(a.tier) - parseTierNum(b.tier))
}

// Prefer the lowest tier >= 1 as default; fall back to the absolute lowest tier
function defaultTier<T extends AffixWithTier>(tiers: T[]): T | null {
  const sorted = sortedTiers(tiers)
  return sorted.find(a => parseTierNum(a.tier) >= 1) ?? sorted[0] ?? null
}

type PreviewLine = { text: string; label?: string; corroded?: boolean } | null

function affixTypeLabel(affixType: string | undefined): string | undefined {
  if (!affixType) return undefined
  if (affixType === 'Base' || affixType === 'Base Affix') return 'Base Affix'
  if (affixType === 'Legendary') return 'Legendary Affix'
  const match = affixType.match(/^(Basic|Advanced|Ultimate)/i)
  return match ? `${match[1]} Affix` : undefined
}

function craftAffixToLegendary(a: CraftAffix | GraftAffix): LegendaryAffix {
  const c = a as Partial<CraftAffix>
  return {
    raw_text: a.raw_text,
    modifier_id: null,
    expression: a.expression,
    condition: a.condition,
    affix_kind: a.affix_kind,
    numeric_values: a.numeric_values,
    stat_key: c.stat_key ?? null,
    stat_keys: c.stat_keys,
    is_range_split: c.is_range_split,
    min_stat_keys: c.min_stat_keys,
    max_stat_keys: c.max_stat_keys,
    dual_stat_groups: c.dual_stat_groups,
    unit: c.unit ?? '',
    affix_type: a.affix_type,
  }
}

// ── Vorax constants and helpers ───────────────────────────────────────────────

const VORAX_GRAFT_SLOTS: Record<string, GearSlot[]> = {
  vorax_limb_head:              ['helmet'],
  vorax_limb_hands:             ['gloves'],
  vorax_limb_chest:             ['chest'],
  vorax_limb_legs:              ['boots'],
  vorax_limb_waist:             ['belt'],
  vorax_limb_neck:              ['amulet'],
  vorax_limb_digits:            ['ring1', 'ring2'],
  vorax_aberrant_limb_digits:   ['ring1', 'ring2'],
  vorax_aberrant_limb_legs:     ['boots'],
  vorax_aberrant_limb_waist:    ['belt'],
}

function getVoraxDisplayName(graft: Graft): string {
  // "Vorax Limb: Head" → "Vorax Head" | "Vorax Aberrant Limb: Digits" → "Vorax Aberrant Digits"
  return graft.name.replace('Limb: ', '')
}

interface VoraxAffixSlot {
  expression: string | null
  affix: GraftAffix | LegendaryAffix | null
  chosenValues: Record<number, number>
  isLegendary: boolean
}

const emptyVoraxSlot = (): VoraxAffixSlot => ({ expression: null, affix: null, chosenValues: {}, isLegendary: false })

// ── Grouped modifiers helper ───────────────────────────────────────────────────

interface ModifierGroup { quality: string; expressions: string[] }

function groupedModifiers(pool: AffixWithTier[]): ModifierGroup[] {
  const groups: Record<string, Set<string>> = {}
  for (const a of pool) {
    const quality = a.affix_type.replace(/\s*(Pre-fix|Suffix|Affix).*$/i, '').trim() || 'Other'
    if (!groups[quality]) groups[quality] = new Set()
    groups[quality].add(normalizeExpression(a.expression))
  }
  return ['Base', 'Basic', 'Advanced', 'Ultimate', 'Mutation', 'Other']
    .filter(q => groups[q])
    .map(q => ({ quality: q, expressions: [...groups[q]].sort() }))
}

// ── Modifier searchable select ─────────────────────────────────────────────────

interface ModifierSearchSelectProps {
  pool: CraftAffix[]
  value: string
  onChange: (expr: string) => void
  disabledExpressions?: ReadonlySet<string>
}

function ModifierSearchSelect({ pool, value, onChange, disabledExpressions }: ModifierSearchSelectProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const MAX_DROPDOWN_H = 260

  useEffect(() => {
    if (!open) { setQuery(''); setTriggerRect(null); return }
    if (containerRef.current) setTriggerRect(containerRef.current.getBoundingClientRect())
    setTimeout(() => inputRef.current?.focus(), 0)
  }, [open])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
        containerRef.current && !containerRef.current.contains(e.target as Node)
      ) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const groups = useMemo(() => groupedModifiers(pool), [pool])
  const isDisabled = (expr: string) => !!(disabledExpressions?.has(expr) && expr !== value)
  const filteredExprs = useMemo(() => {
    if (!query.trim()) return null
    const q = query.toLowerCase()
    return groups.flatMap(g => g.expressions).filter(e => e.toLowerCase().includes(q))
  }, [query, groups])

  const dropdownStyle = triggerRect ? (() => {
    const spaceBelow = window.innerHeight - triggerRect.bottom
    const showAbove = spaceBelow < MAX_DROPDOWN_H + 4 && triggerRect.top > MAX_DROPDOWN_H
    return {
      position: 'fixed' as const,
      left: triggerRect.left,
      width: triggerRect.width,
      maxHeight: MAX_DROPDOWN_H,
      ...(showAbove ? { bottom: window.innerHeight - triggerRect.top + 2 } : { top: triggerRect.bottom + 2 }),
    }
  })() : {}

  return (
    <div ref={containerRef} className="gear-craft-mod-select">
      <div className={`gear-craft-mod-trigger${open ? ' open' : ''}`} onClick={() => setOpen(o => !o)}>
        <span className={value ? 'gear-craft-mod-value' : 'gear-craft-mod-placeholder'}>
          {value || '— modifier —'}
        </span>
        {value && (
          <span
            className="gear-craft-mod-clear"
            onMouseDown={e => { e.stopPropagation(); onChange(''); setOpen(false) }}
          >×</span>
        )}
      </div>
      {open && triggerRect && createPortal(
        <div ref={dropdownRef} className="gear-craft-mod-dropdown" style={dropdownStyle}>
          <input
            ref={inputRef}
            className="gear-craft-mod-search"
            placeholder="Search…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onMouseDown={e => e.stopPropagation()}
          />
          <div className="gear-craft-mod-list">
            {filteredExprs !== null ? (
              filteredExprs.filter(e => !isDisabled(e)).length === 0
                ? <div className="gear-craft-mod-empty">No matches</div>
                : filteredExprs.filter(e => !isDisabled(e)).map(expr => (
                    <div
                      key={expr}
                      className={`gear-craft-mod-option${expr === value ? ' selected' : ''}`}
                      onMouseDown={() => { onChange(expr); setOpen(false) }}
                    >{expr}</div>
                  ))
            ) : (
              groups.map(g => {
                const visible = g.expressions.filter(e => !isDisabled(e))
                if (visible.length === 0) return null
                return (
                  <React.Fragment key={g.quality}>
                    <div className="gear-craft-mod-group">{g.quality}</div>
                    {visible.map(expr => (
                      <div
                        key={expr}
                        className={`gear-craft-mod-option${expr === value ? ' selected' : ''}`}
                        onMouseDown={() => { onChange(expr); setOpen(false) }}
                      >{expr}</div>
                    ))}
                  </React.Fragment>
                )
              })
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

// ── Craft Slot Row ─────────────────────────────────────────────────────────────

interface CraftSlotRowProps {
  pool: CraftAffix[]
  slot: CraftSlotState
  onChange: (next: CraftSlotState) => void
  disabledExpressions?: ReadonlySet<string>
}

function CraftSlotRow({ pool, slot, onChange, disabledExpressions }: CraftSlotRowProps) {
  const [sliderHoverPos, setSliderHoverPos] = useState<{ x: number; y: number } | null>(null)
  const craftSlotId = useId()
  const rawTiers = useMemo(() => slot.expression ? tiersForModifier(pool, slot.expression) : [], [pool, slot.expression])
  const tiers = useMemo(() => sortedTiers(rawTiers), [rawTiers])

  // For slider: span the full range across all tiers when only 1 tier (no tier dropdown)
  const sliderAffix = slot.affix
  const dp = sliderAffix ? Math.max(...sliderAffix.numeric_values.map(nv => rangeDecimals(nv)), 0) : 0
  const step = dp > 0 ? parseFloat((1 / Math.pow(10, dp)).toFixed(dp)) : 1

  const handleModifierChange = (expr: string) => {
    if (!expr) { onChange(emptyCraftSlot()); return }
    const available = tiersForModifier(pool, expr)
    onChange({ expression: expr, affix: defaultTier(available), chosenValues: {} })
  }

  const handleTierChange = (rawText: string) => {
    const affix = tiers.find(a => a.raw_text === rawText) ?? null
    onChange({ ...slot, affix, chosenValues: {} })
  }

  const handleSliderChange = (valIdx: number, val: number) => {
    onChange({ ...slot, chosenValues: { ...slot.chosenValues, [valIdx]: val } })
  }

  return (
    <div className="gear-craft-slot">
      <div className="gear-craft-slot-row">
        <ModifierSearchSelect pool={pool} value={slot.expression ?? ''} onChange={handleModifierChange} disabledExpressions={disabledExpressions} />
        {slot.expression && tiers.length > 1 && (
          <select
            className="gear-craft-select gear-craft-select--tier"
            value={slot.affix?.raw_text ?? ''}
            onChange={e => handleTierChange(e.target.value)}
          >
            {tiers.map(a => (
              <option key={a.raw_text} value={a.raw_text}>Tier: {a.tier}</option>
            ))}
          </select>
        )}
      </div>

      {sliderAffix && sliderAffix.numeric_values.some(v => v.kind === 'range') && (
        <div className="gear-craft-sliders"
          onMouseMove={e => setSliderHoverPos({ x: e.clientX, y: e.clientY })}
          onMouseLeave={() => setSliderHoverPos(null)}
        >
          {sliderAffix.numeric_values.map((nv, valIdx) => {
            if (nv.kind !== 'range') return null
            const nvSign = nv.sign ?? ''
            const rawMin = nv.min ?? 0
            const rawMax = nv.max ?? 0
            const sMin = nvSign === '-' ? -rawMin : rawMin
            const sMax = nvSign === '-' ? -rawMax : rawMax
            const actualMin = Math.min(sMin, sMax)
            const actualMax = Math.max(sMin, sMax)
            const ticks = buildTicks(actualMin, actualMax, step)
            const listId = `${craftSlotId}-${valIdx}`
            const unsignedChosen = slot.chosenValues[valIdx] ?? midpoint(nv)
            const signedChosen = nvSign === '-' ? -unsignedChosen : unsignedChosen
            const display = dp > 0 ? signedChosen.toFixed(dp) : signedChosen
            return (
              <div key={valIdx} className="gear-slider-row">
                <input
                  type="range" className="gear-affix-slider"
                  list={ticks.length > 0 ? listId : undefined}
                  min={actualMin} max={actualMax} step={step} value={signedChosen}
                  onChange={e => {
                    const signed = Number(e.target.value)
                    handleSliderChange(valIdx, nvSign === '-' ? -signed : signed)
                  }}
                />
                {ticks.length > 0 && (
                  <datalist id={listId}>
                    {ticks.map((t, ti) => <option key={ti} value={t} />)}
                  </datalist>
                )}
                <span className="gear-affix-value">{display}</span>
              </div>
            )
          })}
        </div>
      )}
      {sliderHoverPos && sliderAffix && createPortal(
        <div className="gear-slider-tooltip" style={{ left: sliderHoverPos.x + 16, top: Math.min(sliderHoverPos.y - 10, window.innerHeight - 80) }}>
          {reconstructAffixText(craftAffixToLegendary(sliderAffix), slot.chosenValues)}
        </div>,
        document.body
      )}
    </div>
  )
}

// ── Vorax Modifier Select ─────────────────────────────────────────────────────

interface VoraxModSelectProps {
  graftPool: GraftAffix[]
  legPool: LegendaryAffix[]
  value: string
  onChange: (expr: string, isLegendary: boolean) => void
  disabledExpressions?: ReadonlySet<string>
}

function VoraxModSelect({ graftPool, legPool, value, onChange, disabledExpressions }: VoraxModSelectProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const MAX_DROPDOWN_H = 260

  useEffect(() => {
    if (!open) { setQuery(''); setTriggerRect(null); return }
    if (containerRef.current) setTriggerRect(containerRef.current.getBoundingClientRect())
    setTimeout(() => inputRef.current?.focus(), 0)
  }, [open])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
        containerRef.current && !containerRef.current.contains(e.target as Node)
      ) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const graftGroups = useMemo(() => groupedModifiers(graftPool), [graftPool])

  const legExprs = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const a of legPool) {
      if (!seen.has(a.expression)) { seen.add(a.expression); result.push(a.expression) }
    }
    return result.sort()
  }, [legPool])

  const filteredGraft = useMemo(() => {
    if (!query.trim()) return null
    const q = query.toLowerCase()
    return graftGroups.flatMap(g => g.expressions).filter(e => e.toLowerCase().includes(q))
  }, [query, graftGroups])

  const filteredLeg = useMemo(() => {
    if (!query.trim()) return null
    const q = query.toLowerCase()
    return legExprs.filter(e => e.toLowerCase().includes(q))
  }, [query, legExprs])

  const isLegendaryExpr = (expr: string) => legExprs.includes(expr)
  const isVoraxDisabled = (expr: string) => !!(disabledExpressions?.has(expr) && expr !== value)

  const handlePick = (expr: string) => {
    onChange(expr, isLegendaryExpr(expr))
    setOpen(false)
  }

  const isValueLegendary = value ? isLegendaryExpr(value) : false

  // Filtered and de-duplicated results for search mode
  const visibleFilteredLeg = (filteredLeg ?? []).filter(e => !isVoraxDisabled(e))
  const visibleFilteredGraft = (filteredGraft ?? []).filter(e => !isVoraxDisabled(e))

  const dropdownStyle = triggerRect ? (() => {
    const spaceBelow = window.innerHeight - triggerRect.bottom
    const showAbove = spaceBelow < MAX_DROPDOWN_H + 4 && triggerRect.top > MAX_DROPDOWN_H
    return {
      position: 'fixed' as const,
      left: triggerRect.left,
      width: triggerRect.width,
      maxHeight: MAX_DROPDOWN_H,
      ...(showAbove ? { bottom: window.innerHeight - triggerRect.top + 2 } : { top: triggerRect.bottom + 2 }),
    }
  })() : {}

  return (
    <div ref={containerRef} className="gear-craft-mod-select">
      <div className={`gear-craft-mod-trigger${open ? ' open' : ''}`} onClick={() => setOpen(o => !o)}>
        <span className={value ? `gear-craft-mod-value${isValueLegendary ? ' vorax-affix-legendary' : ''}` : 'gear-craft-mod-placeholder'}>
          {value || '— modifier —'}
        </span>
        {value && (
          <span
            className="gear-craft-mod-clear"
            onMouseDown={e => { e.stopPropagation(); onChange('', false); setOpen(false) }}
          >×</span>
        )}
      </div>
      {open && triggerRect && createPortal(
        <div ref={dropdownRef} className="gear-craft-mod-dropdown" style={dropdownStyle}>
          <input
            ref={inputRef}
            className="gear-craft-mod-search"
            placeholder="Search…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onMouseDown={e => e.stopPropagation()}
          />
          <div className="gear-craft-mod-list">
            {query.trim() ? (
              <>
                {visibleFilteredLeg.length > 0 && visibleFilteredGraft.length > 0 && (
                  <div className="gear-craft-mod-group vorax-affix-legendary">Legendary</div>
                )}
                {visibleFilteredLeg.map(expr => (
                  <div key={expr} className={`gear-craft-mod-option vorax-affix-legendary${expr === value ? ' selected' : ''}`} onMouseDown={() => handlePick(expr)}>{expr}</div>
                ))}
                {visibleFilteredGraft.map(expr => (
                  <div key={expr} className={`gear-craft-mod-option${expr === value ? ' selected' : ''}`} onMouseDown={() => handlePick(expr)}>{expr}</div>
                ))}
                {visibleFilteredLeg.length === 0 && visibleFilteredGraft.length === 0 && (
                  <div className="gear-craft-mod-empty">No matches</div>
                )}
              </>
            ) : (
              <>
                {legExprs.length > 0 && (
                  <>
                    <div className="gear-craft-mod-group vorax-affix-legendary">Legendary</div>
                    {legExprs.filter(e => !isVoraxDisabled(e)).map(expr => (
                      <div key={expr} className={`gear-craft-mod-option vorax-affix-legendary${expr === value ? ' selected' : ''}`} onMouseDown={() => handlePick(expr)}>{expr}</div>
                    ))}
                  </>
                )}
                {graftGroups.map(g => {
                  const visible = g.expressions.filter(e => !isVoraxDisabled(e))
                  if (visible.length === 0) return null
                  return (
                    <React.Fragment key={g.quality}>
                      <div className="gear-craft-mod-group">{g.quality}</div>
                      {visible.map(expr => (
                        <div key={expr} className={`gear-craft-mod-option${expr === value ? ' selected' : ''}`} onMouseDown={() => handlePick(expr)}>{expr}</div>
                      ))}
                    </React.Fragment>
                  )
                })}
              </>
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

// ── Vorax Craft Slot Row ───────────────────────────────────────────────────────

interface VoraxCraftSlotRowProps {
  graftPool: GraftAffix[]
  legPool: LegendaryAffix[]
  slot: VoraxAffixSlot
  onChange: (next: VoraxAffixSlot) => void
  disabledExpressions?: ReadonlySet<string>
}

function VoraxCraftSlotRow({ graftPool, legPool, slot, onChange, disabledExpressions }: VoraxCraftSlotRowProps) {
  const [sliderHoverPos, setSliderHoverPos] = useState<{ x: number; y: number } | null>(null)
  const craftSlotId = useId()

  const handleModifierChange = (expr: string, isLeg: boolean) => {
    if (!expr) { onChange(emptyVoraxSlot()); return }
    if (isLeg) {
      const found = legPool.find(a => a.expression === expr) ?? null
      onChange({ expression: expr, affix: found, chosenValues: {}, isLegendary: true })
    } else {
      const available = tiersForModifier(graftPool, expr)
      onChange({ expression: expr, affix: defaultTier(available), chosenValues: {}, isLegendary: false })
    }
  }

  const handleTierChange = (rawText: string) => {
    const affix = sortedTiers(tiersForModifier(graftPool, slot.expression ?? '')).find(a => a.raw_text === rawText) ?? null
    onChange({ ...slot, affix, chosenValues: {} })
  }

  const tiers = useMemo(() =>
    !slot.isLegendary && slot.expression ? sortedTiers(tiersForModifier(graftPool, slot.expression)) : [],
    [graftPool, slot.expression, slot.isLegendary]
  )

  const sliderAffix = slot.affix
  const numericValues: LegendaryNumericValue[] = sliderAffix
    ? (sliderAffix as GraftAffix).numeric_values ?? (sliderAffix as LegendaryAffix).numeric_values ?? []
    : []
  const dp = Math.max(...numericValues.map(nv => rangeDecimals(nv)), 0)
  const step = dp > 0 ? parseFloat((1 / Math.pow(10, dp)).toFixed(dp)) : 1

  return (
    <div className="gear-craft-slot">
      <div className="gear-craft-slot-row">
        <VoraxModSelect
          graftPool={graftPool}
          legPool={legPool}
          value={slot.expression ?? ''}
          onChange={handleModifierChange}
          disabledExpressions={disabledExpressions}
        />
        {!slot.isLegendary && slot.expression && tiers.length > 1 && (
          <select
            className="gear-craft-select gear-craft-select--tier"
            value={(slot.affix as GraftAffix)?.raw_text ?? ''}
            onChange={e => handleTierChange(e.target.value)}
          >
            {tiers.map(a => (
              <option key={a.raw_text} value={a.raw_text}>Tier: {a.tier}</option>
            ))}
          </select>
        )}
      </div>
      {sliderAffix && numericValues.some(v => v.kind === 'range') && (
        <div className="gear-craft-sliders"
          onMouseMove={e => setSliderHoverPos({ x: e.clientX, y: e.clientY })}
          onMouseLeave={() => setSliderHoverPos(null)}
        >
          {numericValues.map((nv, valIdx) => {
            if (nv.kind !== 'range') return null
            const nvSign = nv.sign ?? ''
            const rawMin = nv.min ?? 0
            const rawMax = nv.max ?? 0
            const sMin = nvSign === '-' ? -rawMin : rawMin
            const sMax = nvSign === '-' ? -rawMax : rawMax
            const actualMin = Math.min(sMin, sMax)
            const actualMax = Math.max(sMin, sMax)
            const ticks = buildTicks(actualMin, actualMax, step)
            const listId = `${craftSlotId}-${valIdx}`
            const unsignedChosen = slot.chosenValues[valIdx] ?? midpoint(nv)
            const signedChosen = nvSign === '-' ? -unsignedChosen : unsignedChosen
            const display = dp > 0 ? signedChosen.toFixed(dp) : signedChosen
            return (
              <div key={valIdx} className="gear-slider-row">
                <input
                  type="range" className="gear-affix-slider"
                  list={ticks.length > 0 ? listId : undefined}
                  min={actualMin} max={actualMax} step={step} value={signedChosen}
                  onChange={e => {
                    const signed = Number(e.target.value)
                    onChange({ ...slot, chosenValues: { ...slot.chosenValues, [valIdx]: nvSign === '-' ? -signed : signed } })
                  }}
                />
                {ticks.length > 0 && (
                  <datalist id={listId}>
                    {ticks.map((t, ti) => <option key={ti} value={t} />)}
                  </datalist>
                )}
                <span className="gear-affix-value">{display}</span>
              </div>
            )
          })}
        </div>
      )}
      {sliderHoverPos && sliderAffix && createPortal(
        <div className="gear-slider-tooltip" style={{ left: sliderHoverPos.x + 16, top: Math.min(sliderHoverPos.y - 10, window.innerHeight - 80) }}>
          {slot.isLegendary
            ? reconstructAffixText(sliderAffix as LegendaryAffix, slot.chosenValues)
            : reconstructAffixText(craftAffixToLegendary(sliderAffix as GraftAffix), slot.chosenValues)
          }
        </div>,
        document.body
      )}
    </div>
  )
}

// ── Vorax Editor Panel ────────────────────────────────────────────────────────

interface VoraxEditorPanelProps {
  graft: Graft
  catalog: LegendaryGearItem[]
  catalogIndex: LegendaryGearIndexItem[]
  onAddToBuild: (item: EquippedGearItem) => void
  onClose: () => void
  onBack: () => void
  initialState?: VoraxInitialState | null
  onSaveBuildItem?: (item: EquippedGearItem) => void
}

function VoraxEditorPanel({ graft, catalog, catalogIndex, onAddToBuild, onClose, onBack, initialState, onSaveBuildItem }: VoraxEditorPanelProps) {
  const [baseSlots, setBaseSlots] = useState<[VoraxAffixSlot, VoraxAffixSlot]>(
    () => initialState?.baseSlots ?? [emptyVoraxSlot(), emptyVoraxSlot()]
  )
  const [prefixSlots, setPrefixSlots] = useState<[VoraxAffixSlot, VoraxAffixSlot, VoraxAffixSlot]>(
    () => initialState?.prefixSlots ?? [emptyVoraxSlot(), emptyVoraxSlot(), emptyVoraxSlot()]
  )
  const [suffixSlots, setSuffixSlots] = useState<[VoraxAffixSlot, VoraxAffixSlot, VoraxAffixSlot]>(
    () => initialState?.suffixSlots ?? [emptyVoraxSlot(), emptyVoraxSlot(), emptyVoraxSlot()]
  )
  const [legSourceName, setLegSourceName] = useState<string | null>(() => initialState?.legSourceName ?? null)
  const [legSourceItem, setLegSourceItem] = useState<LegendaryGearItem | null>(() => initialState?.legSourceItem ?? null)
  const [legSearch, setLegSearch] = useState('')
  const [legDropdownOpen, setLegDropdownOpen] = useState(false)
  const legDropdownRef = useRef<HTMLDivElement>(null)
  const legInputRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (!legDropdownOpen) { setLegSearch(''); return }
    setTimeout(() => legInputRef.current?.focus(), 0)
  }, [legDropdownOpen])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (legDropdownRef.current && !legDropdownRef.current.contains(e.target as Node)) setLegDropdownOpen(false)
    }
    if (legDropdownOpen) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [legDropdownOpen])

  const availableLegendaries = useMemo(() =>
    catalogIndex.filter(ci => graft.legendary_items.includes(ci.name)),
    [catalogIndex, graft.legendary_items]
  )

  const filteredLegendaries = useMemo(() => {
    if (!legSearch.trim()) return availableLegendaries
    const q = legSearch.toLowerCase()
    return availableLegendaries.filter(ci => ci.name.toLowerCase().includes(q))
  }, [availableLegendaries, legSearch])

  const legPool: LegendaryAffix[] = useMemo(() => {
    if (!legSourceItem) return []
    const variantKey = Object.keys(legSourceItem.variants)[0] ?? 'base'
    return legSourceItem.variants[variantKey]?.explicits ?? []
  }, [legSourceItem])

  const handleSelectLegendary = (indexItem: LegendaryGearIndexItem) => {
    const full = catalog.find(c => c.item_id === indexItem.item_id) ?? null
    setLegSourceName(indexItem.name)
    setLegSourceItem(full)
    setLegDropdownOpen(false)
    // Clear any legendary slots that were previously selected
    const clearLeg = (s: VoraxAffixSlot) => s.isLegendary ? emptyVoraxSlot() : s
    setPrefixSlots(prev => [clearLeg(prev[0]), clearLeg(prev[1]), clearLeg(prev[2])])
    setSuffixSlots(prev => [clearLeg(prev[0]), clearLeg(prev[1]), clearLeg(prev[2])])
  }

  const handleClearLegendary = () => {
    setLegSourceName(null)
    setLegSourceItem(null)
    const clearLeg = (s: VoraxAffixSlot) => s.isLegendary ? emptyVoraxSlot() : s
    setPrefixSlots(prev => [clearLeg(prev[0]), clearLeg(prev[1]), clearLeg(prev[2])])
    setSuffixSlots(prev => [clearLeg(prev[0]), clearLeg(prev[1]), clearLeg(prev[2])])
  }

  const allCraftSlots = [...prefixSlots, ...suffixSlots]
  const ultimateCount = allCraftSlots.filter(s => (s.affix as GraftAffix)?.affix_type === 'Ultimate Affix').length
  const advancedCount = allCraftSlots.filter(s => (s.affix as GraftAffix)?.affix_type === 'Advanced Affix').length
  const legendaryCount = allCraftSlots.filter(s => s.isLegendary).length
  const warnings: string[] = []
  if (ultimateCount > 2) warnings.push(`${ultimateCount}/2 Ultimate mods (max 2)`)
  if (advancedCount > 2) warnings.push(`${advancedCount}/2 Advanced mods (max 2)`)
  if (legendaryCount > 2) warnings.push(`${legendaryCount}/2 Legendary mods (max 2)`)

  const handleAddToBuild = () => {
    const customizations: CustomizedAffix[] = []

    const baseAffixes: LegendaryAffix[] = baseSlots
      .filter(s => s.affix)
      .map(s => ({ ...craftAffixToLegendary(s.affix as GraftAffix), affix_type: 'Base' }))

    const explicitAffixes: LegendaryAffix[] = [...prefixSlots, ...suffixSlots]
      .filter(s => s.affix)
      .map(s => s.isLegendary
        ? { ...(s.affix as LegendaryAffix), affix_type: 'Legendary' }
        : craftAffixToLegendary(s.affix as GraftAffix))

    const allSlots = [...baseSlots, ...prefixSlots, ...suffixSlots]
    const allAffixes = [...baseAffixes, ...explicitAffixes]
    const craftSlotPositions: number[] = allSlots.map((s, i) => s.affix ? i : -1).filter(i => i >= 0)
    let affixIdx = 0
    for (const s of allSlots) {
      if (!s.affix) continue
      if (Object.keys(s.chosenValues).length > 0) {
        customizations.push({ affix_index: affixIdx, chosen_values: s.chosenValues, chosen_placeholder_key: null })
      }
      affixIdx++
    }

    const item: EquippedGearItem = {
      item_id: graft.item_id,
      name: `${getVoraxDisplayName(graft)} (Vorax)`,
      required_level: 0,
      affixes: allAffixes,
      customizations,
      slot: (VORAX_GRAFT_SLOTS[graft.item_id]?.[0] ?? null) as GearSlot | null,
      base_type: undefined,
      is_crafted: true,
      is_vorax: true,
      implicit_count: baseAffixes.length,
      legendary_source: legSourceName,
      legendary_affix_count: legendaryCount,
      craft_slot_positions: craftSlotPositions,
    }
    if (onSaveBuildItem) {
      onSaveBuildItem(item)
    } else {
      onAddToBuild(item)
    }
    onClose()
  }

  const updateBase = (i: number, next: VoraxAffixSlot) =>
    setBaseSlots(prev => { const n = [...prev] as [VoraxAffixSlot, VoraxAffixSlot]; n[i] = next; return n })
  const updatePrefix = (i: number, next: VoraxAffixSlot) =>
    setPrefixSlots(prev => { const n = [...prev] as [VoraxAffixSlot, VoraxAffixSlot, VoraxAffixSlot]; n[i] = next; return n })
  const updateSuffix = (i: number, next: VoraxAffixSlot) =>
    setSuffixSlots(prev => { const n = [...prev] as [VoraxAffixSlot, VoraxAffixSlot, VoraxAffixSlot]; n[i] = next; return n })

  const basePool: GraftAffix[] = graft.base_affixes

  // Disabled expressions per slot — prevents selecting the same mod twice
  const baseDisabled = baseSlots.map((_, i) =>
    new Set(baseSlots.filter((s, j) => j !== i && s.expression).map(s => s.expression as string))
  )
  const allPrefixSuffix = [...prefixSlots, ...suffixSlots]
  const craftDisabled = allPrefixSuffix.map((_, i) =>
    new Set(allPrefixSuffix.filter((s, j) => j !== i && s.expression).map(s => s.expression as string))
  )

  const voraxPreviewName = `${getVoraxDisplayName(graft)} (Vorax)`
  const voraxPreviewLines = useMemo((): PreviewLine[] => {
    const baseLines: PreviewLine[] = baseSlots
      .filter(s => s.affix)
      .map(s => ({ text: reconstructAffixText(craftAffixToLegendary(s.affix as GraftAffix), s.chosenValues), label: affixTypeLabel((s.affix as GraftAffix).affix_type) }))
    const explicitLines: PreviewLine[] = [...prefixSlots, ...suffixSlots]
      .filter(s => s.affix)
      .map(s => s.isLegendary
        ? { text: reconstructAffixText(s.affix as LegendaryAffix, s.chosenValues), label: 'Legendary Affix' }
        : { text: reconstructAffixText(craftAffixToLegendary(s.affix as GraftAffix), s.chosenValues), label: affixTypeLabel((s.affix as GraftAffix).affix_type) })
    if (baseLines.length > 0 && explicitLines.length > 0) return [...baseLines, null, ...explicitLines]
    return [...baseLines, ...explicitLines]
  }, [baseSlots, prefixSlots, suffixSlots])

  return (
    <div className="gear-customize-panel">
      <div className="gear-craft-editing-header">
        <div className="gear-craft-editing-header-top">
          <span className="gear-craft-base-name">{getVoraxDisplayName(graft)} (Vorax)</span>
          <button className="gear-craft-reset-btn" onClick={onBack} title="Back to search">←</button>
        </div>
      </div>

      <div className="gear-craft-slots-scroll">
        {/* Legendary source selector */}
        <div className="vorax-leg-source-row" ref={legDropdownRef}>
          <span className="vorax-leg-source-label">Legendary Source</span>
          <div className="gear-craft-mod-select" style={{ flex: 1 }}>
            <div className={`gear-craft-mod-trigger${legDropdownOpen ? ' open' : ''}`} onClick={() => setLegDropdownOpen(o => !o)}>
              <span className={legSourceName ? 'gear-craft-mod-value vorax-affix-legendary' : 'gear-craft-mod-placeholder'}>
                {legSourceName || '— none —'}
              </span>
              {legSourceName && (
                <span
                  className="gear-craft-mod-clear"
                  onMouseDown={e => { e.stopPropagation(); handleClearLegendary(); setLegDropdownOpen(false) }}
                >×</span>
              )}
            </div>
            {legDropdownOpen && (
              <div className="gear-craft-mod-dropdown">
                <input
                  ref={legInputRef}
                  className="gear-craft-mod-search"
                  placeholder="Search legendary…"
                  value={legSearch}
                  onChange={e => setLegSearch(e.target.value)}
                  onMouseDown={e => e.stopPropagation()}
                />
                <div className="gear-craft-mod-list">
                  {filteredLegendaries.length === 0
                    ? <div className="gear-craft-mod-empty">No matches</div>
                    : filteredLegendaries.map(ci => (
                        <div
                          key={ci.item_id}
                          className={`gear-craft-mod-option${ci.name === legSourceName ? ' selected' : ''}`}
                          onMouseDown={() => handleSelectLegendary(ci)}
                        >{ci.name}</div>
                      ))
                  }
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Base affix slots (2) — separate pool, not counted in quality limits */}
        <div className="gear-craft-section-label">BASE AFFIXES</div>
        {baseSlots.map((slot, i) => (
          <VoraxCraftSlotRow
            key={`base-${i}`}
            graftPool={basePool}
            legPool={[]}
            slot={slot}
            onChange={next => updateBase(i, next)}
            disabledExpressions={baseDisabled[i]}
          />
        ))}

        {/* Prefix slots (3) */}
        <div className="gear-craft-section-label">PREFIXES</div>
        {prefixSlots.map((slot, i) => (
          <VoraxCraftSlotRow
            key={`prefix-${i}`}
            graftPool={graft.affixes}
            legPool={legPool}
            slot={slot}
            onChange={next => updatePrefix(i, next)}
            disabledExpressions={craftDisabled[i]}
          />
        ))}

        {/* Suffix slots (3) */}
        <div className="gear-craft-section-label">SUFFIXES</div>
        {suffixSlots.map((slot, i) => (
          <VoraxCraftSlotRow
            key={`suffix-${i}`}
            graftPool={graft.affixes}
            legPool={legPool}
            slot={slot}
            onChange={next => updateSuffix(i, next)}
            disabledExpressions={craftDisabled[i + 3]}
          />
        ))}
      </div>

      {warnings.length > 0 && (
        <div className="vorax-quality-warning">
          {warnings.map((w, i) => <div key={i}>{w}</div>)}
        </div>
      )}

      <ItemPreviewCard name={voraxPreviewName} lines={voraxPreviewLines} />
      <div className="gear-craft-actions">
        <button
          className="btn btn-sm btn-primary"
          onClick={handleAddToBuild}
          disabled={baseSlots.every(s => !s.affix) && prefixSlots.every(s => !s.affix) && suffixSlots.every(s => !s.affix)}
        >
          {onSaveBuildItem ? 'Save Changes' : 'Add to Build'}
        </button>
        <button className="btn btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}

// ── Base Item Selector (with hover tooltip) ────────────────────────────────────

interface BaseItemSelectProps {
  items: CraftBaseItem[]
  selected: CraftBaseItem | null
  onSelect: (bi: CraftBaseItem) => void
  getTooltipLines: (bi: CraftBaseItem) => string[]
}

function BaseItemSelect({ items, selected, onSelect, getTooltipLines }: BaseItemSelectProps) {
  const [open, setOpen] = useState(false)
  const [dropdownRect, setDropdownRect] = useState<DOMRect | null>(null)
  const [tooltipState, setTooltipState] = useState<{ item: CraftBaseItem; x: number; y: number } | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const MAX_DROPDOWN_H = 200

  useEffect(() => {
    if (!open) setTooltipState(null)
  }, [open])

  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      if (
        dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
        triggerRef.current && !triggerRef.current.contains(e.target as Node)
      ) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])

  const getDropdownStyle = (rect: DOMRect) => {
    const spaceBelow = window.innerHeight - rect.bottom
    const showAbove = spaceBelow < MAX_DROPDOWN_H + 4 && rect.top > MAX_DROPDOWN_H
    return {
      position: 'fixed' as const,
      left: rect.left,
      width: rect.width,
      maxHeight: MAX_DROPDOWN_H,
      ...(showAbove
        ? { bottom: window.innerHeight - rect.top + 2 }
        : { top: rect.bottom + 2 }),
    }
  }

  return (
    <div className="gear-base-item-select">
      <button
        ref={triggerRef}
        className="gear-base-item-trigger"
        onClick={() => {
          if (!open && triggerRef.current) setDropdownRect(triggerRef.current.getBoundingClientRect())
          setOpen(o => !o)
        }}
      >
        <span>{selected ? `${selected.name}` : '— select base —'}</span>
        {selected && <span className="gear-base-item-trigger-level">Lv. {selected.required_level}</span>}
        <span className="gear-base-item-trigger-arrow">{open ? '▴' : '▾'}</span>
      </button>
      {open && dropdownRect && createPortal(
        <div
          ref={dropdownRef}
          className="gear-base-item-dropdown"
          style={getDropdownStyle(dropdownRect)}
        >
          {items.map(bi => (
            <div
              key={bi.name}
              className={`gear-base-item-option${bi.name === selected?.name ? ' selected' : ''}`}
              onMouseDown={() => { onSelect(bi); setOpen(false) }}
              onMouseEnter={e => setTooltipState({ item: bi, x: e.clientX, y: e.clientY })}
              onMouseMove={e => setTooltipState(t => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
              onMouseLeave={() => setTooltipState(null)}
            >
              <span className="gear-base-item-name">{bi.name}</span>
              <span className="gear-base-item-level">Lv. {bi.required_level}</span>
            </div>
          ))}
        </div>,
        document.body
      )}
      {tooltipState && createPortal(
        <div
          className="gear-base-item-tooltip"
          style={{
            left: Math.min(tooltipState.x + 16, window.innerWidth - 300),
            top: Math.min(tooltipState.y - 10, window.innerHeight - 150),
          }}
        >
          <div className="gear-base-item-tooltip-name">{tooltipState.item.name}</div>
          <div className="gear-base-item-tooltip-level">Required Level: {tooltipState.item.required_level}</div>
          {getTooltipLines(tooltipState.item).map((line, i) => (
            <div key={i} className="gear-base-item-tooltip-stat">{line}</div>
          ))}
        </div>,
        document.body
      )}
    </div>
  )
}

// ── Craft Editor Panel ─────────────────────────────────────────────────────────

interface CraftEditorProps {
  craftBases: CraftBaseType[]
  craftBasesLoaded: boolean
  craftBasesFailed: boolean
  grafts: Graft[]
  onSelectVorax: (g: Graft) => void
  craftBaseItems: CraftBaseItemGroup[]
  baseType: CraftBaseType | null
  setBaseType: (bt: CraftBaseType | null) => void
  baseItem: CraftBaseItem | null
  setBaseItem: (bi: CraftBaseItem | null) => void
  slots: CraftSlotState[]
  setSlots: (slots: CraftSlotState[]) => void
  onAddToBuild: (item: EquippedGearItem) => void
  onClose: () => void
  craftSearch: string
  setCraftSearch: (s: string) => void
  baseItemImplicits: Record<string, string[]>
  previewName: string | null
  previewLines: PreviewLine[] | null
  onSaveBuildItem?: (item: EquippedGearItem) => void
}

function CraftEditorPanel({ craftBases, craftBasesLoaded, craftBasesFailed, craftBaseItems, grafts, onSelectVorax, baseType, setBaseType, baseItem, setBaseItem, slots, setSlots, onAddToBuild, onClose, craftSearch, setCraftSearch, baseItemImplicits, previewName, previewLines, onSaveBuildItem }: CraftEditorProps) {
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!baseType) setTimeout(() => searchRef.current?.focus(), 0)
  }, [baseType])

  // Use craftBaseItems (loaded on mount) for instant display; fall back to craftBases names if loaded
  const displayList = useMemo((): { item_id: string; name: string }[] =>
    craftBases.length > 0
      ? craftBases.map(bt => ({ item_id: bt.item_id, name: bt.name }))
      : craftBaseItems.map(bt => ({ item_id: bt.item_id, name: bt.name })),
    [craftBases, craftBaseItems]
  )

  const filteredBases = craftSearch.trim()
    ? displayList.filter(b => b.name.toLowerCase().includes(craftSearch.toLowerCase()))
    : displayList

  const selectBase = (item_id: string) => {
    const bt = craftBases.find(b => b.item_id === item_id)
    if (!bt) return
    setBaseType(bt)
    const sorted = [...bt.base_items].sort((a, b) => b.required_level - a.required_level)
    setBaseItem(sorted[0] ?? null)
    setSlots(Array.from({ length: 8 }, emptyCraftSlot))
    setCraftSearch('')
  }

  const handleAddToBuild = () => {
    if (!baseType) return
    const filledAffixes = slots.map(s => s.affix).filter((a): a is CraftAffix => a !== null)
    const craftSlotPositions: number[] = slots.map((s, i) => s.affix ? i : -1).filter(i => i >= 0)
    const itemName = baseItem?.name ?? baseType.name
    const implicitTexts = baseItemImplicits[itemName] ?? []
    const implicitAffixes: LegendaryAffix[] = implicitTexts.map(text => ({
      raw_text: text,
      modifier_id: null,
      expression: text,
      condition: null,
      affix_kind: 'implicit' as const,
      numeric_values: [],
      affix_type: 'Implicit',
    }))
    const implicitCount = implicitAffixes.length
    const customizations: CustomizedAffix[] = []
    let affixIdx = implicitCount
    for (const s of slots) {
      if (!s.affix) continue
      if (Object.keys(s.chosenValues).length > 0) {
        customizations.push({ affix_index: affixIdx, chosen_values: s.chosenValues, chosen_placeholder_key: null })
      }
      affixIdx++
    }
    const builtItem: EquippedGearItem = {
      item_id: itemName.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''),
      name: `${itemName} (Crafted)`,
      required_level: baseItem?.required_level ?? 0,
      affixes: [...implicitAffixes, ...filledAffixes.map(craftAffixToLegendary)],
      customizations,
      slot: null,
      base_type: itemName,
      is_crafted: true,
      implicit_count: implicitCount,
      craft_slot_positions: craftSlotPositions,
    }
    if (onSaveBuildItem) {
      onSaveBuildItem(builtItem)
    } else {
      onAddToBuild(builtItem)
    }
    onClose()
  }

  const updateSlot = (i: number, next: CraftSlotState) =>
    setSlots(slots.map((s, idx) => idx === i ? next : s))

  // Disabled sets per slot — same group = [0,1] base, [2,3,4] prefix, [5,6,7] suffix
  const slotGroups = [[0, 1], [2, 3, 4], [5, 6, 7]]
  const craftSlotDisabled = useMemo(() =>
    slots.map((_, i) => {
      const group = slotGroups.find(g => g.includes(i)) ?? []
      return new Set(group.filter(j => j !== i && slots[j].expression).map(j => slots[j].expression as string))
    }),
    [slots]
  )

  const basePool = useMemo(() => baseType?.affixes.filter(a => a.affix_type === 'Base Affix') ?? [], [baseType])
  const prefixPool = useMemo(() => baseType?.affixes.filter(a => a.affix_type.includes('Pre-fix')) ?? [], [baseType])
  const suffixPool = useMemo(() => baseType?.affixes.filter(a => a.affix_type.includes('Suffix')) ?? [], [baseType])
  const pools = useMemo(() => [basePool, basePool, prefixPool, prefixPool, prefixPool, suffixPool, suffixPool, suffixPool], [basePool, prefixPool, suffixPool])
  const sortedBaseItems = useMemo(
    () => baseType ? [...baseType.base_items].sort((a, b) => b.required_level - a.required_level) : [],
    [baseType]
  )

  const filteredVorax = craftSearch.trim()
    ? grafts.filter(g => getVoraxDisplayName(g).toLowerCase().includes(craftSearch.toLowerCase()))
    : grafts

  if (!baseType) {
    return (
      <div className="gear-customize-panel">
        <div className="gear-slots-title">Craft Item</div>
        <div className="gear-search-bar" style={{ margin: '8px 10px 4px' }}>
          <input
            ref={searchRef}
            className="gear-search-input"
            type="text"
            placeholder="Search base type…"
            value={craftSearch}
            onChange={e => setCraftSearch(e.target.value)}
          />
          {craftSearch && <button className="gear-search-clear" onClick={() => setCraftSearch('')}>✕</button>}
        </div>
        <div className="gear-craft-results">
          {craftBasesFailed && (
            <div className="gear-empty" style={{ padding: '12px 10px', color: '#ff6b6b' }}>
              Couldn't load craft base types — restart to retry.
            </div>
          )}
          {!craftBasesFailed && filteredBases.map(bt => (
            <div
              key={bt.item_id}
              className={`gear-craft-result-row${!craftBasesLoaded ? ' gear-craft-result-row--loading' : ''}`}
              onClick={() => craftBasesLoaded && selectBase(bt.item_id)}
            >{bt.name}</div>
          ))}
          {filteredVorax.length > 0 && !craftSearch.trim() && (
            <div className="vorax-section-divider">── Vorax ──</div>
          )}
          {filteredVorax.map(g => (
            <div key={g.item_id} className="gear-craft-result-row" onClick={() => onSelectVorax(g)}>
              {getVoraxDisplayName(g)}
            </div>
          ))}
          {filteredBases.length === 0 && filteredVorax.length === 0 && (
            <div className="gear-empty" style={{ padding: '12px 10px' }}>No matches</div>
          )}
        </div>
        <div style={{ padding: '8px 10px' }}>
          <button className="btn btn-sm" onClick={onClose}>Cancel</button>
        </div>
      </div>
    )
  }

  const sectionLabels = ['BASE AFFIXES', '', 'PREFIXES', '', '', 'SUFFIXES', '', '']
  const classification = CRAFT_CLASSIFICATIONS[baseType.item_id]
  const weaponStats = CRAFT_WEAPON_STATS[baseType.item_id]
  const currentItemName = baseItem?.name ?? baseType.name
  const implicitTexts = baseItemImplicits[currentItemName] ?? []

  return (
    <div className="gear-customize-panel">
      <div className="gear-craft-editing-header">
        <div className="gear-craft-editing-header-top">
          {classification && <span className="gear-craft-classification">{classification}</span>}
          <span className="gear-craft-base-name">{baseType.name} (Crafted)</span>
          <button className="gear-craft-reset-btn" onClick={() => { setBaseType(null); setBaseItem(null); setSlots(Array.from({ length: 8 }, emptyCraftSlot)) }} title="Back to search">←</button>
        </div>
        {sortedBaseItems.length > 0 && (
          <BaseItemSelect
            items={sortedBaseItems}
            selected={baseItem}
            onSelect={setBaseItem}
            getTooltipLines={bi => {
              const implicits = baseItemImplicits[bi.name] ?? []
              if (implicits.length > 0) return implicits
              const ws = CRAFT_WEAPON_STATS[baseType.item_id]
              return ws ? [`${ws.crit} Critical Strike Rating`, `${ws.speed} Attack Speed`] : []
            }}
          />
        )}
        {baseItem && (
          <div className="gear-craft-base-stats">
            <span>Lv. {baseItem.required_level}</span>
            {implicitTexts.length > 0
              ? implicitTexts.map((text, i) => <span key={i} className="gear-craft-implicit">{text}</span>)
              : weaponStats
                ? <>
                    <span>{weaponStats.crit} Crit</span>
                    <span>{weaponStats.speed} APS</span>
                  </>
                : null
            }
          </div>
        )}
      </div>
      <div className="gear-craft-slots-scroll">
        {slots.map((slot, i) => (
          <React.Fragment key={i}>
            {sectionLabels[i] && <div className="gear-craft-section-label">{sectionLabels[i]}</div>}
            <CraftSlotRow pool={pools[i]} slot={slot} onChange={next => updateSlot(i, next)} disabledExpressions={craftSlotDisabled[i]} />
          </React.Fragment>
        ))}
      </div>
      <ItemPreviewCard name={previewName} lines={previewLines} />
      <div className="gear-craft-actions">
        <button className="btn btn-sm btn-primary" onClick={handleAddToBuild} disabled={slots.every(s => !s.affix)}>
          {onSaveBuildItem ? 'Save Changes' : 'Add to Build'}
        </button>
        <button className="btn btn-sm" onClick={onClose}>Cancel</button>
      </div>
    </div>
  )
}

// ── Item Preview Card ─────────────────────────────────────────────────────────

function ItemPreviewCard({ name, lines }: { name: string | null; lines: PreviewLine[] | null }) {
  if (!name || !lines) return null

  type Line = NonNullable<PreviewLine>
  const dividerIdx = lines.indexOf(null)
  const hasImplicitExplicitSplit = dividerIdx !== -1
  const implicitLines = hasImplicitExplicitSplit ? lines.slice(0, dividerIdx) as Line[] : []
  const explicitLines = hasImplicitExplicitSplit ? lines.slice(dividerIdx + 1).filter((l): l is Line => l !== null) : []
  const allLines = hasImplicitExplicitSplit ? null : lines.filter((l): l is Line => l !== null)

  const renderLine = (line: Line, key: string, implicit?: boolean) => (
    <div key={key} className={`gear-preview-affix${implicit ? ' gear-preview-affix--implicit' : ''}${line.corroded ? ' gear-preview-affix--corroded' : ''}`}>
      {line.text}
      {line.label && <span className="gear-affix-label">({line.label})</span>}
    </div>
  )

  return (
    <div className="gear-preview-card">
      <div className="gear-preview-name">{name}</div>
      <div className="gear-preview-divider" />
      {lines.length === 0 ? (
        <div className="gear-preview-empty">No modifiers selected</div>
      ) : hasImplicitExplicitSplit ? (
        <>
          {implicitLines.map((line, i) => renderLine(line, `imp-${i}`, true))}
          <div className="gear-preview-section-dashes" style={{ margin: '5px 0' }} />
          {explicitLines.map((line, i) => renderLine(line, `exp-${i}`))}
        </>
      ) : (
        allLines!.map((line, i) => renderLine(line, `${i}`))
      )}
    </div>
  )
}

// ── Main Screen ───────────────────────────────────────────────────────────────

interface Props {
  equippedItems: EquippedGearItem[]
  onGearChange: (items: EquippedGearItem[]) => void
  onBack: () => void
}

function getItemQualityClass(item: EquippedGearItem): string {
  if (!item.is_crafted) return 'quality-legendary'
  const n = item.affixes.length - (item.implicit_count ?? 0)
  if (n === 0) return 'quality-normal'
  if (n <= 2) return 'quality-magic'
  if (n <= 5) return 'quality-rare'
  return 'quality-unique'
}

export default function GearScreen({ equippedItems, onGearChange }: Props) {
  const legendaryIndex = useReferenceStore(s => s.legendaryIndex)
  const catalogRaw = useReferenceStore(s => s.legendaryCatalog)
  const craftBaseItemsRaw = useReferenceStore(s => s.craftBaseItems)
  const craftBasesRaw = useReferenceStore(s => s.craftBaseTypes)
  const graftsRaw = useReferenceStore(s => s.grafts)
  const referenceResolved = useReferenceStore(s => s.referenceResolved)
  const failedCatalogs = useReferenceStore(s => s.failedCatalogs)

  const catalogIndex = legendaryIndex ?? []
  const catalog = catalogRaw ?? []
  const craftBaseItems = craftBaseItemsRaw ?? []
  const craftBases = craftBasesRaw ?? []
  const grafts = graftsRaw ?? []
  const catalogLoaded = catalogRaw !== null
  const craftBasesLoaded = craftBasesRaw !== null
  const loading = !referenceResolved && legendaryIndex === null

  const [selectedGraft, setSelectedGraft] = useState<Graft | null>(null)
  const [search, setSearch] = useState('')
  const [selectedCatalogItem, setSelectedCatalogItem] = useState<LegendaryGearItem | null>(null)
  const [editingBuildIdx, setEditingBuildIdx] = useState<number | null>(null)
  const [customizations, setCustomizations] = useState<CustomizedAffix[]>([])
  const [corrosionType, setCorrosionType] = useState<'none' | 'desecration' | 'mutation'>('none')
  const [corrodedExplicitIndices, setCorrodedExplicitIndices] = useState<number[]>([])
  const [mutationAffixText, setMutationAffixText] = useState<string | null>(null)
  // Craft state
  const [craftOpen, setCraftOpen] = useState(false)
  const [craftBaseType, setCraftBaseType] = useState<CraftBaseType | null>(null)
  const [craftBaseItem, setCraftBaseItem] = useState<CraftBaseItem | null>(null)
  const [craftSlots, setCraftSlots] = useState<CraftSlotState[]>(Array.from({ length: 8 }, emptyCraftSlot))
  const [craftSearch, setCraftSearch] = useState('')
  const [voraxInitialState, setVoraxInitialState] = useState<VoraxInitialState | null>(null)
  const [slotDropdown, setSlotDropdown] = useState<{ slotId: GearSlot; rect: DOMRect } | null>(null)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverSlot, setDragOverSlot] = useState<GearSlot | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const resetCorrosion = () => {
    setCorrosionType('none')
    setCorrodedExplicitIndices([])
    setMutationAffixText(null)
  }

  const openCraft = () => {
    setCraftOpen(true)
    setCraftBaseType(null)
    setCraftBaseItem(null)
    setCraftSlots(Array.from({ length: 8 }, emptyCraftSlot))
    setCraftSearch('')
    setSelectedGraft(null)
    setSelectedCatalogItem(null)
    setEditingBuildIdx(null)
    setCustomizations([])
    resetCorrosion()
  }

  const closeCraft = () => {
    setCraftOpen(false)
    setCraftBaseType(null)
    setCraftBaseItem(null)
    setCraftSlots(Array.from({ length: 8 }, emptyCraftSlot))
    setCraftSearch('')
    setSelectedGraft(null)
    setVoraxInitialState(null)
    setEditingBuildIdx(null)
    resetCorrosion()
  }

  useEffect(() => {
    searchRef.current?.focus()
  }, [])

  const catalogMap = useMemo(() => new Map(catalog.map(item => [item.item_id, item])), [catalog])

  const q = search.trim().toLowerCase()
  const filtered = useMemo(() => {
    if (!q) return catalogIndex
    return catalogIndex.filter(item => {
      if (item.name.toLowerCase().includes(q)) return true
      const full = catalogMap.get(item.item_id)
      return full ? getItemAffixes(full).some(a => a.raw_text.toLowerCase().includes(q)) : false
    })
  }, [q, catalogIndex, catalogMap])

  const customizeItem: LegendaryGearItem | EquippedGearItem | null =
    editingBuildIdx !== null ? (equippedItems[editingBuildIdx] ?? null) : selectedCatalogItem

  const isEditing = editingBuildIdx !== null

  // The catalog LegendaryGearItem backing the currently-displayed CustomizePanel item
  const legendaryCatalogItem = useMemo((): LegendaryGearItem | null => {
    if (!customizeItem) return null
    if (isLegendaryGearItem(customizeItem)) return customizeItem
    return catalogMap.get(customizeItem.item_id) ?? null
  }, [customizeItem, catalogMap])

  // Mutation affix pool for the current legendary's slot (from craft base type corrosion_base)
  const corrosionBaseAffixes = useMemo((): Array<LegendaryAffix & { modifier_text: string }> => {
    if (!legendaryCatalogItem) return []
    const bt = craftBases.find(slot => slot.base_items.some(bi => bi.name === legendaryCatalogItem.base_type))
    return (bt?.corrosion_base_affixes ?? []) as Array<LegendaryAffix & { modifier_text: string }>
  }, [legendaryCatalogItem, craftBases])

  const handleCorrosionChange = (
    type: 'none' | 'desecration' | 'mutation',
    indices: number[],
    mutationText: string | null,
    updatedAffixes: LegendaryAffix[] | null
  ) => {
    setCorrosionType(type)
    setCorrodedExplicitIndices(indices)
    setMutationAffixText(mutationText)
    const mutationResolvedAffix = type === 'mutation' && mutationText
      ? (corrosionBaseAffixes.find(a => a.modifier_text === mutationText) ?? null)
      : null
    if (editingBuildIdx !== null) {
      const next = [...equippedItems]
      next[editingBuildIdx] = {
        ...next[editingBuildIdx],
        ...(updatedAffixes !== null ? { affixes: updatedAffixes } : {}),
        corrosion_type: type,
        corroded_explicit_indices: indices,
        mutation_affix_text: mutationText,
        mutation_resolved_affix: mutationResolvedAffix,
      }
      onGearChange(next)
    }
  }

  const handleSelectCatalogItem = (indexItem: LegendaryGearIndexItem) => {
    const full = catalogMap.get(indexItem.item_id)
    if (!full) return
    setSelectedCatalogItem(full)
    setEditingBuildIdx(null)
    setCustomizations([])
    setCraftOpen(false)
    setCraftBaseType(null)
    resetCorrosion()
  }

  const handleSelectBuildItem = (idx: number) => {
    const item = equippedItems[idx]
    if (item.is_crafted && !item.is_vorax) {
      const bt = craftBases.find(b => b.base_items.some(bi => bi.name === item.base_type))
      if (bt) {
        const bi = bt.base_items.find(bi => bi.name === item.base_type) ?? bt.base_items[0] ?? null
        setCraftBaseType(bt)
        setCraftBaseItem(bi)
        setCraftSlots(reconstructCraftSlots(item, bt))
        setCraftOpen(true)
        setEditingBuildIdx(idx)
        setSelectedCatalogItem(null)
        setCraftSearch('')
        return
      }
    }
    if (item.is_vorax) {
      const graft = grafts.find(g => g.item_id === item.item_id)
      if (graft) {
        const state = reconstructVoraxSlots(item, graft, catalog)
        setVoraxInitialState(state)
        setSelectedGraft(graft)
        setCraftOpen(true)
        setEditingBuildIdx(idx)
        setSelectedCatalogItem(null)
        return
      }
    }
    // Fallback: legendary or unresolvable crafted — open CustomizePanel
    setEditingBuildIdx(idx)
    setSelectedCatalogItem(null)
    setCustomizations(item.customizations)
    setCraftOpen(false)
    setCraftBaseType(null)
    setCorrosionType(item.corrosion_type ?? 'none')
    setCorrodedExplicitIndices(item.corroded_explicit_indices ?? [])
    setMutationAffixText(item.mutation_affix_text ?? null)
  }

  const handleRemoveBuildItem = (idx: number) => {
    const next = [...equippedItems]
    next.splice(idx, 1)
    onGearChange(next)
    if (editingBuildIdx === idx) {
      setEditingBuildIdx(null)
      setCustomizations([])
    } else if (editingBuildIdx !== null && editingBuildIdx > idx) {
      setEditingBuildIdx(editingBuildIdx - 1)
    }
  }

  const handleAddFromCatalog = () => {
    if (!selectedCatalogItem) return
    const baseAffixes = getItemAffixes(selectedCatalogItem)
    const implCount = getItemImplicits(selectedCatalogItem).length
    const affixes = [...baseAffixes]
    if (corrodedExplicitIndices.length > 0 && selectedCatalogItem.variants.corroded) {
      for (const idx of corrodedExplicitIndices) {
        const corroded = selectedCatalogItem.variants.corroded.explicits[idx]
        if (corroded) affixes[implCount + idx] = corroded
      }
    }
    const mutationResolvedAffix = corrosionType === 'mutation' && mutationAffixText
      ? (corrosionBaseAffixes.find(a => a.modifier_text === mutationAffixText) ?? null)
      : null
    const newItem: EquippedGearItem = {
      item_id: selectedCatalogItem.item_id,
      name: selectedCatalogItem.name,
      required_level: selectedCatalogItem.required_level,
      affixes,
      customizations,
      slot: null,
      base_type: selectedCatalogItem.base_type,
      corrosion_type: corrosionType,
      corroded_explicit_indices: corrodedExplicitIndices,
      mutation_affix_text: mutationAffixText,
      mutation_resolved_affix: mutationResolvedAffix,
    }
    onGearChange([...equippedItems, newItem])
    setSelectedCatalogItem(null)
    setCustomizations([])
    resetCorrosion()
  }

  const handleSaveBuildItem = () => {
    if (editingBuildIdx === null) return
    const next = [...equippedItems]
    next[editingBuildIdx] = { ...next[editingBuildIdx], customizations }
    onGearChange(next)
    setEditingBuildIdx(null)
    setCustomizations([])
    resetCorrosion()
  }

  const handleCancel = () => {
    setSelectedCatalogItem(null)
    setEditingBuildIdx(null)
    setCustomizations([])
    setVoraxInitialState(null)
    resetCorrosion()
  }

  const handleSlotAssign = (slot: GearSlot, buildItemIdx: number | null) => {
    let next = equippedItems.map((item, i) => {
      if (buildItemIdx !== null && i === buildItemIdx) {
        const current = getItemSlots(item)
        if (current.includes(slot)) return item
        const newSlots = [...current, slot]
        return { ...item, slot: (newSlots.length === 1 ? newSlots[0] : newSlots) as GearSlot | GearSlot[] }
      }
      if (itemHasSlot(item, slot)) {
        const newSlots = getItemSlots(item).filter(s => s !== slot)
        return { ...item, slot: (newSlots.length === 0 ? null : newSlots.length === 1 ? newSlots[0] : newSlots) as GearSlot | GearSlot[] | null }
      }
      return item
    })
    // When assigning a 2H weapon to weapon1, clear weapon2 from all other items
    if (slot === 'weapon1' && buildItemIdx !== null) {
      const assignedItem = next[buildItemIdx]
      if (isTwoHandedBaseType(assignedItem?.base_type ?? '', baseTypeToItemId)) {
        next = next.map((item, i) => {
          if (i === buildItemIdx) return item
          const slots = getItemSlots(item).filter(s => s !== 'weapon2')
          if (slots.length === getItemSlots(item).length) return item
          return { ...item, slot: (slots.length === 0 ? null : slots.length === 1 ? slots[0] : slots) as GearSlot | GearSlot[] | null }
        })
      }
    }
    onGearChange(next as EquippedGearItem[])
    setSlotDropdown(null)
  }

  const openSlotDropdown = (slotId: GearSlot, e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setSlotDropdown({ slotId, rect })
  }

  const getEquippedForSlot = (slotId: GearSlot): EquippedGearItem | null =>
    equippedItems.find(item => itemHasSlot(item, slotId)) ?? null

  const getEquippedIdxForSlot = (slotId: GearSlot): number =>
    equippedItems.findIndex(item => itemHasSlot(item, slotId))

  const showTooltip = (item: LegendaryGearItem | EquippedGearItem, e: React.MouseEvent) =>
    setTooltip({ item, x: e.clientX, y: e.clientY })

  const moveTooltip = (e: React.MouseEvent) =>
    setTooltip(t => t ? { ...t, x: e.clientX, y: e.clientY } : null)

  const hideTooltip = () => setTooltip(null)

  const craftBaseSlotMap = useMemo((): Record<string, GearSlot[]> => {
    const map: Record<string, GearSlot[]> = {}
    for (const bt of craftBaseItems) {
      const slots = ITEM_ID_TO_SLOTS[bt.item_id]
      if (slots) {
        for (const bi of bt.base_items) {
          if (bi.name) map[bi.name] = slots
        }
      }
    }
    return map
  }, [craftBaseItems])

  const baseTypeToItemId = useMemo((): Record<string, string> => {
    const map: Record<string, string> = {}
    for (const bt of craftBaseItems) {
      for (const bi of bt.base_items) {
        if (bi.name) map[bi.name] = bt.item_id
      }
    }
    return map
  }, [craftBaseItems])

  const weapon1Is2H = useMemo((): boolean => {
    const w1 = equippedItems.find(item => itemHasSlot(item, 'weapon1'))
    return isTwoHandedBaseType(w1?.base_type ?? '', baseTypeToItemId)
  }, [equippedItems, baseTypeToItemId])

  // Maps base item name → implicit raw texts (array). Sources in priority order:
  // 1. Crawler base_items.implicits (from _craft_base_items.json)
  // 2. Legendary catalog implicits (fallback for any base type with a matching legendary)
  // 3. Craft base armor field for STR items
  const baseItemImplicits = useMemo((): Record<string, string[]> => {
    const map: Record<string, string[]> = {}
    for (const bt of craftBaseItems) {
      for (const bi of bt.base_items) {
        if (bi.implicits && bi.implicits.length > 0) map[bi.name] = bi.implicits
      }
    }
    for (const item of catalog) {
      if (!item.base_type || map[item.base_type]) continue
      const implicits = getItemImplicits(item)
      if (implicits.length > 0) map[item.base_type] = implicits.map(a => a.raw_text)
    }
    for (const bt of craftBaseItems) {
      for (const bi of bt.base_items) {
        if (bi.armor && !map[bi.name]) {
          map[bi.name] = [bi.armor.replace(/(\d)([A-Za-z])/g, '$1 $2')]
        }
      }
    }
    return map
  }, [catalog, craftBaseItems])

  const dragValidSlots = useMemo((): GearSlot[] => {
    if (dragIdx === null) return []
    const item = equippedItems[dragIdx]
    if (item?.is_vorax) return VORAX_GRAFT_SLOTS[item.item_id] ?? []
    const bt = item?.base_type
    if (!bt) return SLOT_ORDER.map(s => s.id)
    const valid = getValidSlots(bt, craftBaseSlotMap)
    let slots = valid.length > 0 ? valid : SLOT_ORDER.map(s => s.id)
    // Block weapon2 when weapon1 has a 2H weapon (unless dragging that 2H weapon itself)
    if (weapon1Is2H) {
      const w1 = equippedItems.find(item => itemHasSlot(item, 'weapon1'))
      if (equippedItems[dragIdx] !== w1) {
        slots = slots.filter(s => s !== 'weapon2')
      }
    }
    return slots
  }, [dragIdx, equippedItems, craftBaseSlotMap, weapon1Is2H])

  const previewName = useMemo((): string | null => {
    if (craftOpen && craftBaseType) {
      const baseName = craftBaseItem?.name ?? craftBaseType.name
      return `${baseName} (Crafted)`
    }
    if (customizeItem) return customizeItem.name
    return null
  }, [craftOpen, craftBaseType, craftBaseItem, customizeItem])

  const previewLines = useMemo((): PreviewLine[] | null => {
    if (craftOpen && craftBaseType) {
      const itemName = craftBaseItem?.name ?? craftBaseType.name
      const implicitTexts = baseItemImplicits[itemName] ?? []
      const implicitLines: PreviewLine[] = implicitTexts.map(t => ({ text: t }))
      const craftLines: PreviewLine[] = craftSlots
        .filter(s => s.affix !== null)
        .map(s => ({ text: reconstructAffixText(craftAffixToLegendary(s.affix!), s.chosenValues), label: affixTypeLabel(s.affix!.affix_type) }))
      if (implicitLines.length > 0 && craftLines.length > 0) return [...implicitLines, null, ...craftLines]
      if (implicitLines.length > 0) return implicitLines
      return craftLines
    }
    if (customizeItem) {
      const mutationLine: PreviewLine = corrosionType === 'mutation' && mutationAffixText
        ? { text: mutationAffixText, corroded: true }
        : null
      if (isLegendaryGearItem(customizeItem)) {
        const implicits = getItemImplicits(customizeItem)
        const explicits = getItemExplicits(customizeItem)
        const corrodedVariant = legendaryCatalogItem?.variants?.corroded
        const implicitLines: PreviewLine[] = implicits.map((a, i) => ({ text: tooltipAffixText(a, i, customizations) }))
        const explicitLines: PreviewLine[] = explicits.map((a, i) => {
          const isCorroded = corrodedExplicitIndices.includes(i)
          const displayAffix = isCorroded && corrodedVariant?.explicits[i] ? corrodedVariant.explicits[i] : a
          return { text: tooltipAffixText(displayAffix, implicits.length + i, isCorroded ? undefined : customizations), corroded: isCorroded }
        })
        const allImplicits = mutationLine ? [mutationLine, ...implicitLines] : implicitLines
        if (allImplicits.length > 0 && explicitLines.length > 0) return [...allImplicits, null, ...explicitLines]
        return [...allImplicits, ...explicitLines]
      }
      const craftItem = customizeItem as EquippedGearItem
      const implicitCount = craftItem.implicit_count ?? 0
      const allAffixes = getItemAffixes(craftItem)
      const implicitLines = allAffixes.slice(0, implicitCount).map((affix, i) => ({
        text: tooltipAffixText(affix, i, customizations),
        label: affixTypeLabel(affix.affix_type),
      }))
      const explicitLines = allAffixes.slice(implicitCount).map((affix, i) => ({
        text: tooltipAffixText(affix, implicitCount + i, customizations),
        label: affixTypeLabel(affix.affix_type),
        corroded: corrodedExplicitIndices.includes(i),
      }))
      const allImplicits = mutationLine ? [mutationLine, ...implicitLines] : implicitLines
      if (allImplicits.length > 0 && explicitLines.length > 0) return [...allImplicits, null, ...explicitLines]
      return [...allImplicits, ...explicitLines]
    }
    return null
  }, [craftOpen, craftBaseType, craftBaseItem, craftSlots, customizeItem, customizations, baseItemImplicits, corrosionType, mutationAffixText, corrodedExplicitIndices, legendaryCatalogItem])

  const handleDragStart = (idx: number) => {
    setDragIdx(idx)
    setTooltip(null)
  }

  const handleDrop = (slotId: GearSlot) => {
    if (dragIdx !== null && dragValidSlots.includes(slotId)) {
      handleSlotAssign(slotId, dragIdx)
    }
    setDragIdx(null)
    setDragOverSlot(null)
  }

  return (
    <div className="screen gear-screen">
      <div className="gear-header">
        <h2 className="title-accent" style={{ fontSize: 20 }}>Gear</h2>
        <span className="gear-header-count">{catalogIndex.length} items</span>
      </div>

      <div className="gear-body">
        {/* Panel 1: Equipment Slots */}
        <div className="gear-slots-panel">
          <div className="gear-slots-title">Equipment</div>
          {SLOT_ORDER.map(slotDef => {
            const equipped = getEquippedForSlot(slotDef.id)
            const isDragging = dragIdx !== null
            const isValidTarget = !isDragging || dragValidSlots.includes(slotDef.id)
            const isDragOver = dragOverSlot === slotDef.id && isValidTarget
            const is2HBlocked = slotDef.id === 'weapon2' && weapon1Is2H
            return (
              <div
                key={slotDef.id}
                className={`gear-slot-row${equipped && !is2HBlocked ? ' gear-slot-occupied' : ''}${isDragOver ? ' gear-slot-drag-over' : ''}${isDragging && !isValidTarget ? ' gear-slot-invalid-target' : ''}${isDragging && isValidTarget ? ' gear-slot-valid-target' : ''}${is2HBlocked ? ' gear-slot-2h-blocked' : ''}`}
                onDragOver={e => { if (isValidTarget && !is2HBlocked) e.preventDefault(); setDragOverSlot(slotDef.id) }}
                onDragLeave={() => setDragOverSlot(null)}
                onDrop={() => !is2HBlocked && handleDrop(slotDef.id)}
              >
                <span className="gear-slot-name">{slotDef.label}</span>
                {is2HBlocked ? (
                  <span className="gear-slot-2h-label">2H</span>
                ) : equipped ? (
                  <button
                    className={`gear-slot-item-name ${getItemQualityClass(equipped)}`}
                    onClick={e => openSlotDropdown(slotDef.id, e)}
                    onMouseEnter={e => showTooltip(equipped, e)}
                    onMouseMove={moveTooltip}
                    onMouseLeave={hideTooltip}
                  >
                    {equipped.name}
                  </button>
                ) : (
                  <button className="gear-slot-empty" onClick={e => openSlotDropdown(slotDef.id, e)}>
                    Empty
                  </button>
                )}
              </div>
            )
          })}
        </div>

        {/* Panel 2: Items in Build */}
        <div className="gear-build-panel">
          <div className="gear-slots-title">Items in Build</div>
          {equippedItems.length === 0 && (
            <div className="gear-build-empty">No items added yet.</div>
          )}
          {equippedItems.map((item, i) => (
            <div
              key={i}
              className={`gear-build-item${editingBuildIdx === i ? ' gear-build-item--selected' : ''}${dragIdx === i ? ' gear-build-item--dragging' : ''}`}
              draggable
              onDragStart={() => handleDragStart(i)}
              onDragEnd={() => { setDragIdx(null); setDragOverSlot(null) }}
            >
              <button
                className="gear-build-item-name"
                onClick={() => handleSelectBuildItem(i)}
                onMouseEnter={e => showTooltip(item, e)}
                onMouseMove={moveTooltip}
                onMouseLeave={hideTooltip}
              >
                <span className={`gear-build-item-label ${getItemQualityClass(item)}`}>{item.name}</span>
                {getItemSlots(item).map(slotId => (
                  <span key={slotId} className="gear-build-item-slot">
                    {SLOT_ORDER.find(s => s.id === slotId)?.label}
                  </span>
                ))}
              </button>
              <button
                className="gear-slot-remove"
                onClick={() => handleRemoveBuildItem(i)}
                title="Remove"
              >×</button>
            </div>
          ))}
        </div>

        {/* Panel 3: Customize or Craft */}
        <div className="gear-editor-column">
          {craftOpen && selectedGraft ? (
            <VoraxEditorPanel
              graft={selectedGraft}
              catalog={catalog}
              catalogIndex={catalogIndex}
              onAddToBuild={item => onGearChange([...equippedItems, item])}
              onClose={closeCraft}
              onBack={() => { setSelectedGraft(null); setVoraxInitialState(null) }}
              initialState={voraxInitialState}
              onSaveBuildItem={editingBuildIdx !== null
                ? (item) => { const orig = equippedItems[editingBuildIdx]; onGearChange(equippedItems.map((g, i) => i === editingBuildIdx ? { ...item, slot: orig.slot } : g)); setEditingBuildIdx(null) }
                : undefined}
            />
          ) : craftOpen ? (
            <CraftEditorPanel
              craftBases={craftBases}
              craftBasesLoaded={craftBasesLoaded}
              craftBasesFailed={referenceResolved && failedCatalogs.has('craftBaseTypes')}
              craftBaseItems={craftBaseItems}
              grafts={grafts}
              onSelectVorax={g => { setSelectedGraft(g); setCraftBaseType(null) }}
              baseType={craftBaseType}
              setBaseType={setCraftBaseType}
              baseItem={craftBaseItem}
              setBaseItem={setCraftBaseItem}
              slots={craftSlots}
              setSlots={setCraftSlots}
              onAddToBuild={item => onGearChange([...equippedItems, item])}
              onClose={closeCraft}
              craftSearch={craftSearch}
              setCraftSearch={setCraftSearch}
              baseItemImplicits={baseItemImplicits}
              previewName={previewName}
              previewLines={previewLines}
              onSaveBuildItem={editingBuildIdx !== null
                ? (item) => { const orig = equippedItems[editingBuildIdx]; onGearChange(equippedItems.map((g, i) => i === editingBuildIdx ? { ...item, slot: orig.slot } : g)); setEditingBuildIdx(null) }
                : undefined}
            />
          ) : (
            <CustomizePanel
              item={customizeItem}
              customizations={customizations}
              isEditing={isEditing}
              onCustomizationChange={setCustomizations}
              onConfirm={isEditing ? handleSaveBuildItem : handleAddFromCatalog}
              onCancel={handleCancel}
              baseItemImplicits={baseItemImplicits}
              previewName={previewName}
              previewLines={previewLines}
              catalogItem={legendaryCatalogItem}
              corrosionBaseAffixes={corrosionBaseAffixes}
              corrosionType={corrosionType}
              corrodedExplicitIndices={corrodedExplicitIndices}
              mutationAffixText={mutationAffixText}
              onCorrosionChange={handleCorrosionChange}
            />
          )}
        </div>

        {/* Panel 4: Legendary Catalog */}
        <div className="gear-catalog">
          <div className="gear-catalog-header">
            <button
              className={`btn btn-sm btn-primary gear-craft-create-btn${craftOpen ? ' active' : ''}`}
              onClick={openCraft}
            >+ Create Item</button>
          </div>
          <div className="gear-search-bar">
            <input
              ref={searchRef}
              className="gear-search-input"
              type="text"
              placeholder="Search by name or affix…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button className="gear-search-clear" onClick={() => setSearch('')}>✕</button>
            )}
          </div>
          <div className="gear-catalog-list">
            {loading && <div className="gear-empty">Loading…</div>}
            {referenceResolved && legendaryIndex === null && (
              <div className="gear-empty" style={{ color: '#ff6b6b' }}>Couldn't load gear catalog — restart to retry.</div>
            )}
            {!loading && legendaryIndex !== null && filtered.length === 0 && <div className="gear-empty">No items found.</div>}
            {filtered.map(item => {
              const full = catalogMap.get(item.item_id)
              return (
                <div
                  key={item.item_id}
                  className={`gear-catalog-item${selectedCatalogItem?.item_id === item.item_id && editingBuildIdx === null && !craftOpen ? ' gear-catalog-item--selected' : ''}${!catalogLoaded ? ' gear-catalog-item--loading' : ''}`}
                  onClick={() => handleSelectCatalogItem(item)}
                  onMouseEnter={e => full && showTooltip(full, e)}
                  onMouseMove={moveTooltip}
                  onMouseLeave={hideTooltip}
                >
                  <span className="gear-catalog-item-name">{item.name}</span>
                  <span className="gear-catalog-item-level">Lv. {item.required_level}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {slotDropdown && (
        <SlotDropdownPortal
          slotId={slotDropdown.slotId}
          rect={slotDropdown.rect}
          equippedItems={equippedItems}
          currentIdx={getEquippedIdxForSlot(slotDropdown.slotId)}
          slotMap={craftBaseSlotMap}
          weapon1Is2H={weapon1Is2H}
          onSelect={handleSlotAssign}
          onClose={() => setSlotDropdown(null)}
        />
      )}
      {tooltip && <GearTooltip state={tooltip} />}
    </div>
  )
}
