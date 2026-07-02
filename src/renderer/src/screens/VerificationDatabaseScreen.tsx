import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api, VerificationDbResponse, VerificationEntry, VerificationStatus,
  GlossaryTerm, HelpDbEntry,
} from '../api/client'
import { markdownToHtml } from '../utils/markdown'
import { buildTermIndex, linkGlossaryTerms, TermIndex } from '../utils/glossaryLinks'

interface Props {
  onBack: () => void
}

// Status → label + badge color. One place so the chips, list badges, and detail header stay in sync.
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

// Render a markdown prose field, or nothing if empty (thin Unverified entries leave these blank on purpose).
function ProseSection({ title, md }: { title: string; md?: string }) {
  if (!md || !md.trim()) return null
  return (
    <div className="verif-section">
      <h4 className="verif-section-title">{title}</h4>
      <div className="verif-prose" dangerouslySetInnerHTML={{ __html: markdownToHtml(md) }} />
    </div>
  )
}

interface HoverState { term: GlossaryTerm; hasArticle: boolean; top: number; left: number }

export default function VerificationDatabaseScreen({ onBack }: Props) {
  const [data, setData] = useState<VerificationDbResponse | null>(null)
  const [glossary, setGlossary] = useState<GlossaryTerm[]>([])
  const [help, setHelp] = useState<HelpDbEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<VerificationStatus | 'all'>('all')
  const [skillFilter, setSkillFilter] = useState('')
  const [tagFilter, setTagFilter] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const [hover, setHover] = useState<HoverState | null>(null)
  const [article, setArticle] = useState<HelpDbEntry | null>(null)

  const detailBodyRef = useRef<HTMLDivElement>(null)
  const articleBodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // The KB is required; glossary/help are enhancements — tolerate their absence.
    Promise.all([
      api.getVerificationDatabase(),
      api.getGlossary().catch(() => ({ season: null, terms: [] })),
      api.getHelpDb().catch(() => ({ entries: [] })),
    ]).then(([db, g, h]) => {
      setData(db); setGlossary(g.terms || []); setHelp(h.entries || []); setLoading(false)
    }).catch(() => { setError(true); setLoading(false) })
  }, [])

  const entries = data?.entries ?? []
  const index: TermIndex = useMemo(() => buildTermIndex(glossary, help), [glossary, help])
  const helpById = useMemo(() => new Map(help.map(e => [e.id, e])), [help])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return entries.filter(e => {
      if (statusFilter !== 'all' && e.status !== statusFilter) return false
      if (skillFilter && !(e.skills ?? []).includes(skillFilter)) return false
      if (tagFilter && !(e.tags ?? []).includes(tagFilter)) return false
      if (!q) return true
      const hay = [
        e.title, e.status, e.backlogId ?? '', e.formula ?? '', e.setup ?? '', e.notes ?? '',
        ...(e.skills ?? []), ...(e.tags ?? []),
      ].join(' ').toLowerCase()
      return hay.includes(q)
    })
  }, [entries, search, statusFilter, skillFilter, tagFilter])

  // Keep a valid selection as filters change; default to the first visible entry.
  const selected: VerificationEntry | null =
    filtered.find(e => e.id === selectedId) ?? filtered[0] ?? null

  // Auto-link glossary terms after the detail prose renders (and re-link on entry/index change). React only
  // touches the injected HTML when the entry changes, so our anchors survive unrelated re-renders (hover etc.).
  useEffect(() => {
    if (detailBodyRef.current && index.regex) linkGlossaryTerms(detailBodyRef.current, index)
  }, [selected?.id, index])

  useEffect(() => {
    if (article && articleBodyRef.current && index.regex) linkGlossaryTerms(articleBodyRef.current, index)
  }, [article, index])

  const openArticleById = (id: string) => {
    const e = helpById.get(id)
    if (e) { setArticle(e); setHover(null) }
  }

  // Delegated click for injected prose links: internal `foo.md` → in-app nav; external http → system browser;
  // glossary term → open its Help-DB article (or nothing if none). Works in both the detail pane and article.
  const handleProseClick = (e: React.MouseEvent) => {
    const anchor = (e.target as HTMLElement).closest('a')
    if (!anchor) return
    if (anchor.classList.contains('glossary-term')) {
      e.preventDefault()
      const art = anchor.getAttribute('data-article')
      if (art) openArticleById(art)
      return
    }
    const href = anchor.getAttribute('href') || ''
    if (/^https?:\/\//i.test(href)) {
      e.preventDefault()
      if (window.api?.openExternal) window.api.openExternal(href)
      else window.open(href, '_blank', 'noopener,noreferrer')
    } else if (href.endsWith('.md')) {
      e.preventDefault()
      const id = href.replace(/^.*\//, '').replace(/\.md$/, '')
      if (entries.some(en => en.id === id)) setSelectedId(id)
    }
  }

  // Hover a glossary term → floating definition popover (positioned from the term's rect). Hover-only.
  const handleTermOver = (e: React.MouseEvent) => {
    const el = (e.target as HTMLElement).closest('.glossary-term') as HTMLElement | null
    if (!el) return
    const term = index.byKey.get(el.getAttribute('data-term') || '')
    if (!term) return
    const r = el.getBoundingClientRect()
    const left = Math.min(r.left, window.innerWidth - 340)
    setHover({ term, hasArticle: !!el.getAttribute('data-article'), top: r.bottom + 6, left: Math.max(8, left) })
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

  return (
    <div className="screen verif-screen">
      <div className="verif-header">
        <button className="btn btn-sm btn-secondary" onClick={onBack}>← Back</button>
        <h2 className="verif-title">📋 Verification Database</h2>
        <span className="verif-subtitle">In-game testing setups, raw data, and confirmed formulas — provable &amp; replicable.</span>
      </div>

      {loading ? (
        <p style={{ color: '#888', padding: 20 }}>Loading…</p>
      ) : error ? (
        <p style={{ color: '#ff7b72', padding: 20 }}>Couldn&apos;t load the verification database.</p>
      ) : (
        <div className="verif-body">
          {/* ── Left: filters + list ── */}
          <div className="verif-list-pane">
            <div className="verif-search-bar">
              <input
                className="verif-search-input"
                placeholder="Search by mechanic, skill, tag, or formula…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              {search && <button className="verif-search-clear" onClick={() => setSearch('')}>×</button>}
            </div>

            <div className="verif-status-chips">
              <button
                className={`verif-chip ${statusFilter === 'all' ? 'active' : ''}`}
                onClick={() => setStatusFilter('all')}
              >All ({counts.all})</button>
              {availableStatuses.map(s => (
                <button
                  key={s}
                  className={`verif-chip ${statusFilter === s ? 'active' : ''}`}
                  style={statusFilter === s ? { color: STATUS_META[s].color, borderColor: STATUS_META[s].color } : undefined}
                  onClick={() => setStatusFilter(s)}
                >{STATUS_META[s].icon} {STATUS_META[s].label} ({counts[s]})</button>
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

            <div className="verif-list dark-scroll">
              {filtered.length === 0 && <div className="verif-empty">No entries match your filters.</div>}
              {filtered.map(e => (
                <div
                  key={e.id}
                  className={`verif-row ${selected?.id === e.id ? 'active' : ''}`}
                  onClick={() => setSelectedId(e.id)}
                >
                  <div className="verif-row-top">
                    <span className="verif-row-title">{e.title}</span>
                    <StatusBadge status={e.status} />
                  </div>
                  {(e.skills.length > 0 || e.tags.length > 0) && (
                    <div className="verif-row-chips">
                      {e.skills.map(s => <span key={'s' + s} className="verif-chip-mini verif-chip-skill">{s}</span>)}
                      {e.tags.map(t => <span key={'t' + t} className="verif-chip-mini verif-chip-tag">{t}</span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* ── Right: detail ── */}
          <div className="verif-detail-pane dark-scroll" onClick={handleProseClick}>
            {!selected ? (
              <div className="verif-empty">Select an entry to see its verification detail.</div>
            ) : (
              <>
                <div className="verif-detail-head">
                  <h3 className="verif-detail-title">{selected.title}</h3>
                  <StatusBadge status={selected.status} />
                </div>
                <div className="verif-meta">
                  {selected.skills.length > 0 && (
                    <div className="verif-meta-row"><span className="verif-meta-label">Skills</span>
                      <span>{selected.skills.map(s => <span key={s} className="verif-chip-mini verif-chip-skill">{s}</span>)}</span>
                    </div>
                  )}
                  {selected.tags.length > 0 && (
                    <div className="verif-meta-row"><span className="verif-meta-label">Tags</span>
                      <span>{selected.tags.map(t => <span key={t} className="verif-chip-mini verif-chip-tag">{t}</span>)}</span>
                    </div>
                  )}
                  {selected.lastVerified && (
                    <div className="verif-meta-row"><span className="verif-meta-label">Last verified</span>
                      <span>{selected.lastVerified}{selected.verifiedBy ? ` · ${selected.verifiedBy}` : ''}</span>
                    </div>
                  )}
                  {selected.backlogId && (
                    <div className="verif-meta-row"><span className="verif-meta-label">Backlog</span>
                      <span className="verif-backlog">{selected.backlogId} <em>(docs/INGAME_VERIFICATION_BACKLOG.md)</em></span>
                    </div>
                  )}
                </div>

                {/* Consistent order; Implementation always sits last, just above Sources. Empty
                    sections auto-hide, so entries stay consistent even when fields are missing. */}
                <div className="verif-prose-body" ref={detailBodyRef} onMouseOver={handleTermOver} onMouseOut={handleTermOut}>
                  <ProseSection title="Setup" md={selected.setup} />
                  <ProseSection title="Raw data points" md={selected.dataPoints} />
                  <ProseSection title="Derived / confirmed formula" md={selected.formula} />
                  <ProseSection title="Notes / caveats / open questions" md={selected.notes} />
                  <ProseSection title="Implementation (engine model)" md={selected.implementation} />
                </div>

                {selected.sources && selected.sources.length > 0 && (
                  <div className="verif-section">
                    <h4 className="verif-section-title">Sources</h4>
                    <ul className="verif-sources">
                      {selected.sources.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Glossary hover popover (non-interactive, hover-only). */}
      {hover && (
        <div className="verif-glossary-pop" style={{ top: hover.top, left: hover.left }}>
          <div className="verif-glossary-name">{hover.term.name}</div>
          <div className="verif-glossary-desc">{hover.term.description}</div>
          {hover.hasArticle && <div className="verif-glossary-more">Click to open the full Help article →</div>}
        </div>
      )}

      {/* Help-DB article deep-dive (slide-over). */}
      {article && (
        <div className="verif-article-backdrop" onClick={() => setArticle(null)}>
          <div className="verif-article-panel dark-scroll" onClick={e => e.stopPropagation()}>
            <div className="verif-article-head">
              <div>
                {article.breadcrumb && <div className="verif-article-crumb">{article.breadcrumb}</div>}
                <h3 className="verif-article-title">{article.title}</h3>
              </div>
              <button className="btn btn-sm btn-secondary" onClick={() => setArticle(null)}>✕ Close</button>
            </div>
            <div
              className="verif-prose verif-article-body"
              ref={articleBodyRef}
              onClick={handleProseClick}
              onMouseOver={handleTermOver}
              onMouseOut={handleTermOut}
              dangerouslySetInnerHTML={{ __html: markdownToHtml(article.markdown) }}
            />
            <div className="verif-article-foot">Source: TLI Help Database — {article.breadcrumb || article.title}</div>
          </div>
        </div>
      )}
    </div>
  )
}
