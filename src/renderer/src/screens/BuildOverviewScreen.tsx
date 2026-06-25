import React, { useEffect, useState } from 'react'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs } from '../store/uiPrefsStore'
import type { ConditionDef, CurseConflict } from '../api/client'
import CustomModsPanel from '../components/CustomModsPanel'
import { wornWeaponFlags, type WornWeaponFlags } from '../utils/statsPayload'
import { TARGET_LEVELS, presetTargetConfig, NONPHYS_ARMOR_FACTOR, type TargetLevel } from '../utils/targetPresets'

// Categories whose conditions always show (player-side scenario inputs relevant to any build).
const ALWAYS_SHOW_CATEGORIES = new Set([
  'Blessings', 'Enemy', 'Resources', 'Movement', 'Character', 'Recent', 'Fervor', 'Attributes',
])
// Exceptions inside an always-show category that are instead source-gated (only shown if a mod consumes them).
const REFERENCE_GATED_KEYS = new Set(['mana_consumed_recently', 'life_consumed_recently'])
// Equipment conditions gated on what the player is actually wielding (not on mod references).
const EQUIPMENT_GATE: Record<string, keyof WornWeaponFlags> = {
  holding_shield: 'shield', holding_one_handed: 'oneHanded', holding_two_handed: 'twoHanded', dual_wielding: 'dualWield',
}

// Per-category accent color for the Config panels' left border (falls back to a neutral lavender).
const CATEGORY_ACCENT: Record<string, string> = {
  Buffs: '#7fc97f', Enemy: '#e0726a', 'Hero Trait': '#c0a0ff', Skill: '#f0c070', Combat: '#e8923c',
  Recent: '#9aa0c8', Resources: '#6fc0e0', Blessings: '#9090e0', Movement: '#60c0e8', Fervor: '#c8a050',
  Character: '#e0a050', Equipment: '#8a8aa0', Tangle: '#8888ff', 'Spell Burst': '#c8a0ff', Attributes: '#6fa8e0',
}
const accentFor = (cat: string): string => CATEGORY_ACCENT[cat] ?? '#7a6cc8'

// Config panel: accent left-border + cool-charcoal uppercase header, matching the Stats screen's StatPanel.
// Collapsible only when Settings → Display "Collapsible panels" is on (mirrors the Stats screen). Default expanded.
function ConfigPanel({ title, accent, headerColor, full, children }: {
  title: React.ReactNode; accent: string; headerColor?: string; full?: boolean; children: React.ReactNode
}) {
  const collapsible = useUiPrefs(s => s.collapsiblePanels)
  const [collapsed, setCollapsed] = useState(false)
  const showCollapsed = collapsible && collapsed
  return (
    <div className={`cond-card${full ? ' cond-card--full' : ''}`} style={{ borderLeftColor: accent }}>
      <div className={`cond-card-header${collapsible ? ' cond-card-header--clickable' : ''}`}
        style={headerColor ? { color: headerColor } : undefined}
        onClick={collapsible ? () => setCollapsed(c => !c) : undefined}
        role={collapsible ? 'button' : undefined}>
        <span>{title}</span>
        {collapsible && <span className="cond-card-collapse">{collapsed ? '+' : '−'}</span>}
      </div>
      {!showCollapsed && <div className="cond-card-body">{children}</div>}
    </div>
  )
}

