import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  api, LegendaryGearItem, LegendaryAffix, LegendaryNumericValue,
  EquippedGearItem, CustomizedAffix, GearSlot,
} from '../api/client'

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
  return createPortal(
    <div className="gear-tooltip-portal" style={{ left: state.x + 16, top: state.y - 10 }}>
      <div className="gear-tooltip-name">{state.item.name}</div>
      <div className="gear-tooltip-level">Required Level: {state.item.required_level}</div>
      <div className="gear-tooltip-divider" />
      {getItemAffixes(state.item).map((affix, i) => (
        <div key={i} className="gear-tooltip-affix">{tooltipAffixText(affix, i, customizations)}</div>
      ))}
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
  onSelect: (slot: GearSlot, idx: number | null) => void
  onClose: () => void
}

function SlotDropdownPortal({ slotId, rect, equippedItems, currentIdx, onSelect, onClose }: SlotDropdownProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  return createPortal(
    <div
      ref={ref}
      className="gear-slot-menu"
      style={{ position: 'fixed', left: rect.left, top: rect.bottom + 4, minWidth: rect.width }}
    >
      <div
        className="gear-slot-menu-option gear-slot-menu-empty"
        onClick={() => onSelect(slotId, null)}
      >
        — Empty —
      </div>
      {equippedItems.map((item, i) => (
        <div
          key={i}
          className={`gear-slot-menu-option${i === currentIdx ? ' gear-slot-menu-option--current' : ''}`}
          onClick={() => onSelect(slotId, i)}
        >
          {item.name}
        </div>
      ))}
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
}

function CustomizePanel({ item, customizations, isEditing, onCustomizationChange, onConfirm, onCancel }: CustomizePanelProps) {
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

  return (
    <div className="gear-customize-panel">
      <div className="gear-customize-header">
        <div className="gear-customize-name">{item.name}</div>
        <div className="gear-customize-level">Required Level: {item.required_level}</div>
      </div>
      <div className="gear-customize-divider" />

      <div className="gear-customize-affixes">
        {getItemAffixes(item).map((affix, affixIdx) => {
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
              <div key={affixIdx} className="gear-affix-row">
                <div className="gear-affix-label">{affix.raw_text}</div>
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
            <div key={affixIdx} className="gear-affix-row gear-affix-range-row">
              <div className="gear-affix-label">{displayText}</div>
              {rangeIndices.map(valIdx => {
                const nv = affix.numeric_values[valIdx]
                const min = nv.min ?? 0
                const max = nv.max ?? 0
                const dp = rangeDecimals(nv)
                const step = dp > 0 ? parseFloat((1 / Math.pow(10, dp)).toFixed(dp)) : 1
                const chosen = chosenMap[valIdx] ?? midpoint(nv)
                const displayChosen = dp > 0 ? chosen.toFixed(dp) : chosen
                return (
                  <div key={valIdx} className="gear-slider-row">
                    <input
                      type="range"
                      className="gear-affix-slider"
                      min={min}
                      max={max}
                      step={step}
                      value={chosen}
                      onChange={e => setChosenValue(affixIdx, valIdx, Number(e.target.value))}
                    />
                    <span className="gear-affix-value">{displayChosen}</span>
                  </div>
                )
              })}
            </div>
          )
        })}
      </div>

      <div className="gear-customize-actions">
        <button className="btn btn-sm" onClick={onCancel}>Cancel</button>
        <button className="btn btn-sm btn-primary gear-confirm-btn" onClick={onConfirm}>
          {isEditing ? 'Save' : 'Add to Build'}
        </button>
      </div>
    </div>
  )
}

// ── Main Screen ───────────────────────────────────────────────────────────────

interface Props {
  equippedItems: EquippedGearItem[]
  onGearChange: (items: EquippedGearItem[]) => void
  onBack: () => void
}

