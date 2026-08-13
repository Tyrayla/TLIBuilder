import React from 'react'
import { api } from '../api/client'
import { getBuildPayload } from '../utils/buildPayload'

interface Props {
  children: React.ReactNode
  // Called when this boundary catches. Keep-alive screens use it to evict the crashed screen from the
  // mounted set so it unmounts and remounts fresh on the next visit (they never unmount on their own).
  onError?: (error: Error) => void
}

interface State {
  hasError: boolean
  error: Error | null
  code: string | null
  codeError: string | null
  codeLoading: boolean
  copied: boolean
}

// Root-level safety net. React 18 unmounts the ENTIRE tree on any uncaught render/effect throw —
// with no boundary anywhere above App, one rare rendering race (e.g. a stale-snapshot null deref)
// used to blank the whole screen AND strand the in-memory Zustand build with no way to save it.
// getBuildPayload() reads the store directly — a plain JS singleton untouched by the crashed React
// tree — so recovery works regardless of what actually broke.
export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = {
    hasError: false, error: null,
    code: null, codeError: null, codeLoading: false, copied: false,
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, code: null, codeError: null, codeLoading: false, copied: false }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary] uncaught error, build recovery UI shown', error, info.componentStack)
    this.props.onError?.(error)
  }

  // The real recovery path: the same tli1_ code the normal Import/Export flow already knows how
  // to read back in. Best-effort — the backend/Pyodide worker generating it could in principle
  // also be in a bad state, which is why the raw JSON download below never depends on it.
  private generateCode = async () => {
    this.setState({ codeLoading: true, codeError: null })
    try {
      const { code } = await api.encodeBuildCode(getBuildPayload())
      this.setState({ code, codeLoading: false })
    } catch (e) {
      this.setState({
        codeLoading: false,
        codeError: `Couldn't generate a recovery code (${e instanceof Error ? e.message : String(e)}) — use the JSON download below instead.`,
      })
    }
  }

  private copyCode = () => {
    if (!this.state.code) return
    navigator.clipboard.writeText(this.state.code).then(() => {
      this.setState({ copied: true })
      setTimeout(() => this.setState({ copied: false }), 2000)
    })
  }

  private downloadJson = () => {
    let json: string
    try {
      json = JSON.stringify(getBuildPayload(), null, 2)
    } catch (e) {
      json = `Could not read the in-progress build: ${e instanceof Error ? e.message : String(e)}`
    }
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tli-builder-recovery-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  private reload = () => window.location.reload()

  render() {
    if (!this.state.hasError) return this.props.children
    const { code, codeError, codeLoading, copied, error } = this.state

    return (
      <div style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'var(--bg-deep, #0a0e18)', color: 'var(--fg, #e8e8f0)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        padding: '40px 24px', overflow: 'auto', fontFamily: 'inherit',
      }}>
        <div style={{ maxWidth: 640, width: '100%' }}>
          <h1 style={{ fontSize: 20, marginBottom: 8 }}>Something went wrong</h1>
          <p style={{ color: 'var(--fg-muted, #9aa)', fontSize: 13, lineHeight: 1.6, marginBottom: 16 }}>
            TLI Builder hit an unexpected error and had to stop. Your in-progress build is still in
            memory — generate a recovery code below before doing anything else, then reload and
            paste it into Import / Export to get your build back.
          </p>

          <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
            <button className="btn btn-primary" onClick={this.generateCode} disabled={codeLoading}>
              {codeLoading ? 'Generating…' : 'Generate recovery code'}
            </button>
            {code && (
              <button className="btn" onClick={this.copyCode}>
                {copied ? 'Copied!' : 'Copy code'}
              </button>
            )}
          </div>
          {code && (
            <textarea
              readOnly
              value={code}
              onFocus={e => e.currentTarget.select()}
              style={{
                width: '100%', height: 70, fontFamily: 'monospace', fontSize: 11,
                background: 'var(--bg-card, #141a26)', color: 'var(--fg, #e8e8f0)',
                border: '1px solid var(--border, #2a3346)', borderRadius: 5, padding: 8,
                resize: 'vertical', marginBottom: 16,
              }}
            />
          )}
          {codeError && (
            <p style={{ color: 'var(--err, #ff6b6b)', fontSize: 12, marginBottom: 16 }}>{codeError}</p>
          )}

          <p style={{ color: 'var(--fg-muted, #9aa)', fontSize: 12, marginBottom: 6 }}>
            Or download the raw build data as a backup (not directly re-importable, but safe to keep):
          </p>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            <button className="btn" onClick={this.downloadJson}>Download build as JSON</button>
            <button className="btn btn-danger" onClick={this.reload}>Reload app</button>
          </div>

          {error && (
            <details style={{ color: 'var(--fg-muted, #9aa)', fontSize: 11 }}>
              <summary style={{ cursor: 'pointer' }}>Error details</summary>
              <pre style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{String(error.stack ?? error.message)}</pre>
            </details>
          )}
        </div>
      </div>
    )
  }
}
