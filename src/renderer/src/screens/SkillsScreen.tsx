import React, { useEffect, useState } from 'react'
import { api, EquippedSkill, SkillItem } from '../api/client'

const SLOT_LABELS = ['Main Skill', 'Skill 2', 'Skill 3', 'Skill 4', 'Skill 5']

interface Props {
  equippedSkills: EquippedSkill[]
  onSkillsChange: (skills: EquippedSkill[]) => void
  onBack: () => void
}

export default function SkillsScreen({ equippedSkills, onSkillsChange, onBack }: Props) {
  const [items, setItems] = useState<SkillItem[]>([])
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeSlot, setActiveSlot] = useState(0)
  const [pendingLevel, setPendingLevel] = useState(20)

  useEffect(() => {
    api.getSkills().then(r => {
      // Active skills only — support skills contain ":" in name
      setItems(r.skills.filter(s => !s.name.includes(':')))
    })
  }, [])

  const equippedInActiveSlot = equippedSkills.find(s => s.slot === activeSlot + 1) ?? null

  const handleSlotClick = (slotIndex: number) => {
    setActiveSlot(slotIndex)
    const equipped = equippedSkills.find(s => s.slot === slotIndex + 1)
    if (equipped) {
      setSelectedId(equipped.item_id)
      setPendingLevel(equipped.level)
    } else {
      setSelectedId(null)
      setPendingLevel(20)
    }
  }

  const handleCatalogClick = (item: SkillItem) => {
    setSelectedId(item.item_id)
    // If this exact skill is already in the active slot, restore its saved level
    if (equippedInActiveSlot?.item_id === item.item_id) {
      setPendingLevel(equippedInActiveSlot.level)
    }
  }

  const handleAssign = () => {
    if (!selectedItem) return
    const newSkill: EquippedSkill = {
      slot: activeSlot + 1,
      item_id: selectedItem.item_id,
      name: selectedItem.name,
      level: pendingLevel,
      skill_tags: selectedItem.skill_tags,
      description_lines: selectedItem.description_lines,
    }
    const updated = equippedSkills.filter(s => s.slot !== activeSlot + 1)
    onSkillsChange([...updated, newSkill])
  }

  const handleRemove = (e: React.MouseEvent, slotNum: number) => {
    e.stopPropagation()
    onSkillsChange(equippedSkills.filter(s => s.slot !== slotNum))
    if (activeSlot + 1 === slotNum) {
      setSelectedId(null)
      setPendingLevel(20)
    }
  }

  const filtered = search.trim()
    ? items.filter(s =>
        s.name.toLowerCase().includes(search.toLowerCase()) ||
        s.skill_tags.some(t => t.toLowerCase().includes(search.toLowerCase())) ||
        s.description_lines.some(l => l.toLowerCase().includes(search.toLowerCase()))
      )
    : items

  const selectedItem = items.find(i => i.item_id === selectedId) ?? null
  const isAssigned = equippedInActiveSlot?.item_id === selectedId

  const isSubHeader = (line: string) => line.trim().endsWith(':') && line.length < 40

  return (
    <div className="skills-screen">
      <div className="skills-header">
        <button className="back-btn" onClick={onBack}>← Overview</button>
        <span className="skills-header-title">Skills</span>
        <span className="skills-header-count">{items.length} active skills</span>
      </div>

      <div className="skills-body">

        {/* Left: skill slots */}
        <div className="skill-slots-panel">
          <div className="skill-slots-title">Skill Slots</div>
          {SLOT_LABELS.map((label, i) => {
            const equipped = equippedSkills.find(s => s.slot === i + 1)
            const isActive = activeSlot === i
            return (
              <div
                key={i}
                className={`skill-slot-row${isActive ? ' active' : ''}${equipped ? ' occupied' : ''}`}
                onClick={() => handleSlotClick(i)}
              >
                <div className="skill-slot-info">
                  <span className="skill-slot-label">{label}</span>
                  {equipped
                    ? <span className="skill-slot-skill-name">{equipped.name}</span>
                    : <span className="skill-slot-empty">Empty</span>
                  }
                </div>
                {equipped && (
                  <div className="skill-slot-right">
                    <span className="skill-slot-level-badge">Lv. {equipped.level}</span>
                    <button
                      className="skill-slot-remove"
                      onClick={e => handleRemove(e, i + 1)}
                    >×</button>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Center: catalog */}
        <div className="skill-catalog">
          <div className="skill-search-bar">
            <input
              className="skill-search-input"
              placeholder="Search by name, tag, or effect…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button className="skill-search-clear" onClick={() => setSearch('')}>×</button>
            )}
          </div>
          <div className="skill-catalog-list">
            {filtered.length === 0 && (
              <div className="skill-catalog-empty">No skills match your search</div>
            )}
            {filtered.map(item => (
              <div
                key={item.item_id}
                className={`skill-catalog-item${selectedId === item.item_id ? ' selected' : ''}`}
                onClick={() => handleCatalogClick(item)}
              >
                <span className="skill-catalog-name">{item.name}</span>
                <div className="skill-catalog-tags">
                  {item.skill_tags.map(t => (
                    <span key={t} className="skill-tag-pill">{t}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: detail */}
        <div className="skill-detail-panel">
          {selectedItem ? (
            <>
              <div className="skill-detail-header">
                <div className="skill-detail-name">{selectedItem.name}</div>
                <div className="skill-detail-tags">
                  {selectedItem.skill_tags.map(t => (
                    <span key={t} className="skill-tag-pill">{t}</span>
                  ))}
                </div>
              </div>

              <div className="skill-panel-divider" />

              <div className="skill-detail-desc">
                {selectedItem.description_lines.map((line, i) => (
                  <p key={i} className={isSubHeader(line) ? 'skill-desc-subheader' : 'skill-desc-line'}>
                    {line}
                  </p>
                ))}
              </div>

              <div className="skill-panel-divider" />

              <div className="skill-level-row">
                <span className="skill-level-label">Skill Level</span>
                <div className="skill-level-controls">
                  <button
                    className="skill-level-btn"
                    onClick={() => setPendingLevel(l => Math.max(1, l - 1))}
                  >−</button>
                  <input
                    type="number"
                    className="skill-level-input"
                    min={1}
                    max={40}
                    value={pendingLevel}
                    onChange={e => {
                      const v = parseInt(e.target.value)
                      if (!isNaN(v)) setPendingLevel(Math.max(1, Math.min(40, v)))
                    }}
                  />
                  <button
                    className="skill-level-btn"
                    onClick={() => setPendingLevel(l => Math.min(40, l + 1))}
                  >+</button>
                </div>
              </div>

              <div className="skill-detail-actions">
                <button className="btn btn-primary" onClick={handleAssign}>
                  {isAssigned ? 'Update Level' : `Assign to ${SLOT_LABELS[activeSlot]}`}
                </button>
              </div>
            </>
          ) : (
            <div className="skill-detail-empty">Select a skill to view details</div>
          )}
        </div>

      </div>
    </div>
  )
}
