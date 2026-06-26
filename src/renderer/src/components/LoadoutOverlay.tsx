import React, { useRef, useState } from 'react'
import { useBuildStore } from '../store/buildStore'
import type { Loadout, AreaKey } from '../api/client'
import { ALL_AREAS, AREA_LABELS, resolveAreaSnapshot } from '../utils/loadoutAreas'

const genId = (): string =>
  (globalThis.crypto?.randomUUID?.() ?? `lo${Date.now()}${Math.floor(Math.random() * 1e6)}`)

// Does following `startId`'s inherit chain for `area` reach `targetId`? Used to forbid inheritance cycles.
function chainReaches(loadouts: Loadout[], startId: string, targetId: string, area: AreaKey): boolean {
  const byId = (id: string) => loadouts.find(l => l.id === id)
  let cur = byId(startId)
  const seen = new Set<string>()
  while (cur && !seen.has(cur.id)) {
    if (cur.id === targetId) return true
    seen.add(cur.id)
    const nx = cur.inherit?.[area]
    if (!nx) break
    cur = byId(nx)
  }
  return false
}

// A fully-independent snapshot of every area for a loadout (resolving inheritance) — for copy/duplicate.
function flattenedData(loadouts: Loadout[], id: string): Loadout['data'] {
  const data: Loadout['data'] = {}
  for (const area of ALL_AREAS) data[area] = resolveAreaSnapshot(loadouts, id, area)
  return data
}

// Close a backdrop only on a deliberate full click on it (press AND release on the backdrop itself) — so dragging a
// text selection off the modal, or releasing the mouse outside, never closes it.
function useBackdropClose(onClose: () => void) {
  const downOnSelf = useRef(false)
  return {
    onMouseDown: (e: React.MouseEvent) => { downOnSelf.current = e.target === e.currentTarget },
    onClick: (e: React.MouseEvent) => {
      if (downOnSelf.current && e.target === e.currentTarget) onClose()
      downOnSelf.current = false
    },
  }
}

type View = { mode: 'list' } | { mode: 'create' } | { mode: 'edit'; id: string }

