import React, { useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  LegendaryGearItem, LegendaryGearIndexItem, LegendaryAffix, LegendaryNumericValue,
  LegendaryRandomAffixGroup,
  EquippedGearItem, CustomizedAffix, GearSlot, CraftBaseType, CraftAffix, CraftBaseItem, CraftBaseItemGroup,
  Graft, GraftAffix, BeltBlend, TowerSequenceEntry, api,
} from '../api/client'
import { FloatingPortal } from '@floating-ui/react'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { useDamageDeltaList, type DeltaRequest, type StateTransform, type DamageDelta, type LabeledDelta } from '../components/tooltip/useDamageDelta'
import { TooltipContributions } from '../components/tooltip/TooltipContributions'
import { legendaryToEquipped, makeCatalogItem } from '../utils/gearItem'
import { GearTooltipBody, type GearTooltipItem } from '../components/tooltip/bodies/GearTooltipBody'
import { ModifierBadge, useConsumedStatSet, useConsumableUniverse, useGearUnresolvedTexts, useTextModifierStatus, useTextModifierStatuses, gearModifierStatus } from '../components/ModifierBadge'
import {
  rangeDecimals, midpoint, hasRangeValues, reconstructAffixText,
  affixTypeLabel, tooltipAffixText, sharedRollGroups,
} from '../utils/affixText'
import { tierForValue, overallRange, signedRange, MAX_CORRODED } from '../utils/affixTiers'
import EditableRollValue from '../components/EditableRollValue'
import { useReferenceStore } from '../store/referenceStore'
import { useBuildStore } from '../store/buildStore'
import { useUiPrefs } from '../store/uiPrefsStore'
import { CoverageBadge } from '../components/CoverageBadge'
import { CoverageLegend } from '../components/CoverageLegend'
import LoadingState from '../components/LoadingState'
import { coverageRank, passesModeledOnly } from '../utils/coverage'

// A damage-delta request plus the band label it should display under.
interface GearSlotDelta { label: string; req: DeltaRequest }

// A cache signature that uniquely identifies the *priced* item within a build version. Crafted
// items derive item_id from the base name (see craft builder), so every "Hollow Rift Axe
// (Crafted)" shares one id — keying the delta cache on item_id alone collides between different
// rolls and shows a stale value. Include the full priced content for crafted items; legendary
// item_ids are already unique.
function gearSig(item: GearTooltipItem): string {
  if (isLegendaryGearItem(item)) return `L:${item.item_id}`
  return `C:${item.item_id}:${JSON.stringify(item.affixes)}:${JSON.stringify(item.customizations ?? [])}:${item.corrosion_type ?? ''}:${item.implicit_count ?? 0}`
}

// The state transform for equipping `equippedItem` into `slot`, keeping the weapon slots valid:
//   - a 2-handed weapon frees BOTH weapon slots (it can't coexist with an offhand)
//   - a one-hander frees its target slot AND drops any 2H weapon already equipped
//   - everything else just frees its single target slot
function equipTransform(
  equippedItem: EquippedGearItem, slot: GearSlot, incoming2H: boolean,
  baseTypeToItemId: Record<string, string>,
): StateTransform {
  return s => {
    let gear = s.gear
    if (incoming2H) {
      gear = gear.filter(i => !itemHasSlot(i, 'weapon1') && !itemHasSlot(i, 'weapon2'))
    } else if (slot === 'weapon1' || slot === 'weapon2') {
      gear = gear.filter(i => !itemHasSlot(i, slot) && !isTwoHandedBaseType(i.base_type ?? '', baseTypeToItemId))
    } else {
      gear = gear.filter(i => !itemHasSlot(i, slot))
    }
    return { ...s, gear: [...gear, equippedItem] }
  }
}

// Build the damage-delta request(s) for a hovered gear item. Returns one labeled band per
// comparison:
//   - equipped item → its contribution (remove it from its slot) → single "Damage" band
//   - catalog / unequipped 2H weapon → equip into Weapon 1, clearing both weapon slots → one band
//   - catalog / unequipped multi-slot item (rings, 1H weapons) → one swap band per candidate slot
//   - catalog / unequipped single-slot item → single "Damage" swap band
function buildGearRequests(
  item: GearTooltipItem, knownSlot?: GearSlot,
  slotMap?: Record<string, GearSlot[]>, baseTypeToItemId?: Record<string, string>,
): GearSlotDelta[] {
  // Equipped item → what you'd LOSE by unequipping it (step = build without it, base = current),
  // matching the talent-node convention: a negative/red band = the damage given up.
  const equippedSlots = !isLegendaryGearItem(item) ? getItemSlots(item) : []
  if (equippedSlots.length > 0) {
    const slot = knownSlot && equippedSlots.includes(knownSlot) ? knownSlot : equippedSlots[0]
    return [{ label: 'Damage', req: { key: `gear:rm:${slot}`, step: s => ({ ...s, gear: s.gear.filter(i => !itemHasSlot(i, slot)) }) } }]
  }

  const baseType = item.base_type ?? ''
  const b2i = baseTypeToItemId ?? {}
  const sig = gearSig(item)
  const slots = knownSlot ? [knownSlot] : getValidSlots(baseType, slotMap)
  if (slots.length === 0) return []

  // 2H weapon: one comparison; equipping frees both weapon slots.
  if (isTwoHandedBaseType(baseType, b2i)) {
    const equippedItem = isLegendaryGearItem(item) ? legendaryToEquipped(item, 'weapon1') : { ...item, slot: 'weapon1' as GearSlot }
    return [{ label: 'Weapons (2H)', req: { key: `gear:eq2h:${sig}`, step: equipTransform(equippedItem, 'weapon1', true, b2i) } }]
  }

  // One swap band per candidate slot. Multi-slot items name each slot; single-slot keep "Damage".
  return slots.map(slot => {
    const equippedItem = isLegendaryGearItem(item) ? legendaryToEquipped(item, slot) : { ...item, slot }
    const label = slots.length > 1 ? (SLOT_ORDER.find(s => s.id === slot)?.label ?? slot) : 'Damage'
    return { label, req: { key: `gear:eq:${sig}:${slot}`, step: equipTransform(equippedItem, slot, false, b2i) } }
  })
}

// Equipped/catalog gear hover tooltip routed through the shared floating-tooltip primitive
// (cursor-anchored). Render-prop hands triggerProps to the hovered element. The slot maps let
// catalog previews resolve a base type's slot(s) and 2H-ness for accurate swap comparisons.
function GearHoverTooltip({ item, slot, slotMap, baseTypeToItemId, children }: {
  item: GearTooltipItem
  slot?: GearSlot
  slotMap?: Record<string, GearSlot[]>
  baseTypeToItemId?: Record<string, string>
  children: (triggerProps: Record<string, unknown>) => React.ReactNode
}) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
  const reqs = buildGearRequests(item, slot, slotMap, baseTypeToItemId)
  const computed = useDamageDeltaList(tip.open ? reqs.map(r => r.req) : null, tip.open)
  const deltas = reqs.map((r, i) => ({ label: r.label, delta: computed[i] ?? ({ state: 'loading' } as DamageDelta) }))
  return (
    <>
      {children(tip.triggerProps)}
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--gear" {...tip.floatingProps}>
            <GearTooltipBody item={item} deltas={deltas} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// Wraps a customize-panel affix row, adding a cursor-anchored hover tooltip showing the
// resolved affix text while the row (with its value slider) is hovered. Hover-only,
// non-interactive — vanishes the moment the cursor leaves the row.
function AffixSliderTooltip({ text, children }: { text: string | null; children: React.ReactElement }) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
  if (!text) return children
  return (
    <>
      {React.cloneElement(children, tip.triggerProps)}
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--slider" {...tip.floatingProps}>{text}</div>
        </FloatingPortal>
      )}
    </>
  )
}

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

