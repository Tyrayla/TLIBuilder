import React, { useState } from 'react'
import { TreeSlot } from '../api/client'

interface Props {
  buildName: string
  buildId: string | null
  slots: (TreeSlot | null)[]
  onBack: () => void
  onTalentTree: () => void
  onSave: (name: string) => Promise<void>
}

export default function BuildOverviewScreen({
  buildName, buildId, slots, onBack, onTalentTree, onSave,
}: Props) {
  const [saveName, setSaveName] = useState(buildName)
  const [saveOpen, setSaveOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')

  const openSave = () => {
    setSaveName(buildName)
    setSaveOpen(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(saveName.trim() || 'Untitled')
      setSaveOpen(false)
      setSavedMsg('Build saved!')
      setTimeout(() => setSavedMsg(''), 3000)
    } catch {
      setSavedMsg('Save failed.')
    } finally {
      setSaving(false)
    }
  }

  const filledSlots = slots.filter(Boolean).length

  return (
    <div className="screen build-overview">
      <div className="overview-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <h2 className="title-accent" style={{ fontSize: 20 }}>
          {buildName || 'New Build'}
        </h2>
        <button className="btn btn-primary btn-sm" onClick={openSave}>
          {buildId ? 'Save Build' : 'Save Build'}
        </button>
      </div>

      {savedMsg && (
        <div style={{ textAlign: 'center', color: '#6bcb77', fontSize: 12, padding: '4px 0' }}>
          {savedMsg}
        </div>
      )}

      <div className="overview-slot-preview">
        {slots.map((slot, i) => (
          <div key={i} className={`overview-slot-chip${slot ? ' filled' : ''}`}>
            <span className="overview-slot-num">Slot {i + 1}</span>
            <span className="overview-slot-tree">{slot?.treeName ?? 'Empty'}</span>
          </div>
        ))}
      </div>

      <div className="overview-nav-area">
        <button className="overview-nav-btn active" onClick={onTalentTree}>
          <span className="overview-nav-icon">🌿</span>
          <span className="overview-nav-label">Talent Tree</span>
          {filledSlots > 0 && (
            <span className="overview-nav-sub">{filledSlots} / 4 slots</span>
          )}
        </button>
        <button className="overview-nav-btn disabled" disabled>
          <span className="overview-nav-icon">📋</span>
          <span className="overview-nav-label">Slates</span>
          <span className="overview-nav-sub">Coming soon</span>
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
            <h3 className="modal-title">Save Build</h3>
            <input
              className="modal-input"
              type="text"
              placeholder="Enter a build name…"
              value={saveName}
              onChange={e => setSaveName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSave()}
              autoFocus
            />
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
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
