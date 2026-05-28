import React, { useState, useCallback } from 'react'
import { useBuildStore } from '../store/buildStore'
import { api } from '../api/client'
import type { OffenseResult, DefenseResult, CustomModStatus } from '../api/client'

function NyiTag() {
  return <span className="nyi-tag">NYI</span>
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 700, color: '#888', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8, marginTop: 4 }}>
      {title}
    </div>
  )
}

function Row({ label, value, unit = '', nyi = false }: { label: string; value?: string | number; unit?: string; nyi?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0', fontSize: 13, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span style={{ color: '#aaa' }}>{label}{nyi && <NyiTag />}</span>
      <span style={{ color: '#e0e0e0', fontVariantNumeric: 'tabular-nums' }}>
        {value !== undefined ? `${value}${unit}` : '—'}
      </span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <SectionHeader title={title} />
      {children}
    </div>
  )
}

function CustomModsPanel({ statuses }: { statuses: CustomModStatus[] }) {
  const customMods = useBuildStore(s => s.customMods)
  const addCustomMod = useBuildStore(s => s.addCustomMod)
  const removeCustomMod = useBuildStore(s => s.removeCustomMod)
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
    <div style={{ marginBottom: 24 }}>
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
        <div style={{ fontSize: 12, color: '#444', fontStyle: 'italic' }}>No custom mods added.</div>
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
                color: '#555', fontSize: 14, lineHeight: 1, padding: '0 2px', flexShrink: 0,
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

function OffensePanel({ offense }: { offense: OffenseResult }) {
  if (!offense.supported) {
    return (
      <div>
        <div style={{ color: '#e0e0e0', fontSize: 13, marginBottom: 4 }}>{offense.skill_name}</div>
        <div style={{ color: '#ff6b6b', fontSize: 12 }}>Offense calculation not yet supported for this skill.</div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ color: '#e0e0e0', fontWeight: 600 }}>{offense.skill_name}</span>
        <span style={{ color: '#aaa', fontSize: 12 }}>Level {offense.effective_level}</span>
      </div>

      {offense.hit_forms.map(form => (
        <div
          key={form.name}
          style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 6, padding: '10px 12px', marginBottom: 10 }}
        >
          <div style={{ fontWeight: 600, color: '#d0d0d0', marginBottom: 6 }}>
            {form.name}
            <span style={{ fontWeight: 400, fontSize: 12, color: '#888', marginLeft: 8 }}>
              {form.effectiveness_pct.toFixed(1)}% · {(form.proc_chance * 100).toFixed(0)}% chance
            </span>
          </div>
          {Object.entries(form.damage_by_type).map(([dtype, avg]) => (
            <Row key={dtype} label={dtype.charAt(0).toUpperCase() + dtype.slice(1)} value={(avg as number).toFixed(1)} unit=" avg" />
          ))}
          <Row label="Avg Hit (pre-crit)" value={form.avg_hit_pre_crit.toFixed(1)} />
          <Row label="Avg Hit (with crit)" value={form.avg_hit_with_crit.toFixed(1)} />
          <Row label="DPS vs Target Dummy" value={form.dps_vs_target.toFixed(0)} />
        </div>
      ))}

      <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 8 }}>
        {offense.steep_strike_chance > 0 && (
          <Row label="Steep Strike Chance" value={(offense.steep_strike_chance * 100).toFixed(1)} unit="%" />
        )}
        <Row label="Crit Chance" value={(offense.crit_chance * 100).toFixed(1)} unit="%" />
        <Row label="Crit Multiplier" value={(offense.crit_multiplier * 100).toFixed(0)} unit="%" />
        <Row label="Attacks per Second" value={offense.attacks_per_second.toFixed(2)} />
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0 4px', marginTop: 4 }}>
          <span style={{ fontWeight: 700, color: '#e0e0e0' }}>DPS vs Target Dummy</span>
          <span style={{ fontWeight: 700, fontSize: 16, color: '#f0c070', fontVariantNumeric: 'tabular-nums' }}>
            {offense.total_dps_vs_target.toFixed(0)}
          </span>
        </div>
      </div>

      {offense.nyi.length > 0 && (
        <div style={{ marginTop: 10, fontSize: 11, color: '#555' }}>
          <div style={{ marginBottom: 4, color: '#777' }}>Not yet included:</div>
          {offense.nyi.map(item => <div key={item} style={{ marginBottom: 2 }}>• {item}</div>)}
        </div>
      )}
    </div>
  )
}

export default function CalcsScreen() {
  const computedStats = useBuildStore(s => s.computedStats)
  const offense = (computedStats.offense ?? null) as OffenseResult | null
  const defense = (computedStats.defense ?? null) as DefenseResult | null
  const customModStatuses = (computedStats.custom_mod_statuses ?? []) as CustomModStatus[]

  return (
    <div style={{ padding: '20px 24px', maxWidth: 680, color: '#e0e0e0', overflowY: 'auto', height: '100%', boxSizing: 'border-box' }}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 20, color: '#e0e0e0' }}>Calcs</div>

      <Section title="Custom Mods">
        <CustomModsPanel statuses={customModStatuses} />
      </Section>

      <Section title="Offense">
        {!offense ? (
          <div style={{ color: '#555', fontSize: 13 }}>No skill selected.</div>
        ) : (
          <OffensePanel offense={offense} />
        )}
      </Section>

      <Section title="Defense">
        {!defense ? (
          <div style={{ color: '#555', fontSize: 13 }}>No data.</div>
        ) : (
          <div>
            <Row label="Max Life" value={defense.max_life.toFixed(0)} />
            <Row label="Max Mana" value={defense.max_mana.toFixed(0)} />
            <Row label="Max Energy Shield" value={defense.max_energy_shield.toFixed(0)} />
            <Row label="Armor" value={defense.armor.toFixed(0)} />
            <Row label="Evasion" value={defense.evasion.toFixed(0)} />
            <Row label="Fire Resistance" value={defense.fire_resist.toFixed(0)} unit="%" nyi />
            <Row label="Cold Resistance" value={defense.cold_resist.toFixed(0)} unit="%" nyi />
            <Row label="Lightning Resistance" value={defense.lightning_resist.toFixed(0)} unit="%" nyi />
            <Row label="Erosion Resistance" value={defense.erosion_resist.toFixed(0)} unit="%" nyi />
            {defense.nyi.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 11, color: '#555' }}>
                <div style={{ marginBottom: 4, color: '#777' }}>Not yet included:</div>
                {defense.nyi.map(item => <div key={item} style={{ marginBottom: 2 }}>• {item}</div>)}
              </div>
            )}
          </div>
        )}
      </Section>

      <Section title="Utility">
        <div style={{ color: '#555', fontSize: 12 }}>Blessings, movement speed, buff uptime — coming soon.</div>
      </Section>
    </div>
  )
}
