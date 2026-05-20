import React, { useState, useEffect, useRef } from 'react'
import { api, SlatePool, SlateModifierOption, CoreTalentOption } from '../api/client'

// ── Board ─────────────────────────────────────────────────────────────────────

const BOARD_VALID: boolean[][] = [
  [false, false, true,  true,  false, false],
  [false, true,  true,  true,  true,  false],
  [true,  true,  true,  true,  true,  true ],
  [true,  true,  true,  true,  true,  true ],
  [false, true,  true,  true,  true,  false],
  [false, false, true,  true,  false, false],
]
const BOARD_ROWS = 6
const BOARD_COLS = 6
const TOTAL_CELLS = 24
const CELL = 72

function isValidCell(r: number, c: number): boolean {
  return r >= 0 && r < BOARD_ROWS && c >= 0 && c < BOARD_COLS && BOARD_VALID[r][c]
}

// ── Types ─────────────────────────────────────────────────────────────────────

const PRIMARY_TREES = [
  'God of Might', 'Goddess of Hunting', 'Goddess of Knowledge',
  'God of War', 'Goddess of Deception', 'God of Machines',
] as const
type PrimaryTree = typeof PRIMARY_TREES[number]

type LegendaryKind =
  | 'pedigree'
  | 'fallen_starlight'
  | 'corner_of_divinity'
  | 'spark_of_moth_fire'
  | 'when_sparks_set_prairie_ablaze'

type SlateKind = 'base' | LegendaryKind
type SlotType = 'magic' | 'rare' | 'legendary'
type MothDirection = 'above' | 'below' | 'left' | 'right'

const LEGEND_GOLD = '#c8881a'
const PRAIRIE_PINK = '#c050a0'

// ── Base shapes (4 shapes × 4 rotations) ─────────────────────────────────────

interface BaseShape { label: string; rotations: [number, number][][] }

const BASE_SHAPES: BaseShape[] = [
  {
    label: 'Square',
    rotations: [
      [[0,0],[0,1],[1,0],[1,1]],
      [[0,0],[0,1],[1,0],[1,1]],
      [[0,0],[0,1],[1,0],[1,1]],
      [[0,0],[0,1],[1,0],[1,1]],
    ],
  },
  {
    label: 'L',
    rotations: [
      [[0,0],[1,0],[2,0],[2,1]],   // upright
      [[0,0],[0,1],[0,2],[1,0]],   // 90° CW
      [[0,0],[0,1],[1,1],[2,1]],   // 180°
      [[0,2],[1,0],[1,1],[1,2]],   // 270°
    ],
  },
  {
    label: 'Z',
    rotations: [
      [[0,0],[0,1],[1,1],[1,2]],
      [[0,1],[1,0],[1,1],[2,0]],
      [[0,0],[0,1],[1,1],[1,2]],
      [[0,1],[1,0],[1,1],[2,0]],
    ],
  },
  {
    label: 'T',
    rotations: [
      [[0,1],[1,0],[1,1],[1,2]],   // up
      [[0,0],[1,0],[1,1],[2,0]],   // right
      [[0,0],[0,1],[0,2],[1,1]],   // down
      [[0,1],[1,0],[1,1],[2,1]],   // left
    ],
  },
]

const ROTATION_LABELS = ['↑ 0°', '→ 90°', '↓ 180°', '← 270°']

// ── Legendary orientations ────────────────────────────────────────────────────

const LEGENDARY_ORIENTATIONS: Record<LegendaryKind, [number, number][][]> = {
  pedigree: [
    [[0,1],[0,2],[1,0],[1,1],[1,2],[2,0],[2,1]],
    [[0,0],[0,1],[1,0],[1,1],[1,2],[2,1],[2,2]],
  ],
  fallen_starlight: [[[0,0],[0,1]], [[0,0],[1,0]]],
  corner_of_divinity: [
    [[0,0],[0,1],[1,0]],
    [[0,0],[0,1],[1,1]],
    [[0,1],[1,0],[1,1]],
    [[0,0],[1,0],[1,1]],
  ],
  spark_of_moth_fire:             [[[0,0]]],
  when_sparks_set_prairie_ablaze: [[[0,0]]],
}

function getOrientationCells(kind: SlateKind, shapeIndex: number, orientationIndex: number): [number, number][] {
  if (kind === 'base') return BASE_SHAPES[shapeIndex]?.rotations[orientationIndex] ?? BASE_SHAPES[0].rotations[0]
  return LEGENDARY_ORIENTATIONS[kind as LegendaryKind][orientationIndex] ?? LEGENDARY_ORIENTATIONS[kind as LegendaryKind][0]
}

function getOrientationCount(kind: SlateKind): number {
  if (kind === 'base') return 4
  return LEGENDARY_ORIENTATIONS[kind as LegendaryKind].length
}

function getCenterOffset(cells: [number, number][]): [number, number] {
  const rows = cells.map(([r]) => r)
  const cols = cells.map(([, c]) => c)
  return [
    Math.floor((Math.min(...rows) + Math.max(...rows)) / 2),
    Math.floor((Math.min(...cols) + Math.max(...cols)) / 2),
  ]
}

function centeredAnchor(kind: SlateKind, shapeIndex: number, orientationIndex: number, cursor: [number, number]): [number, number] {
  const cells = getOrientationCells(kind, shapeIndex, orientationIndex)
  const [cr, cc] = getCenterOffset(cells)
  return [cursor[0] - cr, cursor[1] - cc]
}

function anchorCells(kind: SlateKind, shapeIndex: number, orientationIndex: number, anchor: [number, number]): [number, number][] {
  const [ar, ac] = anchor
  return getOrientationCells(kind, shapeIndex, orientationIndex).map(([dr, dc]) => [ar + dr, ac + dc] as [number, number])
}

// ── Legendary metadata ────────────────────────────────────────────────────────

const LEGENDARY_META: Record<LegendaryKind, { label: string; color: string }> = {
  pedigree:                       { label: 'Pedigree',                           color: LEGEND_GOLD },
  fallen_starlight:               { label: 'Fallen Starlight',                   color: LEGEND_GOLD },
  corner_of_divinity:             { label: 'Corner of Divinity',                 color: LEGEND_GOLD },
  spark_of_moth_fire:             { label: 'Spark of Moth Fire',                 color: LEGEND_GOLD },
  when_sparks_set_prairie_ablaze: { label: 'When Sparks Set the Prairie Ablaze', color: PRAIRIE_PINK },
}

const PREVIEW_CELLS: Record<SlateKind, [number, number][]> = {
  base:                           [[0,1],[1,0],[1,1],[1,2]],
  pedigree:                       [[0,1],[0,2],[1,0],[1,1],[1,2],[2,0],[2,1]],
  fallen_starlight:               [[0,0],[0,1]],
  corner_of_divinity:             [[0,0],[0,1],[1,0]],
  spark_of_moth_fire:             [[0,0]],
  when_sparks_set_prairie_ablaze: [[0,0]],
}

const SLATE_DESCRIPTIONS: Record<SlateKind, string> = {
  base:                           '5 modifiers · tree-based pool',
  pedigree:                       '4 modifiers · all-trees pool',
  fallen_starlight:               '4 modifiers · all-trees pool',
  corner_of_divinity:             '2 modifiers · all-trees pool',
  spark_of_moth_fire:             'Copies one adjacent slate',
  when_sparks_set_prairie_ablaze: 'Copies up to 4 adjacent slates',
}

// ── Slot configuration ────────────────────────────────────────────────────────

