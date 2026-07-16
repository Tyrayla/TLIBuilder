import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api, VerificationDbResponse, VerificationStatus,
  GlossaryTerm, HelpDbEntry,
} from '../api/client'
import { markdownToHtml } from '../utils/markdown'
import { buildTermIndex, linkGlossaryTerms, TermIndex } from '../utils/glossaryLinks'

interface Props {
  onBack: () => void
}

type Mode = 'verification' | 'help' | 'glossary'

// A single navigable location. Every navigation pushes the previous View onto a back-stack, so the in-screen
// Back button and Ctrl+Z can reverse the flow. `articleId` (when set) shows the Help-DB article modal overlay.
interface View {
  mode: Mode
  entryId: string | null
  helpId: string | null
  termKey: string | null
  articleId: string | null
}
const INITIAL_VIEW: View = { mode: 'verification', entryId: null, helpId: null, termKey: null, articleId: null }

const STATUS_META: Record<VerificationStatus, { label: string; color: string; bg: string; icon: string }> = {
  confirmed:  { label: 'Confirmed',  color: '#7ee787', bg: '#0e2a12', icon: '✅' },
  partial:    { label: 'Partial',    color: '#e3b341', bg: '#2a230a', icon: '🔶' },
  pending:    { label: 'Pending',    color: '#79c0ff', bg: '#0d2233', icon: '⬜' },
  unverified: { label: 'Unverified', color: '#d0a0ff', bg: '#221033', icon: '⚠️' },
  failed:     { label: 'Failed',     color: '#ff7b72', bg: '#2a0f0d', icon: '❌' },
}
const STATUS_ORDER: VerificationStatus[] = ['confirmed', 'partial', 'pending', 'unverified', 'failed']

function StatusBadge({ status }: { status: VerificationStatus }) {
  const m = STATUS_META[status] ?? STATUS_META.unverified
  return (
    <span className="verif-badge" style={{ color: m.color, background: m.bg, borderColor: m.color + '55' }}>
      {m.icon} {m.label}
    </span>
  )
}

function ProseSection({ title, md }: { title: string; md?: string }) {
  if (!md || !md.trim()) return null
  return (
    <div className="verif-section">
      <h4 className="verif-section-title">{title}</h4>
      <div className="verif-prose" dangerouslySetInnerHTML={{ __html: markdownToHtml(md) }} />
    </div>
  )
}

interface HoverState { name: string; description?: string; hint?: string; top: number; left: number }

