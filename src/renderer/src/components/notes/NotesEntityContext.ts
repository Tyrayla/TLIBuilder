import { createContext, useContext } from 'react'
import type { NoteResolveCtx } from '../../utils/noteEntities'

// Provides the build-first resolution context to inline EntityChips rendered inside the Lexical editor.
export const NotesEntityContext = createContext<NoteResolveCtx | null>(null)
export const useNoteCtx = (): NoteResolveCtx | null => useContext(NotesEntityContext)
