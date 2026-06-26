import React from 'react'
import { $getRoot, $createParagraphNode, $createTextNode, $createLineBreakNode, type EditorState } from 'lexical'
import { LexicalComposer } from '@lexical/react/LexicalComposer'
import { PlainTextPlugin } from '@lexical/react/LexicalPlainTextPlugin'
import { ContentEditable } from '@lexical/react/LexicalContentEditable'
import { HistoryPlugin } from '@lexical/react/LexicalHistoryPlugin'
import { OnChangePlugin } from '@lexical/react/LexicalOnChangePlugin'
import { LexicalErrorBoundary } from '@lexical/react/LexicalErrorBoundary'
import { MentionNode, $createMentionNode } from './MentionNode'
import MentionsPlugin from './MentionsPlugin'
import { NotesEntityContext } from './NotesEntityContext'
import { parseNoteSegments, type NoteResolveCtx } from '../../utils/noteEntities'

// Build the initial editor state from a stored notes string (prose + {{type:key}} tokens). One paragraph with
// line breaks (PlainText), tokens become atomic MentionNodes.
function prepopulate(notes: string) {
  return () => {
    const root = $getRoot()
    if (root.getFirstChild() !== null) return
    const p = $createParagraphNode()
    for (const seg of parseNoteSegments(notes)) {
      if (seg.kind === 'token') {
        p.append($createMentionNode(seg.type, seg.key))
      } else {
        seg.text.split('\n').forEach((part, i) => {
          if (i > 0) p.append($createLineBreakNode())
          if (part) p.append($createTextNode(part))
        })
      }
    }
    root.append(p)
  }
}

export default function NotesEditor({ initialNotes, onChange, ctx }: {
  initialNotes: string
  onChange: (notes: string) => void
  ctx: NoteResolveCtx
}) {
  const initialConfig = {
    namespace: 'tli-notes',
    nodes: [MentionNode],
    editorState: prepopulate(initialNotes),
    onError: (e: Error) => { console.error('[notes editor]', e) },
    theme: { paragraph: 'note-paragraph' },
  }

  const handleChange = (editorState: EditorState) => {
    editorState.read(() => onChange($getRoot().getTextContent()))
  }

  return (
    <NotesEntityContext.Provider value={ctx}>
      <LexicalComposer initialConfig={initialConfig}>
        <div className="notes-editor">
          <PlainTextPlugin
            contentEditable={<ContentEditable className="notes-contenteditable" aria-placeholder="Write your guide… type @ to link an item, node, skill, trait…" placeholder={<div className="notes-placeholder">Write your guide… type @ to link an item, node, skill, trait…</div>} />}
            ErrorBoundary={LexicalErrorBoundary}
          />
          <HistoryPlugin />
          <OnChangePlugin onChange={handleChange} ignoreSelectionChange />
          <MentionsPlugin ctx={ctx} />
        </div>
      </LexicalComposer>
    </NotesEntityContext.Provider>
  )
}
