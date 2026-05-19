import React, { useEffect, useState } from 'react'
import { api, TreeSlot } from '../api/client'
import { GROUPS, isPrimary, getSubtrees } from '../treeGroups'
import SlotSidebar from '../components/SlotSidebar'

interface Props {
  slots: (TreeSlot | null)[]
  targetSlot: number
  treeColors: Record<string, string>
  onSelectTree: (treeName: string) => void
  onRemoveTree: (slotIndex: number) => void
  onSlotClick: (slotIndex: number) => void
  onBack: () => void
}

function isSelectable(treeName: string, targetSlot: number, slots: (TreeSlot | null)[]): boolean {
  if (targetSlot === 0) return isPrimary(treeName)
  if (targetSlot === 1) {
    const primary = slots[0]?.treeName
    if (!primary) return false
    return getSubtrees(primary).includes(treeName)
  }
  return true
}

function slotOf(treeName: string, slots: (TreeSlot | null)[]): number {
  return slots.findIndex(s => s?.treeName === treeName)
}

export default function TreeSelectorScreen({
  slots, targetSlot, treeColors, onSelectTree, onRemoveTree, onSlotClick, onBack,
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

  const slotLabel = targetSlot === 0
    ? 'Select a Primary (God / Goddess)'
    : targetSlot === 1
      ? `Select a Subtree for ${slots[0]?.treeName ?? '—'}`
      : `Select any Tree for Slot ${targetSlot + 1}`

  return (
    <div className="screen tree-selector">
      <div className="screen-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
        <h2 className="title-accent" style={{ fontSize: 18 }}>{slotLabel}</h2>
      </div>
      <div className="selector-body">
        <SlotSidebar
          slots={slots}
          activeSlot={targetSlot}
          onOverview={onBack}
          onSlotClick={onSlotClick}
        />
        <div className="tree-grid">
          {GROUPS.map(({ primary, trees }) => (
            <div key={primary} className="tree-group-col">
              <TreeCard
                name={primary}
                color={localColors[primary] || '#e94560'}
                isPrimary
                selected={slotOf(primary, slots) !== -1}
                selectable={isSelectable(primary, targetSlot, slots)}
                selectedSlot={slotOf(primary, slots)}
                onSelect={() => onSelectTree(primary)}
                onRemove={() => onRemoveTree(slotOf(primary, slots))}
              />
              {trees.map(name => (
                <TreeCard
                  key={name}
                  name={name}
                  color={localColors[name] || '#0f3460'}
                  selected={slotOf(name, slots) !== -1}
                  selectable={isSelectable(name, targetSlot, slots)}
                  selectedSlot={slotOf(name, slots)}
                  onSelect={() => onSelectTree(name)}
                  onRemove={() => onRemoveTree(slotOf(name, slots))}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function TreeCard({ name, color, isPrimary, selected, selectable, selectedSlot, onSelect, onRemove }: {
  name: string
  color: string
  isPrimary?: boolean
  selected: boolean
  selectable: boolean
  selectedSlot: number
  onSelect: () => void
  onRemove: () => void
}) {
  return (
    <div
      className={`tree-card${isPrimary ? ' tree-card-primary' : ''}${selected ? ' tree-card-selected' : ''}${!selectable && !selected ? ' tree-card-locked' : ''}`}
      style={{ borderColor: selected ? color : selectable ? color : '#2a2a3a' }}
    >
      <div className="tree-card-accent" style={{ background: selected ? color : selectable ? color : '#2a2a3a' }} />
      <div className="tree-card-name" style={{ color: selectable || selected ? '#ffffff' : '#555566' }}>
        {name}
      </div>
      {selected ? (
        <div
          className="tree-card-btn"
          style={{ background: '#3a1a1a', color: '#ff6b6b', cursor: 'pointer' }}
          onClick={onRemove}
        >
          Remove (S{selectedSlot + 1})
        </div>
      ) : selectable ? (
        <div
          className="tree-card-btn"
          style={{ background: color, cursor: 'pointer' }}
          onClick={onSelect}
        >
          Select
        </div>
      ) : (
        <div className="tree-card-btn" style={{ background: '#1a1a2a', color: '#444455' }}>
          —
        </div>
      )}
    </div>
  )
}
