import { useState } from 'react'
import {
  iconUrl, PrismCatalogItem, CraftedPrism, PlacedPrism, PrismRolls,
  EtherealCatalog, EtherealCatalogItem, EtherealConfig, PrismRarity,
} from '../api/client'

// Overlay over the tree: prism inventory + an edit/craft view. Clicking an inventory prism (or the placed prism
// on the tree) opens it for editing with a Place button; "+ Craft a new prism" first picks the prism item, then
// opens that item's craft form. Inverse Image keeps its 3-roll form; Ethereal Prisms get the full affix picker
// (implicit + 1–3 random-affix slots) with a per-item rarity rule.

interface Props {
  items: PrismCatalogItem[]            // raw catalog items (Inverse Image + Ethereal) — for icons/names
  ethereal: EtherealCatalog | null     // Ethereal crafting pools
  inventory: CraftedPrism[]
  setInventory: (inv: CraftedPrism[]) => void
  onPlace: (p: CraftedPrism) => void
  onClose: () => void
  editPlaced?: PlacedPrism | null
  onUpdatePlaced?: (patch: { rolls?: PrismRolls; ethereal?: EtherealConfig }) => void
  onRemovePlaced?: () => void
}

const TIERS: { key: keyof PrismRolls; label: string }[] = [
  { key: 'micro', label: 'Micro Talent Effects' },
  { key: 'medium', label: 'Medium Talent Effects' },
  { key: 'legendary', label: 'Legendary Medium Talent Effects' },
]
const DEFAULT_RANGES = { micro: [-100, 200], medium: [-100, 100], legendary: [-100, 50] } as const
const OFF_ROLLS: PrismRolls = { micro: -100, medium: -100, legendary: -100 }

// Purple recolor of the gold/epic art for a rare-variant named prism (we only ship the epic icons).
export const RARE_TINT = 'sepia(1) saturate(4) hue-rotate(230deg) brightness(0.95)'

function newId(): string {
  return `${Date.now()}-${Math.floor(performance.now() * 1000) % 1000000}`
}

// ── Ethereal draft (the in-progress craft) ──────────────────────────────────
type EthDraft = {
  item: EtherealCatalogItem
  rarity: PrismRarity
  implicit: string
  areaSize?: string
  middle?: string
  advanced?: string
}

function draftFromConfig(item: EtherealCatalogItem, cfg: EtherealConfig): EthDraft {
  return { item, rarity: cfg.rarity, implicit: cfg.implicit,
    areaSize: cfg.areaSize, middle: cfg.middle, advanced: cfg.advanced }
}
function freshDraft(item: EtherealCatalogItem): EthDraft {
  const implicit = item.implicit.kind === 'add_choice'
    ? (item.implicit.options?.[0] ?? '') : (item.implicit.text ?? '')
  return { item, rarity: item.default_rarity, implicit }
}

type EditTarget =
  | { kind: 'inverse_image'; rolls: PrismRolls; source: 'new' | 'inventory' | 'placed'; id?: string }
  | { kind: 'ethereal_prism'; draft: EthDraft; source: 'new' | 'inventory' | 'placed'; id?: string }