interface SectionDef { label: string; count: number; maxType: SlotType; canBeCore?: boolean }

const SLOT_CONFIG: Record<SlateKind, { sections: SectionDef[]; poolScope: 'tree' | 'all' | 'none' }> = {
  base: {
    sections: [
      { label: 'Fixed Talent Nodes', count: 2, maxType: 'legendary' },
      { label: 'Brand Talent Nodes', count: 3, maxType: 'legendary' },
    ],
    poolScope: 'tree',
  },
  fallen_starlight: {
    sections: [
      { label: 'Top Modifiers',    count: 2, maxType: 'rare' },
      { label: 'Bottom Modifiers', count: 2, maxType: 'legendary' },
    ],
    poolScope: 'all',
  },
  corner_of_divinity: {
    sections: [{ label: 'Modifiers', count: 2, maxType: 'legendary' }],
    poolScope: 'all',
  },
  pedigree: {
    sections: [
      { label: 'Talent Modifiers', count: 2, maxType: 'legendary' },
      { label: 'Core Talents',     count: 2, maxType: 'legendary', canBeCore: true },
    ],
    poolScope: 'all',
  },
  spark_of_moth_fire:             { sections: [], poolScope: 'none' },
  when_sparks_set_prairie_ablaze: { sections: [], poolScope: 'none' },
}

// ── Slot model ────────────────────────────────────────────────────────────────

interface CreatorSlot {
  slotType: SlotType
  maxType: SlotType
  canBeCore: boolean
  isCore: boolean
  selectedNodeId: string | null
  selectedCoreKey: string | null
  coreName: string | null
  effects: string[]
}

function initSlots(kind: SlateKind): CreatorSlot[] {
  return (SLOT_CONFIG[kind]?.sections ?? []).flatMap(s =>
    Array.from({ length: s.count }, () => ({
      slotType: s.maxType, maxType: s.maxType,
      canBeCore: s.canBeCore ?? false, isCore: s.canBeCore ?? false,
      selectedNodeId: null, selectedCoreKey: null, coreName: null, effects: [] as string[],
    }))
  )
}

function getSections(kind: SlateKind): { label: string; indices: number[]; canBeCore: boolean }[] {
  let offset = 0
  return (SLOT_CONFIG[kind]?.sections ?? []).map(s => {
    const indices = Array.from({ length: s.count }, (_, i) => offset + i)
    offset += s.count
    return { label: s.label, indices, canBeCore: s.canBeCore ?? false }
  })
}

export interface PlacedSlate {
  id: string
  kind: SlateKind
  cells: [number, number][]
  orientationIndex: number
  shapeIndex: number
  anchor: [number, number]
  slots: CreatorSlot[]
  pool?: SlatePool
  treeType?: PrimaryTree
  mothDirection?: MothDirection
}

// ── Creator state ─────────────────────────────────────────────────────────────

interface CreatorState {
  kind: SlateKind
  shapeIndex: number
  treeType: PrimaryTree | null
  slots: CreatorSlot[]
  orientationIndex: number
  pool: SlatePool | null
  poolLoading: boolean
  openPicker: number | null
  pickerSearch: string
  mothDirection: MothDirection | null
}

type PanelMode =
  | { type: 'idle' }
  | { type: 'creating'; creator: CreatorState }
  | { type: 'editing'; slateId: string; creator: CreatorState }

function defaultCreator(kind: SlateKind): CreatorState {
  return {
    kind, shapeIndex: 0, treeType: null, slots: initSlots(kind),
    orientationIndex: 0, pool: null, poolLoading: false,
    openPicker: null, pickerSearch: '', mothDirection: null,
  }
}

// ── Slot helpers ──────────────────────────────────────────────────────────────

const SLOT_TYPE_COLOR: Record<SlotType, string> = { magic: '#4a90d9', rare: '#9060d0', legendary: '#c8881a' }
const SLOT_TYPE_LABEL: Record<SlotType, string> = { magic: 'M', rare: 'R', legendary: 'L' }

function cycleSlotType(current: SlotType, maxType: SlotType): SlotType {
  const all: SlotType[] = ['legendary', 'rare', 'magic']
  const allowed = all.slice(all.indexOf(maxType))
  return allowed[(allowed.indexOf(current) + 1) % allowed.length]
}

function getSlotModifierPool(pool: SlatePool, slotType: SlotType): SlateModifierOption[] {
  if (slotType === 'magic') return pool.magic
  if (slotType === 'rare') return [...pool.rare, ...pool.magic]
  return [...pool.legendary, ...pool.rare, ...pool.magic]
}

function getBottomEffects(slate: PlacedSlate): string[] {
  if (!slate.slots.length) return []
  return slate.slots[slate.slots.length - 1].effects
}

// ── Prairie / Moth helpers ────────────────────────────────────────────────────

function getPrairieModifiers(prairie: PlacedSlate, placed: PlacedSlate[]): string[] {
  const [pr, pc] = prairie.anchor
  return ([[-1,0],[1,0],[0,-1],[0,1]] as [number,number][]).flatMap(([dr, dc]) => {
    const key = `${pr + dr},${pc + dc}`
    const neighbor = placed.find(s => s.id !== prairie.id && s.cells.some(([r, c]) => `${r},${c}` === key))
    const effects = neighbor ? getBottomEffects(neighbor) : []
    return effects.length ? [effects.join(' / ')] : []
  })
}

function getMothModifier(moth: PlacedSlate, placed: PlacedSlate[]): string | null {
  if (!moth.mothDirection) return null
  const [mr, mc] = moth.anchor
  const delta: Record<MothDirection, [number, number]> = { above: [-1,0], below: [1,0], left: [0,-1], right: [0,1] }
  const [dr, dc] = delta[moth.mothDirection]
  const target = placed.find(s => s.id !== moth.id && s.cells.some(([r, c]) => `${r},${c}` === `${mr + dr},${mc + dc}`))
  if (!target) return null
  const effects = getBottomEffects(target)
  return effects.length ? effects.join(' / ') : null
}

// ── Mini shape preview ────────────────────────────────────────────────────────

function MiniShape({ offsets, color, size = 9 }: { offsets: [number, number][]; color: string; size?: number }) {
  if (!offsets.length) return null
  const maxRow = Math.max(...offsets.map(([r]) => r))
  const maxCol = Math.max(...offsets.map(([, c]) => c))
  const set = new Set(offsets.map(([r, c]) => `${r},${c}`))
  return (
    <div style={{ display: 'inline-grid', gridTemplateColumns: `repeat(${maxCol + 1}, ${size}px)`, gap: 1.5 }}>
      {Array.from({ length: maxRow + 1 }, (_, r) =>
        Array.from({ length: maxCol + 1 }, (_, c) => (
          <div key={`${r},${c}`} style={{
            width: size, height: size,
            background: set.has(`${r},${c}`) ? color : 'rgba(255,255,255,0.04)',
            borderRadius: 2,
          }} />
        ))
      ).flat()}
    </div>
  )
}

// ── Modifier slot ─────────────────────────────────────────────────────────────

interface ModifierSlotProps {
  slot: CreatorSlot; index: number; allSlots: CreatorSlot[]
  pool: SlatePool | null; isOpen: boolean; search: string; accentColor: string
  onTogglePicker: () => void; onCycleType: () => void
  onSelect: (mod: SlateModifierOption) => void; onSelectCore: (core: CoreTalentOption) => void
  onClear: () => void; onToggleCoreMode: () => void; onSearchChange: (s: string) => void
}

