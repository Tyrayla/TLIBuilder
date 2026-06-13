// Minimal, dependency-free markdown → HTML for release notes (the "What's New" modal injects HTML).
// Supports the subset used in our changelogs: #/##/### headers, - / * bullet lists, **bold**, `code`,
// and [text](url) links. Everything is HTML-escaped FIRST, so injecting the result is safe even though
// the source is a (semi-trusted) GitHub release body.

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function inline(s: string): string {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
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
  return out.join('\n')
}
