// TS mirror of backend/engine/affix_identity.py::affix_identity — the value-stripped identity used to
// key a support's explicit per-line roll so the renderer and engine agree on which roll maps to which
// line. MUST stay in sync with the Python version (guarded by affixIdentity.test.ts).
//
// Steps (identical to Python): lowercase → strip value tokens (sign/(range)/%) → drop punctuation
// (keep word chars, whitespace, ASCII hyphen) → collapse whitespace.

// A value token: optional sign, optional '(', a number (optional range and/or decimals), optional ')',
// optional '%'. Dash class includes ASCII hyphen and the unicode dashes used in game ranges.
const VALUE_RE = /[+\-‒–—]?\s*\(?\s*\d[\d.,]*\s*(?:[-‒–—]\s*\d[\d.,]*\s*)?\)?\s*%?/g

export function affixIdentity(text: string): string {
  const stripped = (text ?? '').toLowerCase().replace(VALUE_RE, ' ')
  return stripped.replace(/[^\w\s-]/g, ' ').replace(/\s+/g, ' ').trim()
}
