import React, { useState } from 'react'
import { TreeSlot } from '../api/client'

interface Props {
  slots: (TreeSlot | null)[]
  activeSlot: number
  treeColors: Record<string, string>
  onOverview: () => void
  onSlotClick: (slotIndex: number) => void
  onPreview?: () => void
  viewerMode?: boolean
  dragDropEnabled?: boolean
  onSlotReorder?: (fromSlot: number, toSlot: number) => void
}

export default function SlotSidebar({
  slots, activeSlot, treeColors, onOverview, onSlotClick,
  onPreview, viewerMode = false, dragDropEnabled = false, onSlotReorder,
}: Props) {
  const [dragOverSlot, setDragOverSlot] = useState<number | null>(null)

  return (
    <div className="slot-sidebar">
      <button className="slot-sidebar-overview" onClick={onOverview}>
        Overview
      </button>
      {onPreview && (
        <button className="slot-sidebar-preview" onClick={onPreview}>
          Preview
        </button>
      )}
      {slots.map((slot, i) => {
        const isActive = activeSlot === i
        const isDragOver = dragOverSlot === i
        const color = slot ? (treeColors[slot.treeName] ?? null) : null

        let btnStyle: React.CSSProperties = {}
        let nameColor = '#555566'

        if (isDragOver) {
          btnStyle = { borderColor: '#8888ff', background: 'rgba(100,120,255,0.18)' }
          nameColor = '#aaaaff'
        } else if (color) {
          btnStyle = {
            borderColor: isActive && viewerMode ? '#ffffff' : color + 'aa',
            background: color + '18',
          }
          nameColor = color
        } else if (isActive && viewerMode) {
          btnStyle = { borderColor: '#ffffff', background: 'rgba(200,200,216,0.05)' }
          nameColor = '#e8e8f0'
        }

        return (
          <button
            key={i}
            className={`slot-sidebar-btn${isActive ? ' active' : ''}${slot ? ' filled' : ''}`}
            style={{ ...btnStyle, cursor: dragDropEnabled && slot ? 'grab' : 'default' }}
            onClick={() => onSlotClick(i)}
            draggable={dragDropEnabled && !!slot}
            onDragStart={dragDropEnabled && slot ? e => {
              e.dataTransfer.setData('text/plain', String(i))
              e.dataTransfer.effectAllowed = 'move'
              const el = e.currentTarget
              setTimeout(() => el.classList.add('dragging'), 0)
            } : undefined}
            onDragEnd={dragDropEnabled ? e => e.currentTarget.classList.remove('dragging') : undefined}
            onDragEnter={dragDropEnabled ? e => {
              e.preventDefault()
              setDragOverSlot(i)
            } : undefined}
            onDragOver={dragDropEnabled ? e => {
              e.preventDefault()
              e.dataTransfer.dropEffect = 'move'
            } : undefined}
            onDragLeave={dragDropEnabled ? e => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                setDragOverSlot(null)
              }
            } : undefined}
            onDrop={dragDropEnabled ? e => {
              e.preventDefault()
              setDragOverSlot(null)
              const raw = e.dataTransfer.getData('text/plain')
              const fromSlot = parseInt(raw)
              if (!isNaN(fromSlot) && fromSlot !== i && onSlotReorder) {
                onSlotReorder(fromSlot, i)
              }
            } : undefined}
          >
            <span className="slot-sidebar-name" style={{ color: nameColor }}>
              {slot?.treeName ?? 'Empty'}
            </span>
          </button>
        )
      })}
    </div>
  )
}
