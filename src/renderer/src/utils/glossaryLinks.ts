// Auto-link known glossary terms inside already-rendered markdown prose (Verification DB).
// A DOM TreeWalker wraps the FIRST occurrence of each term in an <a class="glossary-term"> so it never
// breaks existing tags/links/code (unlike a string regex). Hover/click handling lives in the screen.
import { GlossaryTerm, HelpDbEntry } from '../api/client'

// Common words that are also glossary terms but read as plain English in prose — don't auto-link these.
// Multi-word terms are always kept (distinctive); single words must be ≥5 chars and not in this set.
const STOP_TERMS = new Set([
  'focus', 'others', 'effect', 'damage', 'block', 'base', 'level', 'stack', 'stacks',
  'skill', 'skills', 'hit', 'area', 'merge', 'web', 'mana', 'life', 'gain', 'gains',
])
const MIN_SINGLE_WORD_LEN = 5

export interface TermIndex {
  regex: RegExp | null
  byKey: Map<string, GlossaryTerm>       // lowercased name → term
  articleByKey: Map<string, string>      // lowercased name → help-article id (only when one matches)
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

export function buildTermIndex(terms: GlossaryTerm[], help: HelpDbEntry[]): TermIndex {
  const byKey = new Map<string, GlossaryTerm>()
  for (const t of terms) {
    if (!t.name) continue
    const k = t.name.toLowerCase()
    if (keepTerm(t.name) && !byKey.has(k)) byKey.set(k, t)
  }
  // Article resolution: match a term to a Help-DB article by (normalized) title.
  const articleByTitle = new Map<string, string>()
  for (const e of help) if (e.title) articleByTitle.set(e.title.toLowerCase(), e.id)
  const articleByKey = new Map<string, string>()
  for (const k of byKey.keys()) {
    const art = articleByTitle.get(k)
    if (art) articleByKey.set(k, art)
  }
  // Longest names first so "Spell Burst Charge" wins over "Spell Burst".
  const names = [...byKey.keys()].sort((a, b) => b.length - a.length)
  const regex = names.length
    ? new RegExp(`\\b(${names.map(escapeRe).join('|')})\\b`, 'gi')
    : null
  return { regex, byKey, articleByKey }
}

// Wrap first-occurrence term matches inside `container`'s text nodes. Idempotent-ish: skips text already
// inside <a>/<code>/.glossary-term, and only the first occurrence of each term (across the container) links.
export function linkGlossaryTerms(container: HTMLElement, index: TermIndex): void {
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
    const hits: { start: number; end: number; key: string }[] = []
    let m: RegExpExecArray | null
    while ((m = index.regex.exec(text))) {
      const key = m[0].toLowerCase()
      if (!seen.has(key) && index.byKey.has(key)) {
        seen.add(key)
        hits.push({ start: m.index, end: m.index + m[0].length, key })
      }
    }
    if (!hits.length) continue
    const frag = document.createDocumentFragment()
    let cursor = 0
    for (const h of hits) {
      if (h.start > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, h.start)))
      const a = document.createElement('a')
      a.className = 'glossary-term'
      a.setAttribute('data-term', h.key)
      const art = index.articleByKey.get(h.key)
      if (art) a.setAttribute('data-article', art)
      a.textContent = text.slice(h.start, h.end)
      frag.appendChild(a)
      cursor = h.end
    }
    if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)))
    textNode.parentNode?.replaceChild(frag, textNode)
  }
}
