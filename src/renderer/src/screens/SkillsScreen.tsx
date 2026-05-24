import React, { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  api,
  EquippedGearItem,
  EquippedSkill,
  EquippedSupportSkill,
  SkillItem,
  isActiveSkillItem,
  isPassiveSkillItem,
  isSupportCompatible,
  getSupportEnergyCost,
  getMaxEnergy,
} from '../api/client'

const ACTIVE_SLOTS  = [1, 2, 3, 4, 5]
const PASSIVE_SLOTS = [6, 7, 8, 9]
const SUPPORT_COUNT = 5

const SLOT_LABEL: Record<number, string> = {
  1: 'Main Skill', 2: 'Skill 2', 3: 'Skill 3', 4: 'Skill 4', 5: 'Skill 5',
  6: 'Passive 1',  7: 'Passive 2', 8: 'Passive 3', 9: 'Passive 4',
}

const TAG_CLASS: Record<string, string> = {
  'Fire':             'tag-fire',
  'Cold':             'tag-cold',
  'Lightning':        'tag-lightning',
  'Erosion':          'tag-erosion',
  'Physical':         'tag-physical',
  'Attack':           'tag-attack',
  'Melee':            'tag-melee',
  'Ranged':           'tag-ranged',
  'Projectile':       'tag-ranged',
  'Beam':             'tag-beam',
  'Spell':            'tag-spell',
  'Warcry':           'tag-warcry',
  'Aura':             'tag-passive',
  'Spirit Magus':     'tag-passive',
  'Focus':            'tag-passive',
  'Summon':           'tag-summon',
  'Synthetic Troop':  'tag-summon',
  'Minion':           'tag-summon',
  'Activation Medium':'tag-activation',
  'Support':          'tag-support',
  'Strength':         'tag-strength',
  'Intelligence':     'tag-intel',
  'Dexterity':        'tag-dex',
  'Restoration':      'tag-restoration',
  'Demolisher':       'tag-demolisher',
  'Mobility':         'tag-mobility',
}

function tagClass(tag: string): string {
  const modifier = TAG_CLASS[tag]
  return modifier ? `skill-tag-pill ${modifier}` : 'skill-tag-pill'
}

function getAdvancedLines(lines: string[]): string[] {
  const idx = lines.findIndex((l, i) => i > 0 && l.trim().endsWith(':') && l.trim().length < 50)
  return idx >= 0 ? lines.slice(idx) : lines
}

function isPassiveSlot(slot: number) { return slot > 5 }

interface Props {
  equippedSkills: EquippedSkill[]
  onSkillsChange: (skills: EquippedSkill[]) => void
  gear: EquippedGearItem[]
  characterLevel: number
  hasPrism: boolean
  onCharacterLevelChange: (v: number) => void
  onHasPrismChange: (v: boolean) => void
  onBack: () => void
}