export default function GearScreen({ equippedItems, onGearChange, onBack }: Props) {
  const [catalog, setCatalog] = useState<LegendaryGearItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selectedCatalogItem, setSelectedCatalogItem] = useState<LegendaryGearItem | null>(null)
  const [editingBuildIdx, setEditingBuildIdx] = useState<number | null>(null)
  const [customizations, setCustomizations] = useState<CustomizedAffix[]>([])
  const [slotDropdown, setSlotDropdown] = useState<{ slotId: GearSlot; rect: DOMRect } | null>(null)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverSlot, setDragOverSlot] = useState<GearSlot | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.getLegendaryGear()
      .then(res => setCatalog(res.items))
      .catch(() => {})
      .finally(() => setLoading(false))
    searchRef.current?.focus()
  }, [])

  const q = search.trim().toLowerCase()
  const filtered = q
    ? catalog.filter(item =>
        item.name.toLowerCase().includes(q) ||
        getItemAffixes(item).some(a => a.raw_text.toLowerCase().includes(q))
      )
    : catalog

  const customizeItem: LegendaryGearItem | EquippedGearItem | null =
    editingBuildIdx !== null ? (equippedItems[editingBuildIdx] ?? null) : selectedCatalogItem

  const isEditing = editingBuildIdx !== null

  const handleSelectCatalogItem = (item: LegendaryGearItem) => {
    setSelectedCatalogItem(item)
    setEditingBuildIdx(null)
    setCustomizations([])
  }

  const handleSelectBuildItem = (idx: number) => {
    setEditingBuildIdx(idx)
    setSelectedCatalogItem(null)
    setCustomizations(equippedItems[idx].customizations)
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
    const newItem: EquippedGearItem = {
      item_id: selectedCatalogItem.item_id,
      name: selectedCatalogItem.name,
      required_level: selectedCatalogItem.required_level,
      affixes: getItemAffixes(selectedCatalogItem),
      customizations,
      slot: null,
    }
    onGearChange([...equippedItems, newItem])
    setSelectedCatalogItem(null)
    setCustomizations([])
  }

  const handleSaveBuildItem = () => {
    if (editingBuildIdx === null) return
    const next = [...equippedItems]
    next[editingBuildIdx] = { ...next[editingBuildIdx], customizations }
    onGearChange(next)
    setEditingBuildIdx(null)
    setCustomizations([])
  }

  const handleCancel = () => {
    setSelectedCatalogItem(null)
    setEditingBuildIdx(null)
    setCustomizations([])
  }

  const handleSlotAssign = (slot: GearSlot, buildItemIdx: number | null) => {
    const next = equippedItems.map((item, i) => {
      if (buildItemIdx !== null && i === buildItemIdx) return { ...item, slot }
      if (item.slot === slot) return { ...item, slot: null as GearSlot | null }
      return item
    })
    onGearChange(next as EquippedGearItem[])
    setSlotDropdown(null)
  }

  const openSlotDropdown = (slotId: GearSlot, e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setSlotDropdown({ slotId, rect })
  }

  const getEquippedForSlot = (slotId: GearSlot): EquippedGearItem | null =>
    equippedItems.find(item => item.slot === slotId) ?? null

  const getEquippedIdxForSlot = (slotId: GearSlot): number =>
    equippedItems.findIndex(item => item.slot === slotId)

  const showTooltip = (item: LegendaryGearItem | EquippedGearItem, e: React.MouseEvent) =>
    setTooltip({ item, x: e.clientX, y: e.clientY })

  const moveTooltip = (e: React.MouseEvent) =>
    setTooltip(t => t ? { ...t, x: e.clientX, y: e.clientY } : null)

  const hideTooltip = () => setTooltip(null)

  const handleDragStart = (idx: number) => {
    setDragIdx(idx)
    setTooltip(null)
  }

  const handleDrop = (slotId: GearSlot) => {
    if (dragIdx !== null) handleSlotAssign(slotId, dragIdx)
    setDragIdx(null)
    setDragOverSlot(null)
  }

  return (
    <div className="screen gear-screen">
      <div className="gear-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <h2 className="title-accent" style={{ fontSize: 20 }}>Legendary Gear</h2>
        <span className="gear-header-count">{catalog.length} items</span>
      </div>

      <div className="gear-body">
        {/* Panel 1: Equipment Slots */}
        <div className="gear-slots-panel">
          <div className="gear-slots-title">Equipment</div>
          {SLOT_ORDER.map(slotDef => {
            const equipped = getEquippedForSlot(slotDef.id)
            const equippedIdx = getEquippedIdxForSlot(slotDef.id)
            const isDragOver = dragOverSlot === slotDef.id
            return (
              <div
                key={slotDef.id}
                className={`gear-slot-row${equipped ? ' gear-slot-occupied' : ''}${isDragOver ? ' gear-slot-drag-over' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragOverSlot(slotDef.id) }}
                onDragLeave={() => setDragOverSlot(null)}
                onDrop={() => handleDrop(slotDef.id)}
              >
                <span className="gear-slot-name">{slotDef.label}</span>
                {equipped ? (
                  <button
                    className="gear-slot-item-name"
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
                <span className="gear-build-item-label">{item.name}</span>
                {item.slot && (
                  <span className="gear-build-item-slot">
                    {SLOT_ORDER.find(s => s.id === item.slot)?.label}
                  </span>
                )}
              </button>
              <button
                className="gear-slot-remove"
                onClick={() => handleRemoveBuildItem(i)}
                title="Remove"
              >×</button>
            </div>
          ))}
        </div>

        {/* Panel 3: Customization */}
        <CustomizePanel
          item={customizeItem}
          customizations={customizations}
          isEditing={isEditing}
          onCustomizationChange={setCustomizations}
          onConfirm={isEditing ? handleSaveBuildItem : handleAddFromCatalog}
          onCancel={handleCancel}
        />

        {/* Panel 4: Legendary Catalog */}
        <div className="gear-catalog">
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
            {!loading && filtered.length === 0 && <div className="gear-empty">No items found.</div>}
            {filtered.map(item => (
              <div
                key={item.item_id}
                className={`gear-catalog-item${selectedCatalogItem?.item_id === item.item_id && editingBuildIdx === null ? ' gear-catalog-item--selected' : ''}`}
                onClick={() => handleSelectCatalogItem(item)}
                onMouseEnter={e => showTooltip(item, e)}
                onMouseMove={moveTooltip}
                onMouseLeave={hideTooltip}
              >
                <span className="gear-catalog-item-name">{item.name}</span>
                <span className="gear-catalog-item-level">Lv. {item.required_level}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {slotDropdown && (
        <SlotDropdownPortal
          slotId={slotDropdown.slotId}
          rect={slotDropdown.rect}
          equippedItems={equippedItems}
          currentIdx={getEquippedIdxForSlot(slotDropdown.slotId)}
          onSelect={handleSlotAssign}
          onClose={() => setSlotDropdown(null)}
        />
      )}
      {tooltip && <GearTooltip state={tooltip} />}
    </div>
  )
}
