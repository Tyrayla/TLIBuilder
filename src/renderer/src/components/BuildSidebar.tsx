import React from 'react'
import { useBuildStore } from '../store/buildStore'
import type { OffenseResult } from '../api/client'

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
  if (n >= 1_000_000_000_000_000) return `${(n / 1_000_000_000_000_000).toFixed(2)}Q`
  if (n >= 1_000_000_000_000)     return `${(n / 1_000_000_000_000).toFixed(2)}T`
  if (n >= 1_000_000_000)         return `${(n / 1_000_000_000).toFixed(2)}B`
  if (n >= 1_000_000)             return `${(n / 1_000_000).toFixed(2)}M`
  if (n >= 100_000)               return `${(n / 1_000).toFixed(1)}k`
  return n.toFixed(0)
}

function DpsBox({ onNav }: { onNav: (t: string) => void }) {
  const computedStats = useBuildStore(s => s.computedStats)
  const statsLoading  = useBuildStore(s => s.statsLoading)
  // When multi-skill is supported, sum total_dps_vs_target across all active skill slots here.
  const offense = (computedStats.offense ?? null) as OffenseResult | null
  const hasDps  = offense !== null && offense.supported && offense.total_dps_vs_target > 0

  return (
    <div className="sidebar-dps-box" onClick={() => onNav('calcs')} title="Click to open Calcs">
      <div className="sidebar-dps-label">DPS vs Target</div>
      <div className="sidebar-dps-value">
        {statsLoading ? '…' : hasDps ? fmtDps(offense!.total_dps_vs_target) : '—'}
      </div>
    </div>
  )
}

export default function BuildSidebar({ screen, buildName, isDirty, onNav, onSave, onSaveAs, onGoBack }: Props) {
  const isTreeActive = screen === 'tree-selector' || screen === 'tree-viewer'

  return (
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

      <NavBtn label="Conditionals" active={screen === 'build-overview'} onClick={() => onNav('build-overview')} />
      <NavBtn label="Stats" active={screen === 'stats'} onClick={() => onNav('stats')} />
      {import.meta.env.DEV && (
        <NavBtn label="Debug Stats" active={screen === 'debug-stats'} onClick={() => onNav('debug-stats')} />
      )}
      <NavBtn label="Calcs" active={screen === 'calcs'} onClick={() => onNav('calcs')} />

      <div className="sidebar-divider" />

      <NavBtn label="Talent Tree" active={isTreeActive} onClick={() => onNav('tree-selector')} />
      <NavBtn label="Slates" active={screen === 'slate-board'} onClick={() => onNav('slate-board')} />
      <NavBtn label="Gear" active={screen === 'gear'} onClick={() => onNav('gear')} />
      <NavBtn label="Skills" active={screen === 'skills'} onClick={() => onNav('skills')} />
      <NavBtn label="Hero Trait" active={screen === 'hero-traits'} onClick={() => onNav('hero-traits')} />
      <NavBtn label="Pact Spirits" active={screen === 'pact-spirits'} onClick={() => onNav('pact-spirits')} />

      <div className="sidebar-divider" />

      <NavBtn label="Import / Export" active={screen === 'import-export'} onClick={() => onNav('import-export')} />
      <NavBtn label="Notes" active={screen === 'notes'} onClick={() => onNav('notes')} />

      <div className="sidebar-spacer" />

      <button className="sidebar-nav-btn sidebar-back" onClick={onGoBack}>← Back to Builds</button>
    </div>
  )
}
