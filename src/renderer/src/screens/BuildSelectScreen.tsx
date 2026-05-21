import React, { useEffect, useState } from 'react'
import { api, Build } from '../api/client'
import logoSrc from '../assets/logo.png'

interface Props {
  onNewBuild: () => void
  onOpenBuild: (build: Build) => void
  devMode?: boolean
  onDevTools?: () => void
}

function slotSummary(build: Build): string {
  const names = build.slots.filter(Boolean).map(s => s!.treeName)
  return names.length ? names.join(' · ') : 'No trees selected'
}

function totalPoints(build: Build): number {
  return build.slots.filter(Boolean).reduce((sum, s) =>
    sum + Object.values(s!.nodeStates).reduce((a, b) => a + b, 0), 0)
}

export default function BuildSelectScreen({ onNewBuild, onOpenBuild, devMode, onDevTools }: Props) {
  const [builds, setBuilds] = useState<Build[]>([])
  const [loading, setLoading] = useState(true)

  const loadBuilds = () => {
    setLoading(true)
    api.getBuilds()
      .then(b => { setBuilds(b); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { loadBuilds() }, [])

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    await api.deleteBuild(id)
    loadBuilds()
  }

  return (
    <div className="screen build-select">
      <div className="build-select-top">
        <div className="build-select-spacer" />
        <img src={logoSrc} className="build-select-logo" alt="TLI Builder" />
        <div className="build-select-actions">
          {devMode && (
            <button
              className="btn btn-sm"
              onClick={onDevTools}
              style={{ color: '#ff9800', borderColor: '#5a3a00', background: '#1a0e00' }}
              title="Developer Tools"
            >
              Dev Tools
            </button>
          )}
          <button className="btn btn-primary" onClick={onNewBuild}>+ New Build</button>
        </div>
      </div>

      {loading ? (
        <p style={{ color: '#888', marginTop: 8 }}>Loading…</p>
      ) : builds.length === 0 ? (
        <div className="empty-state">
          <p>No saved builds yet.</p>
          <p>Click <strong style={{ color: '#e0e0e0' }}>+ New Build</strong> to get started.</p>
        </div>
      ) : (
        <div className="build-list">
          {builds.map(build => (
            <div key={build.id} className="build-card" onClick={() => onOpenBuild(build)}>
              <div className="build-card-info">
                <span className="build-name">{build.name}</span>
                <span className="build-tree">{slotSummary(build)}</span>
                <span className="build-pts">{totalPoints(build)} pts</span>
              </div>
              <div className="build-card-actions">
                <button
                  className="btn btn-danger btn-sm"
                  onClick={e => build.id && handleDelete(build.id, e)}
                >Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
