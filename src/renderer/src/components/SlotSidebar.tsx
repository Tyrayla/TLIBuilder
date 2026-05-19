import React from 'react'
import { TreeSlot } from '../api/client'

interface Props {
  slots: (TreeSlot | null)[]
  activeSlot: number
  onOverview: () => void
  onSlotClick: (slotIndex: number) => void
}

export default function SlotSidebar({ slots, activeSlot, onOverview, onSlotClick }: Props) {
  return (
    <div className="slot-sidebar">
      <button className="slot-sidebar-overview" onClick={onOverview}>
        Overview
      </button>
      {slots.map((slot, i) => (
        <button
          key={i}
          className={`slot-sidebar-btn${activeSlot === i ? ' active' : ''}${slot ? ' filled' : ''}`}
          onClick={() => onSlotClick(i)}
        >
          <span className="slot-sidebar-num">Slot {i + 1}</span>
          <span className="slot-sidebar-name">{slot?.treeName ?? 'Empty'}</span>
        </button>
      ))}
    </div>
  )
}
