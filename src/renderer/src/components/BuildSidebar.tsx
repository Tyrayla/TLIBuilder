import React, { useState } from 'react'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs, SIDEBAR_MIN, SIDEBAR_MAX } from '../store/uiPrefsStore'
import SettingsOverlay from './SettingsOverlay'
import LoadoutOverlay from './LoadoutOverlay'
import type { OffenseResult } from '../api/client'
import { dec } from '../utils/num'

interface Props {
  screen: string
  buildName: string
  isDirty: boolean
  onNav: (target: string) => void
  onSave: () => void
  onSaveAs: () => void
  onGoBack: () => void
}

function NavBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button className={`sidebar-nav-btn${active ? ' active' : ''}`} onClick={onClick}>
      {label}
    </button>
  )
}

function fmtDps(n: number): string {
  if (n >= 1_000_000_000_000_000) return `${dec((n / 1_000_000_000_000_000))}Q`
  if (n >= 1_000_000_000_000)     return `${dec((n / 1_000_000_000_000))}T`
  if (n >= 1_000_000_000)         return `${dec((n / 1_000_000_000))}B`
  if (n >= 1_000_000)             return `${dec((n / 1_000_000))}M`
  if (n >= 100_000)               return `${dec((n / 1_000))}k`
  return n.toFixed(0)
}

