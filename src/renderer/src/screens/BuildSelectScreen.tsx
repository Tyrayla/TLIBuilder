import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api, Build, BuildFolder, FolderManifest, IS_WEB } from '../api/client'
import ImportPanel from '../components/ImportPanel'
import { characterSummary } from '../utils/characterSummary'
import { useReferenceStore } from '../store/referenceStore'
import SettingsOverlay from '../components/SettingsOverlay'
import LoadingState from '../components/LoadingState'
import logoSrc from '../assets/logo.png'

interface Props {
  onNewBuild: (folderId?: string) => void
  onOpenBuild: (build: Build) => void
  devMode?: boolean
  onDevTools?: () => void
  onOpenVerification?: () => void
}

function totalPoints(build: Build): number {
  return build.slots.filter(Boolean).reduce((sum, s) =>
    sum + Object.values(s!.nodeStates).reduce((a, b) => a + b, 0), 0)
}

const EMPTY_MANIFEST: FolderManifest = { folders: [], assignments: {}, order: {}, folderOrder: {} }

// client.ts's get/post/put/del helpers throw `Error(\`<METHOD> <path> → <status>\`)` — `path` embeds the raw
// resource id, so substring-matching '404' anywhere in the message is unsafe (a build id containing "404",
// e.g. a uuid-hex slice like "abc404xy", would make ANY status misclassify as a 404). Anchor on the trailing
// "→ <digits>" instead. Returns null if the message isn't in that shape (network error, etc.) — never a status.
export function httpErrorStatus(err: unknown): number | null {
  const msg = err instanceof Error ? err.message : String(err)
  const m = /→ (\d+)$/.exec(msg)
  return m ? Number(m[1]) : null
}

export function containerKey(folderId: string | null): string {
  return folderId ?? 'root'
}

function genFolderId(): string {
  const uuid = globalThis.crypto?.randomUUID?.()
  if (uuid) return uuid.replace(/-/g, '').slice(0, 8)
  return `f${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`
}

// Default: newest-saved-first. If `order` lists some ids, THOSE appear in listed order at the bottom;
// anything NOT listed appears above them, newest-first — so a freshly-created/moved item floats to the top
// of a manually-ordered container.
export function sortBuilds(items: Build[], orderList: string[] | undefined): Build[] {
  const byId = new Map(items.map(b => [b.id as string, b]))
  const listedIds = (orderList ?? []).filter(id => byId.has(id))
  const listedSet = new Set(listedIds)
  const unlisted = items
    .filter(b => !listedSet.has(b.id as string))
    .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0))
  return [...unlisted, ...listedIds.map(id => byId.get(id)!)]
}

// Default: alphabetical. Same partial-override rule as sortBuilds via `folderOrder`.
export function sortFolders(items: BuildFolder[], orderList: string[] | undefined): BuildFolder[] {
  const byId = new Map(items.map(f => [f.id, f]))
  const listedIds = (orderList ?? []).filter(id => byId.has(id))
  const listedSet = new Set(listedIds)
  const unlisted = items
    .filter(f => !listedSet.has(f.id))
    .sort((a, b) => a.name.localeCompare(b.name))
  return [...unlisted, ...listedIds.map(id => byId.get(id)!)]
}

// `folders_manager.save()` rejects cycles server-side, but a hand-edited/corrupted folders.json read back
// through load() could still contain one — the `visited` set stops the walk instead of looping forever.
export function folderPath(folders: BuildFolder[], folderId: string | null): BuildFolder[] {
  const byId = new Map(folders.map(f => [f.id, f]))
  const path: BuildFolder[] = []
  const visited = new Set<string>()
  let cur = folderId ? byId.get(folderId) : undefined
  while (cur && !visited.has(cur.id)) {
    visited.add(cur.id)
    path.unshift(cur)
    cur = cur.parentId ? byId.get(cur.parentId) : undefined
  }
  return path
}

// True if `candidateId` IS `ancestorId` or a descendant of it — the cycle guard for nesting a folder.
// Same visited-set guard as folderPath — a corrupted cyclic manifest degrades to "not found" instead of hanging.
export function isSelfOrDescendant(folders: BuildFolder[], candidateId: string, ancestorId: string): boolean {
  const byId = new Map(folders.map(f => [f.id, f]))
  const visited = new Set<string>()
  let cur: BuildFolder | undefined = byId.get(candidateId)
  while (cur && !visited.has(cur.id)) {
    if (cur.id === ancestorId) return true
    visited.add(cur.id)
    cur = cur.parentId ? byId.get(cur.parentId) : undefined
  }
  return false
}