export default function SkillsScreen({
  equippedSkills, onSkillsChange,
  gear, characterLevel, hasPrism, onCharacterLevelChange, onHasPrismChange,
  onBack,
}: Props) {
  const [allItems, setAllItems] = useState<SkillItem[]>([])
  const [focusedSlot, setFocusedSlot] = useState<number | null>(null)
  const [centerView, setCenterView] = useState<'catalog' | 'detail'>('catalog')
  const [focusedSupportIdx, setFocusedSupportIdx] = useState<number | null>(null)
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [selectedSupportId, setSelectedSupportId] = useState<string | null>(null)
  const [pendingLevel, setPendingLevel] = useState(20)
  const [search, setSearch] = useState('')
  const [supportSearch, setSupportSearch] = useState('')
  const [tooltip, setTooltip] = useState<{ name: string; lines: string[]; x: number; y: number } | null>(null)

  const showTooltip = (item: { name: string; description_lines: string[] }, e: React.MouseEvent) =>
    setTooltip({ name: item.name, lines: getAdvancedLines(item.description_lines), x: e.clientX + 14, y: e.clientY - 8 })
  const moveTooltip = (e: React.MouseEvent) =>
    setTooltip(t => t ? { ...t, x: e.clientX + 14, y: e.clientY - 8 } : null)
  const hideTooltip = () => setTooltip(null)

  useEffect(() => {
    api.getSkills().then(r => setAllItems(r.skills))
  }, [])

  const getEquipped = (slot: number) => equippedSkills.find(s => s.slot === slot) ?? null
  const getSupport = (skill: EquippedSkill, idx: number) =>
    (skill.supports ?? []).find(s => s.support_index === idx) ?? null

  const focusedEquipped = focusedSlot !== null ? getEquipped(focusedSlot) : null

  // ── catalog lists ──────────────────────────────────────────────────────────
  const skillCatalogItems = useMemo(() => {
    if (focusedSlot === null) return []
    const base = isPassiveSlot(focusedSlot)
      ? allItems.filter(isPassiveSkillItem)
      : allItems.filter(isActiveSkillItem)
    if (!search.trim()) return base
    const q = search.toLowerCase()
    return base.filter(s =>
      s.name.toLowerCase().includes(q) ||
      s.skill_tags.some(t => t.toLowerCase().includes(q)) ||
      s.description_lines.some(l => l.toLowerCase().includes(q))
    )
  }, [allItems, focusedSlot, search])

  const supportCatalogItems = useMemo(() => {
    if (focusedSlot === null || focusedSupportIdx === null || !focusedEquipped) return []
    const passive = isPassiveSlot(focusedSlot)
    const base = allItems.filter(s => isSupportCompatible(s, focusedEquipped, passive, focusedSupportIdx))
    if (!supportSearch.trim()) return base
    const q = supportSearch.toLowerCase()
    return base.filter(s =>
      s.name.toLowerCase().includes(q) ||
      s.skill_tags.some(t => t.toLowerCase().includes(q)) ||
      s.description_lines.some(l => l.toLowerCase().includes(q))
    )
  }, [allItems, focusedSlot, focusedSupportIdx, focusedEquipped, equippedSkills, supportSearch])

  const selectedSkillItem  = allItems.find(i => i.item_id === selectedSkillId)  ?? null
  const selectedSupportItem = allItems.find(i => i.item_id === selectedSupportId) ?? null

  // ── energy ─────────────────────────────────────────────────────────────────
  const totalEnergyCost = equippedSkills.reduce((total, sk) =>
    total + (sk.supports ?? []).reduce((s, sup) =>
      s + getSupportEnergyCost(isPassiveSlot(sk.slot), sup.support_index), 0), 0)
  const maxEnergy = getMaxEnergy(characterLevel, gear, hasPrism)
  const energyOver = totalEnergyCost > maxEnergy

  // ── slot actions ───────────────────────────────────────────────────────────
  const selectSkillSlot = (slot: number) => {
    setFocusedSlot(slot)
    setFocusedSupportIdx(null)
    setSelectedSupportId(null)
    setSupportSearch('')
    const eq = getEquipped(slot)
    if (eq) {
      setCenterView('detail')
      setSelectedSkillId(eq.item_id)
      setPendingLevel(eq.level)
    } else {
      setCenterView('catalog')
      setSelectedSkillId(null)
      setPendingLevel(20)
    }
    setSearch('')
  }

  const selectSupportSlot = (idx: number) => {
    setFocusedSupportIdx(idx)
    setSelectedSupportId(null)
    setSupportSearch('')
  }

  // ── assign / remove ────────────────────────────────────────────────────────
  const assignSkill = () => {
    if (!selectedSkillItem || focusedSlot === null) return
    const newSkill: EquippedSkill = {
      slot: focusedSlot,
      item_id: selectedSkillItem.item_id,
      name: selectedSkillItem.name,
      level: pendingLevel,
      skill_tags: selectedSkillItem.skill_tags,
      description_lines: selectedSkillItem.description_lines,
      supports: focusedEquipped?.supports ?? [],
    }
    onSkillsChange([...equippedSkills.filter(s => s.slot !== focusedSlot), newSkill])
    setCenterView('detail')
    setSelectedSkillId(selectedSkillItem.item_id)
  }

  const updateLevel = () => {
    if (!focusedEquipped || focusedSlot === null) return
    onSkillsChange(equippedSkills.map(s =>
      s.slot === focusedSlot ? { ...s, level: pendingLevel } : s
    ))
  }

  const removeSkill = (slot: number) => {
    onSkillsChange(equippedSkills.filter(s => s.slot !== slot))
    if (focusedSlot === slot) {
      setCenterView('catalog')
      setSelectedSkillId(null)
      setFocusedSupportIdx(null)
      setSelectedSupportId(null)
    }
  }

  const assignSupport = () => {
    if (!selectedSupportItem || focusedSlot === null || focusedSupportIdx === null) return
    const parent = focusedEquipped
    if (!parent) return
    const newSupport: EquippedSupportSkill = {
      support_index: focusedSupportIdx,
      item_id: selectedSupportItem.item_id,
      name: selectedSupportItem.name,
      skill_tags: selectedSupportItem.skill_tags,
      description_lines: selectedSupportItem.description_lines,
    }
    const updated: EquippedSkill = {
      ...parent,
      supports: [
        ...(parent.supports ?? []).filter(s => s.support_index !== focusedSupportIdx),
        newSupport,
      ],
    }
    onSkillsChange(equippedSkills.map(s => s.slot === focusedSlot ? updated : s))
    setFocusedSupportIdx(null)
    setSelectedSupportId(null)
    setSupportSearch('')
  }

  const removeSupport = (supportIdx: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (focusedSlot === null || !focusedEquipped) return
    const updated: EquippedSkill = {
      ...focusedEquipped,
      supports: (focusedEquipped.supports ?? []).filter(s => s.support_index !== supportIdx),
    }
    onSkillsChange(equippedSkills.map(s => s.slot === focusedSlot ? updated : s))
    if (focusedSupportIdx === supportIdx) {
      setFocusedSupportIdx(null)
      setSelectedSupportId(null)
    }
  }

  // ── helpers ────────────────────────────────────────────────────────────────
  const isSubHeader = (line: string) => line.trim().endsWith(':') && line.length < 40

  // ── render helpers ─────────────────────────────────────────────────────────
  const renderSlotGroup = (slots: number[], label: string) => (
    <div className="skill-slot-group">
      <div className="skill-slots-section-label">{label}</div>
      {slots.map(slot => {
        const eq = getEquipped(slot)
        const isActive = focusedSlot === slot
        return (
          <div
            key={slot}
            className={`skill-slot-row${eq ? ' occupied' : ''}${isActive ? ' active' : ''}`}
            onClick={() => selectSkillSlot(slot)}
          >
            <div className="skill-slot-info">
              <span className="skill-slot-label">{SLOT_LABEL[slot]}</span>
              {eq
                ? <span className="skill-slot-skill-name">{eq.name}</span>
                : <span className="skill-slot-empty">Empty</span>}
            </div>
            {eq && (
              <div className="skill-slot-right">
                <span className="skill-slot-level-badge">Lv.{eq.level}</span>
                <button
                  className="skill-slot-remove"
                  onClick={e => { e.stopPropagation(); removeSkill(slot) }}
                >×</button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )

  const renderCenterPanel = () => {
    if (focusedSlot === null) {
      return (
        <div className="skill-center-empty">
          Select a skill slot to begin
        </div>
      )
    }

    if (centerView === 'catalog') {
      const isPassive = isPassiveSlot(focusedSlot)
      return (
        <>
          <div className="skill-center-catalog-header">
            <span className="skill-center-catalog-title">
              Choose {isPassive ? 'Passive' : 'Active'} Skill — {SLOT_LABEL[focusedSlot]}
            </span>
            {focusedEquipped && (
              <button className="btn btn-secondary btn-sm" onClick={() => setCenterView('detail')}>
                Cancel
              </button>
            )}
          </div>
          <div className="skill-search-bar">
            <input
              className="skill-search-input"
              placeholder="Search by name, tag, or effect…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && <button className="skill-search-clear" onClick={() => setSearch('')}>×</button>}
          </div>
          <div className="skill-catalog-list">
            {skillCatalogItems.length === 0 && (
              <div className="skill-catalog-empty">No skills match your search</div>
            )}
            {skillCatalogItems.map(item => (
              <div
                key={item.item_id}
                className={`skill-catalog-item${selectedSkillId === item.item_id ? ' selected' : ''}`}
                onClick={() => {
                  setSelectedSkillId(item.item_id)
                  if (focusedEquipped?.item_id !== item.item_id) setPendingLevel(20)
                  else setPendingLevel(focusedEquipped.level)
                }}
                onMouseMove={e => showTooltip(item, e)}
                onMouseLeave={hideTooltip}
              >
                <span className="skill-catalog-name">{item.name}</span>
                <div className="skill-catalog-tags">
                  {item.skill_tags.map(t => <span key={t} className={tagClass(t)}>{t}</span>)}
                </div>
              </div>
            ))}
          </div>
          {selectedSkillItem && (
            <div className="skill-center-catalog-footer">
              <div className="skill-level-row">
                <span className="skill-level-label">Level</span>
                <div className="skill-level-controls">
                  <button className="skill-level-btn" onClick={() => setPendingLevel(l => Math.max(1, l - 1))}>−</button>
                  <input
                    type="number" className="skill-level-input" min={1} max={40} value={pendingLevel}
                    onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v)) setPendingLevel(Math.max(1, Math.min(40, v))) }}
                  />
                  <button className="skill-level-btn" onClick={() => setPendingLevel(l => Math.min(40, l + 1))}>+</button>
                </div>
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} onClick={assignSkill}>
                Assign {selectedSkillItem.name} to {SLOT_LABEL[focusedSlot]}
              </button>
            </div>
          )}
        </>
      )
    }

    // detail view
    if (!focusedEquipped) {
      setCenterView('catalog')
      return null
    }

    const isPassive = isPassiveSlot(focusedSlot)
    return (
      <>
        <div className="skill-detail-header">
          <div
            onMouseMove={e => showTooltip(focusedEquipped, e)}
            onMouseLeave={hideTooltip}
            style={{ cursor: 'default' }}
          >
            <div className="skill-detail-name">{focusedEquipped.name}</div>
            <div className="skill-detail-tags">
              {focusedEquipped.skill_tags.map(t => <span key={t} className={tagClass(t)}>{t}</span>)}
            </div>
          </div>
          <div className="skill-level-row" style={{ marginTop: 0, alignItems: 'center' }}>
            <div className="skill-level-controls">
              <button className="skill-level-btn" onClick={() => setPendingLevel(l => Math.max(1, l - 1))}>−</button>
              <input
                type="number" className="skill-level-input" min={1} max={40} value={pendingLevel}
                onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v)) setPendingLevel(Math.max(1, Math.min(40, v))) }}
              />
              <button className="skill-level-btn" onClick={() => setPendingLevel(l => Math.min(40, l + 1))}>+</button>
            </div>
            <button className="btn btn-secondary btn-sm" style={{ marginLeft: 6 }} onClick={updateLevel}>
              Set
            </button>
          </div>
        </div>
        <div className="skill-panel-divider" />

        <div className="skill-support-slots-section">
          <div className="skill-support-slots-label">Support Skills</div>
          {Array.from({ length: SUPPORT_COUNT }, (_, i) => i + 1).map(idx => {
            const sup = getSupport(focusedEquipped, idx)
            const cost = getSupportEnergyCost(isPassive, idx)
            const isActiveSup = focusedSupportIdx === idx
            const supItem = sup ? allItems.find(i => i.item_id === sup.item_id) : null
            return (
              <div
                key={idx}
                className={`skill-support-slot-row${isActiveSup ? ' active' : ''}${sup ? ' occupied' : ''}`}
                onClick={() => selectSupportSlot(idx)}
                onMouseMove={supItem ? e => showTooltip(supItem, e) : undefined}
                onMouseLeave={supItem ? hideTooltip : undefined}
              >
                <span className={`skill-support-cost-badge${sup ? '' : ' dim'}`}>{cost}</span>
                <span className="skill-support-slot-num">{idx}</span>
                {sup ? (
                  <>
                    <span className="skill-support-slot-name">{sup.name}</span>
                    <button className="skill-slot-remove" onClick={e => removeSupport(idx, e)}>×</button>
                  </>
                ) : (
                  <span className="skill-support-slot-empty">Empty — click to add</span>
                )}
              </div>
            )
          })}
        </div>

        <div className="skill-panel-divider" />
        <div className="skill-detail-actions">
          <button className="btn btn-secondary" onClick={() => { setCenterView('catalog'); setSearch('') }}>
            Change Skill
          </button>
          <button className="btn btn-danger" onClick={() => removeSkill(focusedSlot)}>
            Remove Skill
          </button>
        </div>
      </>
    )
  }

  const renderSupportPanel = () => {
    if (focusedSupportIdx === null || !focusedEquipped || focusedSlot === null) {
      return (
        <div className="skill-detail-empty">
          {focusedEquipped ? 'Select a support slot to manage it' : 'Select a skill first'}
        </div>
      )
    }

    const isPassive = isPassiveSlot(focusedSlot)
    const existingSupport = getSupport(focusedEquipped, focusedSupportIdx)
    const cost = getSupportEnergyCost(isPassive, focusedSupportIdx)

    return (
      <>
        <div className="skill-support-panel-header">
          <div className="skill-support-panel-title">
            Support Slot {focusedSupportIdx}
            <span className={`skill-support-cost-badge${existingSupport ? '' : ' dim'}`} style={{ marginLeft: 6 }}>{cost} Energy</span>
          </div>
          <div className="skill-support-panel-parent">{SLOT_LABEL[focusedSlot]}: {focusedEquipped.name}</div>
          {existingSupport && (
            <div className="skill-support-current">
              <span className="skill-support-current-label">Equipped:</span>
              <span className="skill-support-current-name">{existingSupport.name}</span>
              <button className="skill-slot-remove" onClick={e => removeSupport(focusedSupportIdx, e)}>×</button>
            </div>
          )}
        </div>
        <div className="skill-panel-divider" />
        <div className="skill-search-bar">
          <input
            className="skill-search-input"
            placeholder="Search compatible supports…"
            value={supportSearch}
            onChange={e => setSupportSearch(e.target.value)}
          />
          {supportSearch && <button className="skill-search-clear" onClick={() => setSupportSearch('')}>×</button>}
        </div>
        <div className="skill-catalog-list" style={{ flex: 1 }}>
          {supportCatalogItems.length === 0 && (
            <div className="skill-catalog-empty">No compatible supports for this slot</div>
          )}
          {supportCatalogItems.map(item => (
            <div
              key={item.item_id}
              className={`skill-catalog-item${selectedSupportId === item.item_id ? ' selected' : ''}`}
              onClick={() => setSelectedSupportId(item.item_id)}
              onMouseMove={e => showTooltip(item, e)}
              onMouseLeave={hideTooltip}
            >
              <span className="skill-catalog-name">{item.name}</span>
              <div className="skill-catalog-tags">
                {item.skill_tags.map(t => <span key={t} className={tagClass(t)}>{t}</span>)}
              </div>
            </div>
          ))}
        </div>
        {selectedSupportItem && (
          <>
            <div className="skill-panel-divider" />
            <div className="skill-detail-desc" style={{ maxHeight: 120, overflowY: 'auto' }}>
              {selectedSupportItem.description_lines.map((line, i) => (
                <p key={i} className={isSubHeader(line) ? 'skill-desc-subheader' : 'skill-desc-line'}>{line}</p>
              ))}
            </div>
            <button
              className="btn btn-primary"
              style={{ width: '100%', marginTop: 8 }}
              onClick={assignSupport}
              disabled={existingSupport?.item_id === selectedSupportId}
            >
              {existingSupport?.item_id === selectedSupportId
                ? 'Already equipped'
                : `Equip in Slot ${focusedSupportIdx}`}
            </button>
          </>
        )}
        <button
          className="btn btn-secondary"
          style={{ width: '100%', marginTop: 6 }}
          onClick={() => { setFocusedSupportIdx(null); setSelectedSupportId(null); setSupportSearch('') }}
        >
          Close
        </button>
      </>
    )
  }

  return (
    <>
    <div className="skills-screen">
      <div className="skills-header">
        <span className="skills-header-title">Skills</span>
      </div>

      <div className="skills-body">
        {/* Left: skill slots + energy footer */}
        <div className="skill-slots-panel">
          <div className="skill-slots-scroll">
            {renderSlotGroup(ACTIVE_SLOTS, 'Active Skills')}
            {renderSlotGroup(PASSIVE_SLOTS, 'Passive Skills')}
          </div>
          <div className="skills-left-footer">
            <div className="skills-energy-config">
              <label className="skills-energy-config-label">Lvl</label>
              <input
                type="number" className="skills-energy-level-input"
                min={1} max={100} value={characterLevel}
                onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v)) onCharacterLevelChange(Math.max(1, Math.min(100, v))) }}
              />
              <label className="skills-energy-config-label" style={{ marginLeft: 8 }}>
                <input type="checkbox" checked={hasPrism} onChange={e => onHasPrismChange(e.target.checked)} style={{ marginRight: 4 }} />
                Prism
              </label>
            </div>
            <span className={`skills-energy-total${energyOver ? ' over' : ''}`}>
              {totalEnergyCost} / {maxEnergy} Energy
            </span>
          </div>
        </div>

        {/* Center: skill catalog or skill detail */}
        <div className="skill-center-panel">
          {renderCenterPanel()}
        </div>

        {/* Right: support catalog */}
        <div className="skill-support-panel">
          {renderSupportPanel()}
        </div>
      </div>
    </div>
    {tooltip && createPortal(
      <div className="skill-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
        <div className="skill-tooltip-name">{tooltip.name}</div>
        <div className="skill-tooltip-desc">
          {tooltip.lines.map((l, i) => <p key={i}>{l}</p>)}
        </div>
      </div>,
      document.body
    )}
    </>
  )
}
