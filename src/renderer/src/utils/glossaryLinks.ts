// Auto-link known terms inside already-rendered markdown prose (Verification DB).
// A DOM TreeWalker wraps the FIRST occurrence of each term in an <a class="glossary-term …"> so it never
// breaks existing tags/links/code (unlike a string regex). Hover/click handling lives in the screen.
//
// A term can resolve three ways, in priority order (each gets a distinct color):
//   1. entry   — matches a Verification DB entry → in-app navigation      (--entry, blue)
//   2. article — matches a Help-DB article title → opens the deep-dive    (--article, teal)
//   3. glossary— master-glossary term only → hover definition, no click   (base, purple)
import { GlossaryTerm, HelpDbEntry, VerificationEntry } from '../api/client'

// Common words that are also terms but read as plain English in prose — don't auto-link these.
// Multi-word terms are always kept (distinctive); single words must be ≥5 chars and not in this set.
const STOP_TERMS = new Set([
  'focus', 'others', 'effect', 'damage', 'block', 'base', 'level', 'stack', 'stacks',
  'skill', 'skills', 'hit', 'area', 'merge', 'web', 'mana', 'life', 'gain', 'gains',
  'notes', 'setup', 'sources', 'others',
])
const MIN_SINGLE_WORD_LEN = 5

export interface TermInfo {
  name: string
  description?: string   // glossary def, or a Help-article excerpt for article-only terms
  articleId?: string     // → opens the Help-DB article
  entryId?: string       // → navigates to the Verification DB entry (highest priority)
}
export interface TermIndex {
  regex: RegExp | null
  byKey: Map<string, TermInfo>   // lowercased term → info
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function keepTerm(name: string): boolean {
  const k = name.toLowerCase()
  if (STOP_TERMS.has(k)) return false
  if (name.includes(' ')) return true               // multi-word → distinctive, keep
  return name.length >= MIN_SINGLE_WORD_LEN
}

// Verification entry titles often carry a parenthetical suffix ("Blessings (Focus / Agility)"); index the
// base title too so a bare mention ("Blessings") links to the entry.
function entryKeys(title: string): string[] {
  const keys = [title.toLowerCase()]
  const base = title.replace(/\s*\([^)]*\)\s*$/, '').trim().toLowerCase()
  if (base && base !== title.toLowerCase()) keys.push(base)
  return keys
}

// First paragraph of a Help article (H1 stripped, markdown flattened), for the hover preview of an
// article-only term that has no glossary definition.
function excerpt(md: string): string {
  const noH1 = md.replace(/^\s*#\s+.*(?:\r?\n)+/, '')
  const para = noH1.split(/\r?\n\s*\r?\n/)[0] || ''
  const plain = para
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*`_#>]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return plain.length > 260 ? plain.slice(0, 260).trimEnd() + '…' : plain
}

export function buildTermIndex(
  glossary: GlossaryTerm[], help: HelpDbEntry[], entries: VerificationEntry[],
): TermIndex {
  const byKey = new Map<string, TermInfo>()
  const set = (name: string, patch: Partial<TermInfo>) => {
    if (!name || !keepTerm(name)) return
    const key = name.toLowerCase()
    const cur = byKey.get(key) ?? { name }
    byKey.set(key, { ...cur, ...patch, name: cur.name })
  }

  // 1. Glossary defs.
  for (const t of glossary) set(t.name, { description: t.description })
  // 2. Help articles (article id + excerpt fallback if no glossary def).
  for (const e of help) {
    if (!e.title || !keepTerm(e.title)) continue
    const key = e.title.toLowerCase()
    const cur = byKey.get(key)
    set(e.title, { articleId: e.id, description: cur?.description ?? excerpt(e.markdown) })
  }
  // 3. Verification entries (highest priority — in-app nav).
  for (const en of entries) {
    for (const k of entryKeys(en.title)) {
      // Only auto-register a key from an entry if it's linkable; keep any existing glossary/article info.
      if (byKey.has(k)) { byKey.get(k)!.entryId = en.id }
      else if (keepTerm(k)) byKey.set(k, { name: en.title, entryId: en.id })
    }
  }

  const keys = [...byKey.keys()].sort((a, b) => b.length - a.length)  // longest first for greedy correctness
  const regex = keys.length ? new RegExp(`\\b(${keys.map(escapeRe).join('|')})\\b`, 'gi') : null
  return { regex, byKey }
}

// Wrap first-occurrence term matches inside `container`'s text nodes. `skipEntryId` avoids self-links when
// rendering an entry's own prose. Skips text already inside <a>/<code>/<pre>/.glossary-term.
export function linkGlossaryTerms(container: HTMLElement, index: TermIndex, skipEntryId?: string): void {
  if (!index.regex) return
  const seen = new Set<string>()
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const p = (node as Text).parentElement
      if (!p || p.closest('a, code, pre, .glossary-term')) return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  const targets: Text[] = []
  let n: Node | null
  while ((n = walker.nextNode())) targets.push(n as Text)

  for (const textNode of targets) {
    const text = textNode.nodeValue || ''
    index.regex.lastIndex = 0
    const hits: { start: number; end: number; key: string; info: TermInfo }[] = []
    let m: RegExpExecArray | null
    while ((m = index.regex.exec(text))) {
      const key = m[0].toLowerCase()
      const info = index.byKey.get(key)
      if (!info || seen.has(key)) continue
      if (info.entryId && info.entryId === skipEntryId && !info.articleId && !info.description) continue
      seen.add(key)
      hits.push({ start: m.index, end: m.index + m[0].length, key, info })
    }
    if (!hits.length) continue
    const frag = document.createDocumentFragment()
    let cursor = 0
    for (const h of hits) {
      if (h.start > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, h.start)))
      const a = document.createElement('a')
      const type = h.info.entryId ? 'entry' : h.info.articleId ? 'article' : 'glossary'
      a.className = `glossary-term glossary-term--${type}`
      a.setAttribute('data-term', h.key)
      if (h.info.entryId) a.setAttribute('data-entry', h.info.entryId)
      if (h.info.articleId) a.setAttribute('data-article', h.info.articleId)
      a.textContent = text.slice(h.start, h.end)
      frag.appendChild(a)
      cursor = h.end
    }
    if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)))
    textNode.parentNode?.replaceChild(frag, textNode)
  }
}