export default function PrismOverlay({ items, ethereal, inventory, setInventory, onPlace, onClose,
  editPlaced, onUpdatePlaced, onRemovePlaced }: Props) {
  const inverse = items.find(c => c.kind === 'inverse_image')
  const ranges = inverse?.roll_ranges ?? DEFAULT_RANGES

  const ethItem = (shortName: string) => ethereal?.items.find(i => i.short_name === shortName)
  const initialEdit: EditTarget | null = editPlaced
    ? editPlaced.kind === 'ethereal_prism' && editPlaced.ethereal && ethItem(editPlaced.ethereal.shortName)
      ? { kind: 'ethereal_prism', draft: draftFromConfig(ethItem(editPlaced.ethereal.shortName)!, editPlaced.ethereal), source: 'placed', id: editPlaced.id }
      : { kind: 'inverse_image', rolls: { ...editPlaced.rolls }, source: 'placed', id: editPlaced.id }
    : null

  const [edit, setEdit] = useState<EditTarget | null>(initialEdit)
  const [picking, setPicking] = useState(false)   // the "choose a prism item" step
  const [tip, setTip] = useState<CraftedPrism | null>(null)

  // ── Inverse Image roll editing ─────────────────────────────────────────────
  const clamp = (k: keyof PrismRolls, v: number) => {
    const [lo, hi] = ranges[k]
    return Math.max(lo, Math.min(hi, Math.round(v)))
  }
  const setRoll = (k: keyof PrismRolls, v: number) =>
    setEdit(e => e && e.kind === 'inverse_image' ? { ...e, rolls: { ...e.rolls, [k]: clamp(k, v) } } : e)

  // ── Build a CraftedPrism from the current edit ─────────────────────────────
  const buildInverse = (rolls: PrismRolls, id = newId()): CraftedPrism => ({
    id, kind: 'inverse_image', name: inverse?.name ?? 'Inverse Image', iconUrl: inverse?.icon_url ?? '', rolls,
  })
  const buildEthereal = (d: EthDraft, id = newId()): CraftedPrism => {
    const area = ethereal?.area_size.find(a => a.modifier === d.areaSize)
    const cfg: EtherealConfig = {
      shortName: d.item.short_name, rarity: d.rarity, implicit: d.implicit,
      tintWhenRare: d.item.tint_when_rare,
      areaSize: d.areaSize, boxCols: area?.cols, boxRows: area?.rows,
      middle: d.middle, advanced: d.rarity === 'legendary' ? d.advanced : undefined,
    }
    return { id, kind: 'ethereal_prism', name: d.item.name, iconUrl: d.item.icon_url, rolls: OFF_ROLLS, ethereal: cfg }
  }
  const buildFromEdit = (e: EditTarget, id?: string): CraftedPrism =>
    e.kind === 'inverse_image' ? buildInverse(e.rolls, id) : buildEthereal(e.draft, id)

  const saveToInventory = () => {
    if (!edit) return
    const id = edit.source === 'inventory' && edit.id ? edit.id : newId()
    const item = buildFromEdit(edit, id)
    setInventory([...inventory.filter(p => p.id !== id), item])
    setEdit(null)
  }
  const placeFromEdit = () => {
    if (!edit) return
    const item = buildFromEdit(edit, edit.id)
    setInventory([...inventory.filter(p => p.id !== item.id), item])
    onPlace(item)
  }
  const savePlaced = () => {
    if (!edit || !onUpdatePlaced) return
    if (edit.kind === 'inverse_image') onUpdatePlaced({ rolls: edit.rolls })
    else onUpdatePlaced({ ethereal: buildEthereal(edit.draft).ethereal })
    onClose()
  }
  const remove = (id: string) => setInventory(inventory.filter(p => p.id !== id))

  const editInventory = (p: CraftedPrism) => {
    if (p.kind === 'ethereal_prism' && p.ethereal && ethItem(p.ethereal.shortName))
      setEdit({ kind: 'ethereal_prism', draft: draftFromConfig(ethItem(p.ethereal.shortName)!, p.ethereal), source: 'inventory', id: p.id })
    else
      setEdit({ kind: 'inverse_image', rolls: { ...p.rolls }, source: 'inventory', id: p.id })
  }

  const headerTitle = edit
    ? (edit.source === 'placed' ? 'Edit Installed Prism' : edit.source === 'new' ? 'Craft Prism' : 'Edit Prism')
    : picking ? 'Choose a Prism' : 'Prisms'

  return (
    <div className="prism-overlay-backdrop" onClick={onClose}
      style={{ position: 'absolute', inset: 0, background: 'rgba(8,10,20,0.78)', zIndex: 40, display: 'flex',
        alignItems: 'flex-start', justifyContent: 'center', paddingTop: 56 }}>
      {/* Anchored to the top so the hover-tooltip grows DOWNWARD (a centered panel reflows the grid up → flicker). */}
      <div className="prism-overlay-panel" onClick={e => e.stopPropagation()}
        style={{ background: '#12141f', border: '1px solid #2a2e44', borderRadius: 10, width: 600, maxWidth: '92%',
          maxHeight: '84%', overflow: 'auto', boxShadow: '0 12px 40px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', borderBottom: '1px solid #2a2e44' }}>
          <span style={{ fontWeight: 600, color: '#cfd3ee' }}>{headerTitle}</span>
          <div style={{ display: 'flex', gap: 8 }}>
            {!edit && !picking && (
              <button className="btn btn-sm" style={{ background: '#1c2a44', color: '#9fc0ff' }}
                onClick={() => setPicking(true)}>+ Craft a new prism</button>
            )}
            {picking && (
              <button className="btn btn-sm" style={{ background: '#222', color: '#aaa' }}
                onClick={() => setPicking(false)}>Back</button>
            )}
            <button className="btn btn-sm" onClick={onClose} style={{ background: '#2a1a1a', color: '#ff8a8a' }}>✕</button>
          </div>
        </div>

        {picking ? (
          <PickKind inverse={inverse} ethereal={ethereal}
            onPickInverse={() => { setPicking(false); setEdit({ kind: 'inverse_image', rolls: { ...OFF_ROLLS }, source: 'new' }) }}
            onPickEthereal={it => { setPicking(false); setEdit({ kind: 'ethereal_prism', draft: freshDraft(it), source: 'new' }) }} />
        ) : edit?.kind === 'inverse_image' ? (
          <div style={{ padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              {inverse && <img src={iconUrl('prism', inverse.icon_url) ?? undefined} alt="" width={40} height={40}
                style={{ borderRadius: 6, border: '1px solid #4a4e6a' }} />}
              <span style={{ color: '#e9c046', fontWeight: 600 }}>{inverse?.name ?? 'Inverse Image'}</span>
            </div>
            {TIERS.map(({ key, label }) => {
              const [lo, hi] = ranges[key]
              return (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                  <span style={{ flex: 1, color: '#bcc0dd', fontSize: 13 }}>{label}</span>
                  <input type="number" value={edit.rolls[key]} min={lo} max={hi}
                    onChange={e => setRoll(key, Number(e.target.value))}
                    style={{ width: 70, background: '#0d0f18', color: '#e0e0e0', border: '1px solid #333',
                      borderRadius: 4, padding: '4px 6px', textAlign: 'right' }} />
                  <span style={{ color: '#666', fontSize: 11, width: 78 }}>% ({lo}…{hi})</span>
                </div>
              )
            })}
            <EditActions edit={edit} onCancel={() => editPlaced ? onClose() : setEdit(null)}
              onSaveInv={saveToInventory} onPlace={placeFromEdit} onSavePlaced={savePlaced}
              onRemovePlaced={() => { onRemovePlaced?.(); onClose() }} />
          </div>
        ) : edit?.kind === 'ethereal_prism' && ethereal ? (
          <EtherealForm draft={edit.draft} ethereal={ethereal} setDraft={d => setEdit({ ...edit, draft: d })}
            actions={
              <EditActions edit={edit} onCancel={() => editPlaced ? onClose() : setEdit(null)}
                onSaveInv={saveToInventory} onPlace={placeFromEdit} onSavePlaced={savePlaced}
                onRemovePlaced={() => { onRemovePlaced?.(); onClose() }} />
            } />
        ) : (
          <div style={{ padding: 16 }}>
            {inventory.length === 0 ? (
              <div style={{ color: '#777', textAlign: 'center', padding: '28px 0', fontSize: 13 }}>
                No prisms yet. Craft one to get started.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))', gap: 10 }}>
                {inventory.map(p => {
                  const rare = p.kind === 'ethereal_prism' && p.ethereal?.rarity === 'rare'
                  const tint = rare && p.ethereal?.tintWhenRare
                  return (
                    <div key={p.id}
                      title="Left-click: edit / place  ·  Right-click: delete"
                      onMouseEnter={() => setTip(p)} onMouseLeave={() => setTip(null)}
                      onClick={() => editInventory(p)}
                      onContextMenu={e => { e.preventDefault(); remove(p.id) }}
                      style={{ cursor: 'pointer', border: `1px solid ${rare ? '#7a4ea0' : '#3a3e5c'}`, borderRadius: 8,
                        padding: 8, background: '#171a28', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                      <img src={iconUrl('prism', p.iconUrl) ?? undefined} alt="" width={44} height={44}
                        style={{ borderRadius: 6, filter: tint ? RARE_TINT : undefined }} />
                      <span style={{ fontSize: 9.5, color: '#9aa', textAlign: 'center', lineHeight: 1.1 }}>
                        {p.kind === 'ethereal_prism' ? (p.ethereal?.shortName ?? 'Ethereal')
                          : `${p.rolls.micro}/${p.rolls.medium}/${p.rolls.legendary}`}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
            {tip && <InventoryTip prism={tip} />}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sub-views ────────────────────────────────────────────────────────────────

function PickKind({ inverse, ethereal, onPickInverse, onPickEthereal }: {
  inverse?: PrismCatalogItem; ethereal: EtherealCatalog | null
  onPickInverse: () => void; onPickEthereal: (it: EtherealCatalogItem) => void
}) {
  const cell = (icon: string, name: string, onClick: () => void, tint?: boolean, key?: string) => (
    <div key={key ?? name} onClick={onClick} title={name}
      style={{ cursor: 'pointer', border: '1px solid #3a3e5c', borderRadius: 8, padding: 8, background: '#171a28',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <img src={iconUrl('prism', icon) ?? undefined} alt="" width={42} height={42}
        style={{ borderRadius: 6, filter: tint ? RARE_TINT : undefined }} />
      <span style={{ fontSize: 9.5, color: '#9aa', textAlign: 'center', lineHeight: 1.1 }}>{name}</span>
    </div>
  )
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(76px, 1fr))', gap: 10 }}>
        {inverse && cell(inverse.icon_url, 'Inverse Image', onPickInverse, false, 'inv')}
        {(ethereal?.items ?? []).map(it => cell(it.icon_url, it.short_name, () => onPickEthereal(it),
          it.default_rarity === 'rare' && it.tint_when_rare, it.short_name))}
      </div>
    </div>
  )
}

// A searchable single-select: type partial words to filter the options (all words must match, any order). The
// placeholder/none row is always offered to clear the selection.
function Dropdown({ label, value, options, onChange, placeholder }: {
  label: string; value: string | undefined; options: { v: string; t: string }[]
  onChange: (v: string) => void; placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const selected = options.find(o => o.v === value)
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  const filtered = words.length === 0 ? options
    : options.filter(o => { const t = o.t.toLowerCase(); return words.every(w => t.includes(w)) })
  const pick = (v: string) => { onChange(v); setQuery(''); setOpen(false) }
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ color: '#8a8fb0', fontSize: 11, marginBottom: 3, textTransform: 'uppercase', letterSpacing: 0.4 }}>{label}</div>
      <input
        value={open ? query : (selected?.t ?? '')}
        placeholder={placeholder ?? '— none —'}
        onFocus={() => { setQuery(''); setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 120)}   // delay so an option's mousedown lands first
        onChange={e => { setQuery(e.target.value); setOpen(true) }}
        style={{ width: '100%', background: '#0d0f18', color: '#dfe3ff', border: '1px solid #333', borderRadius: 4, padding: '6px 8px', fontSize: 12.5 }} />
      {open && (
        <div style={{ marginTop: 2, border: '1px solid #2a2e44', borderRadius: 4, background: '#0b0d15',
          maxHeight: 200, overflowY: 'auto' }}>
          <div onMouseDown={e => { e.preventDefault(); pick('') }}
            style={{ padding: '5px 8px', fontSize: 12, color: '#777', cursor: 'pointer', borderBottom: '1px solid #1c2030' }}>
            {placeholder ?? '— none —'}
          </div>
          {filtered.map(o => (
            <div key={o.v} onMouseDown={e => { e.preventDefault(); pick(o.v) }}
              style={{ padding: '5px 8px', fontSize: 12, cursor: 'pointer',
                color: o.v === value ? '#c79bff' : '#cfd3ee', background: o.v === value ? '#1a1c2e' : 'transparent' }}
              onMouseEnter={e => { e.currentTarget.style.background = '#161a2a' }}
              onMouseLeave={e => { e.currentTarget.style.background = o.v === value ? '#1a1c2e' : 'transparent' }}>
              {o.t}
            </div>
          ))}
          {filtered.length === 0 && <div style={{ padding: '5px 8px', fontSize: 12, color: '#666' }}>No matches</div>}
        </div>
      )}
    </div>
  )
}

function EtherealForm({ draft, ethereal, setDraft, actions }: {
  draft: EthDraft; ethereal: EtherealCatalog; setDraft: (d: EthDraft) => void; actions: React.ReactNode
}) {
  const { item } = draft
  const tint = draft.rarity === 'rare' && item.tint_when_rare
  // Slot-2 pool by rarity: rare prisms cannot roll Legendary-Medium-targeting bonuses (orange-exclusive); legendary
  // prisms get the full pool. (Blue vs purple among Micro/Medium isn't in the source data — icon-colour only.)
  const middlePool = draft.rarity === 'rare' ? ethereal.middle.filter(m => m.tier !== 'legendary') : ethereal.middle
  const middleOpts = middlePool.map(m => ({ v: m.modifier, t: m.modifier.replace('within the area also gain:', '→') }))
  const dnr = ethereal.do_not_replace[item.short_name] ?? []
  const advOpts = [
    ...dnr.map(d => ({ v: d.modifier, t: `Do-Not-Replace (${d.penalty})` })),
    ...ethereal.advanced.map(a => ({ v: a.modifier, t: a.modifier })),
  ]
  // Switching rarity: drop selections no longer valid for the new rarity.
  const setRarity = (r: PrismRarity) => {
    const next: EthDraft = { ...draft, rarity: r }
    if (r === 'rare') {
      next.advanced = undefined   // no Slot 3 on rare
      if (next.middle && ethereal.middle.find(m => m.modifier === next.middle)?.tier === 'legendary')
        next.middle = undefined   // Legendary-Medium-target bonuses are orange-exclusive
    }
    setDraft(next)
  }
  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <img src={iconUrl('prism', item.icon_url) ?? undefined} alt="" width={40} height={40}
          style={{ borderRadius: 6, border: '1px solid #4a4e6a', filter: tint ? RARE_TINT : undefined }} />
        <span style={{ color: draft.rarity === 'rare' ? '#c79bff' : '#e9c046', fontWeight: 600 }}>{item.short_name}</span>
        {/* Rarity: a toggle only when the item has both variants. */}
        {item.rarities.length > 1 ? (
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
            {item.rarities.map(r => (
              <button key={r} className="btn btn-sm"
                onClick={() => setRarity(r)}
                style={{ background: draft.rarity === r ? (r === 'rare' ? '#3a2a4a' : '#3a2f1a') : '#1a1c28',
                  color: draft.rarity === r ? (r === 'rare' ? '#c79bff' : '#e9c046') : '#777', textTransform: 'capitalize' }}>
                {r === 'legendary' ? 'Legendary' : 'Rare'}
              </button>
            ))}
          </div>
        ) : (
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#777', textTransform: 'capitalize' }}>{draft.rarity}</span>
        )}
      </div>

      {/* Implicit */}
      {item.implicit.kind === 'add_choice' ? (
        <Dropdown label="Implicit (added effect)" value={draft.implicit}
          options={(item.implicit.options ?? []).map(o => ({ v: o, t: addEffectTail(o) }))}
          onChange={v => setDraft({ ...draft, implicit: v })} placeholder="— choose an added effect —" />
      ) : (
        <div style={{ marginBottom: 10 }}>
          <div style={{ color: '#8a8fb0', fontSize: 11, marginBottom: 3, textTransform: 'uppercase', letterSpacing: 0.4 }}>Implicit</div>
          <div style={{ background: '#0d0f18', border: '1px solid #2a2e44', borderRadius: 4, padding: '6px 8px',
            fontSize: 12, color: '#bcc0dd' }}>{implicitSummary(item)}</div>
        </div>
      )}

      {/* Slot 1 — area size */}
      <Dropdown label="Slot 1 — Effect Area" value={draft.areaSize}
        options={ethereal.area_size.map(a => ({ v: a.modifier, t: `${a.cols}×${a.rows} Rectangle` }))}
        onChange={v => setDraft({ ...draft, areaSize: v })} placeholder="— choose an area size —" />

      {/* Slot 2 — middle tier */}
      <Dropdown label="Slot 2 — Area Bonus" value={draft.middle} options={middleOpts}
        onChange={v => setDraft({ ...draft, middle: v })} placeholder="— choose an area bonus —" />

      {/* Slot 3 — advanced (legendary only) */}
      {draft.rarity === 'legendary' && (
        <Dropdown label="Slot 3 — Advanced" value={draft.advanced} options={advOpts}
          onChange={v => setDraft({ ...draft, advanced: v })} placeholder="— choose an advanced affix —" />
      )}

      {actions}
    </div>
  )
}

function EditActions({ edit, onCancel, onSaveInv, onPlace, onSavePlaced, onRemovePlaced }: {
  edit: EditTarget; onCancel: () => void; onSaveInv: () => void; onPlace: () => void
  onSavePlaced: () => void; onRemovePlaced: () => void
}) {
  return (
    <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
      <button className="btn btn-sm" onClick={onCancel} style={{ background: '#222', color: '#aaa' }}>Cancel</button>
      {edit.source === 'placed' ? (
        <>
          <button className="btn btn-sm" onClick={onRemovePlaced} style={{ background: '#3a1a1a', color: '#ff8a8a' }}>Remove prism</button>
          <button className="btn btn-sm" onClick={onSavePlaced} style={{ background: '#1c3a22', color: '#9fe0a8' }}>Save changes</button>
        </>
      ) : (
        <>
          <button className="btn btn-sm" onClick={onSaveInv} style={{ background: '#23314a', color: '#9fc0ff' }}>
            {edit.source === 'inventory' ? 'Save' : 'Add to inventory'}
          </button>
          <button className="btn btn-sm" onClick={onPlace} style={{ background: '#2a1c4a', color: '#c79bff' }}>◈ Place prism</button>
        </>
      )}
    </div>
  )
}

function InventoryTip({ prism }: { prism: CraftedPrism }) {
  return (
    <div style={{ marginTop: 14, padding: 10, background: '#0d0f18', border: '1px solid #2a2e44', borderRadius: 6 }}>
      <div style={{ color: prism.kind === 'ethereal_prism' && prism.ethereal?.rarity === 'rare' ? '#c79bff' : '#e9c046',
        fontWeight: 600, marginBottom: 4 }}>{prism.name}</div>
      {prism.kind === 'inverse_image' ? (
        TIERS.map(({ key, label }) => (
          <div key={key} style={{ fontSize: 12, color: prism.rolls[key] <= -100 ? '#666' : '#bcc0dd' }}>
            {prism.rolls[key] > 0 ? '+' : ''}{prism.rolls[key]}% all reflected {label}
          </div>
        ))
      ) : prism.ethereal ? (
        <div style={{ fontSize: 11.5, color: '#bcc0dd', lineHeight: 1.45 }}>
          <div style={{ color: '#888', textTransform: 'capitalize' }}>{prism.ethereal.rarity}</div>
          <div>{shorten(prism.ethereal.implicit)}</div>
          {prism.ethereal.boxCols && <div>Area: {prism.ethereal.boxCols}×{prism.ethereal.boxRows}</div>}
          {prism.ethereal.middle && <div>{shorten(prism.ethereal.middle)}</div>}
          {prism.ethereal.advanced && <div>{shorten(prism.ethereal.advanced)}</div>}
        </div>
      ) : null}
    </div>
  )
}

// ── text helpers ─────────────────────────────────────────────────────────────
function shorten(s: string, n = 90): string { return s.length > n ? s.slice(0, n - 1) + '…' : s }
function addEffectTail(s: string): string {
  const i = s.indexOf('Advanced Talent Panel:')
  return shorten((i >= 0 ? s.slice(i + 'Advanced Talent Panel:'.length) : s).trim(), 70)
}
function implicitSummary(item: EtherealCatalogItem): string {
  if (item.implicit.kind === 'replace') return `Replaces the Core Talent with: ${item.short_name}`
  if (item.implicit.kind === 'amplify') return item.implicit.text ?? ''
  return ''
}