// A single negative-allowing % field for the enemy editor (local string state so "-" / partial typing is smooth).
function EnemyNum({ label, value, onChange, hint }: {
  label: string; value: number; onChange: (v: number) => void; hint?: string
}) {
  const [raw, setRaw] = useState(String(value))
  useEffect(() => { setRaw(String(value)) }, [value])
  const commit = (s: string) => {
    const n = parseFloat(s)
    const v = isNaN(n) ? 0 : n
    onChange(v); setRaw(String(v))
  }
  return (
    <div className="enemy-field">
      <span className="enemy-field-label">{label}</span>
      <div className="enemy-field-input">
        <input className="cond-stack-input" type="text" inputMode="numeric" value={raw}
          onChange={e => setRaw(e.target.value)}
          onBlur={e => commit(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') commit((e.target as HTMLInputElement).value) }} />
        <span className="enemy-field-pct">%</span>
      </div>
      {hint && <span className="enemy-field-hint">{hint}</span>}
    </div>
  )
}

// Always-present calc-target editor. Picking a dummy level loads the preset; the 5 fields are then editable
// (negatives allowed). Armor-vs-Non-Phys (armor×0.6) + Armor-vs-DoT (0%) are derived/fixed, shown as a hint.
function EnemyTargetBox() {
  const tc = useBuildStore(s => s.targetConfig)
  const setTargetConfig = useBuildStore(s => s.setTargetConfig)
  const setField = (k: keyof typeof tc, v: number) => setTargetConfig({ ...tc, [k]: v })
  return (
    <div className="enemy-box">
      <div className="enemy-box-head">
        <span className="enemy-box-title">Enemy / Target</span>
        <select className="enemy-target-select" value={tc.level}
          onChange={e => setTargetConfig(presetTargetConfig(Number(e.target.value) as TargetLevel))}>
          {TARGET_LEVELS.map(l => <option key={l} value={l}>Training Dummy — Lv {l}</option>)}
        </select>
        <span className="enemy-box-note">All boss. Picking a level loads its defaults; edit any field (negatives allowed).</span>
      </div>
      <div className="enemy-fields">
        <EnemyNum label="Armor" value={tc.armor} onChange={v => setField('armor', v)}
          hint={`vs Non-Phys ${Math.round(tc.armor * NONPHYS_ARMOR_FACTOR)}% · vs DoT 0%`} />
        <EnemyNum label="Fire Res" value={tc.fireRes} onChange={v => setField('fireRes', v)} />
        <EnemyNum label="Cold Res" value={tc.coldRes} onChange={v => setField('coldRes', v)} />
        <EnemyNum label="Lightning Res" value={tc.lightningRes} onChange={v => setField('lightningRes', v)} />
        <EnemyNum label="Erosion Res" value={tc.erosionRes} onChange={v => setField('erosionRes', v)} />
      </div>
    </div>
  )
}

export default function BuildOverviewScreen() {
  const conditionsData = useReferenceStore(s => s.conditions)
  const referenceResolved = useReferenceStore(s => s.referenceResolved)
  const conditionsFailed = useReferenceStore(s => s.failedCatalogs.has('conditions'))
  const conditionMaximums = useBuildStore(s => s.computedStats.condition_maximums)
  const clampReport = useBuildStore(s => s.computedStats.clamp_report)
  const conditionState = useBuildStore(s => s.conditionState)
  const setConditionState = useBuildStore(s => s.setConditionState)
  const traitId = useBuildStore(s => s.traitId)
  const gear = useBuildStore(s => s.gear)
  // Condition keys any build mod references (stable ref — only changes when stats recompute, so no render loop).
  const referencedConditions = useBuildStore(s => s.computedStats.referenced_conditions)
  // Show-all reveals every conditional (skill-gated + hero-trait for other/unselected traits). Defaults OFF
  // so the screen stays focused on what's relevant; computed/auto-derived (visible:false) stay hidden always.
  const [showAll, setShowAll] = useState(false)
  const curseConflict = useBuildStore(
    s => (s.computedStats as { curse_conflict?: CurseConflict | null }).curse_conflict) ?? null
  const warnings = useBuildStore(
    s => (s.computedStats as { warnings?: { kind: string; text: string }[] | null }).warnings) ?? null

  // Curse over-limit resolution: pick which curse(s) apply (up to the limit). Selection rides per-curse boolean
  // conditions `curse_sel_<name>` (set here, read by the engine's apply_curses). Hidden unless there's a conflict.
  const curseSelKeys = curseConflict?.active.map(a => a.sel_key) ?? []
  const curseSelected = curseSelKeys.filter(k => conditionState[k] === true)
  const applyCurseSelection = (keys: string[]) => {
    const set = new Set(keys.filter(Boolean))
    const next = { ...conditionState }
    for (const k of curseSelKeys) next[k] = set.has(k)
    setConditionState(next)
  }
  const chooseCurseAt = (i: number, v: string) => {
    const arr = [...curseSelected]
    arr[i] = v
    applyCurseSelection(arr)
  }

  // General CONFLICTS (red) — these block correct calculation until the player resolves them. Curse over-limit
  // is the only one today; future blocking conflicts append here so the banner stays one general surface.
  // (Contrast WARNINGS, which are purely informational and never gate functionality.)
  const conflicts: { title: string; detail: string }[] = []
  if (curseConflict) conflicts.push({
    title: 'Curse conflict',
    detail: `${curseConflict.active.length} curses are active but your curse limit is ${curseConflict.limit} — `
      + 'resolve it in the Curse Conflict panel below (curse damage-taken isn\'t applied until you do).',
  })

  const worn = wornWeaponFlags(gear)
  const referenced = new Set(referencedConditions ?? [])

  // A condition is "active" when the user has it on (boolean true / numeric > 0, honoring its default).
  const isCondActive = (c: ConditionDef): boolean => {
    const v = conditionState[c.key]
    if (c.value_type === 'boolean') return (v ?? c.default_bool) === true
    return (((v as number) ?? c.default_value ?? 0)) > 0
  }

  // What shows in the Config list. Hidden by default unless the build has a SOURCE for it, so the screen only
  // surfaces relevant scenario inputs. visible:false (computed/derived) is never shown. Order of checks:
  //  - Show all → everything; an already-active toggle is never hidden.
  //  - Equipment → gated on the weapon/offhand actually worn.
  //  - Hero-trait conditions (trait_id) → only when THAT trait is selected.
  //  - Always-show categories (Blessings/Enemy/Resources/…) → shown, except consumption keys.
  //  - Everything else (Buffs/Skill/Combat/Tangle/Spell Burst + consumption) → only if a build mod references it.
  const isCondVisible = (c: ConditionDef): boolean => {
    if (c.visible === false) return false
    if (showAll) return true
    if (isCondActive(c)) return true
    if (c.key in EQUIPMENT_GATE) return worn[EQUIPMENT_GATE[c.key]]
    if (c.trait_id) return c.trait_id === traitId
    if (c.category && ALWAYS_SHOW_CATEGORIES.has(c.category) && !REFERENCE_GATED_KEYS.has(c.key)) return true
    return referenced.has(c.key)
  }

  const setBoolean = (key: string, value: boolean) =>
    setConditionState({ ...conditionState, [key]: value })

  const setNumeric = (key: string, value: number) =>
    setConditionState({ ...conditionState, [key]: value })

  const getNumericMax = (cond: ConditionDef): number | null => {
    if (conditionMaximums[cond.key] !== undefined) return conditionMaximums[cond.key]
    if (cond.numeric_max != null) return cond.numeric_max
    if (cond.max_base) return cond.max_base
    return null
  }

  // Active count: user-controlled booleans that are on + numerics > 0 (excludes derived + hidden)
  let activeCondCount = 0
  if (conditionsData) {
    for (const items of Object.values(conditionsData)) {
      for (const cond of items) {
        if (cond.is_derived || cond.visible === false) continue
        const val = conditionState[cond.key]
        if (cond.value_type === 'boolean' && val === true) activeCondCount++
        if (cond.value_type === 'numeric' && (val as number) > 0) activeCondCount++
      }
    }
  }

  const condCategories = conditionsData ? Object.entries(conditionsData) : []
  const loading = !referenceResolved && !conditionsData

  return (
    <div className="screen build-overview">
      <div className="cond-screen-header">
        <span>Config</span>
        {activeCondCount > 0 && <span className="panel-header-badge">{activeCondCount} active</span>}
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#9aa', cursor: 'pointer', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
          <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />
          Show all
        </label>
      </div>

      <EnemyTargetBox />

      {conflicts.length > 0 && (
        <div style={{
          margin: '0 0 10px', padding: '8px 12px', borderRadius: 4,
          background: 'rgba(192,57,43,0.12)', border: '1px solid #c0392b', color: '#e07a6e', fontSize: 11,
        }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>⚠ Conflicts — must resolve</div>
          {conflicts.map((c, i) => (
            <div key={i} style={{ lineHeight: 1.5, color: '#df8d82' }}><strong>{c.title}:</strong> {c.detail}</div>
          ))}
        </div>
      )}

      {warnings && warnings.length > 0 && (
        <div style={{
          margin: '0 0 10px', padding: '8px 12px', borderRadius: 4,
          background: 'rgba(176,138,74,0.12)', border: '1px solid #b08a4a', color: '#d8b45a', fontSize: 11,
        }}>
          <div style={{ fontWeight: 700, marginBottom: warnings.length ? 4 : 0 }}>⚠ Warnings</div>
          {warnings.map((w, i) => (
            <div key={i} style={{ lineHeight: 1.5, color: '#c9a865' }}>• {w.text}</div>
          ))}
        </div>
      )}

      <div className="config-body">
        <div className="config-conditions">
      {loading && <div className="panel-empty">Loading…</div>}
      {referenceResolved && conditionsFailed && (
        <div className="panel-empty" style={{ color: '#ff6b6b' }}>Couldn't load condition data — restart to retry.</div>
      )}

      {!loading && !conditionsFailed && (
        <div className="cond-grid">
          <div className="cond-masonry">
          {curseConflict && (
            <ConfigPanel title="⚠ Curse Conflict" accent="#c0392b" headerColor="#e07a6e">
              <div style={{ fontSize: 10.5, color: '#cf7d72', lineHeight: 1.45, marginBottom: 8 }}>
                Limit {curseConflict.limit}. Select which {curseConflict.limit === 1 ? 'curse applies' : `${curseConflict.limit} curses apply`} (rest suppressed):
              </div>
              {Array.from({ length: curseConflict.limit }).map((_, i) => (
                <select
                  key={i}
                  className="cond-stack-input"
                  style={{ width: '100%', marginBottom: 6 }}
                  value={curseSelected[i] ?? ''}
                  onChange={e => chooseCurseAt(i, e.target.value)}
                >
                  <option value="">— None —</option>
                  {curseConflict.active
                    .filter(a => a.sel_key === curseSelected[i] || !curseSelected.includes(a.sel_key))
                    .map(a => <option key={a.sel_key} value={a.sel_key}>{a.name} ({a.source})</option>)}
                </select>
              ))}
            </ConfigPanel>
          )}
          {condCategories.map(([cat, items]) => {
            const visibleItems = items.filter(isCondVisible)
            if (visibleItems.length === 0) return null
            return (
              <ConfigPanel key={cat} title={cat} accent={accentFor(cat)}>
                  {visibleItems.map(cond => {
                    const isComputed = cond.source === 'computed_stat'
                    if (cond.value_type === 'numeric') {
                      if (isComputed) {
                        const val = (conditionState[cond.key] as number) ?? 0
                        return (
                          <div key={cond.key} className="cond-item cond-item--derived">
                            <span className="cond-label cond-label--derived">{cond.label}</span>
                            <span className="cond-derived-hint">{val}{cond.unit ? ` ${cond.unit}` : ''}</span>
                          </div>
                        )
                      }
                      return <NumericConditionRow
                        key={cond.key}
                        cond={cond}
                        // Unset → the condition's own default (e.g. Character Level 90), not a bare 0.
                        value={(conditionState[cond.key] as number) ?? cond.default_value ?? 0}
                        max={getNumericMax(cond)}
                        clamp={clampReport[cond.key]}
                        onChange={v => setNumeric(cond.key, v)}
                      />
                    }
                    if (cond.is_derived) {
                      // Auto-derived from corresponding stacks condition — read-only indicator
                      const stackKey = cond.key.replace('_active', '_stacks')
                      const isActive = ((conditionState[stackKey] as number) ?? 0) > 0
                      return (
                        <div key={cond.key} className="cond-item cond-item--derived">
                          <span className={`cond-derived-dot ${isActive ? 'cond-derived-dot--on' : ''}`} />
                          <span className="cond-label cond-label--derived">{cond.label}</span>
                          <span className="cond-derived-hint">{isActive ? 'active' : 'inactive'}</span>
                        </div>
                      )
                    }
                    // Regular boolean — user-togglable checkbox
                    return (
                      <label key={cond.key} className="cond-item">
                        <input
                          type="checkbox"
                          className="cond-check"
                          // Unset → the condition's own default (e.g. inside_holy_domain defaults ON), mirroring
                          // the numeric fields' default_value fallback, so a default-ON toggle shows checked.
                          checked={(conditionState[cond.key] ?? cond.default_bool ?? false) === true}
                          onChange={e => setBoolean(cond.key, e.target.checked)}
                        />
                        <span className="cond-label">{cond.label}</span>
                      </label>
                    )
                  })}
              </ConfigPanel>
            )
          })}
          </div>
        </div>
      )}
        </div>

        <aside className="config-custommods">
          <div className="config-custommods-title">Custom Modifiers</div>
          <CustomModsPanel />
        </aside>
      </div>
    </div>
  )
}

interface NumericRowProps {
  cond: ConditionDef
  value: number
  max: number | null
  clamp: { requested: number; applied: number } | undefined
  onChange: (v: number) => void
}

function NumericConditionRow({ cond, value, max, clamp, onChange }: NumericRowProps) {
  const min = cond.numeric_min ?? 0
  // The value an emptied field falls back to: the condition's own default (not a hardcoded 0).
  const def = cond.default_value ?? min
  const [raw, setRaw] = useState(String(value))

  useEffect(() => { setRaw(String(value)) }, [value])

  const commit = (str: string) => {
    // Cleared input → reset to the condition's default value, not the previous value or a hardcoded 0.
    if (str.trim() === '') { onChange(def); setRaw(String(def)); return }
    const n = parseFloat(str)
    if (isNaN(n)) { setRaw(String(value)); return }
    const clamped = max !== null ? Math.min(Math.max(n, min), max) : Math.max(n, min)
    onChange(clamped)
    setRaw(String(clamped))
  }

  return (
    <div className="cond-stack-row">
      <span className="cond-stack-label">{cond.label}</span>
      <div className="cond-stack-controls">
        <input
          type="number"
          className="cond-stack-input"
          value={raw}
          min={min}
          max={max ?? undefined}
          onChange={e => setRaw(e.target.value)}
          onBlur={e => commit(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') commit((e.target as HTMLInputElement).value) }}
        />
        {max !== null && <span className="cond-stack-max">/ {max}</span>}
        {cond.unit && <span style={{ fontSize: 10, color: '#555577', marginLeft: 2 }}>{cond.unit}</span>}
      </div>
      {clamp && (
        <div style={{ fontSize: 10, color: '#ff9800', padding: '2px 12px 4px' }}>
          ⚠ capped at {clamp.applied}
        </div>
      )}
    </div>
  )
}
