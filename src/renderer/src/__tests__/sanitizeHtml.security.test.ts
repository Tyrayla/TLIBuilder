import { describe, it, expect, vi } from 'vitest'

// --- Why DOMPurify is mocked here -------------------------------------------------------------
// `sanitizeHtml.ts` does `import DOMPurify from 'dompurify'` and calls `DOMPurify.sanitize(...)`
// directly. That works at runtime because the Electron renderer resolves `dompurify` to its
// browser bundle (`dist/purify.js`), which self-instantiates against the global `window` and is
// ready to use. Under this repo's vitest config (`vitest.config.ts` → `environment: 'node'`, no
// jsdom/happy-dom installed), `dompurify` resolves to its Node/factory build instead
// (`dist/purify.cjs.js`), whose default export is a *factory function* — `DOMPurify.sanitize` is
// not a function until you call `createDOMPurify(window)` with a real DOM. Confirmed by hand:
// importing the real `sanitizeHtml`/`markdownToHtml` under the current vitest config throws
// `TypeError: default.sanitize is not a function`.
//
// Neither `jsdom` nor `happy-dom` is present in node_modules, and adding one is a package.json /
// vitest.config.ts change — both out of scope for the testing agent (path-guard restricts writes
// to test directories only). So this file mocks `dompurify` with an identity pass-through
// (`sanitize: (html) => html`) to exercise the REAL `markdown.ts` and `sanitizeHtml.ts` production
// code paths without going through the DOM-dependent step.
//
// This is a faithful regression test for the actual vulnerability class: every attack string this
// suite pins is neutralized by `markdown.ts`'s own defenses — the blanket `escapeHtml()` pass over
// the raw markdown (which turns any literal `<`/`>` into entities before a single character
// reaches an HTML parser) and `sanitizeLinkUrl`/`escapeAttrQuotes` on link hrefs — before
// `sanitizeHtml`'s DOMPurify allowlist ever runs. DOMPurify is genuine defense-in-depth on top of
// that; this file cannot exercise that specific layer (the ALLOWED_TAGS/ALLOWED_ATTR allowlist
// itself) without a real DOM. That gap should be closed by adding a jsdom-capable test runner
// setup (a "jsdom" environment pragma requires the "jsdom" package as a devDependency plus a real
// createDOMPurify(window) instance) — a change for whichever agent owns package.json /
// vitest.config.ts, not this one.
// NOTE: do not write the literal environment-pragma comment token in this file (two slashes,
// "@vitest-environment", a space, then an env name) even in prose — vitest's doc-block scanner
// matches it anywhere in the source text, not just as a real directive, and will force this file
// into that (uninstalled) environment, breaking collection entirely.
// `addHook` is mocked as a no-op: `sanitizeHtml.ts` registers an `afterSanitizeAttributes` hook
// (forcing `rel="noopener noreferrer"` on `target="_blank"` anchors) at module load time. That
// hook only ever runs inside a real DOMPurify + DOM (it walks sanitized DOM nodes), which this
// node-env vitest config cannot provide — see the comment block below for why. Without this
// no-op, every test in this file fails at import time with "default.addHook is not a function"
// (confirmed by hand: this was the observed state of this file before this fix — the whole suite
// was silently failing to collect any tests, a stale mock that predates the rel=noopener hook).
vi.mock('dompurify', () => ({
  default: { sanitize: (html: string) => html, addHook: () => {} },
}))

import { markdownToHtml } from '../utils/markdown'

