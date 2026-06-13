import React from 'react'
import { useBuildStore } from '../store/buildStore'

interface Props {
  onBack?: () => void
}

export default function NotesScreen(_props: Props) {
  const notes = useBuildStore(s => s.notes)
  const setNotes = useBuildStore(s => s.setNotes)

  return (
    <div className="notes-screen">
      <div className="notes-header">
        <h2 className="title-accent" style={{ fontSize: 20 }}>Build Notes</h2>
      </div>
      <textarea
        className="notes-textarea"
        value={notes}
        onChange={e => setNotes(e.target.value)}
        placeholder="Add notes about this build..."
        spellCheck={false}
      />
    </div>
  )
}