function DpsBox({ onNav }: { onNav: (t: string) => void }) {
  const computedStats = useBuildStore(s => s.computedStats)
  const statsLoading  = useBuildStore(s => s.statsLoading)
  const skills        = useBuildStore(s => s.skills)
  const skillsById    = useReferenceStore(s => s.skillsById)

  // Total DPS = sum of each contributing skill's own slot offense. A skill contributes when it's
  // dps-eligible (dev flag), enabled, and toggled into Full DPS (countInDps). Listed in slot order.
  const slotOffense = (computedStats as { slot_offense?: Record<string, OffenseResult> | null }).slot_offense ?? null
  const contributors = [...skills]
    .filter(sk => sk.enabled !== false && sk.countInDps !== false && !!skillsById?.[sk.item_id]?.dps_eligible)
    .sort((a, b) => a.slot - b.slot)
    .map(sk => ({ name: sk.name, dps: slotOffense?.[String(sk.slot)]?.total_dps_vs_target ?? 0 }))
    .filter(c => c.dps > 0)
  const total = contributors.reduce((s, c) => s + c.dps, 0)

  // Keep showing the last computed total/rows while a recompute is in flight (computedStats holds the
  // previous result until the new one lands) — only fall back to a placeholder when there's nothing yet.
  // This avoids the box flashing "…"/empty on every edit.
  return (
    <div className="sidebar-dps-box" onClick={() => onNav('stats')} title="Click to open Calcs">
      <div className="sidebar-dps-label">Full DPS</div>
      <div className="sidebar-dps-value">
        {total > 0 ? fmtDps(total) : statsLoading ? '…' : '—'}
      </div>
      {contributors.length > 0 && (
        <div className="sidebar-dps-breakdown">
          {contributors.map((c, i) => (
            <div key={i} className="sidebar-dps-row">
              <span className="sidebar-dps-row-name" title={c.name}>{c.name}</span>
              <span className="sidebar-dps-row-val">{Math.round(c.dps).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Active-loadout dropdown + gear. The dropdown floats over the nav (absolute) rather than pushing it down.
function LoadoutBar({ onManage }: { onManage: (v: 'list' | 'create') => void }) {
  const loadouts = useBuildStore(s => s.loadouts)
  const activeId = useBuildStore(s => s.activeLoadoutId)
  const switchLoadout = useBuildStore(s => s.switchLoadout)
  const [open, setOpen] = useState(false)
  const active = loadouts.find(l => l.id === activeId)
  return (
    <div className="sidebar-loadout-row">
      <div className="loadout-dd">
        <button className="loadout-dd-trigger" onClick={() => setOpen(o => !o)} title="Switch loadout">
          <span className="loadout-dd-name">{active?.name ?? 'Loadout'}</span>
          <span className="loadout-dd-caret">{open ? '▴' : '▾'}</span>
        </button>
        {open && (
          <>
            <div className="loadout-dd-backdrop" onClick={() => setOpen(false)} />
            <div className="loadout-dd-menu">
              {loadouts.map(l => (
                <button key={l.id} className={`loadout-dd-item${l.id === activeId ? ' active' : ''}`}
                  onClick={() => { switchLoadout(l.id); setOpen(false) }}>
                  <span className="loadout-dd-item-name">{l.name}</span>
                  {l.id === activeId && <span className="loadout-dd-check">✓</span>}
                </button>
              ))}
              <div className="loadout-dd-sep" />
              <button className="loadout-dd-item" onClick={() => { setOpen(false); onManage('create') }}>＋ New loadout…</button>
              <button className="loadout-dd-item" onClick={() => { setOpen(false); onManage('list') }}>⚙ Manage…</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function BuildSidebar({ screen, buildName, isDirty, onNav, onSave, onSaveAs, onGoBack }: Props) {
  const isTreeActive = screen === 'tree-selector' || screen === 'tree-viewer'
  const [showSettings, setShowSettings] = useState(false)
  const [loadoutView, setLoadoutView] = useState<null | 'list' | 'create'>(null)
  const sidebarWidth = useUiPrefs(s => s.sidebarWidth)
  const setSidebarWidth = useUiPrefs(s => s.setSidebarWidth)

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = sidebarWidth
    const onMove = (ev: MouseEvent) => {
      const w = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startW + (ev.clientX - startX)))
      setSidebarWidth(w)
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    document.body.style.userSelect = 'none'
  }

  return (
    <div className="sidebar-shell" style={{ width: sidebarWidth }}>
    <div className="build-sidebar">
      <div className="sidebar-build-name" title={buildName || 'New Build'}>
        {buildName || 'New Build'}
      </div>
      <div className="sidebar-save-row">
        <button className="sidebar-save-btn" onClick={onSave}>
          Save{isDirty ? ' *' : ''}
        </button>
        <button className="sidebar-save-btn" onClick={onSaveAs}>Save As</button>
      </div>

      <DpsBox onNav={onNav} />

      <div className="sidebar-divider" />

      <LoadoutBar onManage={setLoadoutView} />

      <div className="sidebar-divider" />

      <NavBtn label="Config" active={screen === 'build-overview'} onClick={() => onNav('build-overview')} />
      <NavBtn label="Calcs" active={screen === 'stats'} onClick={() => onNav('stats')} />
      <NavBtn label="Notes" active={screen === 'notes'} onClick={() => onNav('notes')} />

      <div className="sidebar-divider" />

      <NavBtn label="Talent Tree" active={isTreeActive} onClick={() => onNav('tree-selector')} />
      <NavBtn label="Slates" active={screen === 'slate-board'} onClick={() => onNav('slate-board')} />
      <NavBtn label="Gear" active={screen === 'gear'} onClick={() => onNav('gear')} />
      <NavBtn label="Skills" active={screen === 'skills'} onClick={() => onNav('skills')} />
      <NavBtn label="Hero Trait" active={screen === 'hero-traits'} onClick={() => onNav('hero-traits')} />
      <NavBtn label="Pact Spirits" active={screen === 'pact-spirits'} onClick={() => onNav('pact-spirits')} />

      <div className="sidebar-divider" />

      <NavBtn label="Import / Export" active={screen === 'import-export'} onClick={() => onNav('import-export')} />
      <NavBtn label="⚙ Settings" active={false} onClick={() => setShowSettings(true)} />

      <div className="sidebar-spacer" />

      {/* The "NYI flags" toggle moved to Settings → Display (defaults ON). */}
      <button className="sidebar-nav-btn sidebar-back" onClick={onGoBack}>← Back to Builds</button>

      {showSettings && <SettingsOverlay onClose={() => setShowSettings(false)} />}
      {loadoutView && <LoadoutOverlay initialView={loadoutView} onClose={() => setLoadoutView(null)} />}
    </div>
      <div className="sidebar-resize-handle" onMouseDown={startResize} title="Drag to resize the sidebar" />
    </div>
  )
}