export default function LoadoutOverlay({ onClose, initialView = 'list' }: {
  onClose: () => void
  initialView?: 'list' | 'create'
}) {
  const loadouts = useBuildStore(s => s.loadouts)
  const activeLoadoutId = useBuildStore(s => s.activeLoadoutId)
  const switchLoadout = useBuildStore(s => s.switchLoadout)
  const editLoadouts = useBuildStore(s => s.editLoadouts)

  const [view, setView] = useState<View>({ mode: initialView })
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const backdrop = useBackdropClose(onClose)

  // ── Create-view state ──
  const [newName, setNewName] = useState('')
  const [startFrom, setStartFrom] = useState<'empty' | 'copy'>('empty')
  const [copyId, setCopyId] = useState('')
  const [copyInherit, setCopyInherit] = useState<Set<AreaKey>>(new Set())
  const resetCreate = () => { setNewName(''); setStartFrom('empty'); setCopyId(''); setCopyInherit(new Set()) }

  const doCreate = () => {
    const id = genId()
    const name = newName.trim() || `Loadout ${loadouts.length + 1}`
    const srcId = startFrom === 'copy' ? (copyId || loadouts[0]?.id) : undefined
    const data = srcId ? flattenedData(loadouts, srcId) : {}
    const inherit: Loadout['inherit'] = {}
    if (srcId) for (const a of copyInherit) inherit[a] = srcId
    editLoadouts(ls => [...ls, { id, name, data, inherit }])
    switchLoadout(id)
    resetCreate()
    setView({ mode: 'list' })
  }

  const doDuplicate = (srcId: string) => {
    const src = loadouts.find(l => l.id === srcId)
    if (!src) return
    const id = genId()
    editLoadouts(ls => [...ls, { id, name: `${src.name} copy`, data: flattenedData(ls, srcId), inherit: {} }])
  }

  const doDelete = (id: string) => {
    // Bake any direct inheritors' values from the deleted loadout, then drop it.
    editLoadouts(ls => ls
      .map(l => {
        if (l.id === id) return l
        const inherit = { ...(l.inherit ?? {}) }
        const data = { ...l.data }
        let changed = false
        for (const area of ALL_AREAS) {
          if (inherit[area] === id) { data[area] = resolveAreaSnapshot(ls, l.id, area); delete inherit[area]; changed = true }
        }
        return changed ? { ...l, inherit, data } : l
      })
      .filter(l => l.id !== id))
    setConfirmDelete(null)
  }

  // Commit an Edit-view draft (name + per-area inherit map) in one structural edit.
  const commitEdit = (id: string, name: string, inherit: Partial<Record<AreaKey, string>>) => {
    editLoadouts(ls => ls.map(l => l.id === id ? { ...l, name: name.trim() || l.name, inherit } : l))
    setView({ mode: 'list' })
  }

  const pushAsGeneral = (generalId: string, areas: AreaKey[], targetIds: string[]) =>
    editLoadouts(ls => {
      const next = ls.map(l => ({ ...l, inherit: { ...(l.inherit ?? {}) }, data: { ...l.data } }))
      const gen = next.find(l => l.id === generalId)
      if (gen) for (const area of areas) {
        if (gen.inherit[area]) { gen.data[area] = resolveAreaSnapshot(ls, generalId, area); delete gen.inherit[area] }
      }
      for (const l of next) {
        if (l.id === generalId || !targetIds.includes(l.id)) continue
        for (const area of areas) l.inherit[area] = generalId
      }
      return next
    })

  const nameOf = (id: string | undefined) => loadouts.find(l => l.id === id)?.name ?? '—'

  // ── Render ──
  let body: React.ReactNode
  if (view.mode === 'create') {
    const copySource = loadouts.find(l => l.id === (copyId || loadouts[0]?.id))
    body = (
      <div className="loadout-body">
        <label className="loadout-field">
          <span>Name</span>
          <input className="loadout-input" value={newName} autoFocus
            onChange={e => setNewName(e.target.value)} placeholder={`Loadout ${loadouts.length + 1}`} />
        </label>
        <div className="loadout-field">
          <span>Start from</span>
          <label className="loadout-radio">
            <input type="radio" checked={startFrom === 'empty'} onChange={() => setStartFrom('empty')} />
            Empty / default
          </label>
          <label className="loadout-radio">
            <input type="radio" checked={startFrom === 'copy'} onChange={() => setStartFrom('copy')} />
            Copy existing
            <select className="loadout-select" value={copyId || loadouts[0]?.id || ''} disabled={startFrom !== 'copy'}
              onChange={e => setCopyId(e.target.value)}>
              {loadouts.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
        </div>
        {startFrom === 'copy' && (
          <>
            <div className="loadout-hint">Choose which copied areas stay independent (Own) or stay linked to the
              source (Inherit).</div>
            <AreaSourceGrid
              value={Object.fromEntries([...copyInherit].map(a => [a, copySource?.id ?? ''])) as Partial<Record<AreaKey, string>>}
              sourcesFor={() => (copySource ? [copySource] : [])}
              onChange={(area, src) => setCopyInherit(s => {
                const n = new Set(s); if (src) n.add(area); else n.delete(area); return n
              })}
            />
          </>
        )}
        <div className="modal-actions">
          <button className="loadout-btn loadout-btn-primary" onClick={doCreate}>Create</button>
          <button className="loadout-btn" onClick={() => { resetCreate(); setView({ mode: 'list' }) }}>Cancel</button>
        </div>
      </div>
    )
  } else if (view.mode === 'edit') {
    const lo = loadouts.find(l => l.id === view.id)
    if (!lo) { body = null; setTimeout(() => setView({ mode: 'list' }), 0) }
    else body = (
      <EditView
        key={lo.id} loadout={lo} loadouts={loadouts}
        onCommit={(name, inherit) => commitEdit(lo.id, name, inherit)}
        onCancel={() => setView({ mode: 'list' })}
        onPush={(areas, targets) => pushAsGeneral(lo.id, areas, targets)}
      />
    )
  } else {
    body = (
      <div className="loadout-body">
        <div className="loadout-list">
          {loadouts.map(l => (
            <div key={l.id} className={`loadout-row${l.id === activeLoadoutId ? ' active' : ''}`}>
              <button className="loadout-row-name" onClick={() => switchLoadout(l.id)} title="Activate">
                {l.id === activeLoadoutId && <span className="loadout-active-dot">●</span>}
                {l.name}
              </button>
              <div className="loadout-row-actions">
                <button className="loadout-btn" onClick={() => setView({ mode: 'edit', id: l.id })}>Edit</button>
                <button className="loadout-btn" onClick={() => doDuplicate(l.id)}>Dup</button>
                <button className="loadout-btn loadout-btn-danger" disabled={loadouts.length <= 1}
                  onClick={() => setConfirmDelete(l.id)}>Del</button>
              </div>
            </div>
          ))}
        </div>
        <div className="modal-actions">
          <button className="loadout-btn loadout-btn-primary" onClick={() => setView({ mode: 'create' })}>
            ＋ Create New Loadout
          </button>
        </div>
      </div>
    )
  }

  const title = view.mode === 'create' ? 'New Loadout'
    : view.mode === 'edit' ? `Edit: ${nameOf(view.id)}`
    : 'Loadouts'

  return (
    <div className="modal-backdrop" {...backdrop}>
      <div className="modal-card loadout-modal-card" onClick={e => e.stopPropagation()}>
        <div className="modal-accent" />
        <h3 className="modal-title">{title}</h3>
        {body}

        {confirmDelete && (
          <ConfirmDelete name={nameOf(confirmDelete)}
            onCancel={() => setConfirmDelete(null)}
            onConfirm={() => doDelete(confirmDelete)} />
        )}
      </div>
    </div>
  )
}

// ── Reusable per-area Own/Inherit grid ──────────────────────────────────────────
function AreaSourceGrid({ value, sourcesFor, onChange }: {
  value: Partial<Record<AreaKey, string>>
  sourcesFor: (area: AreaKey) => Loadout[]
  onChange: (area: AreaKey, sourceId: string | null) => void
}) {
  return (
    <div className="loadout-area-grid">
      <div className="loadout-area-head"><span>Area</span><span>Value source</span></div>
      {ALL_AREAS.map(area => {
        const src = value[area]
        const sources = sourcesFor(area)
        const canInherit = sources.length > 0
        return (
          <div key={area} className="loadout-area-row">
            <span className="loadout-area-label">
              <span className="loadout-expand" title="Sub-parts (coming soon)">▸</span>
              {AREA_LABELS[area]}
            </span>
            <div className="loadout-area-ctrl">
              <label className="loadout-radio">
                <input type="radio" checked={!src} onChange={() => onChange(area, null)} /> Own
              </label>
              <label className="loadout-radio">
                <input type="radio" checked={!!src} disabled={!canInherit}
                  onChange={() => onChange(area, sources[0]?.id ?? null)} /> Inherit
              </label>
              {src && sources.length > 1 && (
                <select className="loadout-select" value={src} onChange={e => onChange(area, e.target.value)}>
                  {sources.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
              )}
              {src && sources.length === 1 && <span className="loadout-src-name">{sources[0].name}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Edit view (draft; applies on Save) ──────────────────────────────────────────
function EditView({ loadout, loadouts, onCommit, onCancel, onPush }: {
  loadout: Loadout
  loadouts: Loadout[]
  onCommit: (name: string, inherit: Partial<Record<AreaKey, string>>) => void
  onCancel: () => void
  onPush: (areas: AreaKey[], targetIds: string[]) => void
}) {
  const [name, setName] = useState(loadout.name)
  const [draft, setDraft] = useState<Partial<Record<AreaKey, string>>>(() => ({ ...(loadout.inherit ?? {}) }))
  const [showPush, setShowPush] = useState(false)

  const sourcesFor = (area: AreaKey) =>
    loadouts.filter(o => o.id !== loadout.id && !chainReaches(loadouts, o.id, loadout.id, area))

  const setSrc = (area: AreaKey, src: string | null) =>
    setDraft(d => { const n = { ...d }; if (src) n[area] = src; else delete n[area]; return n })

  return (
    <div className="loadout-body">
      <label className="loadout-field">
        <span>Name</span>
        <input className="loadout-input" value={name} onChange={e => setName(e.target.value)} />
      </label>

      <AreaSourceGrid value={draft} sourcesFor={sourcesFor} onChange={setSrc} />

      <div className="loadout-hint">Inherited areas show the general’s value; editing them updates the general.
        Changes apply when you hit Save.</div>

      <button className="loadout-btn loadout-btn-wide" disabled={loadouts.length <= 1}
        onClick={() => setShowPush(true)}>Share areas to other loadouts…</button>
      <div className="loadout-hint">“Share” makes other loadouts <b>inherit</b> chosen areas from this one (this
        loadout becomes the “general”, so editing those areas updates them everywhere).</div>

      <div className="modal-actions">
        <button className="loadout-btn loadout-btn-primary" onClick={() => onCommit(name, draft)}>Save</button>
        <button className="loadout-btn" onClick={onCancel}>Cancel</button>
      </div>

      {showPush && (
        <PushPanel loadout={loadout} loadouts={loadouts}
          onApply={(areas, targets) => { onPush(areas, targets); setShowPush(false) }}
          onClose={() => setShowPush(false)} />
      )}
    </div>
  )
}

// ── Push helper ("share areas to other loadouts") ───────────────────────────────
function PushPanel({ loadout, loadouts, onApply, onClose }: {
  loadout: Loadout
  loadouts: Loadout[]
  onApply: (areas: AreaKey[], targetIds: string[]) => void
  onClose: () => void
}) {
  const [areas, setAreas] = useState<Set<AreaKey>>(new Set())
  const [targets, setTargets] = useState<Set<string>>(new Set())
  const backdrop = useBackdropClose(onClose)
  const others = loadouts.filter(l => l.id !== loadout.id)
  const toggle = <T,>(set: Set<T>, v: T): Set<T> => {
    const next = new Set(set); next.has(v) ? next.delete(v) : next.add(v); return next
  }
  return (
    <div className="modal-backdrop" {...backdrop}>
      <div className="modal-card" onClick={e => e.stopPropagation()} style={{ minWidth: 380 }}>
        <div className="modal-accent" />
        <h3 className="modal-title">Share areas from “{loadout.name}”</h3>
        <div className="loadout-body">
          <div className="loadout-hint">The selected loadouts will inherit the chosen areas from “{loadout.name}”.</div>
          <div className="loadout-field"><span>Areas</span>
            <div className="loadout-check-grid">
              {ALL_AREAS.map(a => (
                <label key={a} className="cond-item" style={{ padding: '2px 4px' }}>
                  <input type="checkbox" className="cond-check" checked={areas.has(a)}
                    onChange={() => setAreas(s => toggle(s, a))} />
                  <span className="cond-label">{AREA_LABELS[a]}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="loadout-field"><span>Loadouts that will inherit</span>
            <div className="loadout-check-grid">
              {others.map(o => (
                <label key={o.id} className="cond-item" style={{ padding: '2px 4px' }}>
                  <input type="checkbox" className="cond-check" checked={targets.has(o.id)}
                    onChange={() => setTargets(s => toggle(s, o.id))} />
                  <span className="cond-label">{o.name}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="modal-actions">
            <button className="loadout-btn loadout-btn-primary"
              disabled={areas.size === 0 || targets.size === 0}
              onClick={() => onApply([...areas], [...targets])}>Apply</button>
            <button className="loadout-btn" onClick={onClose}>Cancel</button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Guarded delete confirm ──────────────────────────────────────────────────────
function ConfirmDelete({ name, onConfirm, onCancel }: { name: string; onConfirm: () => void; onCancel: () => void }) {
  const backdrop = useBackdropClose(onCancel)
  return (
    <div className="modal-backdrop" {...backdrop}>
      <div className="modal-card" onClick={e => e.stopPropagation()} style={{ minWidth: 340 }}>
        <div className="modal-accent" />
        <h3 className="modal-title">Delete “{name}”?</h3>
        <div className="loadout-body" style={{ fontSize: 12, color: '#aab' }}>
          Removes its gear, talents, skills, notes, and all other data, and clears any inheritance links to it.
          This can’t be undone.
          <div className="modal-actions">
            <button className="loadout-btn loadout-btn-danger" onClick={onConfirm}>Delete</button>
            <button className="loadout-btn" onClick={onCancel}>Cancel</button>
          </div>
        </div>
      </div>
    </div>
  )
}