function getItemAffixes(item: LegendaryGearItem | EquippedGearItem): LegendaryAffix[] {
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

function getRangeIndices(affix: LegendaryAffix): number[] {
  return affix.numeric_values
    .map((v, i) => (v.kind === 'range' ? i : -1))
    .filter(i => i >= 0)
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

// Second action row (Rename / Duplicate / Remove from Build) shown while editing an existing
// build item — all item actions live in the editor, keeping the Items-in-Build rows clean.
interface EditActions {
  // Keys EditActionRows so its local rename state resets when a different item opens.
  itemKey: number
  displayName: string
  onRename: (next: string) => void
  onDuplicate: () => void
  onRemove: () => void
}

// Rename swaps the row into an inline input; committing sets the item's DISPLAY name only —
// the true item name stays visible in the editor header, preview, and tooltips.
function EditActionRows({ actions }: { actions: EditActions }) {
  const [renaming, setRenaming] = useState(false)
  const [draft, setDraft] = useState('')
  if (renaming) {
    const commit = () => { actions.onRename(draft); setRenaming(false) }
    return (
      <div className="gear-actions-row">
        <input
          className="gear-build-rename-input"
          value={draft}
          autoFocus
          placeholder="Display name…"
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => {
            if (e.key === 'Enter') commit()
            if (e.key === 'Escape') setRenaming(false)
          }}
        />
      </div>
    )
  }
  return (
    <div className="gear-actions-row">
      <button className="btn btn-sm gear-rename-btn" onClick={() => { setDraft(actions.displayName); setRenaming(true) }}>✎ Rename</button>
      <button className="btn btn-sm gear-dup-btn" onClick={actions.onDuplicate}>⧉ Duplicate</button>
      <button className="btn btn-sm gear-remove-btn" onClick={actions.onRemove}>Remove</button>
    </div>
  )
}

interface CustomizePanelProps {
  item: LegendaryGearItem | EquippedGearItem | null
  customizations: CustomizedAffix[]
  isEditing: boolean
  editActions?: EditActions
  onCustomizationChange: (customizations: CustomizedAffix[]) => void
  onConfirm: () => void
  onCancel: () => void
  baseItemImplicits: Record<string, string[]>
  previewName: string | null
  previewLines: PreviewLine[] | null
  previewDeltas?: LabeledDelta[]
  catalogItem: LegendaryGearItem | null
  corrosionBaseAffixes: Array<LegendaryAffix & { modifier_text: string }>
  corrosionType: 'none' | 'desecration' | 'mutation'
  corrodedExplicitIndices: number[]
  mutationAffixText: string | null
  selectedRandomAffixes: Record<number, string>
  onCorrosionChange: (
    type: 'none' | 'desecration' | 'mutation',
    indices: number[],
    mutationText: string | null,
    updatedAffixes: LegendaryAffix[] | null,
    clearRandomAffixIndices?: number[]
  ) => void
  onRandomAffixChange: (explicitIndex: number, modifierId: string, updatedAffixes: LegendaryAffix[]) => void
  isBelt: boolean
  beltBlends: BeltBlend[]
  beltBlend: string | null
  onBeltBlendChange: (talentId: string | null) => void
}

// Belt-blend equip (roadmap #4) — rendered as a slot row directly under Corrosion in whichever editor
// (Customize / Craft / Vorax) is open, gated on the edited item being a belt. Per-item value, not global.
const beltBlendLabel = (b: BeltBlend) => b.talent_name || b.effect_text || b.effect_raw || b.talent_id

// Searchable belt-blend picker styled like the affix modifier box (reuses the gear-craft-mod-* UI), with
// a per-blend engine badge so you can see what's modeled before equipping it.
function BeltBlendSearchSelect({ beltBlends, beltBlend, onChange }: {
  beltBlends: BeltBlend[]
  beltBlend: string | null
  onChange: (id: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const MAX_DROPDOWN_H = 260

  const statuses = useTextModifierStatuses(beltBlends.map(b => ({ text: b.effect_text || b.effect_raw, source: 'talent' as const })))
  const statusById: Record<string, ReturnType<typeof useTextModifierStatus>> = {}
  beltBlends.forEach((b, i) => { statusById[b.talent_id] = statuses[i] })
  const selected = beltBlends.find(b => b.talent_id === beltBlend) ?? null

  useEffect(() => {
    if (!open) { setQuery(''); setTriggerRect(null); return }
    if (containerRef.current) setTriggerRect(containerRef.current.getBoundingClientRect())
    setTimeout(() => inputRef.current?.focus(), 0)
  }, [open])
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
          containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const q = query.trim().toLowerCase()
  const filtered = q
    ? beltBlends.filter(b => beltBlendLabel(b).toLowerCase().includes(q) || (b.talent_type || '').toLowerCase().includes(q))
    : beltBlends

  const dropdownStyle = triggerRect ? (() => {
    const spaceBelow = window.innerHeight - triggerRect.bottom
    const showAbove = spaceBelow < MAX_DROPDOWN_H + 4 && triggerRect.top > MAX_DROPDOWN_H
    return {
      position: 'fixed' as const, left: triggerRect.left, width: triggerRect.width, maxHeight: MAX_DROPDOWN_H,
      ...(showAbove ? { bottom: window.innerHeight - triggerRect.top + 2 } : { top: triggerRect.bottom + 2 }),
    }
  })() : {}

  return (
    <div ref={containerRef} className="gear-craft-mod-select" style={{ flex: 1 }}>
      <div className={`gear-craft-mod-trigger${open ? ' open' : ''}`} onClick={() => setOpen(o => !o)}>
        <span className={selected ? 'gear-craft-mod-value' : 'gear-craft-mod-placeholder'}>
          {selected ? beltBlendLabel(selected) : '— none —'}
          {selected && <ModifierBadge status={statusById[selected.talent_id] ?? null} />}
        </span>
        {selected && (
          <span className="gear-craft-mod-clear" onMouseDown={e => { e.stopPropagation(); onChange(null); setOpen(false) }}>×</span>
        )}
      </div>
      {open && triggerRect && createPortal(
        <div ref={dropdownRef} className="gear-craft-mod-dropdown" style={dropdownStyle}>
          <input ref={inputRef} className="gear-craft-mod-search" placeholder="Search blends…" value={query}
            onChange={e => setQuery(e.target.value)} onMouseDown={e => e.stopPropagation()} />
          <div className="gear-craft-mod-list">
            {filtered.length === 0
              ? <div className="gear-craft-mod-empty">No matches</div>
              : filtered.map(b => (
                  <div key={b.talent_id}
                    className={`gear-craft-mod-option${b.talent_id === beltBlend ? ' selected' : ''}`}
                    onMouseDown={() => { onChange(b.talent_id); setOpen(false) }}>
                    {beltBlendLabel(b)}{b.talent_type ? ` · ${b.talent_type}` : ''}
                    <ModifierBadge status={statusById[b.talent_id] ?? null} />
                  </div>
                ))}
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

function BeltBlendSelector({ beltBlends, beltBlend, onBeltBlendChange }: {
  beltBlends: BeltBlend[]
  beltBlend: string | null
  onBeltBlendChange: (talentId: string | null) => void
}) {
  const selected = beltBlends.find(b => b.talent_id === beltBlend) ?? null
  const effText = selected ? (selected.effect_text || selected.effect_raw) : ''
  // A belt blend is a talent effect — resolve its badge through the SAME unified text resolver every
  // other modifier uses, so it carries the full 4-state (Consumed / Inactive / Unconsumed / NYI).
  const badge = useTextModifierStatus(selected ? effText : null, 'talent')
  return (
    <div className="gear-corrosion-section">
      <div className="gear-corrosion-row gear-corrosion-row--stacked">
        <span className="gear-corrosion-label">Belt Blend</span>
        <BeltBlendSearchSelect beltBlends={beltBlends} beltBlend={beltBlend} onChange={onBeltBlendChange} />
      </div>
      {selected && (
        <div className="gear-affix-label">{effText}<ModifierBadge status={badge} /></div>
      )}
    </div>
  )
}

// Tower Sequence entries carry a trailing "<Intermediate|Advanced> Sequence <n|n|n>" suffix — the
// crafting minigame's bookkeeping, not part of the actual effect. Strip it for display AND for what
// gets stored/sent to the engine (a clean raw_text matches existing modifier-text patterns better);
// the sequence-number identity is meaningless once the affix is equipped. `group` drives the
// Intermediate/Advanced sectioning in the picker, mirroring how prefix/suffix pickers group by tier.
function parseTowerSequenceEntry(affix: string): { label: string; group: string } {
  const m = affix.match(/^(.*?)\s+(Intermediate|Advanced)\s+Sequence\s+[\d|]+\s*$/i)
  if (!m) return { label: affix.trim(), group: 'Other' }
  return { label: m[1].trim(), group: m[2][0].toUpperCase() + m[2].slice(1).toLowerCase() }
}

// Tower Sequence — crafted-only affix pick for weapon/shield bases. Options are grouped into
// Intermediate / Advanced sections, mirroring the Base/Prefix/Suffix affix picker's tier grouping.
// A width-capped portal dropdown (not a native <select>) — the native popup sizes to its widest
// option and overflows past the panel, which is exactly the clipping this replaces.
function TowerSequenceSelector({ entries, towerSequence, onTowerSequenceChange }: {
  entries: TowerSequenceEntry[]
  towerSequence: string | null
  onTowerSequenceChange: (affix: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const [triggerRect, setTriggerRect] = useState<DOMRect | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const MAX_DROPDOWN_H = 260

  useEffect(() => {
    if (!open) { setTriggerRect(null); return }
    if (containerRef.current) setTriggerRect(containerRef.current.getBoundingClientRect())
  }, [open])
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
          containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const parsed = useMemo(() => entries.map(e => parseTowerSequenceEntry(e.affix)), [entries])
  const groups = useMemo(() => {
    const byGroup: Record<string, Set<string>> = {}
    for (const p of parsed) {
      if (!byGroup[p.group]) byGroup[p.group] = new Set()
      byGroup[p.group].add(p.label)
    }
    return ['Intermediate', 'Advanced', 'Other']
      .filter(g => byGroup[g])
      .map(g => ({ group: g, labels: [...byGroup[g]] }))
  }, [parsed])

  const badge = useTextModifierStatus(towerSequence, 'gear')

  const dropdownStyle = triggerRect ? (() => {
    const spaceBelow = window.innerHeight - triggerRect.bottom
    const showAbove = spaceBelow < MAX_DROPDOWN_H + 4 && triggerRect.top > MAX_DROPDOWN_H
    return {
      position: 'fixed' as const, left: triggerRect.left, width: triggerRect.width, maxHeight: MAX_DROPDOWN_H,
      ...(showAbove ? { bottom: window.innerHeight - triggerRect.top + 2 } : { top: triggerRect.bottom + 2 }),
    }
  })() : {}

  return (
    <div className="gear-corrosion-section">
      <div className="gear-corrosion-row gear-corrosion-row--stacked">
        <span className="gear-corrosion-label">Tower Sequence</span>
        <div ref={containerRef} className="gear-craft-mod-select">
          <div className={`gear-craft-mod-trigger${open ? ' open' : ''}`} onClick={() => setOpen(o => !o)}>
            <span className={towerSequence ? 'gear-craft-mod-value' : 'gear-craft-mod-placeholder'}>
              {towerSequence || 'None'}
            </span>
            {towerSequence && (
              <span
                className="gear-craft-mod-clear"
                onMouseDown={e => { e.stopPropagation(); onTowerSequenceChange(null); setOpen(false) }}
              >×</span>
            )}
          </div>
          {open && triggerRect && createPortal(
            <div ref={dropdownRef} className="gear-craft-mod-dropdown" style={dropdownStyle}>
              <div className="gear-craft-mod-list">
                {groups.length === 0
                  ? <div className="gear-craft-mod-empty">No entries</div>
                  : groups.map(g => (
                      <React.Fragment key={g.group}>
                        <div className="gear-craft-mod-group">{g.group} Sequence</div>
                        {g.labels.map(label => (
                          <div
                            key={label}
                            className={`gear-craft-mod-option${label === towerSequence ? ' selected' : ''}`}
                            onMouseDown={() => { onTowerSequenceChange(label); setOpen(false) }}
                          >{label}</div>
                        ))}
                      </React.Fragment>
                    ))}
              </div>
            </div>,
            document.body
          )}
        </div>
      </div>
      {towerSequence && (
        <div className="gear-affix-label">{towerSequence}<ModifierBadge status={badge} /></div>
      )}
    </div>
  )
}

// Mutation corrosion's base-affix pool picker — searchable, width-capped portal dropdown, matching
// every other modifier picker in this screen (previously a plain native <select>, unsearchable and
// prone to the same native-popup overflow Tower Sequence had).
function MutationAffixSearchSelect({ corrosionBaseAffixes, mutationAffixText, onChange }: {
  corrosionBaseAffixes: Array<LegendaryAffix & { modifier_text: string }>
  mutationAffixText: string | null
  onChange: (text: string | null) => void
}) {
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
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
          containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const consumed = useConsumedStatSet()
  const universe = useConsumableUniverse()
  const unresolved = useGearUnresolvedTexts()
  const statusByText = useMemo(() => {
    const m: Record<string, ReturnType<typeof gearModifierStatus>> = {}
    for (const a of corrosionBaseAffixes) {
      if (!(a.modifier_text in m)) m[a.modifier_text] = gearModifierStatus(a, consumed, universe, unresolved)
    }
    return m
  }, [corrosionBaseAffixes, consumed, universe, unresolved])

  const q = query.trim().toLowerCase()
  const filtered = q ? corrosionBaseAffixes.filter(a => a.modifier_text.toLowerCase().includes(q)) : corrosionBaseAffixes

  const dropdownStyle = triggerRect ? (() => {
    const spaceBelow = window.innerHeight - triggerRect.bottom
    const showAbove = spaceBelow < MAX_DROPDOWN_H + 4 && triggerRect.top > MAX_DROPDOWN_H
    return {
      position: 'fixed' as const, left: triggerRect.left, width: triggerRect.width, maxHeight: MAX_DROPDOWN_H,
      ...(showAbove ? { bottom: window.innerHeight - triggerRect.top + 2 } : { top: triggerRect.bottom + 2 }),
    }
  })() : {}

  return (
    <div ref={containerRef} className="gear-craft-mod-select">
      <div className={`gear-craft-mod-trigger${open ? ' open' : ''}`} onClick={() => setOpen(o => !o)}>
        <span className={mutationAffixText ? 'gear-craft-mod-value' : 'gear-craft-mod-placeholder'}>
          {mutationAffixText || '— select mutation —'}
          {mutationAffixText && <ModifierBadge status={statusByText[mutationAffixText] ?? null} />}
        </span>
        {mutationAffixText && (
          <span className="gear-craft-mod-clear" onMouseDown={e => { e.stopPropagation(); onChange(null); setOpen(false) }}>×</span>
        )}
      </div>
      {open && triggerRect && createPortal(
        <div ref={dropdownRef} className="gear-craft-mod-dropdown" style={dropdownStyle}>
          <input
            ref={inputRef}
            className="gear-craft-mod-search"
            placeholder="Search mutations…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onMouseDown={e => e.stopPropagation()}
          />
          <div className="gear-craft-mod-list">
            {filtered.length === 0
              ? <div className="gear-craft-mod-empty">No matches</div>
              : filtered.map((a, i) => (
                  <div
                    key={i}
                    className={`gear-craft-mod-option${a.modifier_text === mutationAffixText ? ' selected' : ''}`}
                    onMouseDown={() => { onChange(a.modifier_text); setOpen(false) }}
                  >
                    {a.modifier_text}
                    <ModifierBadge status={statusByText[a.modifier_text] ?? null} />
                  </div>
                ))}
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

function CustomizePanel({ item, customizations, isEditing, editActions, onCustomizationChange, onConfirm, onCancel, baseItemImplicits, previewName, previewLines, previewDeltas, catalogItem, corrosionBaseAffixes, corrosionType, corrodedExplicitIndices, mutationAffixText, selectedRandomAffixes, onCorrosionChange, onRandomAffixChange, isBelt, beltBlends, beltBlend, onBeltBlendChange }: CustomizePanelProps) {
  const baseTip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
  const custPanelId = useId()
  const consumedStats = useConsumedStatSet() // for inert-modifier badges on affix rows
  const universe = useConsumableUniverse() // splits Inactive (modeled, not this skill) from Unconsumed
  const gearUnresolved = useGearUnresolvedTexts() // raw texts the backend still couldn't resolve

  if (!item) {
    return (
      <div className="gear-customize-panel gear-customize-empty">
        <span>Select an item to customize</span>
      </div>
    )
  }

  // Grouped write for shared-roll lines: fan the SAME unsigned magnitude across every index in the
  // group in ONE update. React batches state, so calling setChosenValue per index would let the 2nd
  // call read the 1st's stale state and clobber it — always write all group indices together.
  const setChosenValues = (affixIdx: number, indices: number[], val: number) => {
    const next = customizations.filter(c => c.affix_index !== affixIdx)
    const existing = customizations.find(c => c.affix_index === affixIdx)
    next.push({
      affix_index: affixIdx,
      chosen_values: { ...(existing?.chosen_values ?? {}), ...Object.fromEntries(indices.map(i => [i, val])) },
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
    const count = (item as EquippedGearItem).implicit_count
    if (count !== undefined) return count
    return catalogItem?.variants?.base?.implicits?.length ?? 0
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

    const isPlaceholderExplicit = catalogItem?.variants?.base?.explicits[explicitIndex]?.affix_kind === 'placeholder'
    onCorrosionChange('desecration', newIndices, null, updatedAffixes, isPlaceholderExplicit ? [explicitIndex] : undefined)
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

    const clearIndices = corrodedExplicitIndices.filter(idx =>
      catalogItem?.variants?.base?.explicits[idx]?.affix_kind === 'placeholder'
    )
    onCorrosionChange(newType, [], newType === 'mutation' ? mutationAffixText : null, updatedAffixes, clearIndices.length > 0 ? clearIndices : undefined)
  }

  // Click-to-edit an exact roll on a legendary explicit: pick the base vs corroded ("T0") variant whose range
  // holds the value (prefer corroded/desecrated when the corroded-slot budget allows), swap it in, KEEP the
  // custom value (unlike the toggle, which clears it), and update the corroded-index set.
  // `indices` is the shared-roll group driven by one control (representative = indices[0] = valIdx).
  // Grouped indices share an identical range/sign, so the tier/corrosion decision is computed ONCE off
  // the representative and the resulting unsigned magnitude is fanned across all group indices in ONE
  // state update (never per-index — React batching would let a 2nd write clobber the 1st).
  const handleLegendaryValueEdit = (affixIdx: number, explicitIndex: number | undefined, valIdx: number, signedValue: number, indices: number[] = [valIdx]) => {
    const baseVariant = catalogItem?.variants?.base
    const corrVariant = catalogItem?.variants?.corroded
    const curAffix = getItemAffixes(item)[affixIdx]
    // No corrosion context → just set the value on the current affix.
    if (explicitIndex === undefined || !baseVariant || !corrVariant) {
      const nv = curAffix?.numeric_values[valIdx]
      setChosenValues(affixIdx, indices, nv?.sign === '-' ? -signedValue : signedValue)
      return
    }
    const baseAff = baseVariant.explicits[explicitIndex]
    const corrAff = corrVariant.explicits[explicitIndex]
    // Random-affix placeholders have no base/corroded tier ranges — just set the value.
    if (baseAff?.affix_kind === 'placeholder' || corrAff?.affix_kind === 'placeholder') {
      const nv = curAffix?.numeric_values[valIdx]
      setChosenValues(affixIdx, indices, nv?.sign === '-' ? -signedValue : signedValue)
      return
    }
    const contains = (aff: LegendaryAffix | undefined) => {
      const nv = aff?.numeric_values[valIdx]
      if (!nv || nv.kind !== 'range') return false
      const [lo, hi] = signedRange(nv)
      return signedValue >= lo - 1e-6 && signedValue <= hi + 1e-6
    }
    const isCurr = corrodedExplicitIndices.includes(explicitIndex)
    const budgetOk = isCurr || corrodedExplicitIndices.length < MAX_CORRODED
    const useCorroded = (contains(corrAff) && budgetOk) ? true : contains(baseAff) ? false : (contains(corrAff) ? isCurr : isCurr)
    const target = useCorroded ? corrAff : baseAff
    if (!target) return

    const newIndices = useCorroded
      ? (isCurr ? corrodedExplicitIndices : [...corrodedExplicitIndices, explicitIndex])
      : corrodedExplicitIndices.filter(i => i !== explicitIndex)
    const currentAffixes = isLegendaryGearItem(item) ? getItemAffixes(item) : [...(item as EquippedGearItem).affixes]
    const updatedAffixes = [...currentAffixes]
    updatedAffixes[affixIdx] = target

    const tnv = target.numeric_values[valIdx]
    const unsigned = tnv?.sign === '-' ? -signedValue : signedValue
    const fan = Object.fromEntries(indices.map(i => [i, unsigned]))
    const variantChanged = useCorroded !== isCurr
    const existing = customizations.find(c => c.affix_index === affixIdx)
    const newChosen = variantChanged ? { ...fan } : { ...(existing?.chosen_values ?? {}), ...fan }
    const newCust = customizations.filter(c => c.affix_index !== affixIdx)
    newCust.push({ affix_index: affixIdx, chosen_values: newChosen, chosen_placeholder_key: existing?.chosen_placeholder_key ?? null })
    onCustomizationChange(newCust)
    onCorrosionChange(newIndices.length > 0 ? 'desecration' : corrosionType, newIndices, null, updatedAffixes, undefined)
  }

  const getRandomGroupForExplicit = (explicitIdx: number): LegendaryRandomAffixGroup | null => {
    if (!catalogItem) return null
    const currentExplicits = explicits
    const affix = currentExplicits[explicitIdx]
    if (!affix || affix.affix_kind !== 'placeholder') return null
    const baseExplicitsLen = catalogItem.variants.base?.explicits?.length ?? 0
    if (explicitIdx < baseExplicitsLen) {
      // Real explicit in variant — use variant-based group lookup so corroded explicits get corroded options
      const isCorroded = corrodedExplicitIndices.includes(explicitIdx)
      const variantKey = isCorroded && catalogItem.random_affixes['corroded'] ? 'corroded' : 'base'
      const variantGroups = catalogItem.random_affixes[variantKey] ?? []
      if (variantGroups.length === 0) return null
      const variantExplicits = isCorroded
        ? (catalogItem.variants.corroded?.explicits ?? catalogItem.variants.base?.explicits ?? [])
        : (catalogItem.variants.base?.explicits ?? [])
      const occurrence = variantExplicits.slice(0, explicitIdx).filter(e => e.affix_kind === 'placeholder').length
      return variantGroups[occurrence] ?? null
    }
    // Synthetic placeholder appended after real explicits — text-based lookup
    const ph = affix.raw_text
    const allGroups = Object.values(catalogItem.random_affixes).flat()
    const matchingGroups = allGroups.filter(g => g.placeholder === ph)
    const occurrence = currentExplicits.slice(0, explicitIdx).filter(e => e.raw_text === ph).length
    return matchingGroups[occurrence] ?? null
  }

  const handleSelectRandomAffix = (explicitIndex: number, modifierId: string) => {
    if (!catalogItem) return
    const group = getRandomGroupForExplicit(explicitIndex)
    if (!group) return
    const chosenOption = group.options.find(o => o.modifier_id === modifierId)
    if (!chosenOption) return
    const implCount = getImplicitCount()
    const affixArrayIndex = implCount + explicitIndex
    let currentAffixes: LegendaryAffix[]
    if (isLegendaryGearItem(item)) {
      currentAffixes = getItemAffixes(item)
    } else {
      currentAffixes = [...(item as EquippedGearItem).affixes]
    }
    const updatedAffixes = [...currentAffixes]
    updatedAffixes[affixArrayIndex] = chosenOption
    onCustomizationChange(customizations.filter(c => c.affix_index !== affixArrayIndex))
    onRandomAffixChange(explicitIndex, modifierId, updatedAffixes)
  }

  const renderAffixRow = (affix: LegendaryAffix, affixIdx: number, explicitIndex?: number) => {
    const isCorroded = explicitIndex !== undefined && corrodedExplicitIndices.includes(explicitIndex)
    const showToggle = corrosionType === 'desecration' && showCorrosion && explicitIndex !== undefined
      && catalogItem?.variants?.corroded?.explicits[explicitIndex] !== undefined
    const toggleDisabled = !isCorroded && corrodedExplicitIndices.length >= 2
    // Hover tooltip text for range affixes (shown while dragging the value slider).
    const hAffix = getItemAffixes(item)[affixIdx]
    const sliderText = hAffix && hasRangeValues(hAffix) ? tooltipAffixText(hAffix, affixIdx, customizations) : null

    if (affix.affix_kind === 'placeholder') {
      const randomGroup = explicitIndex !== undefined ? getRandomGroupForExplicit(explicitIndex) : null
      const chosenModId = explicitIndex !== undefined ? (selectedRandomAffixes[explicitIndex] ?? '') : ''
      const chosenOption = randomGroup?.options.find(o => o.modifier_id === chosenModId) ?? null
      const optRangeIndices = chosenOption ? getRangeIndices(chosenOption) : []
      const chosenMap = getChosenMap(affixIdx)
      return (
        <AffixSliderTooltip key={affixIdx} text={sliderText}>
        <div className={`gear-affix-row gear-affix-placeholder${isCorroded ? ' gear-affix-row--corroded' : ''}${optRangeIndices.length > 0 ? ' gear-affix-range-row' : ''}`}>
          <div className="gear-affix-label-line">
            {showToggle && (
              <button
                className={`gear-corrosion-toggle${isCorroded ? ' active' : ''}`}
                disabled={toggleDisabled}
                onClick={() => handleToggleCorroded(explicitIndex!)}
                title={isCorroded ? 'Remove desecration' : toggleDisabled ? 'Max 2 desecrated mods' : 'Desecrate this modifier'}
              />
            )}
            {randomGroup ? (
              <select
                className="gear-placeholder-select"
                value={chosenModId}
                onChange={e => explicitIndex !== undefined && handleSelectRandomAffix(explicitIndex, e.target.value)}
              >
                <option value="">— Select affix —</option>
                {randomGroup.options.map(opt => (
                  <option key={opt.modifier_id} value={opt.modifier_id ?? ''}>{opt.raw_text}</option>
                ))}
              </select>
            ) : (
              <>
                <div className="gear-affix-label gear-affix-label--dim">{affix.raw_text}</div>
                <select className="gear-placeholder-select" disabled>
                  <option>— Select affix —</option>
                </select>
              </>
            )}
          </div>
          {/* One control per shared-roll group: same-range numbers on this line are ONE in-game roll (rep = group[0]). */}
          {chosenOption && sharedRollGroups(chosenOption.numeric_values, chosenOption.raw_text)
            .filter(group => chosenOption!.numeric_values[group[0]]?.kind === 'range' && optRangeIndices.includes(group[0]))
            .map(group => {
            const valIdx = group[0]
            const nv = chosenOption!.numeric_values[valIdx]
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
            return (
              <div key={valIdx} className="gear-slider-row">
                <input
                  type="range" className="gear-affix-slider"
                  list={ticks.length > 0 ? listId : undefined}
                  min={actualMin} max={actualMax} step={step} value={signedChosen}
                  onChange={e => {
                    const signed = Number(e.target.value)
                    setChosenValues(affixIdx, group, nvSign === '-' ? -signed : signed)
                  }}
                />
                {ticks.length > 0 && (
                  <datalist id={listId}>{ticks.map((t, ti) => <option key={ti} value={t} />)}</datalist>
                )}
                <EditableRollValue
                  value={signedChosen} dp={dp} range={[actualMin, actualMax]}
                  onCommit={v => setChosenValues(affixIdx, group, nvSign === '-' ? -v : v)}
                />
              </div>
            )
          })}
        </div>
        </AffixSliderTooltip>
      )
    }
    if (!hasRangeValues(affix)) {
      return (
        <AffixSliderTooltip key={affixIdx} text={sliderText}>
        <div className={`gear-affix-row${isCorroded ? ' gear-affix-row--corroded' : ''}`}>
          <div className="gear-affix-label-line">
            {showToggle && (
              <button
                className={`gear-corrosion-toggle${isCorroded ? ' active' : ''}`}
                disabled={toggleDisabled}
                onClick={() => handleToggleCorroded(explicitIndex!)}
                title={isCorroded ? 'Remove desecration' : toggleDisabled ? 'Max 2 desecrated mods' : 'Desecrate this modifier'}
              />
            )}
            <div className="gear-affix-label">{affix.raw_text}<ModifierBadge status={gearModifierStatus(affix, consumedStats, universe, gearUnresolved)} /></div>
          </div>
        </div>
        </AffixSliderTooltip>
      )
    }
    const rangeIndices = getRangeIndices(affix)
    const chosenMap = getChosenMap(affixIdx)
    const displayText = reconstructAffixText(affix, {
      ...Object.fromEntries(rangeIndices.map(i => [i, midpoint(affix.numeric_values[i])])),
      ...chosenMap,
    })
    return (
      <AffixSliderTooltip key={affixIdx} text={sliderText}>
      <div className={`gear-affix-row gear-affix-range-row${isCorroded ? ' gear-affix-row--corroded' : ''}`}>
        <div className="gear-affix-label-line">
          {showToggle && (
            <button
              className={`gear-corrosion-toggle${isCorroded ? ' active' : ''}`}
              disabled={toggleDisabled}
              onClick={() => handleToggleCorroded(explicitIndex!)}
              title={isCorroded ? 'Remove desecration' : toggleDisabled ? 'Max 2 desecrated mods' : 'Desecrate this modifier'}
            />
          )}
          <div className="gear-affix-label">{displayText}<ModifierBadge status={gearModifierStatus(affix, consumedStats, universe, gearUnresolved)} /></div>
        </div>
        {/* One control per shared-roll group: same-range numbers on this line are ONE in-game roll (rep = group[0]). */}
        {sharedRollGroups(affix.numeric_values, affix.raw_text)
          .filter(group => affix.numeric_values[group[0]]?.kind === 'range' && rangeIndices.includes(group[0]))
          .map(group => {
          const valIdx = group[0]
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
                  setChosenValues(affixIdx, group, nvSign === '-' ? -signed : signed)
                }}
              />
              {ticks.length > 0 && (
                <datalist id={listId}>
                  {ticks.map((t, ti) => <option key={ti} value={t} />)}
                </datalist>
              )}
              <EditableRollValue
                value={signedChosen} dp={dp}
                range={overallRange(
                  (explicitIndex !== undefined && catalogItem?.variants
                    ? [catalogItem.variants.base?.explicits[explicitIndex], catalogItem.variants.corroded?.explicits[explicitIndex]].filter((a): a is LegendaryAffix => !!a)
                    : [affix]),
                  valIdx) ?? [actualMin, actualMax]}
                onCommit={v => handleLegendaryValueEdit(affixIdx, explicitIndex, valIdx, v, group)}
              />
            </div>
          )
        })}
      </div>
      </AffixSliderTooltip>
    )
  }

  return (
    <div className="gear-customize-panel gear-craft-mode">
      <div className="gear-customize-header">
        {typeLabel && <div className="gear-customize-type">{typeLabel}</div>}
        <div className="gear-customize-name">{item.name}<CoverageLegend /></div>
        {baseType && (() => {
          const baseStats = baseItemImplicits[baseType] ?? []
          const hasStats = baseStats.length > 0
          return (
            <div
              className={`gear-customize-base${hasStats ? ' gear-customize-base--hoverable' : ''}`}
              {...(hasStats ? baseTip.triggerProps : {})}
            >
              Base: {baseType}
            </div>
          )
        })()}
        <div className="gear-customize-level">Required Level: {item.required_level}</div>
      </div>
      {baseTip.open && (() => {
        const baseStats = baseItemImplicits[baseType] ?? []
        if (!baseStats.length) return null
        return (
          <FloatingPortal>
            <div className="tooltip tooltip--base-stat" {...baseTip.floatingProps}>
              <div className="gear-base-stat-tooltip-name">{baseType}</div>
              {baseStats.map((line, i) => (
                <div key={i} className="gear-base-stat-tooltip-stat">{line}</div>
              ))}
            </div>
          </FloatingPortal>
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
              <MutationAffixSearchSelect
                corrosionBaseAffixes={corrosionBaseAffixes}
                mutationAffixText={mutationAffixText}
                onChange={text => onCorrosionChange('mutation', [], text, null)}
              />
            ) : (
              <div className="gear-mutation-unavailable">
                Mutation data not available — re-import craft data from DevTools.
              </div>
            )
          )}
        </div>
      )}

      {isBelt && (
        <BeltBlendSelector beltBlends={beltBlends} beltBlend={beltBlend} onBeltBlendChange={onBeltBlendChange} />
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
          const implCount = craftItem.implicit_count ?? catalogItem?.variants?.base?.implicits?.length ?? 0
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
              {craftExplicits.map((affix, i) => {
                // Editing a build item shows its STORED affixes; swap in the corroded ("T0") variant for the
                // staged desecrated indices so toggling shows the corroded VALUE live (not just the checkbox).
                const shown = catalogItem?.variants?.corroded && corrodedExplicitIndices.includes(i)
                  ? (catalogItem.variants.corroded.explicits[i] ?? affix) : affix
                return renderAffixRow(shown, implCount + i, catalogItem ? i : undefined)
              })}
            </>
          )
        })()}
      </div>

      <ItemPreviewCard name={previewName} lines={previewLines} deltas={previewDeltas} />
      <div className="gear-customize-actions">
        <div className="gear-actions-row">
          <button className="btn btn-sm btn-primary gear-confirm-btn" onClick={onConfirm}>
            {isEditing ? 'Save' : 'Add to Build'}
          </button>
          <button className="btn btn-sm" onClick={onCancel}>Cancel</button>
        </div>
        {editActions && <EditActionRows key={editActions.itemKey} actions={editActions} />}
      </div>
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
  const mutationPool: CraftAffix[] = (baseType.corrosion_base_affixes ?? []).map((a): CraftAffix => ({
    raw_text: a.modifier_text,
    expression: a.expression,
    condition: a.condition,
    affix_kind: (a.affix_kind === 'numeric' || a.affix_kind === 'special') ? a.affix_kind : 'special',
    numeric_values: a.numeric_values,
    source: 'Mutation',
    affix_type: 'Mutation',
    tier: '0+',
    stat_key: a.stat_key,
    stat_keys: a.stat_keys,
    is_range_split: a.is_range_split,
    min_stat_keys: a.min_stat_keys,
    max_stat_keys: a.max_stat_keys,
    dual_stat_groups: a.dual_stat_groups,
    unit: a.unit,
  }))
  explicits.forEach((aff, i) => {
    const slotIdx = positions ? (positions[i] ?? i) : i
    if (slotIdx >= 8) return
    let poolAffix: CraftAffix | null = null
    if (slotIdx < 2 && aff.affix_type === 'Mutation') {
      poolAffix = mutationPool.find(pa => pa.raw_text === aff.raw_text) ?? null
    } else {
      poolAffix = baseType.affixes.find(pa => pa.raw_text === aff.raw_text) ?? null
    }
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
    tier: (a as { tier?: string | number }).tier,   // carry the roll tier so tooltips show "T2 …"
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
  // Per-expression engine badge (Consumed / Inactive / Unconsumed / NYI), classified synchronously from
  // the pool affix's local stat keys — so you can see what's modeled BEFORE adding the item to the build.
  const consumed = useConsumedStatSet()
  const universe = useConsumableUniverse()
  const unresolved = useGearUnresolvedTexts()
  const statusByExpr = useMemo(() => {
    const m: Record<string, ReturnType<typeof gearModifierStatus>> = {}
    for (const a of pool) {
      const key = normalizeExpression(a.expression)
      if (!(key in m)) m[key] = gearModifierStatus(a, consumed, universe, unresolved)
    }
    return m
  }, [pool, consumed, universe, unresolved])
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
          {value && <ModifierBadge status={statusByExpr[value] ?? null} />}
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
                    >{expr}<ModifierBadge status={statusByExpr[expr] ?? null} /></div>
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
                      >{expr}<ModifierBadge status={statusByExpr[expr] ?? null} /></div>
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
  corrupted?: boolean
  corrosionToggle?: { checked: boolean; disabled: boolean; onToggle: () => void }
  // All tiers (incl. the corroded "0+") for the slot's modifier + the value-edit commit handler. When set,
  // the roll number becomes click-to-edit: type a value → parent picks the matching tier + desecrates.
  editTiers?: CraftAffix[]
  // `indices` is the shared-roll group the edited value belongs to (indices[0] === valueIndex is the representative).
  onEditValue?: (valueIndex: number, signedValue: number, indices: number[]) => void
}

function CraftSlotRow({ pool, slot, onChange, disabledExpressions, corrupted, corrosionToggle, editTiers, onEditValue }: CraftSlotRowProps) {
  const sliderTip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
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

  // Shared-roll group: fan the same value across every index in one update (never per-index — batching clobbers).
  const handleSliderChange = (indices: number[], val: number) => {
    onChange({ ...slot, chosenValues: { ...slot.chosenValues, ...Object.fromEntries(indices.map(i => [i, val])) } })
  }

  return (
    <div className={`gear-craft-slot${corrupted ? ' gear-craft-slot--corroded' : ''}`}>
      <div className="gear-craft-slot-row">
        {corrosionToggle && (
          <button
            className={`gear-corrosion-toggle${corrosionToggle.checked ? ' active' : ''}`}
            onClick={corrosionToggle.onToggle}
            disabled={corrosionToggle.disabled}
            title={corrosionToggle.checked ? 'Remove T0+ corruption' : 'Upgrade to T0+ (Desecration)'}
          />
        )}
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
        <div className="gear-craft-sliders" {...sliderTip.triggerProps}>
          {/* One control per shared-roll group: same-range numbers on this line are ONE in-game roll (rep = group[0]). */}
          {sharedRollGroups(sliderAffix.numeric_values, sliderAffix.raw_text)
            .filter(group => sliderAffix.numeric_values[group[0]]?.kind === 'range')
            .map(group => {
            const valIdx = group[0]
            const nv = sliderAffix.numeric_values[valIdx]
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
                    handleSliderChange(group, nvSign === '-' ? -signed : signed)
                  }}
                />
                {ticks.length > 0 && (
                  <datalist id={listId}>
                    {ticks.map((t, ti) => <option key={ti} value={t} />)}
                  </datalist>
                )}
                {onEditValue && editTiers
                  ? <EditableRollValue
                      value={signedChosen} dp={dp}
                      range={overallRange(editTiers, valIdx) ?? [actualMin, actualMax]}
                      onCommit={v => onEditValue(valIdx, v, group)}
                    />
                  : <span className="gear-affix-value">{display}</span>}
              </div>
            )
          })}
        </div>
      )}
      {sliderTip.open && sliderAffix && (
        <FloatingPortal>
          <div className="tooltip tooltip--slider" {...sliderTip.floatingProps}>
            {reconstructAffixText(craftAffixToLegendary(sliderAffix), slot.chosenValues)}
          </div>
        </FloatingPortal>
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
  const sliderTip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
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

  // All tiers for clamping/tier-match (graft mods have tiers; a legendary-source affix is single-tier).
  const editTiers = !slot.isLegendary && slot.expression ? tiers : (slot.affix ? [slot.affix] : [])
  // Click-to-edit an exact roll: for graft mods, switch to the tier whose range holds the value (prefer the
  // better tier); for a legendary-source affix, just set the value. Vorax has no Desecration / corroded slots.
  // `indices` is the shared-roll group driven by one control (indices[0] === valIdx is the representative). The
  // tier decision is computed ONCE off the representative (grouped ranges are identical) and the unsigned value is
  // fanned across all group indices in ONE update (never per-index — React batching would clobber the 1st write).
  const handleEditValue = (valIdx: number, signedValue: number, indices: number[] = [valIdx]) => {
    if (!slot.affix) return
    if (!slot.isLegendary && slot.expression) {
      const matched = tierForValue(tiers, valIdx, signedValue)
      if (matched) {
        const mnv = matched.numeric_values[valIdx]
        const unsigned = mnv?.sign === '-' ? -signedValue : signedValue
        const fan = Object.fromEntries(indices.map(i => [i, unsigned]))
        const sameTier = matched.raw_text === (slot.affix as GraftAffix).raw_text
        onChange({ expression: slot.expression, affix: matched, isLegendary: false,
          chosenValues: sameTier ? { ...slot.chosenValues, ...fan } : { ...fan } })
        return
      }
    }
    const nv = numericValues[valIdx]
    const unsigned = nv?.sign === '-' ? -signedValue : signedValue
    onChange({ ...slot, chosenValues: { ...slot.chosenValues, ...Object.fromEntries(indices.map(i => [i, unsigned])) } })
  }

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
        <div className="gear-craft-sliders" {...sliderTip.triggerProps}>
          {/* One control per shared-roll group: same-range numbers on this line are ONE in-game roll (rep = group[0]). */}
          {sharedRollGroups(numericValues, sliderAffix?.raw_text ?? '')
            .filter(group => numericValues[group[0]]?.kind === 'range')
            .map(group => {
            const valIdx = group[0]
            const nv = numericValues[valIdx]
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
            return (
              <div key={valIdx} className="gear-slider-row">
                <input
                  type="range" className="gear-affix-slider"
                  list={ticks.length > 0 ? listId : undefined}
                  min={actualMin} max={actualMax} step={step} value={signedChosen}
                  onChange={e => {
                    const signed = Number(e.target.value)
                    const unsigned = nvSign === '-' ? -signed : signed
                    onChange({ ...slot, chosenValues: { ...slot.chosenValues, ...Object.fromEntries(group.map(i => [i, unsigned])) } })
                  }}
                />
                {ticks.length > 0 && (
                  <datalist id={listId}>
                    {ticks.map((t, ti) => <option key={ti} value={t} />)}
                  </datalist>
                )}
                <EditableRollValue
                  value={signedChosen} dp={dp}
                  range={overallRange(editTiers, valIdx) ?? [actualMin, actualMax]}
                  onCommit={v => handleEditValue(valIdx, v, group)}
                />
              </div>
            )
          })}
        </div>
      )}
      {sliderTip.open && sliderAffix && (
        <FloatingPortal>
          <div className="tooltip tooltip--slider" {...sliderTip.floatingProps}>
            {slot.isLegendary
              ? reconstructAffixText(sliderAffix as LegendaryAffix, slot.chosenValues)
              : reconstructAffixText(craftAffixToLegendary(sliderAffix as GraftAffix), slot.chosenValues)
            }
          </div>
        </FloatingPortal>
      )}
    </div>
  )
}

// ── Vorax Editor Panel ────────────────────────────────────────────────────────

interface VoraxEditorPanelProps {
  graft: Graft
  catalog: LegendaryGearItem[]
  catalogIndex: LegendaryGearIndexItem[]
  editActions?: EditActions
  onAddToBuild: (item: EquippedGearItem) => void
  onClose: () => void
  onBack: () => void
  initialState?: VoraxInitialState | null
  onSaveBuildItem?: (item: EquippedGearItem) => void
  isBelt: boolean
  beltBlends: BeltBlend[]
  beltBlend: string | null
  onBeltBlendChange: (talentId: string | null) => void
}

function VoraxEditorPanel({ graft, catalog, catalogIndex, editActions, onAddToBuild, onClose, onBack, initialState, onSaveBuildItem, isBelt, beltBlends, beltBlend, onBeltBlendChange }: VoraxEditorPanelProps) {
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

  // Build the EquippedGearItem from current vorax state (shared by confirm + live preview).
  const buildVoraxItem = (): EquippedGearItem => {
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

    return {
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
      // Stamped here (not just at commit) so the live preview/damage-delta reflects it immediately —
      // GearScreen's withBeltBlend re-stamps the same value at commit, which is a harmless no-op.
      beltBlend: isBelt ? beltBlend : undefined,
    }
  }

  const handleAddToBuild = () => {
    const item = buildVoraxItem()
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
    const beltBlendEntry = isBelt ? beltBlends.find(b => b.talent_id === beltBlend) : null
    const beltBlendLine: PreviewLine = beltBlendEntry
      ? { text: beltBlendEntry.effect_text || beltBlendEntry.effect_raw, label: 'Belt Blend' }
      : null
    const baseLines: PreviewLine[] = baseSlots
      .filter(s => s.affix)
      .map(s => ({ text: reconstructAffixText(craftAffixToLegendary(s.affix as GraftAffix), s.chosenValues), label: affixTypeLabel((s.affix as GraftAffix).affix_type) }))
    const explicitLines: PreviewLine[] = [...prefixSlots, ...suffixSlots]
      .filter(s => s.affix)
      .map(s => s.isLegendary
        ? { text: reconstructAffixText(s.affix as LegendaryAffix, s.chosenValues), label: 'Legendary Affix' }
        : { text: reconstructAffixText(craftAffixToLegendary(s.affix as GraftAffix), s.chosenValues), label: affixTypeLabel((s.affix as GraftAffix).affix_type) })
    // Belt Blend renders with the explicit affixes (default color), not prepended to baseLines (which
    // render blue, the "implicit/base stat" color) — it isn't a base stat.
    const allExplicit = beltBlendLine ? [beltBlendLine, ...explicitLines] : explicitLines
    if (baseLines.length > 0 && allExplicit.length > 0) return [...baseLines, null, ...allExplicit]
    return [...baseLines, ...allExplicit]
  }, [baseSlots, prefixSlots, suffixSlots, isBelt, beltBlend, beltBlends])

  // Live damage delta for the vorax item as currently configured. Pinned to the graft's slot.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const voraxPreviewItem = useMemo((): EquippedGearItem => buildVoraxItem(), [baseSlots, prefixSlots, suffixSlots, legSourceName, isBelt, beltBlend])
  const voraxPreviewDeltas = useGearPreviewDeltas(voraxPreviewItem, VORAX_GRAFT_SLOTS[graft.item_id]?.[0])

  return (
    <div className="gear-customize-panel gear-craft-mode">
      <div className="gear-craft-editing-header">
        <div className="gear-craft-editing-header-top">
          <span className="gear-craft-base-name">{getVoraxDisplayName(graft)} (Vorax)</span>
          <button className="gear-craft-reset-btn" onClick={onBack} title="Back to search">←</button>
        </div>
      </div>

      {isBelt && (
        <BeltBlendSelector beltBlends={beltBlends} beltBlend={beltBlend} onBeltBlendChange={onBeltBlendChange} />
      )}

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

      <ItemPreviewCard name={voraxPreviewName} lines={voraxPreviewLines} deltas={voraxPreviewDeltas} />
      <div className="gear-craft-actions">
        <div className="gear-actions-row">
          <button
            className="btn btn-sm btn-primary"
            onClick={handleAddToBuild}
            disabled={baseSlots.every(s => !s.affix) && prefixSlots.every(s => !s.affix) && suffixSlots.every(s => !s.affix)}
          >
            {onSaveBuildItem ? 'Save Changes' : 'Add to Build'}
          </button>
          <button className="btn btn-sm" onClick={onClose}>Cancel</button>
        </div>
        {editActions && <EditActionRows key={editActions.itemKey} actions={editActions} />}
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

// One base-item dropdown option + its hover tooltip via the shared primitive (cursor-anchored).
function BaseItemOption({ bi, selected, onSelect, lines }: {
  bi: CraftBaseItem; selected: boolean; onSelect: () => void; lines: string[]
}) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
  return (
    <>
      <div
        {...tip.triggerProps}
        className={`gear-base-item-option${selected ? ' selected' : ''}`}
        onMouseDown={onSelect}
      >
        <span className="gear-base-item-name">{bi.name}</span>
        <span className="gear-base-item-level">Lv. {bi.required_level}</span>
      </div>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--base-item" {...tip.floatingProps}>
            <div className="gear-base-item-tooltip-name">{bi.name}</div>
            <div className="gear-base-item-tooltip-level">Required Level: {bi.required_level}</div>
            {lines.map((line, i) => (
              <div key={i} className="gear-base-item-tooltip-stat">{line}</div>
            ))}
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

function BaseItemSelect({ items, selected, onSelect, getTooltipLines }: BaseItemSelectProps) {
  const [open, setOpen] = useState(false)
  const [dropdownRect, setDropdownRect] = useState<DOMRect | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const MAX_DROPDOWN_H = 200

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
            <BaseItemOption
              key={bi.name}
              bi={bi}
              selected={bi.name === selected?.name}
              onSelect={() => { onSelect(bi); setOpen(false) }}
              lines={getTooltipLines(bi)}
            />
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
  editActions?: EditActions
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
  previewDeltas?: LabeledDelta[]
  onSaveBuildItem?: (item: EquippedGearItem) => void
  corrosionType: 'none' | 'desecration' | 'mutation'
  onCorrosionTypeChange: (type: 'none' | 'desecration' | 'mutation') => void
  isBelt: boolean
  beltBlends: BeltBlend[]
  beltBlend: string | null
  onBeltBlendChange: (talentId: string | null) => void
  towerSequence: string | null
  onTowerSequenceChange: (affix: string | null) => void
  towerSequenceEntries: TowerSequenceEntry[]
}

function CraftEditorPanel({ craftBases, craftBasesLoaded, craftBasesFailed, craftBaseItems, grafts, editActions, onSelectVorax, baseType, setBaseType, baseItem, setBaseItem, slots, setSlots, onAddToBuild, onClose, craftSearch, setCraftSearch, baseItemImplicits, previewName, previewLines, previewDeltas, onSaveBuildItem, corrosionType, onCorrosionTypeChange, isBelt, beltBlends, beltBlend, onBeltBlendChange, towerSequence, onTowerSequenceChange, towerSequenceEntries }: CraftEditorProps) {
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
    const builtItem = makeCraftedItem(slots, baseType, baseItem, corrosionType, baseItemImplicits)
    if (!builtItem) return
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

  const mutationPool = useMemo((): CraftAffix[] =>
    (baseType?.corrosion_base_affixes ?? []).map((a): CraftAffix => ({
      raw_text: a.modifier_text,
      expression: a.expression,
      condition: a.condition,
      affix_kind: (a.affix_kind === 'numeric' || a.affix_kind === 'special') ? a.affix_kind : 'special',
      numeric_values: a.numeric_values,
      source: 'Mutation',
      affix_type: 'Mutation',
      tier: '0+',
      stat_key: a.stat_key,
      stat_keys: a.stat_keys,
      is_range_split: a.is_range_split,
      min_stat_keys: a.min_stat_keys,
      max_stat_keys: a.max_stat_keys,
      dual_stat_groups: a.dual_stat_groups,
      unit: a.unit,
    })),
    [baseType]
  )
  const basePool = useMemo(() => {
    if (corrosionType === 'mutation') return mutationPool
    return baseType?.affixes.filter(a => a.affix_type === 'Base Affix') ?? []
  }, [baseType, corrosionType, mutationPool])
  const pools = useMemo(() => {
    const allPre = baseType?.affixes.filter(a => a.affix_type.includes('Pre-fix')) ?? []
    const allSuf = baseType?.affixes.filter(a => a.affix_type.includes('Suffix')) ?? []
    return slots.map((slot, i) => {
      if (i < 2) return basePool
      const all = i < 5 ? allPre : allSuf
      if (corrosionType !== 'desecration') return all.filter(a => a.tier !== '0+')
      // In desecration: T0+ only visible in pool when this slot is already at T0+ (toggle controls upgrade)
      const isChecked = !!slot.affix && (slot.affix as CraftAffix).tier === '0+'
      return isChecked ? all : all.filter(a => a.tier !== '0+')
    })
  }, [slots, basePool, baseType, corrosionType])

  const slotHasT0Plus = useMemo(() =>
    slots.map((slot, i) => {
      if (!slot.expression || i < 2) return false
      const all = baseType?.affixes.filter(a => i < 5 ? a.affix_type.includes('Pre-fix') : a.affix_type.includes('Suffix')) ?? []
      return all.some(a => a.tier === '0+' && normalizeExpression(a.expression) === normalizeExpression(slot.expression!))
    }),
    [slots, baseType]
  )

  const corrodedSlotCount = slots.filter((s, i) => i >= 2 && !!s.affix && (s.affix as CraftAffix).tier === '0+').length

  const handleDesecrationToggle = (slotIdx: number) => {
    const s = slots[slotIdx]
    if (!s.affix) return
    const norm = normalizeExpression(s.expression ?? '')
    const all = baseType?.affixes.filter(a => slotIdx < 5 ? a.affix_type.includes('Pre-fix') : a.affix_type.includes('Suffix')) ?? []
    const isCurrCorroded = (s.affix as CraftAffix).tier === '0+'
    if (isCurrCorroded) {
      const candidates = all.filter(a => a.tier !== '0+' && normalizeExpression(a.expression) === norm)
      candidates.sort((a, b) => parseTierNum(a.tier) - parseTierNum(b.tier))
      const best = candidates[0]
      if (!best) return
      updateSlot(slotIdx, { expression: normalizeExpression(best.expression), affix: best, chosenValues: {} })
    } else {
      const corroded = all.find(a => a.tier === '0+' && normalizeExpression(a.expression) === norm)
      if (!corroded) return
      updateSlot(slotIdx, { expression: normalizeExpression(corroded.expression), affix: corroded, chosenValues: {} })
    }
  }

  // Click-to-edit an exact roll: pick the tier whose range holds the value (prefer the better tier), switch
  // to it, and enable Desecration so the corroded 0+ tier is usable (consuming a corroded slot, max 2).
  // `indices` is the shared-roll group driven by one control (indices[0] === valueIndex is the representative).
  // The tier/desecration decision is computed ONCE off the representative (grouped ranges are identical, so the
  // tier match is the same) and the resulting unsigned magnitude is fanned across all group indices in ONE update.
  const handleCraftValueEdit = (slotIdx: number, valueIndex: number, signedValue: number, indices: number[] = [valueIndex]) => {
    const s = slots[slotIdx]
    if (!s.affix || !s.expression) return
    // Base slots (0-1) have no tiers / desecration — just set the value in the current affix.
    if (slotIdx < 2) {
      const nv = s.affix.numeric_values[valueIndex]
      const unsigned = nv?.sign === '-' ? -signedValue : signedValue
      updateSlot(slotIdx, { ...s, chosenValues: { ...s.chosenValues, ...Object.fromEntries(indices.map(i => [i, unsigned])) } })
      return
    }
    const norm = normalizeExpression(s.expression)
    const section = baseType?.affixes.filter(a => slotIdx < 5 ? a.affix_type.includes('Pre-fix') : a.affix_type.includes('Suffix')) ?? []
    const tiers = section.filter(a => normalizeExpression(a.expression) === norm)
    if (corrosionType !== 'desecration') onCorrosionTypeChange('desecration')
    let matched = tierForValue(tiers, valueIndex, signedValue)
    // Corroded-slot budget: landing on 0+ when full (and not already 0+) → use the best non-0+ tier instead.
    if (matched?.tier === '0+' && (s.affix as CraftAffix).tier !== '0+' && corrodedSlotCount >= MAX_CORRODED) {
      matched = tierForValue(tiers.filter(a => a.tier !== '0+'), valueIndex, signedValue) ?? matched
    }
    if (!matched) return
    const mnv = matched.numeric_values[valueIndex]
    const unsigned = mnv?.sign === '-' ? -signedValue : signedValue
    const fan = Object.fromEntries(indices.map(i => [i, unsigned]))
    const sameTier = matched.raw_text === s.affix.raw_text
    const cv = sameTier ? { ...s.chosenValues, ...fan } : { ...fan }
    updateSlot(slotIdx, { expression: normalizeExpression(matched.expression), affix: matched, chosenValues: cv })
  }

  const handleCorrosionTypeChange = (newType: 'none' | 'desecration' | 'mutation') => {
    if (newType === corrosionType) return
    const allPrefixes = baseType?.affixes.filter(a => a.affix_type.includes('Pre-fix')) ?? []
    const allSuffixes = baseType?.affixes.filter(a => a.affix_type.includes('Suffix')) ?? []
    const nextSlots = slots.map((s, i) => {
      if (i < 2) {
        // Only clear base slots when mutation enters or exits (pool changes)
        if (newType === 'mutation' || corrosionType === 'mutation') return emptyCraftSlot()
        return s
      }
      if (!s.affix) return s
      const norm = normalizeExpression(s.expression ?? '')
      const pool = i < 5 ? allPrefixes : allSuffixes
      if (newType === 'desecration') {
        return s
      } else {
        // Leaving desecration: downgrade T0+ to best non-corroded tier
        if ((s.affix as CraftAffix).tier !== '0+') return s
        const candidates = pool.filter(a => a.tier !== '0+' && normalizeExpression(a.expression) === norm)
        candidates.sort((a, b) => parseTierNum(a.tier) - parseTierNum(b.tier))
        const best = candidates[0]
        if (!best) return emptyCraftSlot()
        return { expression: normalizeExpression(best.expression), affix: best, chosenValues: {} }
      }
    })
    setSlots(nextSlots)
    onCorrosionTypeChange(newType)
  }
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
  // Tower Sequence is crafted-only, and only for weapon/shield base types (CRAFT_CLASSIFICATIONS is
  // keyed by exactly those 22 item_ids — weapons + STR/DEX/INT shields, since shields occupy the weapon slot).
  const isCraftedWeaponBase = !!classification
  const towerSequenceOptions = isCraftedWeaponBase
    ? towerSequenceEntries.filter(e => e.source === baseType.name)
    : []

  const isCraftSlotCorrupted = (i: number, slot: CraftSlotState): boolean => {
    if (!slot.affix) return false
    if (i < 2 && corrosionType === 'mutation') return true
    return corrosionType === 'desecration' && (slot.affix as CraftAffix).tier === '0+'
  }

  return (
    <div className="gear-customize-panel gear-craft-mode">
      <div className="gear-craft-editing-header">
        <div className="gear-craft-editing-header-top">
          {classification && <span className="gear-craft-classification">{classification}</span>}
          <span className="gear-craft-base-name">{baseType.name} (Crafted)</span>
          <button
            className="gear-craft-reset-btn"
            onClick={() => {
              // Belt Blend / Tower Sequence are base-type-specific (a belt vs. a weapon/shield) — switching
              // base type without clearing them left a stale selection stamped onto the NEW item on Add to
              // Build (review-correctness finding).
              setBaseType(null); setBaseItem(null); setSlots(Array.from({ length: 8 }, emptyCraftSlot))
              onCorrosionTypeChange('none'); onBeltBlendChange(null); onTowerSequenceChange(null)
            }}
            title="Back to search"
          >←</button>
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
            {mutationPool.length > 0 ? (
              <option value="mutation">Mutation</option>
            ) : (
              <option value="mutation" disabled>Mutation (import craft data)</option>
            )}
          </select>
        </div>
      </div>
      {isBelt && (
        <BeltBlendSelector beltBlends={beltBlends} beltBlend={beltBlend} onBeltBlendChange={onBeltBlendChange} />
      )}
      {isCraftedWeaponBase && (
        <TowerSequenceSelector
          entries={towerSequenceOptions}
          towerSequence={towerSequence}
          onTowerSequenceChange={onTowerSequenceChange}
        />
      )}
      <div className="gear-craft-slots-scroll">
        {slots.map((slot, i) => {
          if (i === 1 && corrosionType === 'mutation') return null
          const showToggle = corrosionType === 'desecration' && i >= 2 && !!slot.affix
          const isChecked = showToggle && (slot.affix as CraftAffix).tier === '0+'
          const corrosionToggle = showToggle ? {
            checked: isChecked,
            disabled: !isChecked && (corrodedSlotCount >= MAX_CORRODED || !slotHasT0Plus[i]),
            onToggle: () => handleDesecrationToggle(i),
          } : undefined
          const editTiers: CraftAffix[] | undefined = slot.affix
            ? (i < 2
                ? [slot.affix]
                : (baseType.affixes.filter(a =>
                    (i < 5 ? a.affix_type.includes('Pre-fix') : a.affix_type.includes('Suffix'))
                    && normalizeExpression(a.expression) === normalizeExpression(slot.expression ?? ''))))
            : undefined
          return (
            <React.Fragment key={i}>
              {sectionLabels[i] && <div className="gear-craft-section-label">{sectionLabels[i]}</div>}
              <CraftSlotRow pool={pools[i]} slot={slot} onChange={next => updateSlot(i, next)} disabledExpressions={craftSlotDisabled[i]} corrupted={isCraftSlotCorrupted(i, slot)} corrosionToggle={corrosionToggle}
                editTiers={editTiers} onEditValue={(vi, v, indices) => handleCraftValueEdit(i, vi, v, indices)} />
            </React.Fragment>
          )
        })}
      </div>
      <ItemPreviewCard name={previewName} lines={previewLines} deltas={previewDeltas} />
      <div className="gear-craft-actions">
        <div className="gear-actions-row">
          {/* Allow white items: only a base is required, not any affix (0-stat bases are valid for testing). */}
          <button className="btn btn-sm btn-primary" onClick={handleAddToBuild} disabled={!baseType}>
            {onSaveBuildItem ? 'Save Changes' : 'Add to Build'}
          </button>
          <button className="btn btn-sm" onClick={onClose}>Cancel</button>
        </div>
        {editActions && <EditActionRows key={editActions.itemKey} actions={editActions} />}
      </div>
    </div>
  )
}

// ── Item builders (single source of truth, shared by confirm handlers and the live preview) ────

// Build the EquippedGearItem for a craft-panel state. Mirrors the saved item exactly so the live
// preview prices what will actually be added. Returns null until a base type is chosen.
function makeCraftedItem(
  slots: CraftSlotState[], baseType: CraftBaseType | null, baseItem: CraftBaseItem | null,
  corrosionType: 'none' | 'desecration' | 'mutation', baseItemImplicits: Record<string, string[]>,
): EquippedGearItem | null {
  if (!baseType) return null
  const filledAffixes = slots.map(s => s.affix).filter((a): a is CraftAffix => a !== null)
  const craftSlotPositions: number[] = slots.map((s, i) => s.affix ? i : -1).filter(i => i >= 0)
  const itemName = baseItem?.name ?? baseType.name
  const implicitTexts = baseItemImplicits[itemName] ?? []
  const implicitAffixes: LegendaryAffix[] = implicitTexts.map(text => ({
    raw_text: text, modifier_id: null, expression: text, condition: null,
    affix_kind: 'implicit' as const, numeric_values: [], affix_type: 'Implicit',
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
  return {
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
    corrosion_type: corrosionType !== 'none' ? corrosionType : undefined,
  }
}

// Build the EquippedGearItem for a legendary catalog item customized in the panel (corrosion,
// random affixes, slider rolls). Mirrors handleAddFromCatalog so the live preview matches.
// ── Item Preview Card ─────────────────────────────────────────────────────────

// Live damage-delta bands for the item currently being built/customized. Prices the in-progress
// item (with its current rolls) as an equip-preview into its slot(s), so the number updates as the
// player tweaks affixes. `previewItem` is the priced item (slot is ignored — always treated as a
// fresh equip); `knownSlot` pins it to a specific slot (a vorax graft slot or the slot an edited
// item already occupies), otherwise multi-slot items (rings, 1H weapons) show one band per slot.
function useGearPreviewDeltas(
  previewItem: EquippedGearItem | null, knownSlot?: GearSlot,
  slotMap?: Record<string, GearSlot[]>, baseTypeToItemId?: Record<string, string>,
): LabeledDelta[] {
  const reqs = useMemo(
    () => previewItem ? buildGearRequests({ ...previewItem, slot: null }, knownSlot, slotMap, baseTypeToItemId) : [],
    [previewItem, knownSlot, slotMap, baseTypeToItemId],
  )
  const computed = useDamageDeltaList(reqs.length ? reqs.map(r => r.req) : null, reqs.length > 0)
  return reqs.map((r, i) => ({ label: r.label, delta: computed[i] ?? ({ state: 'loading' } as DamageDelta) }))
}

function ItemPreviewCard({ name, lines, deltas }: { name: string | null; lines: PreviewLine[] | null; deltas?: LabeledDelta[] }) {
  type Line = NonNullable<PreviewLine>
  // Engine badge per preview line (resolved via the gear text resolver) so the assembled item shows
  // Consumed/Inactive/Unconsumed/NYI before it's added to the build. Hook runs unconditionally.
  const nonNull = (lines ?? []).filter((l): l is Line => l !== null)
  const statuses = useTextModifierStatuses(nonNull.map(l => ({ text: l.text, source: 'gear' as const })))
  const statusByText: Record<string, ReturnType<typeof useTextModifierStatus>> = {}
  nonNull.forEach((l, i) => { if (statusByText[l.text] === undefined) statusByText[l.text] = statuses[i] })

  if (!name || !lines) return null

  const dividerIdx = lines.indexOf(null)
  const hasImplicitExplicitSplit = dividerIdx !== -1
  const implicitLines = hasImplicitExplicitSplit ? lines.slice(0, dividerIdx) as Line[] : []
  const explicitLines = hasImplicitExplicitSplit ? lines.slice(dividerIdx + 1).filter((l): l is Line => l !== null) : []
  const allLines = hasImplicitExplicitSplit ? null : lines.filter((l): l is Line => l !== null)

  const renderLine = (line: Line, key: string, implicit?: boolean) => (
    <div key={key} className={`gear-preview-affix${implicit ? ' gear-preview-affix--implicit' : ''}${line.corroded ? ' gear-preview-affix--corroded' : ''}`}>
      {line.text}
      {line.label && <span className="gear-affix-label">({line.label})</span>}
      <ModifierBadge status={statusByText[line.text] ?? null} />
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
      {deltas && deltas.length > 0 && <TooltipContributions deltas={deltas} />}
    </div>
  )
}

// ── Main Screen ───────────────────────────────────────────────────────────────

interface Props {
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

export default function GearScreen(_props: Props) {
  const gear = useBuildStore(s => s.gear)
  const setGear = useBuildStore(s => s.setGear)
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
  const modeledOnly = useUiPrefs(s => s.modeledOnly)
  const toggleModeledOnly = useUiPrefs(s => s.toggleModeledOnly)
  const legendarySort = useUiPrefs(s => s.legendarySort)
  const setLegendarySort = useUiPrefs(s => s.setLegendarySort)
  const [selectedCatalogItem, setSelectedCatalogItem] = useState<LegendaryGearItem | null>(null)
  const [editingBuildIdx, setEditingBuildIdx] = useState<number | null>(null)
  const [customizations, setCustomizations] = useState<CustomizedAffix[]>([])
  const [corrosionType, setCorrosionType] = useState<'none' | 'desecration' | 'mutation'>('none')
  const [corrodedExplicitIndices, setCorrodedExplicitIndices] = useState<number[]>([])
  const [mutationAffixText, setMutationAffixText] = useState<string | null>(null)
  const [selectedRandomAffixes, setSelectedRandomAffixes] = useState<Record<number, string>>({})
  // Belt-blend state — the blend equipped on the belt being edited (one total), plus the catalog.
  const [beltBlend, setBeltBlend] = useState<string | null>(null)
  const [beltBlends, setBeltBlends] = useState<BeltBlend[]>([])
  // Tower Sequence state — the affix selected for the crafted weapon/shield base being edited, plus the catalog.
  const [towerSequence, setTowerSequence] = useState<string | null>(null)
  const [towerSequenceEntries, setTowerSequenceEntries] = useState<TowerSequenceEntry[]>([])
  // Craft state
  const [craftOpen, setCraftOpen] = useState(false)
  const [craftBaseType, setCraftBaseType] = useState<CraftBaseType | null>(null)
  const [craftBaseItem, setCraftBaseItem] = useState<CraftBaseItem | null>(null)
  const [craftSlots, setCraftSlots] = useState<CraftSlotState[]>(Array.from({ length: 8 }, emptyCraftSlot))
  const [craftSearch, setCraftSearch] = useState('')
  const [craftCorrosionType, setCraftCorrosionType] = useState<'none' | 'desecration' | 'mutation'>('none')
  const [voraxInitialState, setVoraxInitialState] = useState<VoraxInitialState | null>(null)
  const [slotDropdown, setSlotDropdown] = useState<{ slotId: GearSlot; rect: DOMRect } | null>(null)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverSlot, setDragOverSlot] = useState<GearSlot | null>(null)
  const [dragOverBuildIdx, setDragOverBuildIdx] = useState<number | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const resetCorrosion = () => {
    setCorrosionType('none')
    setCorrodedExplicitIndices([])
    setMutationAffixText(null)
    setSelectedRandomAffixes({})
    setBeltBlend(null)
    setTowerSequence(null)
  }

  const openCraft = () => {
    setCraftOpen(true)
    setCraftBaseType(null)
    setCraftBaseItem(null)
    setCraftSlots(Array.from({ length: 8 }, emptyCraftSlot))
    setCraftSearch('')
    setCraftCorrosionType('none')
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
    setCraftCorrosionType('none')
    setSelectedGraft(null)
    setVoraxInitialState(null)
    setEditingBuildIdx(null)
    resetCorrosion()
  }

  useEffect(() => {
    searchRef.current?.focus()
  }, [])

  // Belt blends are season-global; load once for the belt-blend selector in the customize panel.
  useEffect(() => {
    let cancelled = false
    api.getBeltBlends()
      .then(res => { if (!cancelled) setBeltBlends(res.blends ?? []) })
      .catch(() => { /* selector simply shows no blends if the catalog is unavailable */ })
    return () => { cancelled = true }
  }, [])

  // Tower Sequence entries are season-global; load once for the craft-flow weapon/shield selector.
  useEffect(() => {
    let cancelled = false
    api.getTowerSequence()
      .then(res => { if (!cancelled) setTowerSequenceEntries(res.entries ?? []) })
      .catch(() => { /* selector simply shows no options if the catalog is unavailable */ })
    return () => { cancelled = true }
  }, [])

  const catalogMap = useMemo(() => new Map(catalog.map(item => [item.item_id, item])), [catalog])

  const q = search.trim().toLowerCase()
  const filtered = useMemo(() => {
    const matched = !q ? catalogIndex : catalogIndex.filter(item => {
      if (item.name.toLowerCase().includes(q)) return true
      const full = catalogMap.get(item.item_id)
      return full ? getItemAffixes(full).some(a => a.raw_text.toLowerCase().includes(q)) : false
    })
    const visible = matched.filter(item => passesModeledOnly(item.coverage, modeledOnly))
    // 'alpha' preserves the catalog's existing (already name-ordered) default — only 'coverage' reorders.
    if (legendarySort === 'coverage') {
      return [...visible].sort((a, b) =>
        coverageRank(a.coverage) - coverageRank(b.coverage) || a.name.localeCompare(b.name))
    }
    return visible
  }, [q, catalogIndex, catalogMap, modeledOnly, legendarySort])

  const customizeItem: LegendaryGearItem | EquippedGearItem | null =
    editingBuildIdx !== null ? (gear[editingBuildIdx] ?? null) : selectedCatalogItem

  const isEditing = editingBuildIdx !== null

  // Whether the item currently being created/edited is a belt — drives the belt-blend selector. Covers
  // all three editors (Customize / Craft / Vorax) and both create + edit, so the selector shows for
  // crafted and vorax belts too (not just legendary). Belt-ness comes from the equipped slot when
  // editing, else the base type being crafted, else the catalog item's base type.
  const editorTargetIsBelt = useMemo(() => {
    if (editingBuildIdx !== null) {
      const it = gear[editingBuildIdx]
      return !!it && (getItemSlots(it).includes('belt') || getValidSlots(it.base_type ?? '').includes('belt'))
    }
    if (craftOpen) {
      const bt = craftBaseItem?.name ?? craftBaseType?.name ?? ''
      return getValidSlots(bt).includes('belt')
    }
    return !!customizeItem && getValidSlots(customizeItem.base_type ?? '').includes('belt')
  }, [editingBuildIdx, gear, craftOpen, craftBaseItem, craftBaseType, customizeItem])

  // Stamp the equipped belt blend onto a belt item at save time (craft / vorax flows). Non-belts and
  // the no-blend case pass through unchanged.
  const withBeltBlend = (item: EquippedGearItem): EquippedGearItem =>
    editorTargetIsBelt ? { ...item, beltBlend } : item

  // Whether the item currently being crafted/edited is a weapon or shield base — Tower Sequence is
  // crafted-only, so this only ever applies inside the Craft flow (never Customize or Vorax).
  const editorTargetIsCraftedWeaponBase = craftOpen && !!CRAFT_CLASSIFICATIONS[craftBaseType?.item_id ?? '']

  // Stamp the selected Tower Sequence affix onto a crafted weapon/shield item at save time.
  const withTowerSequence = (item: EquippedGearItem): EquippedGearItem =>
    editorTargetIsCraftedWeaponBase ? { ...item, towerSequence } : item

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

  // Corrosion edits STAGE locally (like the slider customizations) and only commit in handleSaveBuildItem.
  // The live preview re-derives the edited item from this staged state via `previewItem`/makeCatalogItem, so
  // editing an equipped item's corruption no longer mutates the live build until "Save Changes" (bug-223).
  // `updatedAffixes` is recomputed at preview/commit time, so it's intentionally unused here.
  const handleCorrosionChange = (
    type: 'none' | 'desecration' | 'mutation',
    indices: number[],
    mutationText: string | null,
    _updatedAffixes: LegendaryAffix[] | null,
    clearRandomAffixIndices?: number[]
  ) => {
    setCorrosionType(type)
    setCorrodedExplicitIndices(indices)
    setMutationAffixText(mutationText)
    if (clearRandomAffixIndices?.length) {
      setSelectedRandomAffixes(prev => {
        const next = { ...prev }
        for (const i of clearRandomAffixIndices) delete next[i]
        return next
      })
    }
  }

  // Random-affix selection also stages only (re-derived at preview/commit). `_updatedAffixes` unused for the same reason.
  const handleRandomAffixChange = (explicitIndex: number, modifierId: string, _updatedAffixes: LegendaryAffix[]) => {
    setSelectedRandomAffixes({ ...selectedRandomAffixes, [explicitIndex]: modifierId })
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
    const item = gear[idx]
    // Belt blend rides every editor flow (crafted / vorax / legendary), so seed it up front.
    setBeltBlend(item.beltBlend ?? null)
    // Tower Sequence only rides the crafted-weapon flow, but seeding here is harmless for other items.
    setTowerSequence(item.towerSequence ?? null)
    if (item.is_crafted && !item.is_vorax) {
      const bt = craftBases.find(b => b.base_items.some(bi => bi.name === item.base_type))
      if (bt) {
        const bi = bt.base_items.find(bi => bi.name === item.base_type) ?? bt.base_items[0] ?? null
        setCraftBaseType(bt)
        setCraftBaseItem(bi)
        setCraftSlots(reconstructCraftSlots(item, bt))
        setCraftCorrosionType(item.corrosion_type ?? 'none')
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
    setSelectedRandomAffixes(item.selected_random_affixes ?? {})
  }

  // Rename sets the item's DISPLAY name only (true `name` untouched — tooltips/editor/preview
  // keep it so the item stays identifiable). Empty or same-as-original clears the label.
  const renameBuildItem = (idx: number, nextRaw: string) => {
    // Clamp: the label is user-controlled, rides in share payloads, and renders in OTHER
    // users' apps on import — strip control chars and cap the length.
    const next = nextRaw.replace(/\p{C}/gu, '').trim().slice(0, 60)
    const cur = useBuildStore.getState().gear
    setGear(cur.map((g, i) => i === idx
      ? { ...g, displayName: next && next !== g.name ? next : undefined }
      : g))
  }

  // Clone a build item so small variants can be compared side by side. The copy must not
  // claim the original's equipment slot — the user assigns it (or swaps) explicitly.
  const handleDuplicateBuildItem = (idx: number) => {
    // Live store read (see commitRename) — a just-blurred rename must survive into the copy.
    const cur = useBuildStore.getState().gear
    // Duplicating the row that's open in the editor copies the LIVE draft the preview shows
    // (mirroring handleSaveBuildItem) — but the display label lives on the committed item, so
    // carry it across explicitly or the copy would lose its name.
    const source = idx === editingBuildIdx && previewItem
      ? { ...previewItem, beltBlend, towerSequence, displayName: cur[idx]?.displayName }
      : cur[idx]
    const copy = JSON.parse(JSON.stringify(source)) as EquippedGearItem
    copy.slot = null
    const next = [...cur]
    next.splice(idx + 1, 0, copy)
    setGear(next)
    if (editingBuildIdx !== null && editingBuildIdx > idx) setEditingBuildIdx(editingBuildIdx + 1)
  }

  const handleRemoveBuildItem = (idx: number) => {
    const next = [...useBuildStore.getState().gear]
    next.splice(idx, 1)
    setGear(next)
    if (editingBuildIdx === idx) {
      setEditingBuildIdx(null)
      setCustomizations([])
    } else if (editingBuildIdx !== null && editingBuildIdx > idx) {
      setEditingBuildIdx(editingBuildIdx - 1)
    }
  }

  const handleAddFromCatalog = () => {
    if (!selectedCatalogItem) return
    const newItem = makeCatalogItem(
      selectedCatalogItem, customizations, corrosionType, corrodedExplicitIndices,
      selectedRandomAffixes, corrosionBaseAffixes, mutationAffixText,
    )
    if (beltBlend) newItem.beltBlend = beltBlend
    setGear([...gear, newItem])
    setSelectedCatalogItem(null)
    setCustomizations([])
    resetCorrosion()
  }

  const handleSaveBuildItem = () => {
    if (editingBuildIdx === null) return
    const orig = gear[editingBuildIdx]
    // Commit exactly the staged draft the live preview showed: committed affixes + staged corrosion + slider
    // customizations (previewItem), preserving the item's slot and the staged belt blend (bug-223). Falls back
    // to the slider-only merge if there's no preview draft (non-legendary build item without catalog backing).
    const edited = previewItem
      ? { ...previewItem, slot: orig.slot, beltBlend, displayName: orig.displayName }
      : { ...orig, customizations, beltBlend }
    setGear(gear.map((g, i) => i === editingBuildIdx ? edited : g))
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

  // Second action row (Rename / Duplicate / Remove) for whichever editor has a build item open.
  const editActions: EditActions | undefined = editingBuildIdx !== null ? {
    itemKey: editingBuildIdx,
    displayName: gear[editingBuildIdx]?.displayName ?? gear[editingBuildIdx]?.name ?? '',
    onRename: (next: string) => renameBuildItem(editingBuildIdx, next),
    onDuplicate: () => handleDuplicateBuildItem(editingBuildIdx),
    onRemove: () => {
      handleRemoveBuildItem(editingBuildIdx)
      if (craftOpen) closeCraft()
      else handleCancel()
    },
  } : undefined

  const handleSlotAssign = (slot: GearSlot, buildItemIdx: number | null) => {
    let next = gear.map((item, i) => {
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
    setGear(next as EquippedGearItem[])
    setSlotDropdown(null)
  }

  const openSlotDropdown = (slotId: GearSlot, e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setSlotDropdown({ slotId, rect })
  }

  const getEquippedForSlot = (slotId: GearSlot): EquippedGearItem | null =>
    gear.find(item => itemHasSlot(item, slotId)) ?? null

  const getEquippedIdxForSlot = (slotId: GearSlot): number =>
    gear.findIndex(item => itemHasSlot(item, slotId))


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
    const w1 = gear.find(item => itemHasSlot(item, 'weapon1'))
    return isTwoHandedBaseType(w1?.base_type ?? '', baseTypeToItemId)
  }, [gear, baseTypeToItemId])

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
    const item = gear[dragIdx]
    if (item?.is_vorax) return VORAX_GRAFT_SLOTS[item.item_id] ?? []
    const bt = item?.base_type
    if (!bt) return SLOT_ORDER.map(s => s.id)
    const valid = getValidSlots(bt, craftBaseSlotMap)
    let slots = valid.length > 0 ? valid : SLOT_ORDER.map(s => s.id)
    // Block weapon2 when weapon1 has a 2H weapon (unless dragging that 2H weapon itself)
    if (weapon1Is2H) {
      const w1 = gear.find(item => itemHasSlot(item, 'weapon1'))
      if (gear[dragIdx] !== w1) {
        slots = slots.filter(s => s !== 'weapon2')
      }
    }
    return slots
  }, [dragIdx, gear, craftBaseSlotMap, weapon1Is2H])

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
      const craftLines: PreviewLine[] = craftSlots.flatMap((s, i) => {
        if (!s.affix) return []
        const corroded = craftCorrosionType === 'mutation' ? i < 2 : craftCorrosionType === 'desecration' && s.affix.tier === '0+'
        return [{ text: reconstructAffixText(craftAffixToLegendary(s.affix), s.chosenValues), label: affixTypeLabel(s.affix.affix_type), corroded: corroded || undefined }]
      })
      // Belt Blend / Tower Sequence are staged separately from craftSlots (they're not real crafted
      // affix slots) — surface them in the live preview so the preview panel and its damage delta
      // actually reflect what the player just picked. They go with the EXPLICIT affixes, not the base
      // implicits — base stat values (implicitLines) always stay at the top, and these render with the
      // default explicit-line color rather than the implicit section's blue.
      const beltBlendEntry = editorTargetIsBelt ? beltBlends.find(b => b.talent_id === beltBlend) : null
      const beltBlendLine: PreviewLine = beltBlendEntry
        ? { text: beltBlendEntry.effect_text || beltBlendEntry.effect_raw, label: 'Belt Blend' }
        : null
      const towerSequenceLine: PreviewLine = editorTargetIsCraftedWeaponBase && towerSequence
        ? { text: towerSequence, label: 'Tower Sequence' }
        : null
      const extraLines = [beltBlendLine, towerSequenceLine].filter((l): l is NonNullable<PreviewLine> => l !== null)
      const allExplicit = [...extraLines, ...craftLines]
      if (implicitLines.length > 0 && allExplicit.length > 0) return [...implicitLines, null, ...allExplicit]
      if (implicitLines.length > 0) return implicitLines
      return allExplicit
    }
    if (customizeItem) {
      const mutationLine: PreviewLine = corrosionType === 'mutation' && mutationAffixText
        ? { text: mutationAffixText, corroded: true }
        : null
      const beltBlendEntry = editorTargetIsBelt ? beltBlends.find(b => b.talent_id === beltBlend) : null
      const beltBlendLine: PreviewLine = beltBlendEntry
        ? { text: beltBlendEntry.effect_text || beltBlendEntry.effect_raw, label: 'Belt Blend' }
        : null
      if (isLegendaryGearItem(customizeItem)) {
        const implicits = getItemImplicits(customizeItem)
        const explicits = getItemExplicits(customizeItem)
        const corrodedVariant = legendaryCatalogItem?.variants?.corroded
        const implicitLines: PreviewLine[] = implicits.map((a, i) => ({ text: tooltipAffixText(a, i, customizations) }))
        const allRandomOptions = legendaryCatalogItem
          ? Object.values(legendaryCatalogItem.random_affixes).flat().flatMap(g => g.options)
          : []
        const explicitLines: PreviewLine[] = explicits.map((a, i) => {
          const isCorroded = corrodedExplicitIndices.includes(i)
          const displayAffix = isCorroded && corrodedVariant?.explicits[i] ? corrodedVariant.explicits[i] : a
          if (displayAffix.affix_kind === 'placeholder') {
            const modId = selectedRandomAffixes[i]
            if (modId) {
              const opt = allRandomOptions.find(o => o.modifier_id === modId)
              if (opt) return { text: tooltipAffixText(opt, implicits.length + i, customizations), corroded: isCorroded }
            }
            return { text: displayAffix.raw_text }
          }
          return { text: tooltipAffixText(displayAffix, implicits.length + i, isCorroded ? undefined : customizations), corroded: isCorroded }
        })
        const allImplicits = mutationLine ? [mutationLine, ...implicitLines] : implicitLines
        const allExplicit = beltBlendLine ? [beltBlendLine, ...explicitLines] : explicitLines
        if (allImplicits.length > 0 && allExplicit.length > 0) return [...allImplicits, null, ...allExplicit]
        return [...allImplicits, ...allExplicit]
      }
      const craftItem = customizeItem as EquippedGearItem
      const implicitCount = craftItem.implicit_count ?? 0
      const allAffixes = getItemAffixes(craftItem)
      const implicitLines = allAffixes.slice(0, implicitCount).map((affix, i) => ({
        text: tooltipAffixText(affix, i, customizations),
        label: affixTypeLabel(affix.affix_type),
      }))
      // Swap in the corroded ("T0") variant for staged desecrated indices so the summary shows the corroded
      // VALUE live (a build-item edit stores base affixes; without this it kept showing base until save+reload).
      const corrodedVariant = legendaryCatalogItem?.variants?.corroded
      const explicitLines = allAffixes.slice(implicitCount).map((affix, i) => {
        const isCorroded = corrodedExplicitIndices.includes(i)
        const shown = isCorroded && corrodedVariant?.explicits[i] ? corrodedVariant.explicits[i] : affix
        return {
          text: tooltipAffixText(shown, implicitCount + i, isCorroded ? undefined : customizations),
          label: affixTypeLabel(shown.affix_type),
          corroded: isCorroded,
        }
      })
      const allImplicits = mutationLine ? [mutationLine, ...implicitLines] : implicitLines
      const allExplicit = beltBlendLine ? [beltBlendLine, ...explicitLines] : explicitLines
      if (allImplicits.length > 0 && allExplicit.length > 0) return [...allImplicits, null, ...allExplicit]
      return [...allImplicits, ...allExplicit]
    }
    return null
  }, [craftOpen, craftBaseType, craftBaseItem, craftSlots, craftCorrosionType, customizeItem, customizations, baseItemImplicits, corrosionType, mutationAffixText, corrodedExplicitIndices, legendaryCatalogItem, selectedRandomAffixes, editorTargetIsBelt, editorTargetIsCraftedWeaponBase, beltBlend, beltBlends, towerSequence])

  // The in-progress item being priced for the live preview (craft + customize modes; vorax prices
  // itself inside its own panel). Mirrors exactly what "Add to build" / "Save" would persist.
  const previewItem = useMemo((): EquippedGearItem | null => {
    // Belt Blend / Tower Sequence are staged separately (not baked into makeCraftedItem/makeCatalogItem's
    // output), so every branch below is stamped through the same withBeltBlend/withTowerSequence helpers
    // used at commit time — otherwise the live preview's damage delta silently ignores whichever one the
    // player just picked, moving only once the item is actually added to the build.
    if (craftOpen && selectedGraft) return null // vorax: handled in VoraxEditorPanel
    if (craftOpen) {
      const item = makeCraftedItem(craftSlots, craftBaseType, craftBaseItem, craftCorrosionType, baseItemImplicits)
      return item ? withTowerSequence(withBeltBlend(item)) : null
    }
    if (customizeItem) {
      if (isLegendaryGearItem(customizeItem)) {
        return withBeltBlend(makeCatalogItem(customizeItem, customizations, corrosionType, corrodedExplicitIndices, selectedRandomAffixes, corrosionBaseAffixes, mutationAffixText))
      }
      // Editing a build item: re-derive from its catalog legendary so STAGED corrosion / random-affix /
      // slider edits all show in the live preview WITHOUT mutating the live build (bug-223). Keep the item's
      // existing slot so this draft is exactly what handleSaveBuildItem will commit. A non-legendary build
      // item (unresolvable crafted) has no catalog backing → just apply pending slider rolls.
      if (legendaryCatalogItem) {
        const derived = makeCatalogItem(legendaryCatalogItem, customizations, corrosionType, corrodedExplicitIndices, selectedRandomAffixes, corrosionBaseAffixes, mutationAffixText)
        return withBeltBlend({ ...derived, slot: customizeItem.slot ?? null })
      }
      return withBeltBlend({ ...customizeItem, customizations }) // editing a build item → apply pending slider rolls
    }
    return null
  }, [craftOpen, selectedGraft, craftBaseType, craftBaseItem, craftSlots, craftCorrosionType, baseItemImplicits, customizeItem, customizations, corrosionType, corrodedExplicitIndices, selectedRandomAffixes, corrosionBaseAffixes, mutationAffixText, legendaryCatalogItem, beltBlend, towerSequence, editorTargetIsBelt, editorTargetIsCraftedWeaponBase])

  // The damage-delta request(s) for the live preview:
  //   - Editing an item already PLACED in the build (incl. multi-slot like a dual-equipped ring or
  //     same-item dual wield) → replace it IN PLACE keeping its exact slot assignment, compared
  //     against the CURRENT build (which still holds the item's old rolls). The band is therefore
  //     the gain from your edits. Replacing in place (not the single-slot equip-preview) is what
  //     keeps the item's other slot from being dropped and reading as a false loss.
  //   - A new craft/catalog item, or an unplaced build item → equip-preview (swap), multi-slot.
  const previewReqs = useMemo((): { label: string; req: DeltaRequest }[] => {
    if (!previewItem) return []
    if (editingBuildIdx !== null) {
      const orig = gear[editingBuildIdx]
      const origSlot = orig?.slot ?? null
      if (origSlot !== null) {
        const edited = { ...previewItem, slot: origSlot }
        return [{
          label: 'Damage',
          req: {
            key: `gear:edit:${editingBuildIdx}:${gearSig(previewItem)}`,
            step: s => ({ ...s, gear: s.gear.map((g, i) => i === editingBuildIdx ? edited : g) }),
            // base omitted = current build (item with its existing rolls) → delta is the edit's gain
          },
        }]
      }
    }
    return buildGearRequests({ ...previewItem, slot: null }, undefined, craftBaseSlotMap, baseTypeToItemId)
  }, [previewItem, editingBuildIdx, gear, craftBaseSlotMap, baseTypeToItemId])

  const previewComputed = useDamageDeltaList(previewReqs.length ? previewReqs.map(r => r.req) : null, previewReqs.length > 0)
  const previewDeltas = previewReqs.map((r, i) => ({ label: r.label, delta: previewComputed[i] ?? ({ state: 'loading' } as DamageDelta) }))

  const handleDragStart = (idx: number) => {
    setDragIdx(idx)
  }

  const handleDrop = (slotId: GearSlot) => {
    if (dragIdx !== null && dragValidSlots.includes(slotId)) {
      handleSlotAssign(slotId, dragIdx)
    }
    setDragIdx(null)
    setDragOverSlot(null)
  }

  // Reorder the "Items in Build" list itself: drop the dragged item before `targetIdx`. The
  // edited item is tracked by identity so the open customize panel stays on the same item.
  const handleReorderBuildItem = (targetIdx: number) => {
    if (dragIdx !== null && dragIdx !== targetIdx) {
      const editingItem = editingBuildIdx !== null ? gear[editingBuildIdx] : null
      const next = [...gear]
      const [moved] = next.splice(dragIdx, 1)
      next.splice(dragIdx < targetIdx ? targetIdx - 1 : targetIdx, 0, moved)
      setGear(next)
      if (editingItem) {
        const newIdx = next.indexOf(editingItem)
        setEditingBuildIdx(newIdx === -1 ? null : newIdx)
      }
    }
    setDragIdx(null)
    setDragOverSlot(null)
    setDragOverBuildIdx(null)
  }

  return (
    <div className="screen gear-screen">
      <div className="gear-header">
        <h2 className="title-accent" style={{ fontSize: 20 }}>Gear</h2>
        <span className="gear-header-count">{legendaryIndex === null ? '' : `${catalogIndex.length} items`}</span>
      </div>

      <div className="gear-body">
        {/* Panels 1+2 share one column (desktop) — frees width for the craft editor's side-by-side
            preview. On mobile the wrapper is display:contents and the panels stack as before. */}
        <div className="gear-left-stack">
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
                  <GearHoverTooltip item={equipped} slot={slotDef.id} slotMap={craftBaseSlotMap} baseTypeToItemId={baseTypeToItemId}>
                    {tp => (
                      <button
                        {...tp}
                        className={`gear-slot-item-name ${getItemQualityClass(equipped)}`}
                        onClick={e => openSlotDropdown(slotDef.id, e)}
                      >
                        {equipped.displayName ?? equipped.name}
                      </button>
                    )}
                  </GearHoverTooltip>
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
          {gear.length === 0 && (
            <div className="gear-build-empty">No items added yet.</div>
          )}
          {gear.map((item, i) => (
            <div
              key={i}
              className={`gear-build-item${editingBuildIdx === i ? ' gear-build-item--selected' : ''}${dragIdx === i ? ' gear-build-item--dragging' : ''}${dragOverBuildIdx === i && dragIdx !== null && dragIdx !== i ? ' gear-build-item--reorder-over' : ''}`}
              draggable
              onDragStart={() => handleDragStart(i)}
              onDragEnd={() => { setDragIdx(null); setDragOverSlot(null); setDragOverBuildIdx(null) }}
              onDragOver={e => { if (dragIdx !== null) { e.preventDefault(); setDragOverBuildIdx(i) } }}
              onDragLeave={() => setDragOverBuildIdx(prev => prev === i ? null : prev)}
              onDrop={() => handleReorderBuildItem(i)}
            >
              <GearHoverTooltip item={item} slotMap={craftBaseSlotMap} baseTypeToItemId={baseTypeToItemId}>
                {tp => (
                  <button
                    {...tp}
                    className="gear-build-item-name"
                    onClick={() => handleSelectBuildItem(i)}
                  >
                    <span className={`gear-build-item-label ${getItemQualityClass(item)}`}>{item.displayName ?? item.name}</span>
                    {getItemSlots(item).map(slotId => (
                      <span key={slotId} className="gear-build-item-slot">
                        {SLOT_ORDER.find(s => s.id === slotId)?.label}
                      </span>
                    ))}
                  </button>
                )}
              </GearHoverTooltip>
              <button
                className="gear-slot-remove"
                onClick={() => handleRemoveBuildItem(i)}
                title="Remove"
              >×</button>
            </div>
          ))}
        </div>
        </div>

        {/* Panel 3: Customize or Craft */}
        <div className="gear-editor-column">
          {craftOpen && selectedGraft ? (
            <VoraxEditorPanel
              graft={selectedGraft}
              catalog={catalog}
              catalogIndex={catalogIndex}
              editActions={editActions}
              onAddToBuild={item => setGear([...gear, withBeltBlend(item)])}
              onClose={closeCraft}
              onBack={() => { setSelectedGraft(null); setVoraxInitialState(null) }}
              initialState={voraxInitialState}
              onSaveBuildItem={editingBuildIdx !== null
                ? (item) => { const orig = gear[editingBuildIdx]; setGear(gear.map((g, i) => i === editingBuildIdx ? withBeltBlend({ ...item, slot: orig.slot, displayName: orig.displayName }) : g)); setEditingBuildIdx(null) }
                : undefined}
              isBelt={editorTargetIsBelt}
              beltBlends={beltBlends}
              beltBlend={beltBlend}
              onBeltBlendChange={setBeltBlend}
            />
          ) : craftOpen ? (
            <CraftEditorPanel
              craftBases={craftBases}
              craftBasesLoaded={craftBasesLoaded}
              editActions={editActions}
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
              onAddToBuild={item => setGear([...gear, withTowerSequence(withBeltBlend(item))])}
              onClose={closeCraft}
              craftSearch={craftSearch}
              setCraftSearch={setCraftSearch}
              baseItemImplicits={baseItemImplicits}
              previewName={previewName}
              previewLines={previewLines}
              previewDeltas={previewDeltas}
              corrosionType={craftCorrosionType}
              onCorrosionTypeChange={setCraftCorrosionType}
              onSaveBuildItem={editingBuildIdx !== null
                ? (item) => { const orig = gear[editingBuildIdx]; setGear(gear.map((g, i) => i === editingBuildIdx ? withTowerSequence(withBeltBlend({ ...item, slot: orig.slot, displayName: orig.displayName })) : g)); setEditingBuildIdx(null) }
                : undefined}
              isBelt={editorTargetIsBelt}
              beltBlends={beltBlends}
              beltBlend={beltBlend}
              onBeltBlendChange={setBeltBlend}
              towerSequence={towerSequence}
              onTowerSequenceChange={setTowerSequence}
              towerSequenceEntries={towerSequenceEntries}
            />
          ) : (
            <CustomizePanel
              item={customizeItem}
              customizations={customizations}
              isEditing={isEditing}
              editActions={editActions}
              onCustomizationChange={setCustomizations}
              onConfirm={isEditing ? handleSaveBuildItem : handleAddFromCatalog}
              onCancel={handleCancel}
              baseItemImplicits={baseItemImplicits}
              previewName={previewName}
              previewLines={previewLines}
              previewDeltas={previewDeltas}
              catalogItem={legendaryCatalogItem}
              corrosionBaseAffixes={corrosionBaseAffixes}
              corrosionType={corrosionType}
              corrodedExplicitIndices={corrodedExplicitIndices}
              mutationAffixText={mutationAffixText}
              selectedRandomAffixes={selectedRandomAffixes}
              onCorrosionChange={handleCorrosionChange}
              onRandomAffixChange={handleRandomAffixChange}
              isBelt={editorTargetIsBelt}
              beltBlends={beltBlends}
              beltBlend={beltBlend}
              onBeltBlendChange={setBeltBlend}
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
            <CoverageLegend />
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
          <div className="skill-sort-row">
            <span className="skill-sort-label">Sort</span>
            <select
              className="skill-sort-select"
              value={legendarySort}
              onChange={e => setLegendarySort(e.target.value as 'alpha' | 'coverage')}
            >
              <option value="alpha">Default</option>
              <option value="coverage">Coverage</option>
            </select>
            <label className="skill-modeled-only-label" title="Hide items the engine doesn't model at all">
              <input type="checkbox" checked={modeledOnly} onChange={toggleModeledOnly} /> Modeled only
            </label>
          </div>
          <div className="gear-catalog-list">
            {loading && <LoadingState label="Loading gear catalog…" />}
            {referenceResolved && legendaryIndex === null && (
              <div className="gear-empty" style={{ color: '#ff6b6b' }}>Couldn't load gear catalog — restart to retry.</div>
            )}
            {!loading && legendaryIndex !== null && filtered.length === 0 && <div className="gear-empty">No items found.</div>}
            {filtered.map(item => {
              const full = catalogMap.get(item.item_id)
              const renderRow = (tp: Record<string, unknown> | null) => (
                <div
                  key={item.item_id}
                  {...(tp ?? {})}
                  className={`gear-catalog-item${selectedCatalogItem?.item_id === item.item_id && editingBuildIdx === null && !craftOpen ? ' gear-catalog-item--selected' : ''}${!catalogLoaded ? ' gear-catalog-item--loading' : ''}`}
                  onClick={() => handleSelectCatalogItem(item)}
                >
                  <span className="gear-catalog-item-name">{item.name}</span>
                  <CoverageBadge coverage={item.coverage} detail={item.coverage_detail} />
                  <span className="gear-catalog-item-level">Lv. {item.required_level}</span>
                </div>
              )
              return full
                ? <GearHoverTooltip key={item.item_id} item={full} slotMap={craftBaseSlotMap} baseTypeToItemId={baseTypeToItemId}>{tp => renderRow(tp)}</GearHoverTooltip>
                : renderRow(null)
            })}
          </div>
        </div>
      </div>

      {slotDropdown && (
        <SlotDropdownPortal
          slotId={slotDropdown.slotId}
          rect={slotDropdown.rect}
          equippedItems={gear}
          currentIdx={getEquippedIdxForSlot(slotDropdown.slotId)}
          slotMap={craftBaseSlotMap}
          weapon1Is2H={weapon1Is2H}
          onSelect={handleSlotAssign}
          onClose={() => setSlotDropdown(null)}
        />
      )}
    </div>
  )
}
