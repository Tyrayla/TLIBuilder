import React, { useEffect, useState } from 'react'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs, SIDEBAR_MIN, SIDEBAR_MAX } from '../store/uiPrefsStore'
import SettingsOverlay from './SettingsOverlay'
import LoadoutOverlay from './LoadoutOverlay'
import type { OffenseResult } from '../api/client'
import { dec } from '../utils/num'
import { characterSummary } from '../utils/characterSummary'
import { characterLevelFrom } from '../utils/conditions'

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

  // Minion owners (Spirit Magi / Synthetic Troops / Modules) contribute their minion's DPS = the ONE combined
  // OffenseResult's total_dps_vs_target. A minion is only ever supported through a bespoke module, which combines
  // its damage abilities into that single result (no double-counting Enhanced-replaces-Base — those are uptime-
  // split hit forms). Unmodelled minions are NYI → supported=false → contribute 0. Gated by the owner skill's
  // enabled / countInDps toggles (the owner passive itself isn't dps_eligible, but its minions deal the damage).
  const minionOffense = (computedStats as { minion_offense?: Record<string, OffenseResult> | null }).minion_offense ?? null
  const minionContributors = minionOffense
    ? Object.entries(minionOffense).flatMap(([ownerId, result]) => {
        const ownerSk = skills.find(sk => sk.item_id === ownerId)
        if (ownerSk && (ownerSk.enabled === false || ownerSk.countInDps === false)) return []
        const dps = result.supported ? (result.total_dps_vs_target ?? 0) : 0
        if (dps <= 0) return []
        const name = ownerSk?.name ?? skillsById?.[ownerId]?.name ?? ownerId
        return [{ name: `${name} (minion)`, dps }]
      })
    : []

  const allContributors = [...contributors, ...minionContributors]
  const total = allContributors.reduce((s, c) => s + c.dps, 0)

  // Keep showing the last computed total/rows while a recompute is in flight (computedStats holds the
  // previous result until the new one lands) — only fall back to a placeholder when there's nothing yet.
  // This avoids the box flashing "…"/empty on every edit.
  return (
    <div className="sidebar-dps-box" onClick={() => onNav('stats')} title="Click to open Calcs">
      <div className="sidebar-dps-label">Full DPS</div>
      <div className="sidebar-dps-value">
        {total > 0 ? fmtDps(total) : statsLoading ? '…' : '—'}
      </div>
      {allContributors.length > 0 && (
        <div className="sidebar-dps-breakdown">
          {allContributors.map((c, i) => (
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
    || screen === 'preview-selector' || screen === 'preview-viewer'
  const [showSettings, setShowSettings] = useState(false)
  const [loadoutView, setLoadoutView] = useState<null | 'list' | 'create'>(null)
  // ≤768px the sidebar collapses into an overlay drawer (see the mobile block in index.css);
  // the floating toggle opens it and any navigation closes it. Desktop ignores all of this.
  // Starts OPEN on mobile: the sidebar mounts when a build opens, and the drawer doubling as the
  // build's landing menu beats dropping the user on a screen with no visible navigation.
  const [mobileOpen, setMobileOpen] = useState(
    () => (typeof window !== 'undefined' && window.matchMedia?.('(max-width: 768px)').matches) ?? false,
  )
  const nav = (target: string) => { setMobileOpen(false); onNav(target) }
  useEffect(() => {
    if (!mobileOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMobileOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobileOpen])
  // Live character identity for the OPEN build — also what identifies a freshly imported build
  // (codes carry no name, so the header alone would just read "New Build"). Level subscribes as a
  // primitive so unrelated condition edits don't re-render the whole sidebar.
  const traitId = useBuildStore(s => s.traitId)
  const level = useBuildStore(s => characterLevelFrom(s.conditionState))
  const heroTraits = useReferenceStore(s => s.heroTraits)
  const { identity } = characterSummary({ traitId }, heroTraits)
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
    <>
    <button
      className={`sidebar-mobile-toggle${mobileOpen ? ' is-open' : ''}`}
      aria-label="Open menu"
      aria-expanded={mobileOpen}
      onClick={() => setMobileOpen(o => !o)}
    >☰</button>
    {mobileOpen && <div className="sidebar-mobile-backdrop" onClick={() => setMobileOpen(false)} />}
    <div className={`sidebar-shell${mobileOpen ? ' mobile-open' : ''}`} style={{ width: sidebarWidth }}>
    <div className="build-sidebar">
      <button className="sidebar-nav-btn sidebar-back" onClick={onGoBack}>← Back to Builds</button>
      <div className="sidebar-divider" />
      <div className="sidebar-build-name" title={buildName || 'New Build'}>
        {buildName || 'New Build'}
      </div>
      <div className="sidebar-hero" title={identity ? `Lv ${level} ${identity}` : `Lv ${level} · no hero trait`}>
        Lv {level}{identity ? <> <span className="sidebar-hero-name">{identity}</span></> : <span className="sidebar-hero-none"> · no hero trait</span>}
      </div>
      <div className="sidebar-save-row">
        <button className="sidebar-save-btn" onClick={onSave}>
          Save{isDirty ? ' *' : ''}
        </button>
        <button className="sidebar-save-btn" onClick={onSaveAs}>Save As</button>
      </div>

      <DpsBox onNav={nav} />

      <div className="sidebar-divider" />

      <LoadoutBar onManage={setLoadoutView} />

      <div className="sidebar-divider" />

      <NavBtn label="Config" active={screen === 'build-overview'} onClick={() => nav('build-overview')} />
      <NavBtn label="Calcs" active={screen === 'stats'} onClick={() => nav('stats')} />
      <NavBtn label="Notes" active={screen === 'notes'} onClick={() => nav('notes')} />

      <div className="sidebar-divider" />

      <NavBtn label="Talent Tree" active={isTreeActive} onClick={() => nav('tree-selector')} />
      <NavBtn label="Slates" active={screen === 'slate-board'} onClick={() => nav('slate-board')} />
      <NavBtn label="Gear" active={screen === 'gear'} onClick={() => nav('gear')} />
      <NavBtn label="Skills" active={screen === 'skills'} onClick={() => nav('skills')} />
      <NavBtn label="Hero Trait" active={screen === 'hero-traits'} onClick={() => nav('hero-traits')} />
      <NavBtn label="Pact Spirits" active={screen === 'pact-spirits'} onClick={() => nav('pact-spirits')} />

      <div className="sidebar-divider" />

      <NavBtn label="Import / Export" active={screen === 'import-export'} onClick={() => nav('import-export')} />
      {/* The "NYI flags" toggle moved to Settings → Display (defaults ON). */}
      <NavBtn label="⚙ Settings" active={false} onClick={() => setShowSettings(true)} />

      {/* Intentional trailing filler — keeps the nav packed at the top now that nothing sits at the bottom. */}
      <div className="sidebar-spacer" />
    </div>
      <div className="sidebar-resize-handle" onMouseDown={startResize} title="Drag to resize the sidebar" />
    </div>
    {/* Overlays live OUTSIDE .sidebar-shell: on mobile the shell is fixed+transformed (a stacking
        and containing block), which would trap the modals' z-index and drag them offscreen with
        the drawer. As siblings they layer against the page like every other modal. */}
    {showSettings && <SettingsOverlay onClose={() => setShowSettings(false)} />}
    {loadoutView && <LoadoutOverlay initialView={loadoutView} onClose={() => setLoadoutView(null)} />}
    </>
  )
}
