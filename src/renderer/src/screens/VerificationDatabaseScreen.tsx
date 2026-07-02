import { useEffect, useMemo, useState } from 'react'
import { api, VerificationDbResponse, VerificationEntry, VerificationStatus } from '../api/client'
import { markdownToHtml } from '../utils/markdown'

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

export default function VerificationDatabaseScreen({ onBack }: Props) {
  const [data, setData] = useState<VerificationDbResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<VerificationStatus | 'all'>('all')
  const [skillFilter, setSkillFilter] = useState('')
  const [tagFilter, setTagFilter] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    api.getVerificationDatabase()
      .then(d => { setData(d); setLoading(false) })
      .catch(() => { setError(true); setLoading(false) })
  }, [])

  const entries = data?.entries ?? []

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

  // Prose is injected HTML, so links can't carry React handlers. Delegate clicks on the detail pane:
  // internal cross-links (`foo.md`) select that entry in-app; external `http(s)` links open the system
  // browser. Without this, `<a href="collapse.md">` resolves against the app URL and opens localhost.
  const handleProseClick = (e: React.MouseEvent) => {
    const anchor = (e.target as HTMLElement).closest('a')
    if (!anchor) return
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

  // Per-status counts for the filter chips.
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
                <ProseSection title="Setup" md={selected.setup} />
                <ProseSection title="Raw data points" md={selected.dataPoints} />
                <ProseSection title="Derived / confirmed formula" md={selected.formula} />
                <ProseSection title="Notes / caveats / open questions" md={selected.notes} />
                <ProseSection title="Implementation (engine model)" md={selected.implementation} />

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
    </div>
  )
}
