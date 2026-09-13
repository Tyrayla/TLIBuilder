import React, { useMemo, useState } from 'react'
import { submitBugReport } from '../api/share'
import type { TliErrorPayload } from '../errors/tliError'
import { createCalculationSnapshot, createDiagnostics, currentSeason, getReportRuntimeContext, REPORT_CATEGORIES, type ReportCategory } from '../reports/reporting'

export default function ReportModal({ onClose, error }: { onClose: () => void, error?: TliErrorPayload }) {
  const [category, setCategory] = useState<ReportCategory>(error ? 'app_behavior' : 'wrong_calculation')
  const [expected, setExpected] = useState('')
  const [actual, setActual] = useState(error ? `${error.title} (${error.code})` : '')
  const [steps, setSteps] = useState('')
  const [discord, setDiscord] = useState('')
  const [includeBuild, setIncludeBuild] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [receipt, setReceipt] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const snapshotSummary = useMemo(() => includeBuild ? 'Current engine inputs (not build name, notes, local IDs, folders, or share links)' : 'No build configuration', [includeBuild])

  const submit = async () => {
    if (!expected.trim() || !actual.trim() || submitting) return
    setSubmitting(true); setSubmitError(null)
    try {
      const runtime = getReportRuntimeContext()
      const response = await submitBugReport({
        category,
        runtime: runtime.runtime,
        form_factor: runtime.form_factor,
        transport: runtime.transport,
        app_version: (typeof __APP_VERSION__ !== 'undefined' && __APP_VERSION__) || 'desktop-dev',
        season: currentSeason(),
        error_code: error?.code,
        operation: error?.operation,
        fingerprint: error?.fingerprint,
        description: `Expected behavior:\n${expected.trim()}\n\nActual behavior:\n${actual.trim()}`,
        reproduction_steps: steps.trim() || undefined,
        discord_username: discord.trim() || undefined,
        diagnostics: createDiagnostics(error),
        build_snapshot: includeBuild ? createCalculationSnapshot() : undefined,
      })
      setReceipt(response.reportId)
    } catch {
      setSubmitError('The report could not be sent. Check your connection and try again.')
    } finally { setSubmitting(false) }
  }

  return <div className="modal-backdrop" onClick={onClose}>
    <div className="modal-card" onClick={e => e.stopPropagation()} style={{ maxWidth: 640 }}>
      <div className="modal-accent" />
      <h3 className="modal-title">Report a bug</h3>
      {receipt ? <div className="settings-modal-body">
        <p>Thank you—your report was received.</p><p><strong>Report ID: {receipt}</strong></p>
        <div className="modal-actions"><button className="btn btn-primary" onClick={onClose}>Done</button></div>
      </div> : <div className="settings-modal-body">
        <label className="settings-row-label">Category<select className="settings-select" value={category} onChange={e => setCategory(e.target.value as ReportCategory)}>{REPORT_CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}</select></label>
        <label className="settings-row-label">Expected behavior<textarea value={expected} onChange={e => setExpected(e.target.value)} maxLength={4000} /></label>
        <label className="settings-row-label">Actual behavior<textarea value={actual} onChange={e => setActual(e.target.value)} maxLength={4000} /></label>
        <label className="settings-row-label">Steps to reproduce (optional)<textarea value={steps} onChange={e => setSteps(e.target.value)} maxLength={4000} /></label>
        <label className="settings-row-label">Discord username (optional)<input value={discord} onChange={e => setDiscord(e.target.value)} maxLength={128} /></label>
        <span className="settings-row-hint">You must be in the TLI Builder Discord for us to follow up there.</span>
        <label className="settings-row-label"><input type="checkbox" checked={includeBuild} onChange={e => setIncludeBuild(e.target.checked)} /> Include build configuration (recommended)</label>
        <span className="settings-row-hint">Sending: {snapshotSummary}.</span>
        {submitError && <p style={{ color: 'var(--err, #ff6b6b)' }}>{submitError}</p>}
        <div className="modal-actions"><button className="btn btn-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={!expected.trim() || !actual.trim() || submitting} onClick={() => void submit()}>{submitting ? 'Sending…' : 'Submit report'}</button></div>
      </div>}
    </div>
  </div>
}
