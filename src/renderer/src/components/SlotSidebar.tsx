import React, { useState } from 'react'
import { iconUrl, TreeSlot } from '../api/client'
import { MAX_TALENT_POINTS, slotPointTotal, totalAllocatedPoints } from '../utils/talentPoints'

interface Props {
  slots: (TreeSlot | null)[]
  activeSlot: number
  treeColors: Record<string, string>
  treeIcons?: Record<string, string | null>
  onOverview: () => void
  onSlotClick: (slotIndex: number) => void
  onPreview?: () => void
  inPreview?: boolean
  viewerMode?: boolean
  dragDropEnabled?: boolean
  onSlotReorder?: (fromSlot: number, toSlot: number) => void
}

export default function SlotSidebar({
  slots, activeSlot, treeColors, treeIcons = {}, onOverview, onSlotClick,
  onPreview, inPreview = false, viewerMode = false, dragDropEnabled = false, onSlotReorder,
}: Props) {
  const [dragOverSlot, setDragOverSlot] = useState<number | null>(null)
  const totalPoints = totalAllocatedPoints(slots)
  const overBudget = totalPoints > MAX_TALENT_POINTS

  return (
    <div className="slot-sidebar">
      <button className="slot-sidebar-overview" onClick={onOverview}>
        Overview
      </button>
      {onPreview && (
        <button
          className={`slot-sidebar-preview${inPreview ? ' active' : ''}`}
          onClick={onPreview}
        >
          {inPreview ? 'Exit Preview' : 'Preview'}
        </button>
      )}
      {slots.map((slot, i) => {
        const isActive = activeSlot === i
        const isDragOver = dragOverSlot === i
        const color = slot ? (treeColors[slot.treeName] ?? null) : null
        const icon = slot ? iconUrl('talent_tree_selector', treeIcons[slot.treeName]) : null

        let btnStyle: React.CSSProperties = {}
        let nameColor = '#555566'

        if (isDragOver) {
          btnStyle = { borderColor: '#8888ff', background: 'rgba(100,120,255,0.18)' }
          nameColor = '#aaaaff'
        } else if (color) {
          btnStyle = {
            borderColor: isActive && viewerMode ? '#ffffff' : color + 'aa',
            background: color + '18',
            '--slot-accent': color,
          } as React.CSSProperties
          nameColor = color
        } else if (isActive && viewerMode) {
          btnStyle = { borderColor: '#ffffff', background: 'rgba(200,200,216,0.05)' }
          nameColor = '#e8e8f0'
        }

        return (
          <button
            key={i}
            className={`slot-sidebar-btn${isActive ? ' active' : ''}${slot ? ' filled' : ''}${icon ? ' has-icon' : ''}`}
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
            {icon && <img className="slot-sidebar-bg-icon" src={icon} alt="" />}
            <div className="slot-sidebar-btn-body">
              <span className="slot-sidebar-name" style={{ color: nameColor }}>
                {slot?.treeName ?? (inPreview ? 'Preview Mode' : 'Empty')}
              </span>
              {slot && (
                <span className="slot-sidebar-points">{slotPointTotal(slot)} pts</span>
              )}
            </div>
          </button>
        )
      })}
      <div
        className={`slot-sidebar-total${overBudget ? ' over' : ''}`}
        title={overBudget ? `Exceeds the assumed in-game maximum of ${MAX_TALENT_POINTS} talent points (pending verification)` : undefined}
      >
        <div
          className="slot-sidebar-total-fill"
          style={{ width: `${Math.min(100, (totalPoints / MAX_TALENT_POINTS) * 100)}%` }}
        />
        {overBudget && <span className="slot-sidebar-total-warn">⚠</span>}
        <span className="slot-sidebar-total-label">Points</span>
        <span className="slot-sidebar-total-value">{totalPoints} / {MAX_TALENT_POINTS}</span>
      </div>
    </div>
  )
}
