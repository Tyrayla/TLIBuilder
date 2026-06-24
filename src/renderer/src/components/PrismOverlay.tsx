import { useState } from 'react'
import { iconUrl, PrismCatalogItem, CraftedPrism, PlacedPrism, PrismRolls } from '../api/client'

// Overlay over the tree: prism inventory + an edit/craft view. Clicking an inventory prism (or the placed prism
// on the tree) opens its editable rolls with a Place button; "+ Craft a new prism" opens a fresh one. Plan 1
// supports Inverse Image (3 user-set rolls, default −100).

interface Props {
  catalog: PrismCatalogItem[]
  inventory: CraftedPrism[]
  setInventory: (inv: CraftedPrism[]) => void
  onPlace: (p: CraftedPrism) => void
  onClose: () => void
  editPlaced?: PlacedPrism | null              // when opened to edit the prism installed on the tree
  onUpdatePlaced?: (rolls: PrismRolls) => void
}

const TIERS: { key: keyof PrismRolls; label: string }[] = [
  { key: 'micro', label: 'Micro Talent Effects' },
  { key: 'medium', label: 'Medium Talent Effects' },
  { key: 'legendary', label: 'Legendary Medium Talent Effects' },
]

const DEFAULT_RANGES = { micro: [-100, 200], medium: [-100, 100], legendary: [-100, 50] } as const

function newId(): string {
  return `${Date.now()}-${Math.floor(performance.now() * 1000) % 1000000}`
}

type EditTarget = { rolls: PrismRolls; source: 'new' | 'inventory' | 'placed'; id?: string }

export default function PrismOverlay({ catalog, inventory, setInventory, onPlace, onClose, editPlaced, onUpdatePlaced }: Props) {
  const inverse = catalog.find(c => c.kind === 'inverse_image')
  const ranges = inverse?.roll_ranges ?? DEFAULT_RANGES
  const [edit, setEdit] = useState<EditTarget | null>(
    editPlaced ? { rolls: { ...editPlaced.rolls }, source: 'placed', id: editPlaced.id } : null,
  )
  const [tip, setTip] = useState<CraftedPrism | null>(null)

  const clamp = (k: keyof PrismRolls, v: number) => {
    const [lo, hi] = ranges[k]
    return Math.max(lo, Math.min(hi, Math.round(v)))
  }
  const setRoll = (k: keyof PrismRolls, v: number) =>
    setEdit(e => e ? { ...e, rolls: { ...e.rolls, [k]: clamp(k, v) } } : e)

  const toCrafted = (rolls: PrismRolls, id = newId()): CraftedPrism => ({
    id, kind: 'inverse_image', name: inverse?.name ?? 'Inverse Image', iconUrl: inverse?.icon_url ?? '', rolls,
  })

  const saveToInventory = () => {
    if (!edit) return
    const id = edit.source === 'inventory' && edit.id ? edit.id : newId()
    const item = toCrafted(edit.rolls, id)
    setInventory([...inventory.filter(p => p.id !== id), item])
    setEdit(null)
  }

  const remove = (id: string) => setInventory(inventory.filter(p => p.id !== id))

  return (
    <div className="prism-overlay-backdrop" onClick={onClose}
      style={{ position: 'absolute', inset: 0, background: 'rgba(8,10,20,0.78)', zIndex: 40, display: 'flex',
        alignItems: 'flex-start', justifyContent: 'center', paddingTop: 56 }}>
      {/* Anchored to the top so the hover-tooltip grows DOWNWARD (a centered panel reflows the grid up → flicker). */}
      <div className="prism-overlay-panel" onClick={e => e.stopPropagation()}
        style={{ background: '#12141f', border: '1px solid #2a2e44', borderRadius: 10, width: 560, maxWidth: '90%',
          maxHeight: '84%', overflow: 'auto', boxShadow: '0 12px 40px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', borderBottom: '1px solid #2a2e44' }}>
          <span style={{ fontWeight: 600, color: '#cfd3ee' }}>
            {edit ? (edit.source === 'placed' ? 'Edit Installed Prism' : edit.source === 'new' ? 'Craft Prism' : 'Edit Prism') : 'Prisms'}
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            {!edit && (
              <button className="btn btn-sm" style={{ background: '#1c2a44', color: '#9fc0ff' }}
                onClick={() => setEdit({ rolls: { micro: -100, medium: -100, legendary: -100 }, source: 'new' })}
                disabled={!inverse}>+ Craft a new prism</button>
            )}
            <button className="btn btn-sm" onClick={onClose} style={{ background: '#2a1a1a', color: '#ff8a8a' }}>✕</button>
          </div>
        </div>

        {edit ? (
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
            <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
              <button className="btn btn-sm" onClick={() => editPlaced ? onClose() : setEdit(null)}
                style={{ background: '#222', color: '#aaa' }}>Cancel</button>
              {edit.source === 'placed' ? (
                <button className="btn btn-sm" onClick={() => { onUpdatePlaced?.(edit.rolls); onClose() }}
                  style={{ background: '#1c3a22', color: '#9fe0a8' }}>Save changes</button>
              ) : (
                <>
                  <button className="btn btn-sm" onClick={saveToInventory}
                    style={{ background: '#23314a', color: '#9fc0ff' }}>
                    {edit.source === 'inventory' ? 'Save' : 'Add to inventory'}
                  </button>
                  <button className="btn btn-sm"
                    onClick={() => { const item = toCrafted(edit.rolls, edit.id); setInventory([...inventory.filter(p => p.id !== item.id), item]); onPlace(item) }}
                    style={{ background: '#2a1c4a', color: '#c79bff' }}>◈ Place prism</button>
                </>
              )}
            </div>
          </div>
        ) : (
          <div style={{ padding: 16 }}>
            {inventory.length === 0 ? (
              <div style={{ color: '#777', textAlign: 'center', padding: '28px 0', fontSize: 13 }}>
                No prisms yet. Craft one to get started.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))', gap: 10 }}>
                {inventory.map(p => (
                  <div key={p.id}
                    title="Left-click: edit / place  ·  Right-click: delete"
                    onMouseEnter={() => setTip(p)} onMouseLeave={() => setTip(null)}
                    onClick={() => setEdit({ rolls: { ...p.rolls }, source: 'inventory', id: p.id })}
                    onContextMenu={e => { e.preventDefault(); remove(p.id) }}
                    style={{ cursor: 'pointer', border: '1px solid #3a3e5c', borderRadius: 8, padding: 8,
                      background: '#171a28', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                    <img src={iconUrl('prism', p.iconUrl) ?? undefined} alt="" width={44} height={44}
                      style={{ borderRadius: 6 }} />
                    <span style={{ fontSize: 10, color: '#9aa', textAlign: 'center', lineHeight: 1.1 }}>
                      {p.rolls.micro}/{p.rolls.medium}/{p.rolls.legendary}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {tip && (
              <div style={{ marginTop: 14, padding: 10, background: '#0d0f18', border: '1px solid #2a2e44',
                borderRadius: 6 }}>
                <div style={{ color: '#e9c046', fontWeight: 600, marginBottom: 4 }}>{tip.name}</div>
                {TIERS.map(({ key, label }) => (
                  <div key={key} style={{ fontSize: 12, color: tip.rolls[key] <= -100 ? '#666' : '#bcc0dd' }}>
                    {tip.rolls[key] > 0 ? '+' : ''}{tip.rolls[key]}% all reflected {label}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