function ModifierSlot({ slot, allSlots, pool, isOpen, search, accentColor,
  onTogglePicker, onCycleType, onSelect, onSelectCore, onClear, onToggleCoreMode, onSearchChange,
}: ModifierSlotProps) {
  const usedNodeIds = new Set(allSlots.map(s => s.selectedNodeId).filter(Boolean) as string[])
  const usedCoreKeys = new Set(allSlots.map(s => s.selectedCoreKey).filter(Boolean) as string[])
  const isDuplicate = slot.isCore && slot.selectedCoreKey
    ? (Array.from(usedCoreKeys).filter(k => k === slot.selectedCoreKey).length > 1) : false

  const displayText = slot.isCore
    ? (slot.selectedCoreKey ? slot.effects.join(' / ') : null)
    : (slot.selectedNodeId ? slot.effects.join(' / ') : null)

  const modOptions = !slot.isCore && pool
    ? getSlotModifierPool(pool, slot.slotType).filter(m => {
        if (m.nodeId === slot.selectedNodeId) return true
        if (usedNodeIds.has(m.nodeId)) return false
        return !search || m.effects.some(e => e.toLowerCase().includes(search.toLowerCase()))
      }) : []

  const coreOptions = slot.isCore && pool
    ? pool.core.filter(c => {
        if (c.key === slot.selectedCoreKey) return true
        return !search || c.effects.some(e => e.toLowerCase().includes(search.toLowerCase())) || c.name.toLowerCase().includes(search.toLowerCase())
      }) : []

  // canBeCore slots always show golden C
  const badgeColor = slot.canBeCore ? LEGEND_GOLD : SLOT_TYPE_COLOR[slot.slotType]
  const badgeLabel = slot.canBeCore ? 'C' : SLOT_TYPE_LABEL[slot.slotType]

  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 9, padding: '9px 12px',
        background: isDuplicate ? '#2a1010' : '#191930',
        border: `1px solid ${isOpen ? accentColor : isDuplicate ? '#aa3333' : '#252545'}`,
        borderRadius: 6,
      }}>
        <div
          onClick={e => { e.stopPropagation(); if (!slot.canBeCore) onCycleType() }}
          title={slot.canBeCore ? 'Core talent slot' : `${slot.slotType} (click to cycle)`}
          style={{
            width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
            background: badgeColor, color: '#fff', fontSize: 11, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: slot.canBeCore ? 'default' : 'pointer',
          }}
        >{badgeLabel}</div>

        <div onClick={onTogglePicker} style={{ flex: 1, minWidth: 0, cursor: 'pointer' }}>
          {displayText
            ? <div style={{ lineHeight: 1.4 }}>
                {isDuplicate && <span style={{ fontSize: 11, color: '#cc4444' }}>[duplicate] </span>}
                {slot.coreName && (
                  <div style={{ fontSize: 13, fontWeight: 700, color: LEGEND_GOLD, marginBottom: 2 }}>{slot.coreName}</div>
                )}
                <div style={{ fontSize: 13, color: isDuplicate ? '#cc4444' : '#bbb' }}>{displayText}</div>
              </div>
            : <div style={{ fontSize: 13, color: '#404058', fontStyle: 'italic' }}>Empty Talent Node</div>
          }
        </div>

        {slot.canBeCore && (
          <div onClick={e => { e.stopPropagation(); onToggleCoreMode() }}
            title={slot.isCore ? 'Switch to modifier' : 'Switch to core talent'}
            style={{ fontSize: 14, color: slot.isCore ? LEGEND_GOLD : '#555', cursor: 'pointer', flexShrink: 0 }}>
            {slot.isCore ? '◈' : '◇'}
          </div>
        )}

        {(slot.selectedNodeId || slot.selectedCoreKey) && (
          <div onClick={e => { e.stopPropagation(); onClear() }}
            style={{ fontSize: 14, color: '#444', cursor: 'pointer', flexShrink: 0 }}>✕</div>
        )}
      </div>

      {isOpen && (
        <div style={{
          background: '#111128', border: `1px solid ${accentColor}55`,
          borderTop: 'none', borderRadius: '0 0 6px 6px', maxHeight: 260, overflowY: 'auto',
        }} onClick={e => e.stopPropagation()}>
          <div style={{ padding: '6px 9px', borderBottom: '1px solid #1e1e3a', position: 'sticky', top: 0, background: '#111128' }}>
            <input autoFocus value={search} onChange={e => onSearchChange(e.target.value)}
              placeholder="Search modifiers…"
              style={{ width: '100%', boxSizing: 'border-box', background: '#1a1a3a', border: '1px solid #2a2a5a', color: '#ddd', padding: '5px 9px', fontSize: 14, borderRadius: 3 }}
            />
          </div>
          {slot.isCore && pool && (
            coreOptions.length === 0
              ? <div style={{ padding: '11px 14px', fontSize: 14, color: '#444' }}>No core talents available</div>
              : coreOptions.map(core => {
                const selected = core.key === slot.selectedCoreKey
                return (
                  <div key={core.key} onClick={() => onSelectCore(core)} style={{
                    padding: '8px 14px', cursor: 'pointer', borderBottom: '1px solid #1a1a30',
                    background: selected ? `${accentColor}18` : 'transparent',
                    borderLeft: selected ? `2px solid ${accentColor}` : '2px solid transparent',
                    opacity: (!selected && usedCoreKeys.has(core.key)) ? 0.4 : 1,
                  }}>
                    <div style={{ fontSize: 14, color: selected ? '#fff' : '#bbb' }}>{core.name}</div>
                    {core.effects.map((e, i) => <div key={i} style={{ fontSize: 12, color: '#888' }}>{e}</div>)}
                    <div style={{ fontSize: 11, color: '#444', marginTop: 2 }}>{core.treeName}</div>
                  </div>
                )
              })
          )}
          {!slot.isCore && (
            modOptions.length === 0
              ? <div style={{ padding: '11px 14px', fontSize: 14, color: '#444' }}>
                  {pool ? 'No modifiers available' : 'No season active — no modifier pool'}
                </div>
              : modOptions.map(mod => {
                const selected = mod.nodeId === slot.selectedNodeId
                return (
                  <div key={mod.nodeId} onClick={() => onSelect(mod)} style={{
                    padding: '9px 14px', cursor: 'pointer', borderBottom: '1px solid #1a1a30',
                    background: selected ? `${accentColor}18` : 'transparent',
                    borderLeft: selected ? `2px solid ${accentColor}` : '2px solid transparent',
                  }}
                  onMouseEnter={e => { if (!selected) (e.currentTarget as HTMLElement).style.background = '#1e1e38' }}
                  onMouseLeave={e => { if (!selected) (e.currentTarget as HTMLElement).style.background = 'transparent' }}>
                    {mod.effects.map((ef, i) => <div key={i} style={{ fontSize: 14, color: selected ? '#fff' : '#ccc' }}>{ef}</div>)}
                    <div style={{ fontSize: 11, color: '#444', marginTop: 3 }}>{mod.treeName} · {mod.nodeType}</div>
                  </div>
                )
              })
          )}
        </div>
      )}
    </div>
  )
}

// ── Shape panel (right side) ──────────────────────────────────────────────────

