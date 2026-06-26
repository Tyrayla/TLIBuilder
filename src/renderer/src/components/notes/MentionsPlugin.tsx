import React, { useCallback, useMemo, useState } from 'react'
import * as ReactDOM from 'react-dom'
import { useLexicalComposerContext } from '@lexical/react/LexicalComposerContext'
import {
  LexicalTypeaheadMenuPlugin, MenuOption, useBasicTypeaheadTriggerMatch,
} from '@lexical/react/LexicalTypeaheadMenuPlugin'
import { $createTextNode, type TextNode } from 'lexical'
import { $createMentionNode } from './MentionNode'
import { buildEntityIndex, type NoteEntity, type NoteResolveCtx } from '../../utils/noteEntities'

class EntityOption extends MenuOption {
  ent: NoteEntity
  constructor(ent: NoteEntity) { super(`${ent.type}:${ent.key}`); this.ent = ent }
}

// Typing "@" opens an autocomplete listing build entities first, then catalog. Selecting inserts a MentionNode chip.
export default function MentionsPlugin({ ctx }: { ctx: NoteResolveCtx }) {
  const [editor] = useLexicalComposerContext()
  const [query, setQuery] = useState<string | null>(null)
  const triggerFn = useBasicTypeaheadTriggerMatch('@', { minLength: 0 })

  const index = useMemo(() => buildEntityIndex(ctx), [ctx])
  const options = useMemo(() => {
    const q = (query ?? '').trim().toLowerCase()
    const matched = q ? index.filter(e => e.name.toLowerCase().includes(q)) : index
    return matched.slice(0, 12).map(e => new EntityOption(e))
  }, [index, query])

  const onSelectOption = useCallback(
    (option: EntityOption, nodeToReplace: TextNode | null, closeMenu: () => void) => {
      editor.update(() => {
        const mention = $createMentionNode(option.ent.type, option.ent.key)
        if (nodeToReplace) nodeToReplace.replace(mention)
        const space = $createTextNode(' ')
        mention.insertAfter(space)
        space.select()
        closeMenu()
      })
    },
    [editor],
  )

  return (
    <LexicalTypeaheadMenuPlugin<EntityOption>
      options={options}
      onQueryChange={setQuery}
      onSelectOption={onSelectOption}
      triggerFn={triggerFn}
      menuRenderFn={(anchorRef, { selectedIndex, selectOptionAndCleanUp, setHighlightedIndex }) =>
        anchorRef.current && options.length
          ? ReactDOM.createPortal(
              <div className="note-typeahead">
                {options.map((opt, i) => (
                  <button
                    key={`${opt.ent.type}:${opt.ent.key}`}
                    className={`note-typeahead-item${i === selectedIndex ? ' active' : ''}`}
                    onMouseEnter={() => setHighlightedIndex(i)}
                    onMouseDown={e => e.preventDefault()}
                    onClick={() => { setHighlightedIndex(i); selectOptionAndCleanUp(opt) }}
                  >
                    <span className="note-typeahead-name" style={{ color: opt.ent.color }}>{opt.ent.name}</span>
                    <span className="note-typeahead-kind">{opt.ent.kindLabel}{opt.ent.source === 'build' ? ' · build' : ''}</span>
                  </button>
                ))}
              </div>,
              anchorRef.current,
            )
          : null
      }
    />
  )
}
