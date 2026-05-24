import React, { useEffect, useState } from 'react'
import { api, TreeSlot } from '../api/client'
import { GROUPS, canAddTree, findShiftCandidate } from '../treeGroups'
import SlotSidebar from '../components/SlotSidebar'

interface Props {
  slots: (TreeSlot | null)[]
  activeSlot: number
  treeColors: Record<string, string>
  onSelectTree: (treeName: string) => void
  onRemoveTree: (slotIndex: number) => void
  onSlotClick: (slotIndex: number) => void
  onSlotReorder: (fromSlot: number, toSlot: number) => void
  onGoToTree?: (slotIndex: number) => void
  onBack: () => void
  onGoToSelector: () => void
  onShiftUp: (fromSlot: number) => void
  onPreview: () => void
  previewMode?: boolean
}

const ORDINALS = ['', '1st', '2nd', '3rd', '4th']

function slotOf(treeName: string, slots: (TreeSlot | null)[]): number {
  return slots.findIndex(s => s?.treeName === treeName)
}

function contextLabel(slots: (TreeSlot | null)[]): string {
  if (!slots[0]) return 'Choose your Primary — one of the 6 Gods or Goddesses'
  if (!slots[1]) return `Choose a Subtree for ${slots[0].treeName}`
  const filled = slots.filter(Boolean).length
  if (filled === 4) return 'All slots filled — Remove a tree to replace it'
  return `Select your ${ORDINALS[filled + 1]} tree`
}

export default function TreeSelectorScreen({
  slots, activeSlot, treeColors, onSelectTree, onRemoveTree, onSlotClick,
  onSlotReorder, onGoToTree, onBack, onGoToSelector, onShiftUp, onPreview, previewMode = false,
}: Props) {
  const [localColors, setLocalColors] = useState<Record<string, string>>(treeColors)

  useEffect(() => {
    if (Object.keys(treeColors).length === 0) {
      api.getTrees().then(trees => {
        const colors: Record<string, string> = {}
        trees.forEach(t => { colors[t.name] = t.color })
        setLocalColors(colors)
      })
    } else {
      setLocalColors(treeColors)
    }
  }, [treeColors])

  const shiftCandidate = findShiftCandidate(slots)

  const normalHeader = (
    <div className="screen-header">
      <button className="btn-back" onClick={onBack}>← Build Overview</button>
      <h2 style={{ fontSize: 16, color: '#aaa', fontWeight: 500 }}>
        {contextLabel(slots)}
      </h2>
    </div>
  )

  const previewHeader = (
    <div className="screen-header preview-mode-header">
      <button className="btn-back" onClick={onBack} style={{ alignSelf: 'flex-start', marginTop: 2 }}>
        ← Build Overview
      </button>
      <div className="preview-header-content">
        <div className="preview-header-badge">◈ PREVIEW MODE</div>
        <div className="preview-header-title">Browse Trees</div>
        <div className="preview-header-sub">
          Click any tree to explore its nodes — nothing is saved to your build
        </div>
      </div>
      <div style={{ width: 60, flexShrink: 0 }} />
    </div>
  )

  return (
    <div className="screen tree-selector">
      {previewMode ? previewHeader : normalHeader}
      <div className="selector-body">
        {!previewMode && (
          <SlotSidebar
            slots={slots}
            activeSlot={activeSlot}
            treeColors={localColors}
            onOverview={onGoToSelector}
            onSlotClick={onSlotClick}
            onPreview={onPreview}
            dragDropEnabled
            onSlotReorder={onSlotReorder}
          />
        )}
        <div className="tree-grid">
          {GROUPS.map(({ primary, trees }) => (
            <div key={primary} className="tree-group-col">
              <TreeCard
                name={primary}
                color={localColors[primary] || '#e94560'}
                isPrimary
                selectedSlot={previewMode ? -1 : slotOf(primary, slots)}
                selectable={previewMode ? true : canAddTree(primary, slots)}
                onSelect={() => onSelectTree(primary)}
                onRemove={() => onRemoveTree(slotOf(primary, slots))}
                onGoToTree={onGoToTree ? () => onGoToTree(slotOf(primary, slots)) : undefined}
                previewMode={previewMode}
              />
              <div className="tree-subtrees">
                {trees.map(name => {
                  const isShiftTarget = !previewMode && shiftCandidate?.treeName === name
                  return (
                    <TreeCard
                      key={name}
                      name={name}
                      color={localColors[name] || '#0f3460'}
                      selectedSlot={previewMode ? -1 : slotOf(name, slots)}
                      selectable={previewMode ? true : canAddTree(name, slots)}
                      onSelect={() => onSelectTree(name)}
                      onRemove={() => onRemoveTree(slotOf(name, slots))}
                      onGoToTree={onGoToTree ? () => onGoToTree(slotOf(name, slots)) : undefined}
                      shiftCandidate={isShiftTarget ? shiftCandidate : null}
                      onShiftUp={onShiftUp}
                      previewMode={previewMode}
                    />
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function TreeCard({
  name, color, isPrimary: isPrim, selectedSlot, selectable,
  onSelect, onRemove, onGoToTree, shiftCandidate, onShiftUp, previewMode = false,
}: {
  name: string
  color: string
  isPrimary?: boolean
  selectedSlot: number
  selectable: boolean
  onSelect: () => void
  onRemove: () => void
  onGoToTree?: () => void
  shiftCandidate?: { treeName: string; fromSlot: number } | null
  onShiftUp?: (fromSlot: number) => void
  previewMode?: boolean
}) {
  const isSelected = !previewMode && selectedSlot !== -1
  const isLocked = !isSelected && !selectable
  const isSelectable = selectable && !isSelected
  const isClickable = isSelectable || (isSelected && !!onGoToTree)

  const borderColor = isSelected ? '#3a5a8a' : '#1e2535'

  function handleClick() {
    if (isSelectable) onSelect()
    else if (isSelected && onGoToTree) onGoToTree()
  }

  return (
    <div
      className={`tree-card${isPrim ? ' tree-card-primary' : ''}${isSelected ? ' tree-card-selected' : ''}${isLocked ? ' tree-card-locked' : ''}${isSelectable ? ' tree-card-selectable' : ''}`}
      style={{ borderColor, cursor: isClickable ? 'pointer' : 'default' }}
      onClick={isClickable ? handleClick : undefined}
    >
      <div className="tree-card-accent" style={{ background: color }} />
      <div className="tree-card-name" style={{ color: isLocked ? '#444455' : '#ffffff' }}>
        {name}
      </div>
      {isSelected && (
        <div
          className="tree-card-btn tree-card-btn-remove"
          onClick={e => { e.stopPropagation(); onRemove() }}
        >
          Remove
        </div>
      )}
      {shiftCandidate && onShiftUp && (
        <div
          className="tree-card-shift"
          onClick={e => { e.stopPropagation(); onShiftUp(shiftCandidate.fromSlot) }}
        >
          ↑ Move to Slot 2
        </div>
      )}
    </div>
  )
}