describe('markdownToHtml — XSS regression pins (H1/M1 fix)', () => {
  it('escapes a raw <img onerror> payload to inert text, no live <img> tag', () => {
    const html = markdownToHtml('<img src=x onerror=alert(1)>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img')
    expect(html).toContain('&gt;')
  })

  it('neutralizes a javascript: link to href="#"', () => {
    const html = markdownToHtml('[x](javascript:alert(1))')
    expect(html).toContain('href="#"')
    expect(html).not.toContain('javascript:')
  })

  it('neutralizes a data: URL link (with embedded script) to href="#"', () => {
    const html = markdownToHtml('[x](data:text/html,<script>alert(1)</script>)')
    expect(html).toContain('href="#"')
    expect(html).not.toContain('data:')
    expect(html).not.toContain('<script>')
  })

  it('neutralizes a vbscript: link to href="#"', () => {
    const html = markdownToHtml('[x](vbscript:msgbox(1))')
    expect(html).toContain('href="#"')
    expect(html).not.toContain('vbscript:')
  })

  it('neutralizes a protocol-relative //host link to href="#"', () => {
    const html = markdownToHtml('[x](//evil.example.com/payload)')
    expect(html).toContain('href="#"')
  })

  it('entity-escapes a quote-breakout attempt inside a link URL — no attribute breakout, no live <script>', () => {
    const html = markdownToHtml('[x](https://example.com/">​<script>alert(1)</script>)')
    // The quote that would have broken out of the href="..." attribute must survive only as &quot;
    expect(html).not.toMatch(/href="https:\/\/example\.com\/"[^&]/)
    expect(html).toContain('&quot;')
    // No unescaped script tag anywhere in the output
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('</script>')
    // The link is still recognized as https and kept (not collapsed to "#") since the scheme is legit
    expect(html).toMatch(/href="https:\/\/example\.com/)
  })

  it('renders a legit https link untouched', () => {
    const html = markdownToHtml('[safe](https://example.com/p)')
    expect(html).toContain('href="https://example.com/p"')
    expect(html).toContain('>safe</a>')
  })

  it('renders headers, bold, code, and bullet lists correctly', () => {
    expect(markdownToHtml('# Title')).toBe('<h1>Title</h1>')
    expect(markdownToHtml('**bold**')).toBe('<p><strong>bold</strong></p>')
    expect(markdownToHtml('`code`')).toBe('<p><code>code</code></p>')
    expect(markdownToHtml('- one\n- two')).toBe('<ul>\n<li>one</li>\n<li>two</li>\n</ul>')
  })
})

describe('markdownToHtml — sanitizeLinkUrl control-char bypass fix (security regression)', () => {
  // `sanitizeLinkUrl` (markdown.ts) now strips ASCII control chars AND whitespace anywhere in the
  // URL before running the scheme regex, because a browser does the same before parsing a URL's
  // scheme — so `java\x00script:` is really `javascript:` to the browser even though the scheme
  // regex alone wouldn't recognize it.
  //
  // Two of the four "control char" inputs below (`\t`, `\r` — and `\n`, tested separately) never
  // reach `sanitizeLinkUrl` as a link at all: the *outer* link-syntax regex in `inline()`,
  // `\[([^\]]+)\]\(([^)\s]+)\)`, requires the parenthesized URL portion to contain NO whitespace
  // (`\s` in JS matches tab/CR/LF along with space). So `[x](java\tscript:alert(1))` fails to
  // match as a link in the first place — it falls through to plain escaped paragraph text, with
  // no `<a>` tag and no `href` attribute of any kind. That is a *stronger* outcome than
  // `href="#"` (the link is never rendered as a link at all) — but it means the naive expectation
  // "collapses to href=#" does not literally hold for whitespace control chars; it holds instead
  // for non-whitespace control chars
  // (e.g. NUL, 0x01, 0x7F) which DO pass the outer regex's `[^)\s]+` filter and reach
  // `sanitizeLinkUrl`, which is where the fix's `stripControlAndWhitespace` actually strips them
  // and the scheme regex then correctly identifies `javascript:` and collapses it to `#`.
  //
  // Every case below is checked against the one invariant that actually matters: no output ever
  // contains a live, browser-interpretable `javascript:`-scheme href.
  it('tab-split "java\\tscript:" never becomes a live javascript: href', () => {
    const html = markdownToHtml('[x](java\tscript:alert(1))')
    expect(html).not.toMatch(/href="javascript:/i)
    expect(html).not.toContain('<a ') // outer link regex rejects whitespace in the URL span
  })

  it('newline-split "java\\nscript:" never becomes a live javascript: href', () => {
    const html = markdownToHtml('[x](java\nscript:alert(1))')
    expect(html).not.toMatch(/href="javascript:/i)
    expect(html).not.toContain('<a ')
  })

  it('CR-split "java\\rscript:" never becomes a live javascript: href', () => {
    const html = markdownToHtml('[x](java\rscript:alert(1))')
    expect(html).not.toMatch(/href="javascript:/i)
    expect(html).not.toContain('<a ')
  })

  it('NUL-embedded "java\\x00script:" reaches sanitizeLinkUrl and collapses to href="#"', () => {
    // No nested parens in the URL here (unlike the other cases' `alert(1)`) so the outer link
    // regex — which stops at the first `)` — captures the whole URL cleanly as one link.
    const html = markdownToHtml('[x](java\x00script:evil)')
    expect(html).toContain('href="#"')
    expect(html).not.toMatch(/href="javascript:/i)
    expect(html).not.toContain('\x00')
  })

  it('non-whitespace control chars (0x01, 0x7F) also collapse to href="#"', () => {
    expect(markdownToHtml('[x](java\x01script:evil)')).toContain('href="#"')
    expect(markdownToHtml('[x](java\x7fscript:evil)')).toContain('href="#"')
  })

  it('legit https URL with a query string is preserved unchanged', () => {
    const html = markdownToHtml('[safe](https://example.com/a?b=c)')
    expect(html).toContain('href="https://example.com/a?b=c"')
  })

  it('legit relative path is preserved unchanged', () => {
    const html = markdownToHtml('[safe](/rel/path)')
    expect(html).toContain('href="/rel/path"')
  })

  it('legit anchor link is preserved unchanged', () => {
    const html = markdownToHtml('[safe](#anchor)')
    expect(html).toContain('href="#anchor"')
  })
})

// --- Fix 2 (rel=noopener afterSanitizeAttributes hook) — coverage deferred, reported not skipped-silently ---
// `sanitizeHtml.ts`'s `afterSanitizeAttributes` hook (forcing `rel="noopener noreferrer"` on
// `target="_blank"` anchors) only runs inside REAL DOMPurify walking REAL DOM nodes
// (`node.tagName`, `node.getAttribute`, `node.setAttribute`). This repo's vitest.config.ts sets
// `environment: 'node'` with no jsdom/happy-dom installed, and this file's own `dompurify` mock
// (see above) is an identity pass-through with a no-op `addHook` — by design, since the real
// factory-mode `dompurify` package (resolved under Node, not the browser bundle) has no working
// `.sanitize()` without `createDOMPurify(window)`. Neither jsdom nor happy-dom is a devDependency
// here, and adding one is a vitest.config.ts / package.json change outside the testing agent's
// path-guard lane. There is no test in this repo, under the current config, that can exercise
// this hook against a real DOM. This coverage gap is the same one already called out above for
// the DOMPurify ALLOWED_TAGS/ALLOWED_ATTR allowlist itself — both need a jsdom-capable environment
// to close, tracked as one backlog item for whichever agent owns the vitest/jsdom config change.
