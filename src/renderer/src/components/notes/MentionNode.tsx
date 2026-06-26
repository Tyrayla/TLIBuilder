import React from 'react'
import { DecoratorNode, type LexicalNode, type NodeKey, type SerializedLexicalNode } from 'lexical'
import EntityChip from './EntityChip'
import { tokenFor, type NoteEntityType } from '../../utils/noteEntities'

export type SerializedMentionNode = SerializedLexicalNode & {
  entityType: NoteEntityType
  entityKey: string
}

// An ATOMIC, non-editable inline node = one note hyperlink. Decorates to an <EntityChip>. Its getTextContent()
// returns the `{{type:key}}` token, so `$getRoot().getTextContent()` serializes the whole document back to the
// stored notes string for free.
export class MentionNode extends DecoratorNode<React.ReactNode> {
  __entityType: NoteEntityType
  __entityKey: string

  static getType(): string { return 'note-mention' }

  static clone(node: MentionNode): MentionNode {
    return new MentionNode(node.__entityType, node.__entityKey, node.__key)
  }

  constructor(entityType: NoteEntityType, entityKey: string, key?: NodeKey) {
    super(key)
    this.__entityType = entityType
    this.__entityKey = entityKey
  }

  createDOM(): HTMLElement {
    const span = document.createElement('span')
    span.className = 'note-chip-host'
    return span
  }
  updateDOM(): boolean { return false }
  isInline(): boolean { return true }

  getTextContent(): string { return tokenFor(this.__entityType, this.__entityKey) }

  decorate(): React.ReactNode {
    return <EntityChip type={this.__entityType} entKey={this.__entityKey} />
  }

  exportJSON(): SerializedMentionNode {
    return { ...super.exportJSON(), type: 'note-mention', version: 1, entityType: this.__entityType, entityKey: this.__entityKey }
  }
  static importJSON(json: SerializedMentionNode): MentionNode {
    return new MentionNode(json.entityType, json.entityKey)
  }
}

export function $createMentionNode(entityType: NoteEntityType, entityKey: string): MentionNode {
  return new MentionNode(entityType, entityKey)
}
export function $isMentionNode(node: LexicalNode | null | undefined): node is MentionNode {
  return node instanceof MentionNode
}
