// Minimal, dependency-free markdown → HTML for release notes (the "What's New" modal injects HTML).
// Supports the subset used in our changelogs: #/##/### headers, - / * bullet lists, **bold**, `code`,
// and [text](url) links. Everything is HTML-escaped FIRST, and the final output is run through the
// shared `sanitizeHtml` (DOMPurify) before it's returned — see sanitizeHtml.ts for why that's the one
// rendering path every dangerouslySetInnerHTML site must go through.
import { sanitizeHtml } from './sanitizeHtml'

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function escapeAttrQuotes(s: string): string {
  return s.replace(/"/g, '&quot;')
}

// Only http(s) and relative/anchor links are allowed as `[text](url)` targets. Everything else —
// javascript:, data:, vbscript:, protocol-relative "//host", or any other scheme — is neutralized to
// "#" so a malicious changelog/markdown entry can't get a live script-executing href.
//
// Browsers strip ASCII control chars (\x00-\x1f, \x7f) and all whitespace (not just leading/
// trailing) from a URL before parsing its scheme, so `java\tscript:alert(1)` is really
// `javascript:alert(1)`. `.trim()` alone only catches the ends; an internal control char defeats
// the scheme regex below (it breaks the match, `scheme` becomes null, and the raw string would
// pass through untouched). Strip those chars everywhere in the string before scheme-checking.
function stripControlAndWhitespace(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/[\x00-\x1f\x7f\s]+/g, '')
}

function sanitizeLinkUrl(url: string): string {
  const trimmed = stripControlAndWhitespace(url.trim())
  if (/^\/\//.test(trimmed)) return '#'
  if (/^#/.test(trimmed)) return trimmed
  const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(trimmed)
  if (!scheme) return trimmed // no scheme → relative path, safe
  return /^https?$/i.test(scheme[1]) ? trimmed : '#'
}

function inline(s: string): string {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, text: string, url: string) =>
      `<a href="${escapeAttrQuotes(sanitizeLinkUrl(url))}" target="_blank" rel="noreferrer">${text}</a>`)
}

export function markdownToHtml(md: string): string {
  if (!md) return ''
  const lines = escapeHtml(md).split(/\r?\n/)
  const out: string[] = []
  let inList = false
  const closeList = () => { if (inList) { out.push('</ul>'); inList = false } }

  for (const raw of lines) {
    const line = raw.trimEnd()
    const header = /^(#{1,6})\s+(.*)$/.exec(line)
    if (header) {
      closeList()
      const lvl = Math.min(header[1].length, 6)
      out.push(`<h${lvl}>${inline(header[2])}</h${lvl}>`)
      continue
    }
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line)
    if (bullet) {
      if (!inList) { out.push('<ul>'); inList = true }
      out.push(`<li>${inline(bullet[1])}</li>`)
      continue
    }
    if (line.trim() === '') { closeList(); continue }
    closeList()
    out.push(`<p>${inline(line)}</p>`)
  }
  closeList()
  return sanitizeHtml(out.join('\n'))
}
