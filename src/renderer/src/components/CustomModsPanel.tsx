import React, { useState, useEffect, useRef } from 'react'
import { useBuildStore } from '../store/buildStore'
import type { CustomModStatus } from '../api/client'

// Stable empty default so the selector never returns a fresh array (which would loop re-renders).
const EMPTY_STATUSES: CustomModStatus[] = []

// Editor metrics — MUST match the .cmods-* CSS (line-height + top padding) so the colored backdrop lines up with
// the textarea text and the hover→line math is correct.
const LINE_H = 18
const PAD_TOP = 8

// Path-of-Building-style custom-modifier editor: a free multi-line text box where each line is one modifier.
// Lines resolve independently (strict per-line) — green if recognized to a stat, red if not. Hovering a line shows
// the stat it resolved to (or "Unrecognized"). The colored backdrop sits behind a transparent-text textarea.
export default function CustomModsPanel() {
  const customMods = useBuildStore(s => s.customMods)
  const setCustomMods = useBuildStore(s => s.setCustomMods)
  const statuses = (useBuildStore(s => s.computedStats.custom_mod_statuses) ?? EMPTY_STATUSES) as CustomModStatus[]

  const [text, setText] = useState(() => customMods.join('\n'))
  const taRef = useRef<HTMLTextAreaElement>(null)
  const hlRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ x: number; y: number; label: string; ok: boolean } | null>(null)

  // Resync the editor from the store on EXTERNAL change (e.g. opening a build) — but not from our own keystrokes
  // (where the derived lines already equal customMods), so the caret never jumps while typing.
  useEffect(() => {
    const derived = text.split('\n').map(s => s.trim()).filter(Boolean)
    if (JSON.stringify(derived) !== JSON.stringify(customMods)) setText(customMods.join('\n'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customMods])

  const statusMap = Object.fromEntries(statuses.map(s => [s.text, s]))
  const lines = text.split('\n')

  const lineClass = (raw: string): string => {
    const t = raw.trim()
    if (!t) return ''
    const st = statusMap[t]
    if (!st) return 'cmods-line-pending'   // typed but not yet resolved by the engine pass
    return st.resolved ? 'cmods-line-ok' : 'cmods-line-bad'
  }

  const onChange = (v: string) => {
    setText(v)
    setCustomMods(v.split('\n').map(s => s.trim()).filter(Boolean))
  }

  const syncScroll = () => {
    if (hlRef.current && taRef.current) {
      hlRef.current.scrollTop = taRef.current.scrollTop
      hlRef.current.scrollLeft = taRef.current.scrollLeft
    }
  }

  const onMove = (e: React.MouseEvent) => {
    const ta = taRef.current
    if (!ta) return
    const rect = ta.getBoundingClientRect()
    const idx = Math.floor((e.clientY - rect.top + ta.scrollTop - PAD_TOP) / LINE_H)
    const t = lines[idx]?.trim()
    if (!t) { setHover(null); return }
    const st = statusMap[t]
    if (!st) { setHover({ x: e.clientX, y: e.clientY, label: 'Resolving…', ok: true }); return }
    setHover({
      x: e.clientX, y: e.clientY,
      label: st.resolved ? (st.stat_display || 'Recognized') : 'Unrecognized',
      ok: st.resolved,
    })
  }

  return (
    <div className="cmods-wrap">
      <div className="cmods-editor">
        <div className="cmods-highlight" ref={hlRef} aria-hidden>
          {lines.map((ln, i) => (
            <div key={i} className={`cmods-line ${lineClass(ln)}`}>{ln === '' ? '​' : ln}</div>
          ))}
        </div>
        <textarea
          ref={taRef}
          className="cmods-textarea"
          value={text}
          spellCheck={false}
          placeholder={'One modifier per line, e.g.\n10% additional attack damage\n+200 to maximum life'}
          onChange={e => onChange(e.target.value)}
          onScroll={syncScroll}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        />
      </div>
      {hover && (
        <div className={`cmods-tip ${hover.ok ? 'cmods-tip-ok' : 'cmods-tip-bad'}`}
          style={{ left: hover.x + 12, top: hover.y + 14 }}>
          {hover.ok ? '✓ ' : '✗ '}{hover.label}
        </div>
      )}
    </div>
  )
}
