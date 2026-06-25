import React, { useState, useCallback } from 'react'
import { useBuildStore } from '../store/buildStore'
import { api } from '../api/client'
import type { CustomModStatus } from '../api/client'

// Stable empty default so the selector below never returns a fresh array (which would loop re-renders).
const EMPTY_STATUSES: CustomModStatus[] = []

// User-entered modifier lines. Self-contained: reads the mods + add/remove actions from the build store and the
// per-mod resolution statuses from the latest computed stats. Lives on the Config screen (was on the old Calcs page).
export default function CustomModsPanel() {
  const customMods = useBuildStore(s => s.customMods)
  const addCustomMod = useBuildStore(s => s.addCustomMod)
  const removeCustomMod = useBuildStore(s => s.removeCustomMod)
  // Default OUTSIDE the selector — selecting `?? []` inside returns a new array each render → infinite loop.
  const statuses = (useBuildStore(s => s.computedStats.custom_mod_statuses) ?? EMPTY_STATUSES) as CustomModStatus[]
  const [inputText, setInputText] = useState('')
  const [preview, setPreview] = useState<{ resolved: boolean; label: string } | null>(null)

  const statusMap = Object.fromEntries(statuses.map(s => [s.text, s]))

  const handlePreview = useCallback(async (text: string) => {
    const t = text.trim()
    if (!t) { setPreview(null); return }
    try {
      const res = await api.resolveMod(t)
      if (res.resolved.length > 0) {
        setPreview({ resolved: true, label: res.resolved.map(r => r.display_name).join(', ') })
      } else {
        setPreview({ resolved: false, label: 'unrecognized' })
      }
    } catch {
      setPreview(null)
    }
  }, [])

  const handleAdd = () => {
    const t = inputText.trim()
    if (!t) return
    addCustomMod(t)
    setInputText('')
    setPreview(null)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAdd()
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        <input
          value={inputText}
          onChange={e => { setInputText(e.target.value); handlePreview(e.target.value) }}
          onKeyDown={handleKeyDown}
          placeholder="e.g. 10% additional attack damage"
          style={{
            flex: 1, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 4, padding: '5px 8px', fontSize: 12, color: '#e0e0e0', outline: 'none',
          }}
        />
        <button
          onClick={handleAdd}
          style={{
            background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 4, padding: '5px 10px', fontSize: 12, color: '#e0e0e0', cursor: 'pointer',
          }}
        >
          Add
        </button>
      </div>

      {preview && inputText.trim() && (
        <div style={{ fontSize: 11, marginBottom: 6, paddingLeft: 2 }}>
          {preview.resolved
            ? <span style={{ color: '#6ddb6d' }}>✓ {preview.label}</span>
            : <span style={{ color: '#ff6b6b' }}>✗ unrecognized</span>}
        </div>
      )}

      {customMods.length === 0 && (
        <div style={{ fontSize: 12, color: '#666', fontStyle: 'italic' }}>No custom mods added.</div>
      )}

      {customMods.map((mod, i) => {
        const st = statusMap[mod]
        return (
          <div
            key={i}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '4px 6px', marginBottom: 3,
              background: 'rgba(255,255,255,0.03)', borderRadius: 4,
              border: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 12, color: '#ccc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {mod}
              </div>
              {st && (
                <div style={{ fontSize: 10, marginTop: 1 }}>
                  {st.resolved
                    ? <span style={{ color: '#6ddb6d' }}>✓ {st.stat_display}</span>
                    : <span style={{ color: '#ff6b6b' }}>✗ unrecognized</span>}
                </div>
              )}
            </div>
            <button
              onClick={() => removeCustomMod(i)}
              style={{
                marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer',
                color: '#777', fontSize: 14, lineHeight: 1, padding: '0 2px', flexShrink: 0,
              }}
              title="Remove"
            >
              ×
            </button>
          </div>
        )
      })}
    </div>
  )
}
