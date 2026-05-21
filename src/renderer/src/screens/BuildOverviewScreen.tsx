import React, { useEffect, useState } from 'react'
import { api, TreeSlot, SeasonSummary } from '../api/client'

interface Props {
  buildName: string
  buildId: string | null
  slots: (TreeSlot | null)[]
  onBack: () => void
  onTalentTree: () => void
  onSlates: () => void
  onStats: () => void
  onSave: (name: string) => Promise<void>
  onSaveAs: (name: string) => Promise<void>
  devMode?: boolean
  onSeasonChange?: () => void
}

type SaveMode = 'save' | 'saveas'

export default function BuildOverviewScreen({
  buildName, buildId, slots, onBack, onTalentTree, onSlates, onStats, onSave, onSaveAs,
  devMode = false, onSeasonChange,
}: Props) {
  const [saveOpen, setSaveOpen] = useState(false)
  const [seasons, setSeasons] = useState<SeasonSummary[]>([])
  const [activeSeason, setActiveSeason] = useState<string | null>(null)

  useEffect(() => {
    if (!devMode) return
    api.listSeasons().then(s => {
      setSeasons(s)
      setActiveSeason(s.find(x => x.is_active)?.name ?? null)
    }).catch(() => {})
  }, [devMode])

  const handleSeasonChange = async (name: string | null) => {
    try {
      await api.setActiveSeason(name)
      setActiveSeason(name)
      setSeasons(prev => prev.map(s => ({ ...s, is_active: s.name === name })))
      onSeasonChange?.()
    } catch { /* ignore */ }
  }

  const [saveMode, setSaveMode] = useState<SaveMode>('save')
  const [saveName, setSaveName] = useState(buildName)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')

  const showMsg = (msg: string) => {
    setSavedMsg(msg)
    setTimeout(() => setSavedMsg(''), 2500)
  }

  const handleSave = async () => {
    if (buildId) {
      setSaving(true)
      try {
        await onSave(buildName || 'Untitled')
        showMsg('Saved!')
      } catch { showMsg('Save failed.') }
      finally { setSaving(false) }
    } else {
      setSaveMode('save')
      setSaveName(buildName || '')
      setSaveOpen(true)
    }
  }

  const handleSaveAs = () => {
    setSaveMode('saveas')
    setSaveName(buildName || '')
    setSaveOpen(true)
  }

  const handleModalConfirm = async () => {
    const name = saveName.trim() || 'Untitled'
    setSaving(true)
    try {
      if (saveMode === 'saveas') {
        await onSaveAs(name)
      } else {
        await onSave(name)
      }
      setSaveOpen(false)
      showMsg('Saved!')
    } catch { showMsg('Save failed.') }
    finally { setSaving(false) }
  }

  const filledSlots = slots.filter(Boolean).length

  return (
    <div className="screen build-overview">
      <div className="overview-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <h2 className="title-accent" style={{ fontSize: 20 }}>
          {buildName || 'New Build'}
        </h2>
        <div className="overview-save-btns">
          <button
            className="btn btn-sm overview-save-btn"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            className="btn btn-sm overview-saveas-btn"
            onClick={handleSaveAs}
            disabled={saving}
          >
            Save As
          </button>
        </div>
      </div>

      {savedMsg && (
        <div className="overview-saved-msg">{savedMsg}</div>
      )}

      {devMode && seasons.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', background: '#0e0e28', borderBottom: '1px solid #2a2a4a', fontSize: 12 }}>
          <span style={{ color: '#666', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>Season:</span>
          <select
            value={activeSeason ?? ''}
            onChange={e => handleSeasonChange(e.target.value || null)}
            style={{ background: '#1a1a3a', color: '#ddd', border: '1px solid #3a3a5a', borderRadius: 4, padding: '3px 8px', fontSize: 12 }}
          >
            <option value="">— Current (Python builders) —</option>
            {seasons.map(s => (
              <option key={s.name} value={s.name}>{s.name}</option>
            ))}
          </select>
          {activeSeason && (
            <span style={{ fontSize: 11, color: '#c0a0ff' }}>
              {seasons.find(s => s.name === activeSeason)?.trees.length ?? 0} trees loaded
            </span>
          )}
        </div>
      )}

      <div className="overview-nav-area">
        <button className="overview-nav-btn active" onClick={onTalentTree}>
          <span className="overview-nav-icon">🌿</span>
          <span className="overview-nav-label">Talent Tree</span>
          {filledSlots > 0 && (
            <span className="overview-nav-sub">{filledSlots} / 4 slots</span>
          )}
        </button>
        <button className="overview-nav-btn active" onClick={onSlates}>
          <span className="overview-nav-icon">📋</span>
          <span className="overview-nav-label">Slates</span>
        </button>
        <button className="overview-nav-btn active" onClick={onStats}>
          <span className="overview-nav-icon">📊</span>
          <span className="overview-nav-label">Stats</span>
        </button>
        <button className="overview-nav-btn disabled" disabled>
          <span className="overview-nav-icon">⚔️</span>
          <span className="overview-nav-label">Gear</span>
          <span className="overview-nav-sub">Coming soon</span>
        </button>
      </div>

      {saveOpen && (
        <div className="modal-backdrop" onClick={() => setSaveOpen(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">
              {saveMode === 'saveas' ? 'Save As New Build' : 'Name Your Build'}
            </h3>
            <input
              className="modal-input"
              type="text"
              placeholder="Enter a build name…"
              value={saveName}
              onChange={e => setSaveName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleModalConfirm()}
              autoFocus
            />
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleModalConfirm} disabled={saving}>
                {saving ? 'Saving…' : 'Save'}
              </button>
              <button className="btn btn-danger" onClick={() => setSaveOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