type DragOver =
  | { kind: 'build'; id: string; edge: 'before' | 'after' }
  | { kind: 'folder'; id: string; edge: 'before' | 'after' | 'onto' }
  | null

export default function BuildSelectScreen({ onNewBuild, onOpenBuild, devMode, onDevTools, onOpenVerification }: Props) {
  const heroTraits = useReferenceStore(s => s.heroTraits)
  const [builds, setBuilds] = useState<Build[]>([])
  const [manifest, setManifest] = useState<FolderManifest>(EMPTY_MANIFEST)
  const [loading, setLoading] = useState(true)
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null)

  const [aboutOpen, setAboutOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  // Open an external link on either platform: desktop routes through the IPC openExternal (system browser),
  // web falls back to window.open (where window.api doesn't exist).
  const openExternal = (url: string) => {
    if (window.api?.openExternal) window.api.openExternal(url)
    else window.open(url, '_blank', 'noopener,noreferrer')
  }
  const [importOpen, setImportOpen] = useState(false)

  const [version, setVersion] = useState('')
  const [checkStatus, setCheckStatus] = useState<'idle' | 'checking' | 'up-to-date' | 'available' | 'error'>('idle')
  const [checkError, setCheckError] = useState('')

  // ── Folder + select-mode state ──────────────────────────────────────────────
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [moveModalOpen, setMoveModalOpen] = useState(false)

  const [folderModalOpen, setFolderModalOpen] = useState(false)
  const [folderModalMode, setFolderModalMode] = useState<'create' | 'rename'>('create')
  const [folderModalName, setFolderModalName] = useState('')
  const [folderModalTargetId, setFolderModalTargetId] = useState<string | null>(null)
  const folderNameRef = useRef<HTMLInputElement>(null)

  const [deleteFolderTarget, setDeleteFolderTarget] = useState<BuildFolder | null>(null)

  const [draggedBuildId, setDraggedBuildId] = useState<string | null>(null)
  const [draggedFolderId, setDraggedFolderId] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState<DragOver>(null)
  const [dragOverCrumb, setDragOverCrumb] = useState<string>('') // folder id, or 'root'

  const loadAll = () => {
    setLoading(true)
    Promise.all([api.getBuilds(), api.getBuildFolders()])
      .then(([b, m]) => { setBuilds(b); setManifest(m); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { loadAll() }, [])

  useEffect(() => {
    // Desktop reads the version via IPC; the web build has no IPC, so it uses the version baked in at build
    // time (vite `define` __APP_VERSION__). `typeof` guard keeps the desktop bundle safe where it's undefined.
    if (typeof __APP_VERSION__ !== 'undefined' && __APP_VERSION__) setVersion(__APP_VERSION__)
    window.api?.getAppVersion?.().then(v => setVersion(v)).catch(() => {})
    window.api?.onUpdateNotAvailable?.(() => setCheckStatus('up-to-date'))
    window.api?.onUpdateAvailable?.(() => setCheckStatus('available'))
    window.api?.onUpdateCheckError?.((msg) => { setCheckStatus('error'); setCheckError(msg) })
  }, [])

  const handleCheckForUpdate = async () => {
    setCheckStatus('checking')
    const timeout = setTimeout(() => setCheckStatus('idle'), 10000)
    await window.api?.checkForUpdate?.().catch(() => {})
    clearTimeout(timeout)
  }

  useEffect(() => {
    if (folderModalOpen) setTimeout(() => folderNameRef.current?.focus(), 50)
  }, [folderModalOpen])

  const openImport = () => setImportOpen(true)

  // ── Folder manifest persistence ─────────────────────────────────────────────
  // Optimistic write, then PUT; on failure, reload the manifest from the server (per contract, the server
  // validates/cleans and hands back the authoritative manifest on success).
  const persistManifest = async (next: FolderManifest) => {
    setManifest(next)
    try {
      const saved = await api.putBuildFolders(next)
      setManifest(saved)
    } catch {
      try {
        const fresh = await api.getBuildFolders()
        setManifest(fresh)
      } catch { /* leave the optimistic state if even the reload fails */ }
    }
  }

  // ── Derived: current container contents ─────────────────────────────────────
  const buildsById = useMemo(() => new Map(builds.filter(b => b.id).map(b => [b.id as string, b])), [builds])

  const childFolders = useMemo(() => {
    const raw = manifest.folders.filter(f => f.parentId === currentFolderId)
    return sortFolders(raw, manifest.folderOrder[containerKey(currentFolderId)])
  }, [manifest, currentFolderId])

  const containerBuilds = useMemo(() => {
    const raw = builds.filter(b => b.id && (manifest.assignments[b.id] ?? null) === currentFolderId)
    return sortBuilds(raw, manifest.order[containerKey(currentFolderId)])
  }, [builds, manifest, currentFolderId])

  const crumbPath = useMemo(() => folderPath(manifest.folders, currentFolderId), [manifest.folders, currentFolderId])

  // ── Folder CRUD ──────────────────────────────────────────────────────────────
  const openCreateFolder = () => {
    setFolderModalMode('create')
    setFolderModalName('')
    setFolderModalTargetId(null)
    setFolderModalOpen(true)
  }

  const openRenameFolder = (f: BuildFolder) => {
    setFolderModalMode('rename')
    setFolderModalName(f.name)
    setFolderModalTargetId(f.id)
    setFolderModalOpen(true)
  }

  const handleFolderModalConfirm = () => {
    const name = folderModalName.trim() || 'New Folder'
    if (folderModalMode === 'create') {
      const id = genFolderId()
      persistManifest({
        ...manifest,
        folders: [...manifest.folders, { id, name, parentId: currentFolderId }],
      })
    } else if (folderModalTargetId) {
      persistManifest({
        ...manifest,
        folders: manifest.folders.map(f => f.id === folderModalTargetId ? { ...f, name } : f),
      })
    }
    setFolderModalOpen(false)
  }

  const handleDeleteFolderConfirm = () => {
    const target = deleteFolderTarget
    if (!target) return
    const parentId = target.parentId
    const assignments = { ...manifest.assignments }
    Object.keys(assignments).forEach(buildId => {
      if (assignments[buildId] === target.id) {
        if (parentId) assignments[buildId] = parentId
        else delete assignments[buildId]
      }
    })
    const order = { ...manifest.order }
    delete order[target.id]
    const folderOrder: Record<string, string[]> = {}
    Object.entries(manifest.folderOrder).forEach(([k, ids]) => {
      if (k === target.id) return // its own child-order list is dropped along with it
      folderOrder[k] = ids.filter(id => id !== target.id)
    })
    persistManifest({
      folders: manifest.folders
        .filter(f => f.id !== target.id)
        .map(f => f.parentId === target.id ? { ...f, parentId } : f),
      assignments,
      order,
      folderOrder,
    })
    if (currentFolderId === target.id) setCurrentFolderId(parentId)
    setDeleteFolderTarget(null)
  }

  // ── Drag-and-drop mutations ──────────────────────────────────────────────────
  const assignBuildToFolder = (buildId: string, folderId: string | null) => {
    const assignments = { ...manifest.assignments }
    if (folderId) assignments[buildId] = folderId
    else delete assignments[buildId]
    const order: Record<string, string[]> = {}
    Object.entries(manifest.order).forEach(([k, ids]) => { order[k] = ids.filter(id => id !== buildId) })
    persistManifest({ ...manifest, assignments, order })
  }

  const reorderBuilds = (folderId: string | null, draggedId: string, targetId: string, edge: 'before' | 'after') => {
    const key = containerKey(folderId)
    const raw = builds.filter(b => b.id && (manifest.assignments[b.id] ?? null) === folderId)
    const ordered = sortBuilds(raw, manifest.order[key])
    const ids = ordered.map(b => b.id as string).filter(id => id !== draggedId)
    const targetIdx = ids.indexOf(targetId)
    const insertAt = targetIdx === -1 ? ids.length : (edge === 'before' ? targetIdx : targetIdx + 1)
    ids.splice(insertAt, 0, draggedId)
    persistManifest({ ...manifest, order: { ...manifest.order, [key]: ids } })
  }

  const nestFolder = (draggedId: string, targetParentId: string | null) => {
    if (draggedId === targetParentId) return
    if (targetParentId && isSelfOrDescendant(manifest.folders, targetParentId, draggedId)) return
    const folderOrder: Record<string, string[]> = {}
    Object.entries(manifest.folderOrder).forEach(([k, ids]) => { folderOrder[k] = ids.filter(id => id !== draggedId) })
    persistManifest({
      ...manifest,
      folders: manifest.folders.map(f => f.id === draggedId ? { ...f, parentId: targetParentId } : f),
      folderOrder,
    })
  }

  const reorderFolders = (parentId: string | null, draggedId: string, targetId: string, edge: 'before' | 'after') => {
    const key = containerKey(parentId)
    const raw = manifest.folders.filter(f => f.parentId === parentId)
    const ordered = sortFolders(raw, manifest.folderOrder[key])
    const ids = ordered.map(f => f.id).filter(id => id !== draggedId)
    const targetIdx = ids.indexOf(targetId)
    const insertAt = targetIdx === -1 ? ids.length : (edge === 'before' ? targetIdx : targetIdx + 1)
    ids.splice(insertAt, 0, draggedId)
    persistManifest({ ...manifest, folderOrder: { ...manifest.folderOrder, [key]: ids } })
  }

  const endDrag = () => {
    setDraggedBuildId(null)
    setDraggedFolderId(null)
    setDragOver(null)
    setDragOverCrumb('')
  }

  // Build cards
  const handleBuildDragStart = (e: React.DragEvent, id: string) => {
    if (selectMode) { e.preventDefault(); return }
    setDraggedBuildId(id)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', id)
  }
  const handleBuildCardDragOver = (e: React.DragEvent, id: string) => {
    if (!draggedBuildId || draggedBuildId === id) return
    e.preventDefault()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const edge: 'before' | 'after' = e.clientY - rect.top < rect.height / 2 ? 'before' : 'after'
    setDragOver({ kind: 'build', id, edge })
  }
  const handleBuildCardDrop = (e: React.DragEvent, id: string) => {
    e.preventDefault()
    if (draggedBuildId && draggedBuildId !== id) {
      reorderBuilds(currentFolderId, draggedBuildId, id, dragOver?.kind === 'build' ? dragOver.edge : 'before')
    }
    endDrag()
  }

  // Folder cards
  const handleFolderDragStart = (e: React.DragEvent, id: string) => {
    setDraggedFolderId(id)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', id)
  }
  const handleFolderCardDragOver = (e: React.DragEvent, id: string) => {
    if (draggedBuildId) {
      e.preventDefault()
      setDragOver({ kind: 'folder', id, edge: 'onto' })
      return
    }
    if (!draggedFolderId || draggedFolderId === id) return
    e.preventDefault()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const y = e.clientY - rect.top
    let edge: 'before' | 'after' | 'onto'
    if (y < rect.height * 0.25) edge = 'before'
    else if (y > rect.height * 0.75) edge = 'after'
    else edge = 'onto'
    setDragOver({ kind: 'folder', id, edge })
  }
  const handleFolderCardDrop = (e: React.DragEvent, id: string) => {
    e.preventDefault()
    if (draggedBuildId) {
      assignBuildToFolder(draggedBuildId, id)
    } else if (draggedFolderId && draggedFolderId !== id) {
      const edge = dragOver?.kind === 'folder' ? dragOver.edge : 'onto'
      if (edge === 'onto') nestFolder(draggedFolderId, id)
      else reorderFolders(currentFolderId, draggedFolderId, id, edge)
    }
    endDrag()
  }

  // Breadcrumb segments
  const handleCrumbDragOver = (e: React.DragEvent, id: string | null) => {
    if (!draggedBuildId && !draggedFolderId) return
    e.preventDefault()
    setDragOverCrumb(containerKey(id))
  }
  const handleCrumbDrop = (e: React.DragEvent, id: string | null) => {
    e.preventDefault()
    if (draggedBuildId) {
      assignBuildToFolder(draggedBuildId, id)
    } else if (draggedFolderId) {
      if (id === draggedFolderId) { endDrag(); return }
      if (id && isSelfOrDescendant(manifest.folders, id, draggedFolderId)) { endDrag(); return }
      nestFolder(draggedFolderId, id)
    }
    endDrag()
  }

  // ── Select mode ──────────────────────────────────────────────────────────────
  const toggleSelectMode = () => {
    setSelectMode(m => !m)
    setSelectedIds(new Set())
  }

  const toggleSelected = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const handleDeleteSelected = async () => {
    const ids = [...selectedIds]
    setDeleting(true)
    setDeleteError(null)
    // allSettled — never let one failed delete (backend down mid-batch, build already gone) leave the whole
    // batch unhandled. A 404 counts as success: the build is gone either way, whichever request got there first.
    const results = await Promise.allSettled(ids.map(id => api.deleteBuild(id)))
    const succeeded: string[] = []
    const failed: string[] = []
    results.forEach((r, i) => {
      const id = ids[i]
      if (r.status === 'fulfilled') { succeeded.push(id); return }
      if (httpErrorStatus(r.reason) === 404) succeeded.push(id)
      else failed.push(id)
    })
    // Reflect whatever DID succeed locally right away, regardless of overall outcome.
    if (succeeded.length > 0) {
      const assignments = { ...manifest.assignments }
      succeeded.forEach(id => delete assignments[id])
      const order: Record<string, string[]> = {}
      Object.entries(manifest.order).forEach(([k, list]) => { order[k] = list.filter(id => !succeeded.includes(id)) })
      setManifest(m => ({ ...m, assignments, order }))
    }
    // Always reconcile against the server — builds list + manifest — whether this batch fully succeeded,
    // partially succeeded, or fully failed, so the UI never drifts from what's actually on disk.
    loadAll()
    setDeleting(false)
    if (failed.length > 0) {
      const names = failed.map(id => buildsById.get(id)?.name || 'Untitled').join(', ')
      setDeleteError(`Failed to delete: ${names}. Try again.`)
      setSelectedIds(new Set(failed))
    } else {
      setDeleteConfirmOpen(false)
      setSelectMode(false)
      setSelectedIds(new Set())
    }
  }

  const handleMoveSelectedTo = (targetFolderId: string | null) => {
    const ids = [...selectedIds]
    const assignments = { ...manifest.assignments }
    ids.forEach(id => {
      if (targetFolderId) assignments[id] = targetFolderId
      else delete assignments[id]
    })
    const order: Record<string, string[]> = {}
    Object.entries(manifest.order).forEach(([k, list]) => { order[k] = list.filter(id => !ids.includes(id)) })
    persistManifest({ ...manifest, assignments, order })
    setMoveModalOpen(false)
    setSelectMode(false)
    setSelectedIds(new Set())
  }

  const containerEmpty = childFolders.length === 0 && containerBuilds.length === 0

  const renderFolderTreeOptions = (parentId: string | null, depth: number): React.ReactNode[] => {
    const kids = sortFolders(manifest.folders.filter(f => f.parentId === parentId), manifest.folderOrder[containerKey(parentId)])
    return kids.flatMap(f => [
      <button
        key={f.id}
        className="folder-picker-row"
        style={{ paddingLeft: 14 + depth * 18 }}
        onClick={() => handleMoveSelectedTo(f.id)}
      >
        {f.name}
      </button>,
      ...renderFolderTreeOptions(f.id, depth + 1),
    ])
  }

  return (
    <div className="screen build-select">
      <div className="build-select-top">
        <div className="build-select-corner">
          {devMode && (
            <button
              className="btn btn-sm build-select-devtools"
              onClick={onDevTools}
              title="Developer Tools"
            >
              Dev Tools
            </button>
          )}
          <button
            className="btn btn-sm build-select-discord"
            onClick={() => openExternal('https://discord.gg/7hEySM4WYx')}
          >
            Join the Discord to share feedback or bugs you find!
          </button>
        </div>
        <img src={logoSrc} className="build-select-logo" alt="TLI Builder" />
        {/* Create cluster: the three "add a build" actions, grouped as one unit — Import Code on top,
            + New Folder / + New Build together in a row beneath it. + New Build stays the sole primary
            (filled/accent) action; the other two read as secondary. */}
        <div className="build-select-actions build-select-create-cluster">
          <button className="btn btn-secondary btn-sm build-select-import" onClick={openImport}>Import Code</button>
          <div className="build-select-create-row">
            <button className="btn btn-secondary" onClick={openCreateFolder}>+ New Folder</button>
            <button className="btn btn-primary" onClick={() => onNewBuild(currentFolderId ?? undefined)}>+ New Build</button>
          </div>
        </div>
      </div>

      {/* Select-mode trigger — pulled out of the create cluster since it's a selection MODE that acts on
          the build list, not a create action. Presented as a checkbox-style toggle: unchecked = "Select",
          checked = live selected count + the Delete/Move actions right there. Un-checking it exits select
          mode via the SAME toggleSelectMode handler the old "Cancel" button used. */}
      {builds.length > 0 && (
        <div className="build-select-toolbar">
          <label className={`select-toggle${selectMode ? ' select-toggle--active' : ''}`}>
            <input
              type="checkbox"
              className="select-toggle-checkbox"
              checked={selectMode}
              onChange={toggleSelectMode}
            />
            <span className="select-toggle-label">
              {selectMode ? `${selectedIds.size} selected` : 'Select'}
            </span>
          </label>
          {selectMode && (
            <div className="select-toggle-actions">
              <button
                className="btn btn-danger btn-sm"
                disabled={selectedIds.size === 0}
                onClick={() => { setDeleteError(null); setDeleteConfirmOpen(true) }}
              >Delete</button>
              <button
                className="btn btn-secondary btn-sm"
                disabled={selectedIds.size === 0}
                onClick={() => setMoveModalOpen(true)}
              >Move to…</button>
            </div>
          )}
        </div>
      )}

      <div className="build-breadcrumb">
        <span
          className={`build-breadcrumb-seg${currentFolderId === null ? ' build-breadcrumb-seg--current' : ''}${dragOverCrumb === 'root' ? ' drop-target' : ''}`}
          onClick={() => setCurrentFolderId(null)}
          onDragOver={e => handleCrumbDragOver(e, null)}
          onDragLeave={() => setDragOverCrumb('')}
          onDrop={e => handleCrumbDrop(e, null)}
        >All Builds</span>
        {crumbPath.map((f, i) => (
          <React.Fragment key={f.id}>
            <span className="build-breadcrumb-sep">›</span>
            <span
              className={`build-breadcrumb-seg${i === crumbPath.length - 1 ? ' build-breadcrumb-seg--current' : ''}${dragOverCrumb === f.id ? ' drop-target' : ''}`}
              onClick={() => setCurrentFolderId(f.id)}
              onDragOver={e => handleCrumbDragOver(e, f.id)}
              onDragLeave={() => setDragOverCrumb('')}
              onDrop={e => handleCrumbDrop(e, f.id)}
            >{f.name}</span>
          </React.Fragment>
        ))}
      </div>

      {loading ? (
        <LoadingState label="Loading builds…" />
      ) : builds.length === 0 ? (
        <div className="empty-state">
          <p>No saved builds yet.</p>
          <p>Click <strong style={{ color: '#e0e0e0' }}>+ New Build</strong> to get started.</p>
        </div>
      ) : containerEmpty ? (
        <div className="empty-state">
          <p>This folder is empty.</p>
        </div>
      ) : (
        <div className="build-list dark-scroll">
          {childFolders.map(f => {
            const over = dragOver?.kind === 'folder' && dragOver.id === f.id ? dragOver.edge : null
            return (
              <div
                key={f.id}
                className={`folder-card${over ? ` folder-card--${over}` : ''}`}
                draggable={!selectMode}
                onDragStart={e => handleFolderDragStart(e, f.id)}
                onDragOver={e => handleFolderCardDragOver(e, f.id)}
                onDragEnd={endDrag}
                onDrop={e => handleFolderCardDrop(e, f.id)}
                onClick={() => setCurrentFolderId(f.id)}
              >
                <span className="folder-card-icon" />
                <span className="folder-card-name">{f.name}</span>
                <div className="folder-card-actions">
                  <button className="btn btn-secondary btn-sm" onClick={e => { e.stopPropagation(); openRenameFolder(f) }}>Rename</button>
                  <button className="btn btn-danger btn-sm" onClick={e => { e.stopPropagation(); setDeleteFolderTarget(f) }}>Delete</button>
                </div>
              </div>
            )
          })}
          {containerBuilds.map(build => {
            const over = dragOver?.kind === 'build' && dragOver.id === build.id ? dragOver.edge : null
            return (
              <div
                key={build.id}
                className={`build-card${over ? ` build-card--${over}` : ''}${selectedIds.has(build.id as string) ? ' build-card--selected' : ''}`}
                draggable={!selectMode}
                onDragStart={e => handleBuildDragStart(e, build.id as string)}
                onDragOver={e => handleBuildCardDragOver(e, build.id as string)}
                onDragEnd={endDrag}
                onDrop={e => handleBuildCardDrop(e, build.id as string)}
                onClick={() => selectMode ? toggleSelected(build.id as string) : onOpenBuild(build)}
              >
                {selectMode && (
                  <input
                    type="checkbox"
                    className="build-card-checkbox"
                    checked={selectedIds.has(build.id as string)}
                    onClick={e => e.stopPropagation()}
                    onChange={() => toggleSelected(build.id as string)}
                  />
                )}
                <div className="build-card-info">
                  <span className="build-name">{build.name}</span>
                  {(() => {
                    const { level, identity } = characterSummary(build, heroTraits)
                    return (
                      <span className="build-hero">
                        Lv {level}{identity && <> <span className="build-hero-name">{identity}</span></>}
                      </span>
                    )
                  })()}
                  <span className="build-pts">{totalPoints(build)} pts</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="build-select-footer">
        {/* Row 1: version stacked ABOVE the Check-for-Update button (not inline beside it). */}
        {version && <span className="build-select-version">v{version}</span>}
        {/* Auto-update is desktop-only; the web app updates by redeploy + refresh. */}
        {!IS_WEB && <div className="build-select-footer-actions">
          <button
            className="btn btn-sm btn-secondary"
            onClick={handleCheckForUpdate}
            disabled={checkStatus === 'checking'}
            title={checkStatus === 'error' ? checkError : undefined}
          >
            {checkStatus === 'checking' ? 'Checking…'
              : checkStatus === 'up-to-date' ? '✓ Up to date'
              : checkStatus === 'available' ? 'Update available'
              : checkStatus === 'error' ? `Check failed`
              : 'Check for Update'}
          </button>
        </div>}
        {/* Row 2: Settings + About. */}
        <div className="build-select-footer-actions">
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => setSettingsOpen(true)}
          >
            ⚙ Settings
          </button>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => setAboutOpen(true)}
          >
            About
          </button>
        </div>
        {/* Row 3: Verification Database (app-global, sits below Settings/About). */}
        {onOpenVerification && <div className="build-select-footer-actions">
          <button
            className="btn btn-sm btn-secondary"
            onClick={onOpenVerification}
          >
            Reference &amp; Verification
          </button>
        </div>}
        {/* Row 4: Support the developer (Ko-fi) — subtle link matching the sidebar's style. */}
        <div className="build-select-footer-actions">
          <button
            className="build-select-support"
            onClick={() => openExternal('https://ko-fi.com/tlibuilder')}
            title="Support TLI Builder on Ko-fi"
          >
            ♥ Support the developer
          </button>
        </div>
      </div>

      {settingsOpen && <SettingsOverlay onClose={() => setSettingsOpen(false)} />}

      {aboutOpen && (
        <div className="modal-backdrop" onClick={() => setAboutOpen(false)}>
          <div className="modal-card about-modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">About TLI Builder{version ? ` · v${version}` : ''}</h3>
            <div className="about-modal-body">
              <h4 className="about-section-title">Guides &amp; Info</h4>
              <p>
                Visit the TLI Builder website for guides, FAQs, and more about the project:{' '}
                <button className="about-link-inline" onClick={() => openExternal('https://about.tlibuilder.com')}>about.tlibuilder.com</button>
              </p>

              <h4 className="about-section-title">Disclaimer</h4>
              <p>
                <strong>TLI Builder is an unofficial, non-commercial fan-made project.</strong> It is not
                affiliated with, endorsed by, sponsored by, or in any way officially connected to XD Inc. /
                XD Games or any of their subsidiaries or affiliates.
              </p>
              <p>
                <em>Torchlight: Infinite</em> and all related names, logos, characters, images, and assets
                are trademarks and copyrights of their respective owners. They are used here solely for
                identification and reference purposes.
              </p>

              <h4 className="about-section-title">Data &amp; Sources</h4>
              <p>
                Game data and icons used throughout TLI Builder — skills, gear, talent trees, pact spirits,
                hero traits, and more — are sourced from <strong>TLIDB</strong>, the community Torchlight:
                Infinite database, used with permission. Full credit and thanks go to the TLIDB team for
                maintaining this resource. No ownership of any game assets is claimed.
              </p>

              <h4 className="about-section-title">Asset Removal &amp; Contact</h4>
              <p>
                If you are a rights holder (or an authorized representative) and would like any asset removed,
                please reach out and it will be removed promptly:
              </p>
              <p className="about-contact">
                Email: <span>Tyrayla@gmail.com</span><br />
                Discord: <span>tyrayla</span>
              </p>
              <p className="about-links">
                <button className="about-link-btn" onClick={() => openExternal('https://about.tlibuilder.com')}>Website</button>
                <button className="about-link-btn" onClick={() => openExternal('https://tlidb.com')}>TLIDB</button>
                <button className="about-link-btn" onClick={() => openExternal('https://github.com/Tyrayla/TLIBuilder')}>GitHub</button>
              </p>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setAboutOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {importOpen && (
        <div className="modal-backdrop" onClick={() => setImportOpen(false)}>
          <div className="modal-card share-modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">Import Build</h3>
            <ImportPanel onImport={(build) => { setImportOpen(false); onOpenBuild(build) }} autoFocus />
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setImportOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {folderModalOpen && (
        <div className="modal-backdrop" onClick={() => setFolderModalOpen(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">{folderModalMode === 'rename' ? 'Rename Folder' : 'New Folder'}</h3>
            <input
              ref={folderNameRef}
              className="modal-input"
              type="text"
              placeholder="Folder name…"
              value={folderModalName}
              onChange={e => setFolderModalName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleFolderModalConfirm()}
            />
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleFolderModalConfirm}>
                {folderModalMode === 'rename' ? 'Rename' : 'Create'}
              </button>
              <button className="btn btn-secondary" onClick={() => setFolderModalOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {deleteFolderTarget && (
        <div className="modal-backdrop" onClick={() => setDeleteFolderTarget(null)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">Delete "{deleteFolderTarget.name}"?</h3>
            <p style={{ padding: '0 20px 16px', color: '#aaa', fontSize: 13, lineHeight: 1.6 }}>
              Its builds and subfolders will move up to {deleteFolderTarget.parentId ? 'its parent folder' : '"All Builds"'}.
              The folder itself will be removed. This can't be undone.
            </p>
            <div className="modal-actions">
              <button className="btn btn-danger" onClick={handleDeleteFolderConfirm}>Delete Folder</button>
              <button className="btn btn-secondary" onClick={() => setDeleteFolderTarget(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {deleteConfirmOpen && (
        <div
          className="modal-backdrop"
          onClick={() => { if (!deleting) { setDeleteConfirmOpen(false); setDeleteError(null) } }}
        >
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">Delete {selectedIds.size} build{selectedIds.size === 1 ? '' : 's'}?</h3>
            <div style={{ padding: '0 20px 8px', maxHeight: '30vh', overflowY: 'auto' }}>
              <ul style={{ margin: 0, paddingLeft: 18, color: '#cfd6e6', fontSize: 13, lineHeight: 1.8 }}>
                {[...selectedIds].map(id => (
                  <li key={id}>{buildsById.get(id)?.name || 'Untitled'}</li>
                ))}
              </ul>
            </div>
            <p style={{ padding: '0 20px 16px', color: '#aaa', fontSize: 13 }}>This can't be undone.</p>
            {deleteError && <p className="share-import-error">{deleteError}</p>}
            <div className="modal-actions">
              <button className="btn btn-danger" onClick={handleDeleteSelected} disabled={deleting}>
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => { setDeleteConfirmOpen(false); setDeleteError(null) }}
                disabled={deleting}
              >Cancel</button>
            </div>
          </div>
        </div>
      )}

      {moveModalOpen && (
        <div className="modal-backdrop" onClick={() => setMoveModalOpen(false)}>
          <div className="modal-card folder-picker-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">Move {selectedIds.size} build{selectedIds.size === 1 ? '' : 's'} to…</h3>
            <div className="folder-picker-list dark-scroll">
              <button className="folder-picker-row" style={{ paddingLeft: 14 }} onClick={() => handleMoveSelectedTo(null)}>
                All Builds
              </button>
              {renderFolderTreeOptions(null, 1)}
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setMoveModalOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