// Help articles carry their own "# Title" H1; we show the title in the header, so drop the leading H1.
function stripLeadingH1(md: string): string {
  return md.replace(/^\s*#\s+.*(?:\r?\n)+/, '')
}

export default function VerificationDatabaseScreen({ onBack }: Props) {
  const [data, setData] = useState<VerificationDbResponse | null>(null)
  const [glossary, setGlossary] = useState<GlossaryTerm[]>([])
  const [help, setHelp] = useState<HelpDbEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const [view, setView] = useState<View>(INITIAL_VIEW)
  const [backStack, setBackStack] = useState<View[]>([])
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<VerificationStatus | 'all'>('all')
  const [skillFilter, setSkillFilter] = useState('')
  const [tagFilter, setTagFilter] = useState('')
  const [hover, setHover] = useState<HoverState | null>(null)

  const detailBodyRef = useRef<HTMLDivElement>(null)
  const articleBodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    Promise.all([
      api.getVerificationDatabase(),
      api.getGlossary().catch(() => ({ season: null, terms: [] })),
      api.getHelpDb().catch(() => ({ entries: [] })),
    ]).then(([db, g, h]) => {
      setData(db); setGlossary(g.terms || []); setHelp(h.entries || []); setLoading(false)
    }).catch(() => { setError(true); setLoading(false) })
  }, [])

  const entries = data?.entries ?? []
  const index: TermIndex = useMemo(() => buildTermIndex(glossary, help, entries), [glossary, help, entries])
  const helpById = useMemo(() => new Map(help.map(e => [e.id, e])), [help])
  const helpByTitle = useMemo(() => new Map(help.map(e => [e.title.toLowerCase(), e])), [help])

  // ── Navigation (history-aware) ──
  const navigate = (patch: Partial<View>) => {
    setBackStack(s => [...s, view])
    setView(v => ({ ...v, ...patch }))
    setHover(null)
  }
  const goBack = () => {
    setBackStack(s => {
      if (!s.length) return s
      setView(s[s.length - 1])
      setHover(null)
      return s.slice(0, -1)
    })
  }
  const goBackRef = useRef(goBack)
  goBackRef.current = goBack

  // Ctrl/Cmd+Z reverses navigation (unless a text field is focused → let it do normal undo).
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
        const t = e.target as HTMLElement | null
        if (t && /^(input|textarea|select)$/i.test(t.tagName)) return
        e.preventDefault(); goBackRef.current()
      }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  const switchMode = (m: Mode) => { setSearch(''); navigate({ mode: m, articleId: null }) }
  const goEntry = (id: string) => { if (entries.some(e => e.id === id)) navigate({ mode: 'verification', entryId: id, articleId: null }) }
  const openArticle = (id: string) => { if (helpById.has(id)) navigate({ articleId: id }) }

  // ── Per-mode filtered lists ──
  const q = search.trim().toLowerCase()
  const vFiltered = useMemo(() => entries.filter(e => {
    if (statusFilter !== 'all' && e.status !== statusFilter) return false
    if (skillFilter && !(e.skills ?? []).includes(skillFilter)) return false
    if (tagFilter && !(e.tags ?? []).includes(tagFilter)) return false
    if (!q) return true
    return [e.title, e.status, e.backlogId ?? '', e.formula ?? '', e.setup ?? '', e.notes ?? '',
      ...(e.skills ?? []), ...(e.tags ?? [])].join(' ').toLowerCase().includes(q)
  }), [entries, statusFilter, skillFilter, tagFilter, q])

  const hFiltered = useMemo(() => help.filter(e =>
    !q || [e.title, e.breadcrumb, e.markdown].join(' ').toLowerCase().includes(q)
  ), [help, q])

  const gFiltered = useMemo(() => glossary.filter(t =>
    !q || [t.name, t.description, ...(t.sources ?? [])].join(' ').toLowerCase().includes(q)
  ), [glossary, q])

  const vSelected = vFiltered.find(e => e.id === view.entryId) ?? vFiltered[0] ?? null
  const hSelected = hFiltered.find(e => e.id === view.helpId) ?? hFiltered[0] ?? null
  const gSelected = gFiltered.find(t => t.name.toLowerCase() === view.termKey) ?? gFiltered[0] ?? null
  const articleEntry = view.articleId ? helpById.get(view.articleId) ?? null : null

  // Re-link terms in the visible detail + the article modal whenever their content changes.
  const detailKey = view.mode === 'verification' ? vSelected?.id : view.mode === 'help' ? hSelected?.id : gSelected?.name
  useEffect(() => {
    if (detailBodyRef.current && index.regex) {
      linkGlossaryTerms(detailBodyRef.current, index, view.mode === 'verification' ? vSelected?.id : undefined)
    }
  }, [view.mode, detailKey, index])
  useEffect(() => {
    if (articleEntry && articleBodyRef.current && index.regex) linkGlossaryTerms(articleBodyRef.current, index)
  }, [articleEntry, index])

  // Delegated click for injected prose links (detail pane + article modal).
  const handleProseClick = (e: React.MouseEvent) => {
    const anchor = (e.target as HTMLElement).closest('a')
    if (!anchor) return
    if (anchor.classList.contains('glossary-term')) {
      e.preventDefault()
      const entry = anchor.getAttribute('data-entry')
      const art = anchor.getAttribute('data-article')
      if (entry) goEntry(entry)          // in-app entry nav
      else if (art) openArticle(art)     // Help article → contained modal (stay put)
      // glossary-only terms are hover-only (no navigation)
      return
    }
    const href = anchor.getAttribute('href') || ''
    if (/^https?:\/\//i.test(href)) {
      e.preventDefault()
      if (window.api?.openExternal) window.api.openExternal(href)
      else window.open(href, '_blank', 'noopener,noreferrer')
    } else if (href.endsWith('.md')) {
      e.preventDefault()
      goEntry(href.replace(/^.*\//, '').replace(/\.md$/, ''))
    }
  }

  const handleTermOver = (e: React.MouseEvent) => {
    const el = (e.target as HTMLElement).closest('.glossary-term') as HTMLElement | null
    if (!el) return
    const info = index.byKey.get(el.getAttribute('data-term') || '')
    const name = info?.name ?? el.textContent ?? ''
    const description = info?.description
    const hint = el.classList.contains('glossary-term--entry') ? 'Click to open this entry →'
      : el.classList.contains('glossary-term--article') ? 'Click for the full Help article →'
      : undefined
    if (!description && !hint) return
    const r = el.getBoundingClientRect()
    setHover({ name, description, hint, top: r.bottom + 6, left: Math.max(8, Math.min(r.left, window.innerWidth - 340)) })
  }
  const handleTermOut = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.glossary-term')) setHover(null)
  }

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: entries.length }
    for (const e of entries) c[e.status] = (c[e.status] ?? 0) + 1
    return c
  }, [entries])
  const availableStatuses = STATUS_ORDER.filter(s => (counts[s] ?? 0) > 0)

  const searchPlaceholder = view.mode === 'verification' ? 'Search by mechanic, skill, tag, or formula…'
    : view.mode === 'help' ? 'Search Help articles…' : 'Search glossary terms…'

  return (
    <div className="screen verif-screen">
      <div className="verif-header">
        <div className="verif-header-row">
          <button className="btn btn-sm btn-secondary" onClick={onBack}>Main Menu</button>
          <button className="btn btn-sm btn-secondary" onClick={goBack} disabled={backStack.length === 0} title="Back (Ctrl+Z)">← Back</button>
          <span className="verif-legend">
            <span className="verif-legend-label">Link colors:</span>
            <span className="verif-legend-item verif-legend-entry">entry</span>
            <span className="verif-legend-item verif-legend-article">help article</span>
            <span className="verif-legend-item verif-legend-glossary">glossary term</span>
          </span>
        </div>
        <div className="verif-tabs">
          <button className={`verif-tab ${view.mode === 'verification' ? 'active' : ''}`} onClick={() => switchMode('verification')}>Verification Database</button>
          <button className={`verif-tab ${view.mode === 'help' ? 'active' : ''}`} onClick={() => switchMode('help')}>Help Database</button>
          <button className={`verif-tab ${view.mode === 'glossary' ? 'active' : ''}`} onClick={() => switchMode('glossary')}>Master Glossary</button>
        </div>
      </div>

      {loading ? (
        <p style={{ color: '#888', padding: 20 }}>Loading…</p>
      ) : error ? (
        <p style={{ color: '#ff7b72', padding: 20 }}>Couldn&apos;t load the reference data.</p>
      ) : (
        <div className="verif-body">
          {/* ── Left: search + filters + list ── */}
          <div className="verif-list-pane">
            <div className="verif-search-bar">
              <input className="verif-search-input" placeholder={searchPlaceholder} value={search} onChange={e => setSearch(e.target.value)} />
              {search && <button className="verif-search-clear" onClick={() => setSearch('')}>×</button>}
            </div>

            {view.mode === 'verification' && (
              <>
                <div className="verif-status-chips">
                  <button className={`verif-chip ${statusFilter === 'all' ? 'active' : ''}`} onClick={() => setStatusFilter('all')}>All ({counts.all})</button>
                  {availableStatuses.map(s => (
                    <button key={s} className={`verif-chip ${statusFilter === s ? 'active' : ''}`}
                      style={statusFilter === s ? { color: STATUS_META[s].color, borderColor: STATUS_META[s].color } : undefined}
                      onClick={() => setStatusFilter(s)}>{STATUS_META[s].icon} {STATUS_META[s].label} ({counts[s]})</button>
                  ))}
                </div>
                <div className="verif-select-row">
                  <select className="verif-select" value={skillFilter} onChange={e => setSkillFilter(e.target.value)}>
                    <option value="">All skills</option>
                    {(data?.skills ?? []).map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <select className="verif-select" value={tagFilter} onChange={e => setTagFilter(e.target.value)}>
                    <option value="">All tags</option>
                    {(data?.tags ?? []).map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
              </>
            )}

            <div className="verif-list dark-scroll">
              {view.mode === 'verification' && (vFiltered.length === 0
                ? <div className="verif-empty">No entries match your filters.</div>
                : vFiltered.map(e => (
                  <div key={e.id} className={`verif-row ${vSelected?.id === e.id ? 'active' : ''}`} onClick={() => navigate({ entryId: e.id })}>
                    <div className="verif-row-top"><span className="verif-row-title">{e.title}</span><StatusBadge status={e.status} /></div>
                    {(e.skills.length > 0 || e.tags.length > 0) && (
                      <div className="verif-row-chips">
                        {e.skills.map(s => <span key={'s' + s} className="verif-chip-mini verif-chip-skill">{s}</span>)}
                        {e.tags.map(t => <span key={'t' + t} className="verif-chip-mini verif-chip-tag">{t}</span>)}
                      </div>
                    )}
                  </div>
                )))}

              {view.mode === 'help' && (hFiltered.length === 0
                ? <div className="verif-empty">No Help articles match.</div>
                : hFiltered.map(e => (
                  <div key={e.id} className={`verif-row ${hSelected?.id === e.id ? 'active' : ''}`} onClick={() => navigate({ helpId: e.id })}>
                    <div className="verif-row-title">{e.title}</div>
                    {e.breadcrumb && <div className="verif-row-crumb">{e.breadcrumb}</div>}
                  </div>
                )))}

              {view.mode === 'glossary' && (gFiltered.length === 0
                ? <div className="verif-empty">No glossary terms match.</div>
                : gFiltered.map(t => (
                  <div key={t.name} className={`verif-row ${gSelected?.name === t.name ? 'active' : ''}`} onClick={() => navigate({ termKey: t.name.toLowerCase() })}>
                    <div className="verif-row-title">{t.name}</div>
                  </div>
                )))}
            </div>
          </div>

          {/* ── Right: detail (per mode) ── */}
          <div className="verif-detail-pane dark-scroll" onClick={handleProseClick} onMouseOver={handleTermOver} onMouseOut={handleTermOut}>
            {view.mode === 'verification' && (!vSelected
              ? <div className="verif-empty">Select an entry to see its verification detail.</div>
              : (
                <>
                  <div className="verif-detail-head"><h3 className="verif-detail-title">{vSelected.title}</h3><StatusBadge status={vSelected.status} /></div>
                  <div className="verif-meta">
                    {vSelected.skills.length > 0 && <div className="verif-meta-row"><span className="verif-meta-label">Skills</span><span>{vSelected.skills.map(s => <span key={s} className="verif-chip-mini verif-chip-skill">{s}</span>)}</span></div>}
                    {vSelected.tags.length > 0 && <div className="verif-meta-row"><span className="verif-meta-label">Tags</span><span>{vSelected.tags.map(t => <span key={t} className="verif-chip-mini verif-chip-tag">{t}</span>)}</span></div>}
                    {vSelected.lastVerified && <div className="verif-meta-row"><span className="verif-meta-label">Last verified</span><span>{vSelected.lastVerified}{vSelected.verifiedBy ? ` · ${vSelected.verifiedBy}` : ''}</span></div>}
                    {vSelected.backlogId && <div className="verif-meta-row"><span className="verif-meta-label">Backlog</span><span className="verif-backlog">{vSelected.backlogId} <em>(docs/INGAME_VERIFICATION_BACKLOG.md)</em></span></div>}
                  </div>
                  <div className="verif-prose-body" ref={detailBodyRef}>
                    <ProseSection title="Setup" md={vSelected.setup} />
                    <ProseSection title="Raw data points" md={vSelected.dataPoints} />
                    <ProseSection title="Derived / confirmed formula" md={vSelected.formula} />
                    <ProseSection title="Notes / caveats / open questions" md={vSelected.notes} />
                    <ProseSection title="Implementation (engine model)" md={vSelected.implementation} />
                  </div>
                  {vSelected.sources && vSelected.sources.length > 0 && (
                    <div className="verif-section"><h4 className="verif-section-title">Sources</h4>
                      <ul className="verif-sources">{vSelected.sources.map((s, i) => <li key={i}>{s}</li>)}</ul>
                    </div>
                  )}
                </>
              ))}

            {view.mode === 'help' && (!hSelected
              ? <div className="verif-empty">Select a Help article.</div>
              : (
                <>
                  <div className="verif-detail-head verif-detail-head--col">
                    {hSelected.breadcrumb && <div className="verif-article-crumb">{hSelected.breadcrumb}</div>}
                    <h3 className="verif-detail-title">{hSelected.title}</h3>
                  </div>
                  <div className="verif-prose verif-article-body" ref={detailBodyRef}
                    dangerouslySetInnerHTML={{ __html: markdownToHtml(stripLeadingH1(hSelected.markdown)) }} />
                  <div className="verif-article-foot">Source: TLI Help Database{hSelected.breadcrumb ? ` — ${hSelected.breadcrumb}` : ''}</div>
                </>
              ))}

            {view.mode === 'glossary' && (!gSelected
              ? <div className="verif-empty">Select a glossary term.</div>
              : (
                <>
                  <div className="verif-detail-head"><h3 className="verif-detail-title">{gSelected.name}</h3></div>
                  <div className="verif-prose-body" ref={detailBodyRef}>
                    <div className="verif-section"><div className="verif-prose"><p>{gSelected.description}</p></div></div>
                  </div>
                  {gSelected.sources && gSelected.sources.length > 0 && (
                    <div className="verif-meta-row"><span className="verif-meta-label">Sources</span><span>{gSelected.sources.join(', ')}</span></div>
                  )}
                  {helpByTitle.has(gSelected.name.toLowerCase()) && (
                    <button className="btn btn-sm btn-secondary verif-openhelp" onClick={() => openArticle(helpByTitle.get(gSelected.name.toLowerCase())!.id)}>
                      Open the full Help article →
                    </button>
                  )}
                </>
              ))}
          </div>
        </div>
      )}

      {/* Term hover popover (non-interactive, hover-only). */}
      {hover && (
        <div className="verif-glossary-pop" style={{ top: hover.top, left: hover.left }}>
          <div className="verif-glossary-name">{hover.name}</div>
          {hover.description && <div className="verif-glossary-desc">{hover.description}</div>}
          {hover.hint && <div className="verif-glossary-more">{hover.hint}</div>}
        </div>
      )}

      {/* Help-DB article deep-dive (contained modal — opened by clicking a help-linked term). */}
      {articleEntry && (
        <div className="modal-backdrop" onClick={goBack}>
          <div className="modal-card verif-article-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <div className="verif-article-head">
              <div className="verif-article-heading">
                {articleEntry.breadcrumb && <div className="verif-article-crumb">{articleEntry.breadcrumb}</div>}
                <h3 className="verif-article-title">{articleEntry.title}</h3>
              </div>
              <button className="verif-article-close" onClick={goBack} title="Close (Ctrl+Z)">✕</button>
            </div>
            <div className="verif-prose verif-article-body verif-article-modal-body dark-scroll" ref={articleBodyRef}
              onClick={handleProseClick} onMouseOver={handleTermOver} onMouseOut={handleTermOut}
              dangerouslySetInnerHTML={{ __html: markdownToHtml(stripLeadingH1(articleEntry.markdown)) }} />
            <div className="verif-article-foot">Source: TLI Help Database{articleEntry.breadcrumb ? ` — ${articleEntry.breadcrumb}` : ''}</div>
          </div>
        </div>
      )}
    </div>
  )
}
