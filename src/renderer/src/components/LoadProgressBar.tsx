import React, { useEffect, useState } from 'react'
import { useReferenceStore } from '../store/referenceStore'
import { useBuildStore } from '../store/buildStore'

// Global load-progress pill (bottom-left): fills as the reference catalogs (10) + the pact-spirit
// catalog settle, shows a brief "Loaded" state, then fades out. Gives users a clear signal for
// "everything is fetched and cached" without any screen owning it.
export default function LoadProgressBar() {
  const loadDone = useReferenceStore(s => s.loadDone)
  const loadTotal = useReferenceStore(s => s.loadTotal)
  const spiritsResolved = useBuildStore(s => s.spiritsResolved)

  const total = loadTotal + 1                       // +1: pact spirits (App-level fetch)
  const done = Math.min(loadDone + (spiritsResolved ? 1 : 0), total)
  const complete = loadTotal > 0 && done >= total

  // Keep the pill mounted briefly after completion so the full bar + "Loaded" is visible, then drop it.
  const [gone, setGone] = useState(false)
  useEffect(() => {
    if (!complete) { setGone(false); return }
    const t = setTimeout(() => setGone(true), 1600)
    return () => clearTimeout(t)
  }, [complete])

  if (loadTotal === 0 || gone) return null

  return (
    <div className={`load-progress-pill${complete ? ' load-progress-pill--done' : ''}`} role="status" aria-live="polite">
      <div className="load-progress-track">
        <div className="load-progress-fill" style={{ width: `${Math.round((done / total) * 100)}%` }} />
      </div>
      <span className="load-progress-label">{complete ? 'Loaded' : `Loading data… ${done}/${total}`}</span>
    </div>
  )
}
