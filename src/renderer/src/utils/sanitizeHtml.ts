// The ONE sanitized-HTML rendering path in the renderer. Every string that ends up on
// `dangerouslySetInnerHTML` — whether it's markdown we rendered ourselves (markdown.ts) or an
// upstream HTML blob we trust less (a GitHub release body in UpdateBanner) — must pass through
// `sanitizeHtml` immediately before it's injected. Do not add a new dangerouslySetInnerHTML call
// site that skips this.
import DOMPurify from 'dompurify'

const ALLOWED_TAGS = [
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li',
  'strong', 'em', 'b', 'i', 'a', 'code', 'pre', 'blockquote', 'br', 'div', 'span',
]
const ALLOWED_ATTR = ['href', 'target', 'rel', 'class']

// ALLOWED_ATTR lets `target`/`rel` through as-authored. markdown.ts's own <a> tags hardcode
// `rel="noreferrer"`, but the "looks like HTML" branch in UpdateBanner.tsx feeds raw upstream
// (GitHub release body) HTML straight into this function with no markdown.ts escaping in front —
// so an anchor from that source could carry `target="_blank"` with no `rel` at all, leaving the
// opened page able to reach back via `window.opener` (reverse tabnabbing). Force safe `rel` on
// every `target="_blank"` anchor regardless of source, closing that gap for parity with the
// markdown path. Registered once at module load, not per-call.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A' && node.getAttribute('target') === '_blank') {
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function sanitizeHtml(html: string): string {
  if (!html) return ''
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    // DOMPurify's own default URI regexp already excludes javascript:/data:/vbscript:; this is
    // defense-in-depth on top of the URL-scheme check markdown.ts's inline() already applies.
  })
}