function ShapePanel({ creator, treeColors, onRotate, onSelectOrientation, onSelectShape }: {
  creator: CreatorState; treeColors: Record<string, string>
  onRotate: () => void; onSelectOrientation: (i: number) => void; onSelectShape: (i: number) => void
}) {
  const { kind, orientationIndex, shapeIndex, treeType } = creator
  const color = kind === 'base'
    ? (treeType ? treeColors[treeType] ?? '#888' : '#888')
    : LEGENDARY_META[kind as LegendaryKind].color
  const count = getOrientationCount(kind)

  const legLabel = (idx: number) => {
    if (kind === 'pedigree') return idx === 0 ? '→ Right' : '← Left'
    if (kind === 'fallen_starlight') return idx === 0 ? '↔ H' : '↕ V'
    return ['↗','↘','↙','↖'][idx] ?? `${idx}`
  }

  return (
    <div style={{ width: 220, flexShrink: 0, background: '#12121e', borderLeft: '1px solid #2a2a4a', padding: '16px 14px', display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>
      {kind === 'base' ? (
        <>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#666', marginBottom: 8 }}>Shape</div>
            {BASE_SHAPES.map((shape, idx) => {
              const active = idx === shapeIndex
              return (
                <button key={idx} onClick={() => onSelectShape(idx)} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', width: '100%', marginBottom: 4,
                  background: active ? `${color}22` : '#1a1a3a', border: `1px solid ${active ? color : '#252540'}`,
                  borderRadius: 6, cursor: 'pointer',
                }}>
                  <div style={{ minWidth: 32, display: 'flex', justifyContent: 'center' }}>
                    <MiniShape offsets={shape.rotations[0] as [number,number][]} color={active ? color : '#484870'} size={12} />
                  </div>
                  <span style={{ fontSize: 14, color: active ? color : '#777' }}>{shape.label}</span>
                </button>
              )
            })}
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#666', marginBottom: 8 }}>Rotation</div>
            {BASE_SHAPES[shapeIndex].rotations.map((cells, idx) => {
              const active = idx === orientationIndex
              return (
                <button key={idx} onClick={() => onSelectOrientation(idx)} style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', width: '100%', marginBottom: 4,
                  background: active ? `${color}22` : '#1a1a3a', border: `1px solid ${active ? color : '#252540'}`,
                  borderRadius: 6, cursor: 'pointer',
                }}>
                  <div style={{ minWidth: 32, display: 'flex', justifyContent: 'center' }}>
                    <MiniShape offsets={cells as [number,number][]} color={active ? color : '#484870'} size={12} />
                  </div>
                  <span style={{ fontSize: 13, color: active ? color : '#777' }}>{ROTATION_LABELS[idx]}</span>
                </button>
              )
            })}
            <button onClick={onRotate} style={{ padding: '8px 12px', fontSize: 14, width: '100%', marginTop: 4, background: '#1e1e38', color: '#888', border: '1px solid #2a2a50', borderRadius: 6, cursor: 'pointer' }}>
              ↻ Rotate
            </button>
          </div>
        </>
      ) : (
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#666', marginBottom: 8 }}>
            {count > 1 ? 'Rotation' : 'Shape'}
          </div>
          {LEGENDARY_ORIENTATIONS[kind as LegendaryKind].map((offsets, idx) => {
            const active = idx === orientationIndex
            return (
              <button key={idx} onClick={() => onSelectOrientation(idx)} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', width: '100%', marginBottom: 4,
                background: active ? `${color}20` : '#1a1a3a', border: `1px solid ${active ? color : '#252540'}`,
                borderRadius: 6, cursor: 'pointer',
              }}>
                <div style={{ minWidth: 32, display: 'flex', justifyContent: 'center' }}>
                  <MiniShape offsets={offsets as [number,number][]} color={active ? color : '#484870'} size={12} />
                </div>
                <span style={{ fontSize: 14, color: active ? color : '#777' }}>{legLabel(idx)}</span>
              </button>
            )
          })}
          {count > 1 && (
            <button onClick={onRotate} style={{ padding: '8px 12px', fontSize: 14, marginTop: 4, width: '100%', background: '#1e1e38', color: '#888', border: '1px solid #2a2a50', borderRadius: 6, cursor: 'pointer' }}>
              ↻ Rotate
            </button>
          )}
          <div style={{ fontSize: 12, color: '#3a3a5a', marginTop: 4, lineHeight: 1.7 }}>
            {kind === 'pedigree' && 'Flip to mirror'}
            {kind === 'spark_of_moth_fire' && 'No rotation'}
            {kind === 'when_sparks_set_prairie_ablaze' && 'No rotation'}
            {kind === 'fallen_starlight' && 'H or V orientation'}
            {kind === 'corner_of_divinity' && '4 clockwise rotations'}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Hover tooltip (right panel, idle mode) ────────────────────────────────────

