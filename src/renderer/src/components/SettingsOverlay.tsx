import React, { useEffect, useState } from 'react'
import { IS_WEB } from '../api/client'
import { useUiPrefs } from '../store/uiPrefsStore'

type Channel = 'stable' | 'nightly'

interface AppSettings {
  updateChannel: Channel
  numberSeparator?: 'commas' | 'decimals'
  decimalPrecision?: number
}

/**
 * Global app-settings modal. Reuses the shared `.modal-*` styling. Today only the update-channel control is
 * wired (it round-trips through the main process via the settings IPC so the updater can read it before the
 * renderer loads). The display rows are intentionally rendered disabled — scaffolding for a later pass.
 */
export default function SettingsOverlay({ onClose }: { onClose: () => void }) {
  const [channel, setChannel] = useState<Channel>('stable')
  const [saving, setSaving] = useState(false)
  const collapsiblePanels = useUiPrefs(s => s.collapsiblePanels)
  const setCollapsiblePanels = useUiPrefs(s => s.setCollapsiblePanels)
  const showModifierBadges = useUiPrefs(s => s.showModifierBadges)
  const toggleModifierBadges = useUiPrefs(s => s.toggleModifierBadges)

  useEffect(() => {
    window.api?.getSettings?.().then((s: AppSettings) => setChannel(s.updateChannel)).catch(() => {})
  }, [])

  const switchChannel = async (ch: Channel) => {
    if (ch === channel || saving) return
    setChannel(ch)
    setSaving(true)
    try { await window.api?.setSetting?.('updateChannel', ch) } catch { /* ignore */ }
    setSaving(false)
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card settings-modal-card" onClick={e => e.stopPropagation()}>
        <div className="modal-accent" />
        <h3 className="modal-title">Settings</h3>

        <div className="settings-modal-body">
          {/* ── Updates (desktop only; the web app updates by redeploy) ─────── */}
          {!IS_WEB && <section className="settings-section">
            <h4 className="settings-section-title">Updates</h4>
            <div className="settings-row">
              <div className="settings-row-label">
                <span>Release channel</span>
                <span className="settings-row-hint">
                  Nightly gets frequent in-progress patches; Stable is the weekly release.
                </span>
              </div>
              <div className="settings-segmented">
                <button
                  className={`settings-seg-btn${channel === 'stable' ? ' active' : ''}`}
                  onClick={() => switchChannel('stable')}
                  disabled={saving}
                >Stable</button>
                <button
                  className={`settings-seg-btn${channel === 'nightly' ? ' active' : ''}`}
                  onClick={() => switchChannel('nightly')}
                  disabled={saving}
                >Nightly</button>
              </div>
            </div>
          </section>}

          {/* ── Display ───────────────────────────────────────────────────── */}
          <section className="settings-section">
            <h4 className="settings-section-title">Display</h4>
            <div className="settings-row">
              <div className="settings-row-label">
                <span>NYI flags</span>
                <span className="settings-row-hint">Show badges marking modifiers the engine doesn't recognize or use for this build.</span>
              </div>
              <div className="settings-segmented">
                <button
                  className={`settings-seg-btn${!showModifierBadges ? ' active' : ''}`}
                  onClick={() => { if (showModifierBadges) toggleModifierBadges() }}
                >Off</button>
                <button
                  className={`settings-seg-btn${showModifierBadges ? ' active' : ''}`}
                  onClick={() => { if (!showModifierBadges) toggleModifierBadges() }}
                >On</button>
              </div>
            </div>
            <div className="settings-row">
              <div className="settings-row-label">
                <span>Collapsible panels</span>
                <span className="settings-row-hint">Show a +/− control on stat boxes so they can collapse. Off keeps every box expanded.</span>
              </div>
              <div className="settings-segmented">
                <button
                  className={`settings-seg-btn${!collapsiblePanels ? ' active' : ''}`}
                  onClick={() => setCollapsiblePanels(false)}
                >Off</button>
                <button
                  className={`settings-seg-btn${collapsiblePanels ? ' active' : ''}`}
                  onClick={() => setCollapsiblePanels(true)}
                >On</button>
              </div>
            </div>
            <div className="settings-row settings-row-disabled">
              <div className="settings-row-label">
                <span>Number separator</span>
                <span className="settings-row-hint">How large numbers are grouped.</span>
              </div>
              <div className="settings-segmented">
                <button className="settings-seg-btn" disabled>Commas</button>
                <button className="settings-seg-btn active" disabled>Decimals</button>
              </div>
            </div>
            <div className="settings-row settings-row-disabled">
              <div className="settings-row-label">
                <span>Decimal precision</span>
                <span className="settings-row-hint">Decimals shown on abbreviated numbers (1.1M, 1.12M, 1.123M, 1.234M).</span>
              </div>
              <select className="settings-select" disabled defaultValue="2">
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
              </select>
            </div>
          </section>
        </div>

        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
