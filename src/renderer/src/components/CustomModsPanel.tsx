import React, { useState, useEffect, useRef, useMemo } from 'react'
import { useBuildStore } from '../store/buildStore'
import { api } from '../api/client'
import { debounce } from '../utils/fn'
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
  // Green/red comes from a LIGHTWEIGHT parse-only endpoint (fast, updates while typing) merged over whatever the
  // last full engine pass reported — so validation feels instant and doesn't wait on the (debounced) recompute.
  const storeStatuses = (useBuildStore(s => s.computedStats.custom_mod_statuses) ?? EMPTY_STATUSES) as CustomModStatus[]

  const [text, setText] = useState(() => customMods.join('\n'))
  const [localStatuses, setLocalStatuses] = useState<CustomModStatus[]>([])
  const taRef = useRef<HTMLTextAreaElement>(null)
  const hlRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<{ x: number; y: number; label: string; ok: boolean } | null>(null)

  // (b) fast green/red via the parse-only endpoint; (a) the heavier full recompute (store push) waits for a longer
  // pause so typing a mod doesn't fire an engine pass per keystroke. Both stable across renders.
  const pending = useRef<string[] | null>(null)   // lines typed but not yet pushed to the store (debounce in flight)
  const validate = useMemo(() => debounce(async (lines: string[]) => {
    if (!lines.length) { setLocalStatuses([]); return }
    try { const { statuses } = await api.validateCustomMods(lines); setLocalStatuses(statuses) } catch { /* keep last */ }
  }, 150), [])
  const pushToStore = useMemo(() => debounce((lines: string[]) => { setCustomMods(lines); pending.current = null }, 350), [setCustomMods])
  // Flush any pending edit immediately (on blur / unmount) so clicking Save or navigating away never drops the
  // last-typed mod while the debounce is still in flight.
  const flush = () => { if (pending.current !== null) { pushToStore.cancel(); setCustomMods(pending.current); pending.current = null } }
  useEffect(() => () => { validate.cancel(); flush() }, [validate, pushToStore])   // eslint-disable-line react-hooks/exhaustive-deps

  // Resync the editor from the store on EXTERNAL change (e.g. opening a build) — but not from our own keystrokes
  // (where the derived lines already equal customMods), so the caret never jumps while typing.
  useEffect(() => {
    const derived = text.split('\n').map(s => s.trim()).filter(Boolean)
    if (JSON.stringify(derived) !== JSON.stringify(customMods)) setText(customMods.join('\n'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customMods])

  // Local (live) validation wins; fall back to the last full-pass statuses for lines not yet re-validated.
  const statusMap: Record<string, CustomModStatus> = {}
  for (const s of storeStatuses) statusMap[s.text] = s
  for (const s of localStatuses) statusMap[s.text] = s
  const lines = text.split('\n')

  const lineClass = (raw: string): string => {
    const t = raw.trim()
    if (!t) return ''
    const st = statusMap[t]
    if (!st) return 'cmods-line-pending'   // typed but not yet resolved by the validate pass
    return st.resolved ? 'cmods-line-ok' : 'cmods-line-bad'
  }

  const onChange = (v: string) => {
    setText(v)
    const derived = v.split('\n').map(s => s.trim()).filter(Boolean)
    pending.current = derived
    validate(derived)      // (b) fast green/red
    pushToStore(derived)   // (a) debounced full recompute
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
          onBlur={flush}
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