function HoverTooltip({ slate, treeColors, placed: allPlaced }: {
  slate: PlacedSlate; treeColors: Record<string, string>; placed: PlacedSlate[]
}) {
  const isMoth = slate.kind === 'spark_of_moth_fire'
  const isPrairie = slate.kind === 'when_sparks_set_prairie_ablaze'
  const color = slate.kind === 'base'
    ? (treeColors[slate.treeType ?? ''] ?? '#666')
    : LEGENDARY_META[slate.kind as LegendaryKind].color
  const label = slate.kind === 'base' ? 'Base Slate' : LEGENDARY_META[slate.kind as LegendaryKind].label

  const mothMod = isMoth ? getMothModifier(slate, allPlaced) : null
  const prairieMods = isPrairie ? getPrairieModifiers(slate, allPlaced) : []

  return (
    <div style={{
      width: 220, flexShrink: 0, background: '#12121e', borderLeft: '1px solid #2a2a4a',
      padding: '16px 14px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 700, color, marginBottom: 2 }}>{label}</div>
        {slate.treeType && <div style={{ fontSize: 11, color: '#666' }}>{slate.treeType}</div>}
      </div>

      {isMoth && (
        <div>
          <div style={{ fontSize: 11, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
            Copies {slate.mothDirection ?? '?'}
          </div>
          {mothMod
            ? <div style={{ fontSize: 12, color: '#ddd', lineHeight: 1.5 }}>{mothMod}</div>
            : <div style={{ fontSize: 12, color: '#3a3a5a', fontStyle: 'italic' }}>No adjacent slate</div>}
        </div>
      )}

      {isPrairie && (
        <div>
          <div style={{ fontSize: 11, color: '#555', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
            Copies {prairieMods.length} adjacent
          </div>
          {prairieMods.length > 0
            ? prairieMods.map((m, i) => <div key={i} style={{ fontSize: 12, color: '#ddd', lineHeight: 1.5, marginBottom: 3 }}>{m}</div>)
            : <div style={{ fontSize: 12, color: '#3a3a5a', fontStyle: 'italic' }}>No adjacent slates</div>}
        </div>
      )}

      {slate.slots.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {slate.slots.map((slot, i) => {
            const filled = !!(slot.selectedNodeId || slot.selectedCoreKey)
            const text = filled ? slot.effects.join(' / ') : null
            const badgeColor = slot.canBeCore ? LEGEND_GOLD : SLOT_TYPE_COLOR[slot.slotType]
            const badgeLabel = slot.canBeCore ? 'C' : SLOT_TYPE_LABEL[slot.slotType]
            return (
              <div key={i} style={{ display: 'flex', gap: 7, alignItems: 'flex-start', opacity: filled ? 1 : 0.28 }}>
                <div style={{
                  width: 18, height: 18, borderRadius: '50%', flexShrink: 0, marginTop: 2,
                  background: badgeColor, color: '#fff', fontSize: 9, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>{badgeLabel}</div>
                <div style={{ minWidth: 0 }}>
                  {slot.coreName && filled && (
                    <div style={{ fontSize: 12, fontWeight: 700, color: LEGEND_GOLD, marginBottom: 2 }}>{slot.coreName}</div>
                  )}
                  <div style={{ fontSize: 12, color: filled ? '#ccc' : '#3a3a5a', lineHeight: 1.5, fontStyle: filled ? 'normal' : 'italic' }}>
                    {text ?? 'Empty Talent Node'}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

interface Props { treeColors: Record<string, string>; onBack: () => void }

export default function SlateScreen({ treeColors, onBack }: Props) {
  const [placed, setPlaced] = useState<PlacedSlate[]>([])
  const [mode, setMode] = useState<PanelMode>({ type: 'idle' })
  const [hover, setHover] = useState<[number, number] | null>(null)
  const [hoverSlateId, setHoverSlateId] = useState<string | null>(null)
  const [dragSlate, setDragSlate] = useState<{ slate: PlacedSlate; startCell: [number, number] } | null>(null)
  const suppressNextClick = useRef(false)

  useEffect(() => {
    const handler = () => setMode(prev => {
      if (prev.type === 'idle') return prev
      return { ...prev, creator: { ...prev.creator, openPicker: null } }
    })
    window.addEventListener('click', handler)
    return () => window.removeEventListener('click', handler)
  }, [])

  // Global pointer-up: finish drag or open edit
  useEffect(() => {
    const handler = () => {
      if (!dragSlate) return
      suppressNextClick.current = true

      const sameCell = hover && hover[0] === dragSlate.startCell[0] && hover[1] === dragSlate.startCell[1]

      if (sameCell || !hover) {
        // Click on idle mode — open edit panel; in editing mode the panel is already open
        if (mode.type !== 'editing') {
          const slate = dragSlate.slate
          setMode({
            type: 'editing', slateId: slate.id, creator: {
              kind: slate.kind, shapeIndex: slate.shapeIndex, treeType: slate.treeType ?? null,
              slots: slate.slots.map(s => ({ ...s })), orientationIndex: slate.orientationIndex,
              pool: slate.pool ?? null, poolLoading: false, openPicker: null, pickerSearch: '',
              mothDirection: slate.mothDirection ?? null,
            },
          })
        }
      } else if (hover) {
        // Drag — move to new position (allow anywhere within grid bounds); mode stays unchanged
        const { slate } = dragSlate
        const anchor = centeredAnchor(slate.kind, slate.shapeIndex, slate.orientationIndex, hover)
        const cells = anchorCells(slate.kind, slate.shapeIndex, slate.orientationIndex, anchor)
        if (cells.every(([r, c]) => r >= 0 && r < BOARD_ROWS && c >= 0 && c < BOARD_COLS)) {
          setPlaced(prev => prev.map(s => s.id === slate.id ? { ...s, cells, anchor } : s))
        }
      }

      setDragSlate(null)
    }
    window.addEventListener('pointerup', handler)
    return () => window.removeEventListener('pointerup', handler)
  }, [dragSlate, hover, placed, mode])

  // Right-click anywhere exits editing/creating mode (saves editing state)
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (mode.type === 'idle') return
      e.preventDefault()
      if (mode.type === 'editing') {
        const { slateId, creator: c } = mode
        setPlaced(prev => prev.map(s => s.id !== slateId ? s : {
          ...s, slots: c.slots.map(sl => ({ ...sl })),
          pool: c.pool ?? s.pool, treeType: c.treeType ?? s.treeType,
          mothDirection: c.mothDirection ?? s.mothDirection,
          orientationIndex: c.orientationIndex, shapeIndex: c.shapeIndex,
        }))
      }
      setMode({ type: 'idle' })
    }
    window.addEventListener('contextmenu', handler)
    return () => window.removeEventListener('contextmenu', handler)
  }, [mode])

  const creator = mode.type !== 'idle' ? mode.creator : null
  const editingSlateId = mode.type === 'editing' ? mode.slateId : null

  // Instantly apply rotation/shape changes to the placed slate while editing
  const editOrientIdx = mode.type === 'editing' ? mode.creator.orientationIndex : null
  const editShapeIdx = mode.type === 'editing' ? mode.creator.shapeIndex : null
  useEffect(() => {
    if (editOrientIdx === null || editShapeIdx === null || !editingSlateId) return
    setPlaced(prev => prev.map(s => {
      if (s.id !== editingSlateId) return s
      const cells = anchorCells(s.kind, editShapeIdx, editOrientIdx, s.anchor)
      if (!cells.every(([r, c]) => r >= 0 && r < BOARD_ROWS && c >= 0 && c < BOARD_COLS)) return s
      return { ...s, cells, orientationIndex: editOrientIdx, shapeIndex: editShapeIdx }
    }))
  }, [editOrientIdx, editShapeIdx, editingSlateId])

  // Build occupied map (skip slate being edited or dragged)
  const occupied = new Map<string, string>()
  for (const s of placed) {
    if (s.id === editingSlateId) continue
    if (dragSlate && s.id === dragSlate.slate.id) continue
    for (const [r, c] of s.cells) occupied.set(`${r},${c}`, s.id)
  }

  // Ghost cells — only during creating mode or drag (not while editing an existing slate)
  let ghostCells: [number, number][] = []
  if (hover) {
    if (creator && mode.type === 'creating') {
      const anchor = centeredAnchor(creator.kind, creator.shapeIndex, creator.orientationIndex, hover)
      ghostCells = anchorCells(creator.kind, creator.shapeIndex, creator.orientationIndex, anchor)
    } else if (dragSlate) {
      const { slate } = dragSlate
      const anchor = centeredAnchor(slate.kind, slate.shapeIndex, slate.orientationIndex, hover)
      ghostCells = anchorCells(slate.kind, slate.shapeIndex, slate.orientationIndex, anchor)
    }
  }
  const ghostSet = new Set(ghostCells.map(([r, c]) => `${r},${c}`))

  // Per-cell ghost validity: valid board cell AND not occupied by another slate
  const ghostValidCells = new Set<string>()
  for (const [r, c] of ghostCells) {
    if (isValidCell(r, c) && !occupied.has(`${r},${c}`)) ghostValidCells.add(`${r},${c}`)
  }

  // All placed cells for rendering (first slate wins per cell)
  const placedCellMap = new Map<string, string>()
  for (const s of placed) {
    for (const [r, c] of s.cells) {
      const k = `${r},${c}`
      if (!placedCellMap.has(k)) placedCellMap.set(k, s.id)
    }
  }

  // Conflicted cells: out-of-bounds board cell OR overlapping slates
  const conflictedCells = new Set<string>()
  {
    const cellSlates = new Map<string, string[]>()
    for (const s of placed) {
      for (const [r, c] of s.cells) {
        const k = `${r},${c}`
        if (!isValidCell(r, c)) conflictedCells.add(k)
        if (!cellSlates.has(k)) cellSlates.set(k, [])
        cellSlates.get(k)!.push(s.id)
      }
    }
    for (const [k, ids] of cellSlates) if (ids.length > 1) conflictedCells.add(k)
  }
  const boardIsValid = conflictedCells.size === 0

  const editingCells = new Set((editingSlateId ? placed.find(s => s.id === editingSlateId)?.cells : null)?.map(([r, c]) => `${r},${c}`) ?? [])
  const hoverSlateCells = new Set(!dragSlate && !creator && hoverSlateId
    ? (placed.find(s => s.id === hoverSlateId)?.cells ?? []).map(([r, c]) => `${r},${c}`)
    : [])
  const hoverSlate = !creator && !dragSlate && hoverSlateId
    ? placed.find(s => s.id === hoverSlateId) ?? null
    : null

  // ── Creator helpers ─────────────────────────────────────────────────────────

  function updateCreator(patch: Partial<CreatorState>) {
    setMode(prev => prev.type === 'idle' ? prev : { ...prev, creator: { ...prev.creator, ...patch } })
  }

  async function loadTreePool(tree: PrimaryTree) {
    updateCreator({ treeType: tree, poolLoading: true, pool: null })
    try { updateCreator({ pool: await api.getSlatePool(tree), poolLoading: false }) }
    catch { updateCreator({ poolLoading: false }) }
  }

  function startCreating(kind: SlateKind) {
    const initial = defaultCreator(kind)
    if (kind === 'base') initial.treeType = PRIMARY_TREES[0]
    if (kind === 'spark_of_moth_fire') initial.mothDirection = 'above'
    setMode({ type: 'creating', creator: initial })
    if (kind === 'base') {
      setTimeout(() => {
        setMode(prev => prev.type === 'idle' ? prev : { ...prev, creator: { ...prev.creator, poolLoading: true } })
        api.getSlatePool(PRIMARY_TREES[0])
          .then(pool => setMode(prev => prev.type === 'idle' ? prev : { ...prev, creator: { ...prev.creator, pool, poolLoading: false } }))
          .catch(() => setMode(prev => prev.type === 'idle' ? prev : { ...prev, creator: { ...prev.creator, poolLoading: false } }))
      }, 0)
    } else if (SLOT_CONFIG[kind].poolScope === 'all') {
      setTimeout(() => {
        setMode(prev => prev.type === 'idle' ? prev : { ...prev, creator: { ...prev.creator, poolLoading: true } })
        api.getSlatePoolAll()
          .then(pool => setMode(prev => prev.type === 'idle' ? prev : { ...prev, creator: { ...prev.creator, pool, poolLoading: false } }))
          .catch(() => setMode(prev => prev.type === 'idle' ? prev : { ...prev, creator: { ...prev.creator, poolLoading: false } }))
      }, 0)
    }
  }

  function updateSlot(idx: number, patch: Partial<CreatorSlot>) {
    if (!creator) return
    updateCreator({ slots: creator.slots.map((s, i) => i === idx ? { ...s, ...patch } : s) })
  }

  function handleCycleSlotType(idx: number) {
    if (!creator) return
    const slot = creator.slots[idx]
    updateSlot(idx, { slotType: cycleSlotType(slot.slotType, slot.maxType), selectedNodeId: null, selectedCoreKey: null, coreName: null, effects: [], isCore: false })
  }

  function handleTogglePicker(idx: number) {
    updateCreator({ openPicker: creator?.openPicker === idx ? null : idx, pickerSearch: '' })
  }

  function handleSelectModifier(idx: number, mod: SlateModifierOption) {
    updateSlot(idx, { selectedNodeId: mod.nodeId, selectedCoreKey: null, effects: mod.effects })
    updateCreator({ openPicker: null })
  }

  function handleSelectCore(idx: number, core: CoreTalentOption) {
    updateSlot(idx, { selectedCoreKey: core.key, selectedNodeId: null, coreName: core.name, effects: core.effects })
    updateCreator({ openPicker: null })
  }

  function handleToggleCoreMode(idx: number) {
    if (!creator) return
    const slot = creator.slots[idx]
    updateSlot(idx, { isCore: !slot.isCore, selectedNodeId: null, selectedCoreKey: null, effects: [] })
  }

  function handleRotate() {
    if (!creator) return
    updateCreator({ orientationIndex: (creator.orientationIndex + 1) % getOrientationCount(creator.kind) })
  }

  // ── Board interactions ──────────────────────────────────────────────────────

  function handleCellPointerDown(row: number, col: number) {
    if (mode.type === 'creating') return
    if (mode.type === 'editing') {
      const editingSlate = placed.find(s => s.id === editingSlateId)
      if (!editingSlate) return
      if (!editingSlate.cells.some(([r, c]) => r === row && c === col)) return
      setDragSlate({ slate: editingSlate, startCell: [row, col] })
      return
    }
    const slateId = occupied.get(`${row},${col}`)
    if (!slateId) return
    const slate = placed.find(s => s.id === slateId)
    if (!slate) return
    setDragSlate({ slate, startCell: [row, col] })
  }

  function handleCellClick(row: number, col: number) {
    if (suppressNextClick.current) { suppressNextClick.current = false; return }
    if (!creator) return
    if (mode.type === 'editing') return

    const anchor = centeredAnchor(creator.kind, creator.shapeIndex, creator.orientationIndex, [row, col])
    const cells = anchorCells(creator.kind, creator.shapeIndex, creator.orientationIndex, anchor)
    if (!cells.every(([r, c]) => r >= 0 && r < BOARD_ROWS && c >= 0 && c < BOARD_COLS)) return

    setPlaced(prev => [...prev, {
      id: `${Date.now()}-${Math.random()}`, kind: creator.kind, cells, anchor,
      orientationIndex: creator.orientationIndex, shapeIndex: creator.shapeIndex,
      slots: creator.slots.map(s => ({ ...s })),
      pool: creator.pool ?? undefined, treeType: creator.treeType ?? undefined,
      mothDirection: creator.mothDirection ?? undefined,
    }])
    setMode({ type: 'idle' })
  }

  function handleRemoveSlate(id: string) {
    setPlaced(prev => prev.filter(s => s.id !== id))
    if (editingSlateId === id) setMode({ type: 'idle' })
  }

  function handleDoneEditing() {
    if (!creator || mode.type !== 'editing') return
    setPlaced(prev => prev.map(s => s.id !== editingSlateId ? s : {
      ...s, slots: creator.slots.map(sl => ({ ...sl })),
      pool: creator.pool ?? s.pool, treeType: creator.treeType ?? s.treeType,
      mothDirection: creator.mothDirection ?? s.mothDirection,
      orientationIndex: creator.orientationIndex, shapeIndex: creator.shapeIndex,
    }))
    setMode({ type: 'idle' })
  }

  const usedCells = placed.reduce((n, s) => n + s.cells.length, 0)

  // ── Left panel ──────────────────────────────────────────────────────────────

  function renderCreatorPanel() {
    if (!creator) return null
    const { kind, treeType, slots, pool, poolLoading, openPicker, pickerSearch, mothDirection } = creator
    const accentColor = kind === 'base'
      ? (treeType ? treeColors[treeType] ?? '#888' : '#888')
      : LEGENDARY_META[kind as LegendaryKind].color
    const sections = getSections(kind)
    const showDividers = kind === 'base'

    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }} onClick={e => e.stopPropagation()}>

        {/* Large Done button — editing mode only, at the top */}
        {mode.type === 'editing' && (
          <button onClick={handleDoneEditing} style={{
            width: '100%', padding: '13px 16px', marginBottom: 12, flexShrink: 0,
            fontSize: 17, fontWeight: 700, letterSpacing: 0.5,
            background: '#1a4a1a', color: '#5fdf5f',
            border: '2px solid #2d8a2d', borderRadius: 7, cursor: 'pointer',
          }}>
            ✓ Done Editing
          </button>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexShrink: 0 }}>
          <button onClick={() => setMode({ type: 'idle' })}
            style={{ fontSize: 13, color: '#666', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
            {mode.type === 'editing' ? '✕ Close' : '← Cancel'}
          </button>
          <span style={{ fontSize: 17, fontWeight: 700, color: kind === 'base' ? '#ccc' : accentColor }}>
            {kind === 'base' ? 'Base Slate' : LEGENDARY_META[kind as LegendaryKind].label}
          </span>
          {mode.type === 'editing' && (
            <span style={{ marginLeft: 'auto', fontSize: 11, color: '#444' }}>right-click to close</span>
          )}
        </div>

        {kind === 'base' && (
          <div style={{ marginBottom: 14, flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#555', marginBottom: 7 }}>Tree Branch</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
              {PRIMARY_TREES.map(tree => {
                const tc = treeColors[tree] ?? '#888'
                const active = treeType === tree
                return (
                  <button key={tree} onClick={() => { if (!active) loadTreePool(tree) }} style={{
                    padding: '6px 7px', fontSize: 13, textAlign: 'left',
                    background: active ? `${tc}22` : '#1a1a3a', color: active ? tc : '#666',
                    border: `1px solid ${active ? tc : '#252545'}`, borderRadius: 4, cursor: 'pointer',
                  }}>
                    {tree.replace('Goddess of ', '').replace('God of ', '')}
                  </button>
                )
              })}
            </div>
            {poolLoading && <div style={{ fontSize: 13, color: '#555', marginTop: 6 }}>Loading modifiers…</div>}
          </div>
        )}

        {kind !== 'base' && poolLoading && (
          <div style={{ fontSize: 13, color: '#555', marginBottom: 10, flexShrink: 0 }}>Loading modifiers…</div>
        )}

        {kind === 'spark_of_moth_fire' && (
          <div style={{ marginBottom: 14, flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#555', marginBottom: 7 }}>Copy Direction</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
              {(['above', 'below', 'left', 'right'] as MothDirection[]).map(dir => {
                const active = mothDirection === dir
                const icon = { above: '↑', below: '↓', left: '←', right: '→' }[dir]
                return (
                  <button key={dir} onClick={() => updateCreator({ mothDirection: dir })} style={{
                    padding: '7px 8px', fontSize: 14,
                    background: active ? `${LEGEND_GOLD}22` : '#1a1a3a', color: active ? LEGEND_GOLD : '#777',
                    border: `1px solid ${active ? LEGEND_GOLD : '#252545'}`, borderRadius: 5, cursor: 'pointer',
                  }}>
                    {icon} {dir.charAt(0).toUpperCase() + dir.slice(1)}
                  </button>
                )
              })}
            </div>
            {!mothDirection && <div style={{ fontSize: 12, color: '#555', marginTop: 7 }}>Select direction before placing</div>}
          </div>
        )}

        {kind === 'when_sparks_set_prairie_ablaze' && (
          <div style={{ fontSize: 13, color: '#666', lineHeight: 1.7, marginBottom: 12 }}>
            Copies the bottom modifier of each adjacent slate (up to 4).
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {sections.map(({ label, indices }) => (
            <div key={label} style={{ marginBottom: 10 }}>
              {showDividers && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <div style={{ flex: 1, height: 1, background: '#252545' }} />
                  <span style={{ fontSize: 10, fontWeight: 700, color: '#4a4a6a', textTransform: 'uppercase', letterSpacing: 0.5, whiteSpace: 'nowrap' }}>{label}</span>
                  <div style={{ flex: 1, height: 1, background: '#252545' }} />
                </div>
              )}
              {indices.map(idx => (
                <ModifierSlot key={idx} slot={slots[idx]} index={idx} allSlots={slots} pool={pool}
                  isOpen={openPicker === idx} search={openPicker === idx ? pickerSearch : ''}
                  accentColor={accentColor}
                  onTogglePicker={() => handleTogglePicker(idx)}
                  onCycleType={() => handleCycleSlotType(idx)}
                  onSelect={mod => handleSelectModifier(idx, mod)}
                  onSelectCore={core => handleSelectCore(idx, core)}
                  onClear={() => updateSlot(idx, { selectedNodeId: null, selectedCoreKey: null, coreName: null, effects: [] })}
                  onToggleCoreMode={() => handleToggleCoreMode(idx)}
                  onSearchChange={s => updateCreator({ pickerSearch: s })}
                />
              ))}
            </div>
          ))}
        </div>

        {mode.type === 'editing' && (
          <button onClick={() => handleRemoveSlate(editingSlateId!)}
            style={{ marginTop: 10, padding: '12px 16px', fontSize: 15, fontWeight: 600, background: '#3a1010', color: '#dd5555', border: '1px solid #6a2020', borderRadius: 7, cursor: 'pointer', flexShrink: 0, width: '100%' }}>
            ⊗ Remove Slate
          </button>
        )}
      </div>
    )
  }

  function renderIdlePanel() {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#555', marginBottom: 10 }}>Add Slate</div>

        {/* Base Slate */}
        <button onClick={() => startCreating('base')} style={{
          width: '100%', padding: '11px 14px', marginBottom: 6, textAlign: 'left',
          background: '#1a1a3a', border: '1px solid #2a2a50', borderRadius: 7,
          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14,
        }}>
          <div style={{ flexShrink: 0, minWidth: 36, display: 'flex', justifyContent: 'center' }}>
            <MiniShape offsets={PREVIEW_CELLS.base} color='#6060aa' size={15} />
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#ccc', marginBottom: 3 }}>+ Base Slate</div>
            <div style={{ fontSize: 12, color: '#555' }}>{SLATE_DESCRIPTIONS.base}</div>
          </div>
        </button>

        {/* Legendary slates */}
        {(Object.entries(LEGENDARY_META) as [LegendaryKind, typeof LEGENDARY_META[LegendaryKind]][]).map(([kind, meta]) => (
          <button key={kind} onClick={() => startCreating(kind)} style={{
            width: '100%', padding: '11px 14px', marginBottom: 6, textAlign: 'left',
            background: '#1a1a3a', border: `1px solid #252540`, borderLeft: `3px solid ${meta.color}`,
            borderRadius: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 14,
          }}>
            <div style={{ flexShrink: 0, minWidth: 36, display: 'flex', justifyContent: 'center' }}>
              <MiniShape offsets={PREVIEW_CELLS[kind]} color={meta.color} size={15} />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: meta.color, marginBottom: 3 }}>+ {meta.label}</div>
              <div style={{ fontSize: 12, color: '#555' }}>{SLATE_DESCRIPTIONS[kind]}</div>
            </div>
          </button>
        ))}

        {placed.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: '#555', marginBottom: 7 }}>Placed Slates</div>
            {placed.map(slate => {
              const color = slate.kind === 'base'
                ? (treeColors[slate.treeType ?? ''] ?? '#666')
                : LEGENDARY_META[slate.kind as LegendaryKind].color
              const label = slate.kind === 'base'
                ? (slate.treeType ?? 'Base Slate')
                : LEGENDARY_META[slate.kind as LegendaryKind].label
              const filled = slate.slots.filter(s => s.selectedNodeId || s.selectedCoreKey).length
              return (
                <div key={slate.id} style={{
                  display: 'flex', alignItems: 'center', gap: 7, padding: '6px 10px', marginBottom: 4,
                  background: '#191929', border: `1px solid ${color}44`, borderRadius: 5,
                }}>
                  <div style={{ width: 9, height: 9, borderRadius: '50%', background: color, flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: 13, color: '#aaa', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
                  {slate.slots.length > 0 && (
                    <span style={{ fontSize: 12, color: filled === slate.slots.length ? color : '#555' }}>{filled}/{slate.slots.length}</span>
                  )}
                  <button onClick={() => handleRemoveSlate(slate.id)}
                    style={{ fontSize: 13, color: '#444', background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px' }}>✕</button>
                </div>
              )
            })}
          </div>
        )}

        {placed.length === 0 && (
          <div style={{ marginTop: 12, fontSize: 13, color: '#333', lineHeight: 1.8 }}>
            Select a slate type to begin.<br />
            Drag placed slates to move, click to edit.
          </div>
        )}
      </div>
    )
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const ghostColor = creator
    ? (creator.kind === 'base' && creator.treeType ? treeColors[creator.treeType] ?? '#888'
        : creator.kind !== 'base' ? LEGENDARY_META[creator.kind as LegendaryKind].color : '#888')
    : dragSlate
      ? (dragSlate.slate.kind === 'base' ? treeColors[dragSlate.slate.treeType ?? ''] ?? '#888'
          : LEGENDARY_META[dragSlate.slate.kind as LegendaryKind].color)
      : '#888'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#0e0e1e', color: '#e0e0e0', userSelect: 'none' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid #2a2a4a', background: '#1a1a2e', flexShrink: 0 }}>
        <button className="btn-back" onClick={onBack}>← Back</button>
        <h2 style={{ margin: 0, fontSize: 18, color: '#c0a0ff' }}>Slate Board</h2>
        <span style={{ marginLeft: 'auto', fontSize: 13, color: '#555' }}>{usedCells} / {TOTAL_CELLS} cells</span>
        {placed.length > 0 && !creator && !dragSlate && (
          <span style={{ fontSize: 12, fontWeight: 600, color: boardIsValid ? '#4ab87a' : '#f05555' }}>
            {boardIsValid ? '✓ Valid' : '⚠ Conflicts'}
          </span>
        )}
        {(creator || dragSlate) && (
          <span style={{ fontSize: 12, color: '#555' }}>
            {dragSlate ? 'Dragging — release to place'
              : mode.type === 'editing' ? 'Right-click or Done to finish'
              : 'Click board to place'}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left panel */}
        <div style={{ width: 320, flexShrink: 0, background: '#12121e', borderRight: '1px solid #2a2a4a', padding: '14px 16px', display: 'flex', flexDirection: 'column' }}>
          {creator ? renderCreatorPanel() : renderIdlePanel()}
        </div>

        {/* Board */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${BOARD_COLS}, ${CELL}px)`, gridTemplateRows: `repeat(${BOARD_ROWS}, ${CELL}px)`, gap: 4 }}>
            {Array.from({ length: BOARD_ROWS }, (_, row) =>
              Array.from({ length: BOARD_COLS }, (_, col) => {
                const key = `${row},${col}`
                const valid = isValidCell(row, col)
                const isGhost = ghostSet.has(key)
                const isPlacedHere = placedCellMap.has(key)
                if (!valid && !isGhost && !isPlacedHere) return <div key={key} style={{ width: CELL, height: CELL }} />

                const slateId = placedCellMap.get(key) ?? null
                const slate = slateId ? placed.find(s => s.id === slateId) : null
                const isDragging = dragSlate && dragSlate.slate.cells.some(([r, c]) => r === row && c === col)
                const isEditing = editingCells.has(key)
                const isHovered = hoverSlateCells.has(key)
                const isConflicted = conflictedCells.has(key)
                const isGhostValid = ghostValidCells.has(key)
                const sColor = slate
                  ? (slate.kind === 'base' ? treeColors[slate.treeType ?? ''] ?? '#666' : LEGENDARY_META[slate.kind as LegendaryKind].color)
                  : null
                const isSelected = slate?.id === editingSlateId

                const bg = isGhost
                  ? (isGhostValid ? `${ghostColor}28` : '#ff444418')
                  : isDragging ? (valid ? '#15152a' : 'transparent')
                  : isConflicted ? '#ff222218'
                  : isEditing ? `${sColor}40`
                  : sColor ? `${sColor}22` : (valid ? '#15152a' : 'transparent')

                const borderColor = isGhost
                  ? (isGhostValid ? ghostColor : '#ff4444')
                  : isDragging ? (valid ? '#1e1e3a' : 'transparent')
                  : isConflicted ? '#cc3333'
                  : isHovered ? '#9090b8'
                  : isEditing || isSelected ? (sColor ?? '#888')
                  : sColor ? `${sColor}88` : (valid ? '#1e1e3a' : 'transparent')

                const isPrairie = slate?.kind === 'when_sparks_set_prairie_ablaze'
                const isMoth = slate?.kind === 'spark_of_moth_fire'
                const prairieMods = isPrairie ? getPrairieModifiers(slate!, placed) : []
                const mothMod = isMoth ? getMothModifier(slate!, placed) : null

                return (
                  <div key={key}
                    onClick={() => handleCellClick(row, col)}
                    onPointerDown={() => handleCellPointerDown(row, col)}
                    onMouseEnter={() => {
                      setHover([row, col])
                      if (!creator && !dragSlate && slateId) setHoverSlateId(slateId)
                      else if (!slateId) setHoverSlateId(null)
                    }}
                    onMouseLeave={() => { setHover(null); setHoverSlateId(null) }}
                    style={{
                      width: CELL, height: CELL, boxSizing: 'border-box',
                      background: bg, border: `2px solid ${borderColor}`, borderRadius: 6,
                      cursor: (creator && mode.type === 'creating') ? 'crosshair' : dragSlate ? 'grabbing' : slate ? 'grab' : 'default',
                      transition: 'border-color 60ms, background 60ms',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end',
                      padding: '3px 2px', position: 'relative', overflow: 'hidden',
                      boxShadow: (isPlacedHere && !isGhost && !isDragging) ? 'inset 0 0 0 2px rgba(0,0,0,0.88)' : undefined,
                    }}
                  >
                    {isPrairie && prairieMods.length > 0 && (
                      <div style={{ fontSize: 8, color: PRAIRIE_PINK, textAlign: 'center' }}>×{prairieMods.length}</div>
                    )}
                    {isMoth && (
                      <div style={{ fontSize: 9, color: LEGEND_GOLD }}>
                        {slate?.mothDirection ? { above: '↑', below: '↓', left: '←', right: '→' }[slate.mothDirection] : '?'}
                        {mothMod ? ' ✓' : ''}
                      </div>
                    )}
                    {sColor && slate && !isDragging && slate.cells[0]?.[0] === row && slate.cells[0]?.[1] === col && !isPrairie && !isMoth && (
                      <span style={{ fontSize: 9, color: `${sColor}bb`, textAlign: 'center', lineHeight: 1.1 }}>
                        {slate.kind === 'base'
                          ? slate.treeType?.split(' ').pop()
                          : LEGENDARY_META[slate.kind as LegendaryKind].label.split(' ')[0]}
                      </span>
                    )}
                  </div>
                )
              })
            ).flat()}
          </div>
        </div>

        {/* Right panel: shape picker when creating/editing, always-visible info panel when idle */}
        {creator ? (
          <ShapePanel
            creator={creator} treeColors={treeColors}
            onRotate={handleRotate}
            onSelectOrientation={idx => updateCreator({ orientationIndex: idx })}
            onSelectShape={idx => updateCreator({ shapeIndex: idx, orientationIndex: 0 })}
          />
        ) : (
          hoverSlate
            ? <HoverTooltip slate={hoverSlate} treeColors={treeColors} placed={placed} />
            : <div style={{ width: 220, flexShrink: 0, background: '#12121e', borderLeft: '1px solid #2a2a4a' }} />
        )}
      </div>
    </div>
  )
}
