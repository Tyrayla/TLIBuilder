import React from 'react'
import { useUiPrefs } from '../../store/uiPrefsStore'

// Plain-language copy for the owner's review. It is not the privacy notice; the owner writes that.
export default function PrivacySection() {
  const on = useUiPrefs((s) => s.shareCompositionStats)
  const set = useUiPrefs((s) => s.setShareCompositionStats)

  return (
    <section className="settings-section">
      <h4 className="settings-section-title">Privacy</h4>
      <div className="settings-row">
        <div className="settings-row-label">
          <span>Anonymous build statistics</span>
          <span className="settings-row-hint">
            When this is on, TLI Builder reports which game items, skills, and mechanics appear in the builds
            you calculate, so the project can decide what to support and verify. A report contains only catalog
            item IDs and the game data version. It has no build code, build name, notes, or custom text, and no
            account, Discord ID, cookie, or device identifier. The service adds reports to daily totals and does
            not keep individual reports. Turn this off and the app stops sending them.
          </span>
        </div>
        <div className="settings-segmented">
          <button className={`settings-seg-btn${!on ? ' active' : ''}`} onClick={() => set(false)}>Off</button>
          <button className={`settings-seg-btn${on ? ' active' : ''}`} onClick={() => set(true)}>On</button>
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span>Guest use</span>
          <span className="settings-row-hint">
            Using TLI Builder without an account creates no account record. The network services that deliver
            the app and its data still process connection details to deliver requests and keep the service secure.
          </span>
        </div>
      </div>
    </section>
  )
}
