import React from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { useFloatingTooltip } from '../tooltip/useFloatingTooltip'
import { useNoteCtx } from './NotesEntityContext'
import { resolveNoteEntity, unknownEntity, type NoteEntityType } from '../../utils/noteEntities'

// Inline colored "chip" for a note hyperlink — resolves the entity (build-first), colors by type/rarity, and shows
// a tooltip (name + kind + key lines) on hover. Rendered by the Lexical MentionNode decorator.
export default function EntityChip({ type, entKey }: { type: NoteEntityType; entKey: string }) {
  const ctx = useNoteCtx()
  const tip = useFloatingTooltip({ anchor: 'element', side: 'top' })
  const ent = (ctx && resolveNoteEntity(type, entKey, ctx)) || unknownEntity(type, entKey)
  return (
    <span className="note-chip" style={{ color: ent.color, borderColor: ent.color }} {...tip.triggerProps}>
      {ent.name}
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip note-chip-tip" {...tip.floatingProps}>
            <div className="note-chip-tip-title" style={{ color: ent.color }}>{ent.name}</div>
            <div className="note-chip-tip-kind">{ent.kindLabel}{ent.source === 'catalog' ? ' · catalog' : ''}</div>
            {ent.lines.map((l, i) => <div key={i} className="note-chip-tip-line">{l}</div>)}
          </div>
        </FloatingPortal>
      )}
    </span>
  )
}
