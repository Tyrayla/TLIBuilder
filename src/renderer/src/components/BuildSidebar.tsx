import React from 'react'

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

      <div className="sidebar-divider" />

      <NavBtn label="Conditionals" active={screen === 'build-overview'} onClick={() => onNav('build-overview')} />
      <NavBtn label="Stats" active={screen === 'stats'} onClick={() => onNav('stats')} />

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
