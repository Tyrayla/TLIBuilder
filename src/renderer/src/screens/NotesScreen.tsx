import React from 'react'

interface Props {
  notes: string
  onNotesChange: (v: string) => void
}

export default function NotesScreen({ notes, onNotesChange }: Props) {
  return (
    <div className="notes-screen">
      <div className="notes-header">
        <h2 className="title-accent" style={{ fontSize: 20 }}>Build Notes</h2>
      </div>
      <textarea
        className="notes-textarea"
        value={notes}
        onChange={e => onNotesChange(e.target.value)}
        placeholder="Add notes about this build..."
        spellCheck={false}
      />
    </div>
  )
}
