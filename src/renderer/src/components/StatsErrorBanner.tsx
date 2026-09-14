import React from 'react'
import { copyableErrorDetails, prepareReport, type TliErrorPayload } from '../errors/tliError'

// Keeps a failed calculation visible and actionable instead of leaving stale stats without context.
export function StatsErrorBanner({ error }: { error: TliErrorPayload | null }) {
  if (!error) return null
  const copyDetails = () => void navigator.clipboard?.writeText(copyableErrorDetails(error))
  return (
    <div
      role="alert"
      style={{
        background: 'rgba(255, 107, 107, 0.12)',
        border: '1px solid var(--err, #ff6b6b)',
        borderRadius: 6,
        padding: '10px 14px',
        margin: '0 0 10px',
        color: 'var(--err, #ff6b6b)',
        fontSize: 13,
        lineHeight: 1.5,
        flex: '1 0 100%',
      }}
    >
      <strong>{error.title} ({error.code}) — </strong>
      <span>the stats below are not up to date. {error.message}</span>
      {error.remediation && <div style={{ marginTop: 4, color: 'var(--fg-muted, #9aa)' }}>{error.remediation}</div>}
      <button className="btn" style={{ marginTop: 8 }} onClick={copyDetails}>Copy details</button>
      {error.retryable && <button className="btn" style={{ margin: '8px 0 0 8px' }} onClick={() => window.location.reload()}>Retry</button>}
      <button className="btn" style={{ margin: '8px 0 0 8px' }} onClick={() => prepareReport(error)}>Report this problem</button>
    </div>
  )
}
