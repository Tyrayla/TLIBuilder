import React, { useEffect, useState } from 'react'
import { api, Build } from '../api/client'

interface Props {
  onNewBuild: () => void
  onOpenBuild: (build: Build) => void
}

function slotSummary(build: Build): string {
  const names = build.slots.filter(Boolean).map(s => s!.treeName)
  return names.length ? names.join(' · ') : 'No trees selected'
}

function totalPoints(build: Build): number {
  return build.slots.filter(Boolean).reduce((sum, s) =>
    sum + Object.values(s!.nodeStates).reduce((a, b) => a + b, 0), 0)
}

export default function BuildSelectScreen({ onNewBuild, onOpenBuild }: Props) {
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
      <div className="build-select-header">
        <h1 className="title-accent">TLI Planner</h1>
        <button className="btn btn-primary" onClick={onNewBuild}>+ New Build</button>
      </div>

      {loading ? (
        <p style={{ color: '#888', marginTop: 24 }}>Loading…</p>
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
