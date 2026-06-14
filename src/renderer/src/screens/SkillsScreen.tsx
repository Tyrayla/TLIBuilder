import React, { useEffect, useMemo, useState } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import {
  api,
  EquippedSkill,
  EquippedSupportSkill,
  SkillItem,
  isActiveSkillItem,
  isPassiveSkillItem,
  isSupportCompatible,
  getSupportEnergyCost,
  getMaxEnergy,
} from '../api/client'
import { useBuildStore } from '../store/buildStore'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { TooltipShell } from '../components/tooltip/TooltipShell'
import { SkillTooltipBody } from '../components/tooltip/bodies/SkillTooltipBody'
import { DamageDeltaBand } from '../components/tooltip/DamageDeltaBand'
import { useDamageDelta, useDamageDeltaList, withSupport, type DeltaRequest, type DamageDelta } from '../components/tooltip/useDamageDelta'
import { buildEngineStatsPayload, type BuildState } from '../utils/statsPayload'
import { characterLevelFrom } from '../utils/conditions'
import { modeledRolledLines } from '../utils/supportRolls'

// djb2 string hash → short base36. Used to fingerprint the build slice the support-pick deltas depend on.
function hashStr(str: string): string {
  let h = 5381
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0
  return (h >>> 0).toString(36)
}

// Cursor-anchored skill / support hover tooltip via the shared primitive (informational —
// no contributions band). Render-prop hands triggerProps to the hovered element.
function SkillHoverTooltip({ name, descLines, children, deltaReq = null }: {
  name: string
  descLines: string[]
  children: (triggerProps: Record<string, unknown>) => React.ReactNode
  deltaReq?: DeltaRequest | null   // when set, a DPS-delta band is computed on hover (e.g. equip preview)
}) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'top' })
  const delta = useDamageDelta(deltaReq, tip.open && !!deltaReq)
  return (
    <>
      {children(tip.triggerProps)}
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--skill" {...tip.floatingProps}>
            <TooltipShell title={name} delta={deltaReq ? delta : undefined}>
              <SkillTooltipBody lines={getAdvancedLines(cleanDescLines(descLines))} />
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

const ACTIVE_SLOTS  = [1, 2, 3, 4, 5]
const PASSIVE_SLOTS = [6, 7, 8, 9]
const SUPPORT_COUNT = 5

const SLOT_LABEL: Record<number, string> = {
  1: 'Main Skill', 2: 'Skill 2', 3: 'Skill 3', 4: 'Skill 4', 5: 'Skill 5',
  6: 'Passive 1',  7: 'Passive 2', 8: 'Passive 3', 9: 'Passive 4',
}

const TAG_CLASS: Record<string, string> = {
  'Fire':             'tag-fire',
  'Cold':             'tag-cold',
  'Lightning':        'tag-lightning',
  'Erosion':          'tag-erosion',
  'Physical':         'tag-physical',
  'Attack':           'tag-attack',
  'Melee':            'tag-melee',
  'Ranged':           'tag-ranged',
  'Projectile':       'tag-ranged',
  'Beam':             'tag-beam',
  'Spell':            'tag-spell',
  'Warcry':           'tag-warcry',
  'Aura':             'tag-passive',
  'Spirit Magus':     'tag-passive',
  'Focus':            'tag-passive',
  'Summon':           'tag-summon',
  'Synthetic Troop':  'tag-summon',
  'Minion':           'tag-summon',
  'Activation Medium':'tag-activation',
  'Support':          'tag-support',
  'Strength':         'tag-strength',
  'Intelligence':     'tag-intel',
  'Dexterity':        'tag-dex',
  'Restoration':      'tag-restoration',
  'Demolisher':       'tag-demolisher',
  'Mobility':         'tag-mobility',
}

function tagClass(tag: string): string {
  const modifier = TAG_CLASS[tag]
  return modifier ? `skill-tag-pill ${modifier}` : 'skill-tag-pill'
}

function getAdvancedLines(lines: string[]): string[] {
  const idx = lines.findIndex((l, i) => i > 0 && l.trim().endsWith(':') && l.trim().length < 50)
  return idx >= 0 ? lines.slice(idx) : lines
}

// Tidy a support description for tooltips: strip the per-level scaling annotations "(Lv1:2)(Lv2:…)"
// that clutter standard supports, collapse a phrase that the source repeats back-to-back, and drop
// duplicate lines.
function cleanDescLines(lines: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of lines) {
    let s = (raw ?? '').replace(/\(Lv\.?\s*\d+\s*:[^)]*\)/gi, '').replace(/\s{2,}/g, ' ').trim()
    // Collapse an immediately-repeated half ("A A" → "A"), which the game data does for some supports.
    const half = Math.floor(s.length / 2)
    if (half > 12 && s.slice(0, half).trim() === s.slice(half).trim()) s = s.slice(0, half).trim()
    if (!s || seen.has(s)) continue
    seen.add(s)
    out.push(s)
  }
  return out
}

function isPassiveSlot(slot: number) { return slot > 5 }

const TIERED_SUPPORT_TYPES = new Set(['activation_medium_skill', 'magnificent_support_skill', 'noble_support_skill'])

function supportLevelRange(skill_type: string | undefined): { min: number; max: number; default: number } {
  return TIERED_SUPPORT_TYPES.has(skill_type ?? '')
    ? { min: 0, max: 2, default: 1 }
    : { min: 1, max: 40, default: 20 }
}

// Tiered supports (Noble / Magnificent / Activation Medium) are levelled by "Tier" in-game; basic
// support skills use "Level".
function supportLevelLabel(skill_type: string | undefined): string {
  return TIERED_SUPPORT_TYPES.has(skill_type ?? '') ? 'Tier' : 'Level'
}

// Only Noble/Magnificent supports carry the rank (1-5) that scales their universal
// "+% additional damage for the supported skill" line. Other support types have no rank.
const RANKED_SUPPORT_TYPES = new Set(['magnificent_support_skill', 'noble_support_skill'])
const DEFAULT_SUPPORT_RANK = 1  // 0% universal — the conservative default; the user raises it to match
function isRankedSupport(skill_type: string | undefined): boolean {
  return RANKED_SUPPORT_TYPES.has(skill_type ?? '')
}
// Universal "+% additional damage for the supported skill" by rank (mirror support_resolver._RANK_TABLE).
const RANK_TABLE = [0, 0.04, 0.08, 0.14, 0.20]
function rankAdditional(rank: number | undefined): number {
  return RANK_TABLE[Math.max(1, Math.min(5, rank ?? 1)) - 1]
}

// Compact inline DPS-delta shown beside a support's name (gain/loss %). Returns null when there's
// nothing useful to show (no value yet / not modeled).
function deltaInline(d: DamageDelta | undefined): React.ReactNode {
  if (!d) return null
  if (d.state === 'loading') return <span style={{ fontSize: 11, opacity: 0.4 }}>…</span>
  if (d.state === 'value' && d.direction !== 'neutral') {
    return (
      <span style={{ fontSize: 11, fontWeight: 600, color: d.direction === 'gain' ? '#5fc16a' : '#e06c6c' }}>
        {d.percent > 0 ? '+' : ''}{d.percent.toFixed(1)}%
      </span>
    )
  }
  return null
}

// Build a fresh EquippedSupportSkill from a catalog item (default rank/tier + tier-mid rolls). Shared
// by assignSupport and the catalog DPS-delta preview transform.
function makeSupport(item: SkillItem, supportIndex: number): EquippedSupportSkill {
  const range = supportLevelRange(item.skill_type)
  const rolls = modeledRolledLines(item, range.default)
  return {
    support_index: supportIndex,
    item_id: item.item_id,
    name: item.name,
    skill_type: item.skill_type ?? 'support_skill',
    level: range.default,
    skill_tags: item.skill_tags,
    description_lines: item.description_lines,
    ...(isRankedSupport(item.skill_type) ? { rank: DEFAULT_SUPPORT_RANK } : {}),
    ...(rolls.length ? { specific_rolls: Object.fromEntries(rolls.map(r => [r.identity, r.mid])) } : {}),
  }
}

interface Props {
  onBack: () => void
}

export default function SkillsScreen(_props: Props) {
  const equippedSkills = useBuildStore(s => s.skills)
  const onSkillsChange = useBuildStore(s => s.setSkills)
  const gear = useBuildStore(s => s.gear)
  // Character level now comes from the `level` condition (default 90); the old level control is gone.
  const conditionState = useBuildStore(s => s.conditionState)
  const characterLevel = characterLevelFrom(conditionState)
  const hasPrism = useBuildStore(s => s.hasPrism)
  const onHasPrismChange = useBuildStore(s => s.setHasPrism)
  const [allItems, setAllItems] = useState<SkillItem[]>([])
  const [focusedSlot, setFocusedSlot] = useState<number | null>(null)
  const [centerView, setCenterView] = useState<'catalog' | 'detail'>('catalog')
  const [focusedSupportIdx, setFocusedSupportIdx] = useState<number | null>(null)
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [selectedSupportId, setSelectedSupportId] = useState<string | null>(null)
  const [pendingLevel, setPendingLevel] = useState(20)
  const [search, setSearch] = useState('')
  const [supportSearch, setSupportSearch] = useState('')

  useEffect(() => {
    api.getSkills().then(r => setAllItems(r.skills))
  }, [])

  const getEquipped = (slot: number) => equippedSkills.find(s => s.slot === slot) ?? null
  const getSupport = (skill: EquippedSkill, idx: number) =>
    (skill.supports ?? []).find(s => s.support_index === idx) ?? null

  const focusedEquipped = focusedSlot !== null ? getEquipped(focusedSlot) : null

  // What you'd LOSE by unequipping the focused support (slot-1 only). step = slot emptied, base = current,
  // so the delta is the negative drop and the % is relative to current DPS (how much of your damage this
  // support accounts for). Recomputes live as its rank/tier/roll change.
  const focusedEquippedSupport = (focusedSlot === 1 && focusedSupportIdx !== null && focusedEquipped)
    ? getSupport(focusedEquipped, focusedSupportIdx) : null
  const equippedSupportDelta = useDamageDelta(
    focusedEquippedSupport && focusedSupportIdx !== null
      ? { key: `support-lose:${focusedSupportIdx}:${focusedEquippedSupport.item_id}`,
          step: s => withSupport(s, focusedSupportIdx, null) }
      : null,
    !!focusedEquippedSupport,
  )

  // ── catalog lists ──────────────────────────────────────────────────────────
  const skillCatalogItems = useMemo(() => {
    if (focusedSlot === null) return []
    const base = isPassiveSlot(focusedSlot)
      ? allItems.filter(isPassiveSkillItem)
      : allItems.filter(isActiveSkillItem)
    if (!search.trim()) return base
    const q = search.toLowerCase()
    return base.filter(s =>
      s.name.toLowerCase().includes(q) ||
      s.skill_tags.some(t => t.toLowerCase().includes(q)) ||
      s.description_lines.some(l => l.toLowerCase().includes(q))
    )
  }, [allItems, focusedSlot, search])

  const supportCatalogItems = useMemo(() => {
    if (focusedSlot === null || focusedSupportIdx === null || !focusedEquipped) return []
    const passive = isPassiveSlot(focusedSlot)
    const base = allItems.filter(s => isSupportCompatible(s, focusedEquipped, passive, focusedSupportIdx))
    if (!supportSearch.trim()) return base
    const q = supportSearch.toLowerCase()
    return base.filter(s =>
      s.name.toLowerCase().includes(q) ||
      s.skill_tags.some(t => t.toLowerCase().includes(q)) ||
      s.description_lines.some(l => l.toLowerCase().includes(q))
    )
  }, [allItems, focusedSlot, focusedSupportIdx, focusedEquipped, equippedSkills, supportSearch])

  // Baseline signature FROZEN when the support panel opens (deps = focused slot/support only, NOT
  // buildVersion), capturing the current build incl. the equipped support at its open-time rolls. So
  // each pick-delta is the swap result vs the CURRENT support, computed once on open and cached — tweaking
  // the equipped support's roll/rank/tier afterward doesn't change or recompute the catalog numbers.
  const pickBaseSig = useMemo(() => {
    if (focusedSlot !== 1 || focusedSupportIdx === null) return ''
    return hashStr(JSON.stringify(buildEngineStatsPayload(useBuildStore.getState() as unknown as BuildState)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedSlot, focusedSupportIdx])

  // Per-catalog-support DPS swap-delta (slot-1 only) vs the current support, used to label + sort the
  // list. base omitted → current build (only the focused support index is swapped, other slots untouched).
  const supportPickReqs = useMemo<DeltaRequest[]>(() =>
    (focusedSlot === 1 && focusedSupportIdx !== null)
      ? supportCatalogItems.map(item => ({
          key: `support-pick:${item.item_id}:${focusedSupportIdx}:${pickBaseSig}`,
          step: (s) => withSupport(s, focusedSupportIdx, makeSupport(item, focusedSupportIdx)),
          stable: true,
        }))
      : [],
    [supportCatalogItems, focusedSlot, focusedSupportIdx, pickBaseSig])
  const supportPickDeltas = useDamageDeltaList(supportPickReqs.length ? supportPickReqs : null, supportPickReqs.length > 0)
  const supportDeltaById = useMemo(() => {
    const m: Record<string, DamageDelta> = {}
    supportCatalogItems.forEach((it, i) => { if (supportPickDeltas[i]) m[it.item_id] = supportPickDeltas[i] })
    return m
  }, [supportCatalogItems, supportPickDeltas])
  // Sort by contribution (gain desc); unresolved/nyi sink, preserving original order among equals.
  const sortedSupportCatalog = useMemo(() => {
    const score = (i: number) => {
      const d = supportPickDeltas[i]
      return d && d.state === 'value' ? d.absolute : Number.NEGATIVE_INFINITY
    }
    return supportCatalogItems.map((it, i) => ({ it, i }))
      .sort((a, b) => score(b.i) - score(a.i))
      .map(x => x.it)
  }, [supportCatalogItems, supportPickDeltas])

  const selectedSkillItem  = allItems.find(i => i.item_id === selectedSkillId)  ?? null
  const selectedSupportItem = allItems.find(i => i.item_id === selectedSupportId) ?? null

  // ── energy ─────────────────────────────────────────────────────────────────
  const totalEnergyCost = equippedSkills.reduce((total, sk) =>
    total + (sk.supports ?? []).reduce((s, sup) =>
      s + getSupportEnergyCost(isPassiveSlot(sk.slot), sup.support_index), 0), 0)
  const maxEnergy = getMaxEnergy(characterLevel, gear, hasPrism)
  const energyOver = totalEnergyCost > maxEnergy

  // ── slot actions ───────────────────────────────────────────────────────────
  const selectSkillSlot = (slot: number) => {
    setFocusedSlot(slot)
    setFocusedSupportIdx(null)
    setSelectedSupportId(null)
    setSupportSearch('')
    const eq = getEquipped(slot)
    if (eq) {
      setCenterView('detail')
      setSelectedSkillId(eq.item_id)
      setPendingLevel(eq.level)
    } else {
      setCenterView('catalog')
      setSelectedSkillId(null)
      setPendingLevel(20)
    }
    setSearch('')
  }

  const selectSupportSlot = (idx: number) => {
    setFocusedSupportIdx(idx)
    setSelectedSupportId(null)
    setSupportSearch('')
  }

  // ── assign / remove ────────────────────────────────────────────────────────
  const assignSkill = () => {
    if (!selectedSkillItem || focusedSlot === null) return
    const newSkill: EquippedSkill = {
      slot: focusedSlot,
      item_id: selectedSkillItem.item_id,
      name: selectedSkillItem.name,
      level: pendingLevel,
      skill_tags: selectedSkillItem.skill_tags,
      description_lines: selectedSkillItem.description_lines,
      supports: focusedEquipped?.supports ?? [],
    }
    onSkillsChange([...equippedSkills.filter(s => s.slot !== focusedSlot), newSkill])
    setCenterView('detail')
    setSelectedSkillId(selectedSkillItem.item_id)
  }

  // Commit an equipped skill's level immediately (no Set button — any change auto-updates).
  const setEquippedLevel = (newLevel: number) => {
    if (!focusedEquipped || focusedSlot === null) return
    const clamped = Math.max(1, Math.min(40, newLevel))
    onSkillsChange(equippedSkills.map(s =>
      s.slot === focusedSlot ? { ...s, level: clamped } : s
    ))
  }

  const removeSkill = (slot: number) => {
    onSkillsChange(equippedSkills.filter(s => s.slot !== slot))
    if (focusedSlot === slot) {
      setCenterView('catalog')
      setSelectedSkillId(null)
      setFocusedSupportIdx(null)
      setSelectedSupportId(null)
    }
  }

  // Enable/disable a skill — disabled skills (and their supports + sourced buffs/debuffs) drop out of the
  // calc without losing the setup. Persisted in the build (rides inside the skills array).
  const toggleSkillEnabled = (slot: number) => {
    onSkillsChange(equippedSkills.map(s =>
      s.slot === slot ? { ...s, enabled: s.enabled === false } : s
    ))
  }

  // Enable/disable a single support on the focused skill.
  const toggleSupportEnabled = (supportIdx: number) => {
    if (focusedSlot === null) return
    onSkillsChange(equippedSkills.map(s =>
      s.slot === focusedSlot
        ? { ...s, supports: s.supports.map(sup =>
              sup.support_index === supportIdx ? { ...sup, enabled: sup.enabled === false } : sup
            )}
        : s
    ))
  }

  const assignSupport = () => {
    if (!selectedSupportItem || focusedSlot === null || focusedSupportIdx === null) return
    const parent = focusedEquipped
    if (!parent) return
    const newSupport = makeSupport(selectedSupportItem, focusedSupportIdx)
    const updated: EquippedSkill = {
      ...parent,
      supports: [
        ...(parent.supports ?? []).filter(s => s.support_index !== focusedSupportIdx),
        newSupport,
      ],
    }
    onSkillsChange(equippedSkills.map(s => s.slot === focusedSlot ? updated : s))
    setFocusedSupportIdx(null)
    setSelectedSupportId(null)
    setSupportSearch('')
  }

  const removeSupport = (supportIdx: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (focusedSlot === null || !focusedEquipped) return
    const updated: EquippedSkill = {
      ...focusedEquipped,
      supports: (focusedEquipped.supports ?? []).filter(s => s.support_index !== supportIdx),
    }
    onSkillsChange(equippedSkills.map(s => s.slot === focusedSlot ? updated : s))
    if (focusedSupportIdx === supportIdx) {
      setFocusedSupportIdx(null)
      setSelectedSupportId(null)
    }
  }

  // ── helpers ────────────────────────────────────────────────────────────────
  const isSubHeader = (line: string) => line.trim().endsWith(':') && line.length < 40

  // ── render helpers ─────────────────────────────────────────────────────────
  const renderSlotGroup = (slots: number[], label: string) => (
    <div className="skill-slot-group">
      <div className="skill-slots-section-label">{label}</div>
      {slots.map(slot => {
        const eq = getEquipped(slot)
        const isActive = focusedSlot === slot
        return (
          <div
            key={slot}
            className={`skill-slot-row${eq ? ' occupied' : ''}${isActive ? ' active' : ''}`}
            onClick={() => selectSkillSlot(slot)}
          >
            <div className="skill-slot-info">
              <span className="skill-slot-label">{SLOT_LABEL[slot]}</span>
              {eq
                ? <span className="skill-slot-skill-name">{eq.name}</span>
                : <span className="skill-slot-empty">Empty</span>}
            </div>
            {eq && (
              <div className="skill-slot-right">
                <span className="skill-slot-level-badge">Lv.{eq.level}</span>
                <button
                  className="skill-slot-remove"
                  onClick={e => { e.stopPropagation(); removeSkill(slot) }}
                >×</button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )

  const renderCenterPanel = () => {
    if (focusedSlot === null) {
      return (
        <div className="skill-center-empty">
          Select a skill slot to begin
        </div>
      )
    }

    if (centerView === 'catalog') {
      const isPassive = isPassiveSlot(focusedSlot)
      return (
        <>
          <div className="skill-center-catalog-header">
            <span className="skill-center-catalog-title">
              Choose {isPassive ? 'Passive' : 'Active'} Skill — {SLOT_LABEL[focusedSlot]}
            </span>
            {focusedEquipped && (
              <button className="btn btn-secondary btn-sm" onClick={() => setCenterView('detail')}>
                Cancel
              </button>
            )}
          </div>
          <div className="skill-search-bar">
            <input
              className="skill-search-input"
              placeholder="Search by name, tag, or effect…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && <button className="skill-search-clear" onClick={() => setSearch('')}>×</button>}
          </div>
          <div className="skill-catalog-list">
            {skillCatalogItems.length === 0 && (
              <div className="skill-catalog-empty">No skills match your search</div>
            )}
            {skillCatalogItems.map(item => (
              <SkillHoverTooltip key={item.item_id} name={item.name} descLines={item.description_lines}>
                {tp => (
                  <div
                    {...tp}
                    className={`skill-catalog-item${selectedSkillId === item.item_id ? ' selected' : ''}`}
                    onClick={() => {
                      setSelectedSkillId(item.item_id)
                      if (focusedEquipped?.item_id !== item.item_id) setPendingLevel(20)
                      else setPendingLevel(focusedEquipped.level)
                    }}
                  >
                    <span className="skill-catalog-name">{item.name}</span>
                    <div className="skill-catalog-tags">
                      {item.skill_tags.map(t => <span key={t} className={tagClass(t)}>{t}</span>)}
                    </div>
                  </div>
                )}
              </SkillHoverTooltip>
            ))}
          </div>
          {selectedSkillItem && (
            <div className="skill-center-catalog-footer">
              <div className="skill-level-row">
                <span className="skill-level-label">Level</span>
                <div className="skill-level-controls">
                  <button className="skill-level-btn" onClick={() => setPendingLevel(l => Math.max(1, l - 1))}>−</button>
                  <input
                    type="number" className="skill-level-input" min={1} max={40} value={pendingLevel}
                    onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v)) setPendingLevel(Math.max(1, Math.min(40, v))) }}
                  />
                  <button className="skill-level-btn" onClick={() => setPendingLevel(l => Math.min(40, l + 1))}>+</button>
                </div>
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }} onClick={assignSkill}>
                Assign {selectedSkillItem.name} to {SLOT_LABEL[focusedSlot]}
              </button>
            </div>
          )}
        </>
      )
    }

    // detail view
    if (!focusedEquipped) {
      setCenterView('catalog')
      return null
    }

    const isPassive = isPassiveSlot(focusedSlot)
    return (
      <>
        <div className="skill-detail-header">
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
            <SkillHoverTooltip name={focusedEquipped.name} descLines={focusedEquipped.description_lines}>
              {tp => (
                <div {...tp} style={{ cursor: 'default', flex: 1, minWidth: 0 }}>
                  <div className="skill-detail-name">{focusedEquipped.name}</div>
                  <div className="skill-detail-tags">
                    {focusedEquipped.skill_tags.map(t => <span key={t} className={tagClass(t)}>{t}</span>)}
                  </div>
                </div>
              )}
            </SkillHoverTooltip>
            <button
              className={`btn btn-sm ${focusedEquipped.enabled === false ? 'btn-danger' : 'btn-success'}`}
              title="Enable/disable this skill (and its supports) in the calculation"
              onClick={() => toggleSkillEnabled(focusedSlot)}
            >{focusedEquipped.enabled === false ? 'Disabled' : 'Enabled'}</button>
            <button className="btn btn-secondary btn-sm" onClick={() => { setCenterView('catalog'); setSearch('') }}>Change</button>
            <button className="btn btn-danger btn-sm" onClick={() => removeSkill(focusedSlot)}>Remove</button>
          </div>
          <div className="skill-level-row" style={{ marginTop: 0, alignItems: 'center' }}>
            <span className="skill-level-label">Level</span>
            <div className="skill-level-controls">
              <button className="skill-level-btn" onClick={() => setEquippedLevel(focusedEquipped.level - 1)}>−</button>
              <input
                type="number" className="skill-level-input" min={1} max={40} value={focusedEquipped.level}
                onChange={e => setEquippedLevel(Number(e.target.value) || 1)}
              />
              <button className="skill-level-btn" onClick={() => setEquippedLevel(focusedEquipped.level + 1)}>+</button>
            </div>
          </div>
        </div>
        <div className="skill-panel-divider" />

        <div className="skill-support-slots-section">
          <div className="skill-support-slots-label">Support Skills</div>
          {Array.from({ length: SUPPORT_COUNT }, (_, i) => i + 1).map(idx => {
            const sup = getSupport(focusedEquipped, idx)
            const cost = getSupportEnergyCost(isPassive, idx)
            const isActiveSup = focusedSupportIdx === idx
            const supItem = sup ? allItems.find(i => i.item_id === sup.item_id) : null
            const renderRow = (tp: Record<string, unknown> | null) => (
              <div
                key={idx}
                {...(tp ?? {})}
                className={`skill-support-slot-row${isActiveSup ? ' active' : ''}${sup ? ' occupied' : ''}`}
                onClick={() => selectSupportSlot(idx)}
              >
                {sup ? (
                  <input
                    type="checkbox"
                    className="skill-support-toggle"
                    checked={sup.enabled !== false}
                    title={sup.enabled === false ? 'Disabled — click to enable' : 'Enabled — click to disable'}
                    onClick={e => e.stopPropagation()}
                    onChange={e => { e.stopPropagation(); toggleSupportEnabled(idx) }}
                  />
                ) : <span className="skill-support-toggle-spacer" />}
                <span className={`skill-support-cost-badge${sup ? '' : ' dim'}`}>{cost}</span>
                <span className="skill-support-slot-num">{idx}</span>
                {sup ? (
                  <>
                    <span className="skill-support-slot-name"
                          style={sup.enabled === false ? { opacity: 0.45, textDecoration: 'line-through' } : undefined}>
                      {sup.name}{sup.enabled === false ? ' (off)' : ''}
                    </span>
                    <button className="skill-slot-remove" onClick={e => removeSupport(idx, e)}>×</button>
                  </>
                ) : (
                  <span className="skill-support-slot-empty">Empty — click to add</span>
                )}
              </div>
            )
            return supItem
              ? <SkillHoverTooltip key={idx} name={supItem.name} descLines={supItem.description_lines}>{tp => renderRow(tp)}</SkillHoverTooltip>
              : renderRow(null)
          })}
        </div>

      </>
    )
  }

  const renderSupportPanel = () => {
    if (focusedSupportIdx === null || !focusedEquipped || focusedSlot === null) {
      return (
        <div className="skill-detail-empty">
          {focusedEquipped ? 'Select a support slot to manage it' : 'Select a skill first'}
        </div>
      )
    }

    const isPassive = isPassiveSlot(focusedSlot)
    const existingSupport = getSupport(focusedEquipped, focusedSupportIdx)
    const cost = getSupportEnergyCost(isPassive, focusedSupportIdx)

    return (
      <>
        <div className="skill-support-panel-header">
          <div className="skill-support-panel-title">
            Support Slot {focusedSupportIdx}
            <span className={`skill-support-cost-badge${existingSupport ? '' : ' dim'}`} style={{ marginLeft: 6 }}>{cost} Energy</span>
          </div>
          <div className="skill-support-panel-parent">{SLOT_LABEL[focusedSlot]}: {focusedEquipped.name}</div>
          {existingSupport && (
            <div className="skill-support-current">
              <span className="skill-support-current-label">Equipped:</span>
              <span className="skill-support-current-name">{existingSupport.name}</span>
              <button
                className={`btn btn-sm ${existingSupport.enabled === false ? 'btn-danger' : 'btn-success'}`}
                style={{ marginLeft: 6 }}
                title="Enable/disable this support in the calculation"
                onClick={() => toggleSupportEnabled(focusedSupportIdx)}
              >{existingSupport.enabled === false ? 'Disabled' : 'Enabled'}</button>
              <button className="skill-slot-remove" onClick={e => removeSupport(focusedSupportIdx, e)}>×</button>
            </div>
          )}
          {existingSupport && (() => {
            const lvlRange = supportLevelRange(existingSupport.skill_type)
            const updateLevel = (newLevel: number) => {
              const clamped = Math.max(lvlRange.min, Math.min(lvlRange.max, newLevel))
              // Re-seed each modeled roll to the new tier's midpoint — otherwise the explicit roll
              // overrides the tier and changing the tier alone wouldn't move DPS.
              const rolls = modeledRolledLines(allItems.find(i => i.item_id === existingSupport.item_id), clamped)
              const newRolls = rolls.length ? Object.fromEntries(rolls.map(r => [r.identity, r.mid])) : undefined
              onSkillsChange(equippedSkills.map(sk =>
                sk.slot === focusedSlot
                  ? { ...sk, supports: sk.supports.map(s =>
                        s.support_index === focusedSupportIdx ? { ...s, level: clamped, specific_rolls: newRolls } : s
                      )}
                  : sk
              ))
            }
            return (
              <div className="skill-level-controls" style={{ marginTop: 6 }}>
                <span className="skill-level-label">{supportLevelLabel(existingSupport.skill_type)}</span>
                <button className="skill-level-btn" onClick={() => updateLevel(existingSupport.level - 1)}>−</button>
                <input
                  className="skill-level-input"
                  type="number"
                  min={lvlRange.min}
                  max={lvlRange.max}
                  value={existingSupport.level}
                  onChange={e => updateLevel(Number(e.target.value) || lvlRange.min)}
                />
                <button className="skill-level-btn" onClick={() => updateLevel(existingSupport.level + 1)}>+</button>
              </div>
            )
          })()}
          {existingSupport && isRankedSupport(existingSupport.skill_type) && (() => {
            const rank = existingSupport.rank ?? DEFAULT_SUPPORT_RANK
            const updateRank = (newRank: number) => {
              const clamped = Math.max(1, Math.min(5, newRank))
              onSkillsChange(equippedSkills.map(sk =>
                sk.slot === focusedSlot
                  ? { ...sk, supports: sk.supports.map(s =>
                        s.support_index === focusedSupportIdx ? { ...s, rank: clamped } : s
                      )}
                  : sk
              ))
            }
            return (
              <div className="skill-level-controls" style={{ marginTop: 6 }}>
                <span className="skill-level-label">Rank</span>
                <button className="skill-level-btn" onClick={() => updateRank(rank - 1)}>−</button>
                <input
                  className="skill-level-input"
                  type="number"
                  min={1}
                  max={5}
                  value={rank}
                  onChange={e => updateRank(Number(e.target.value) || 1)}
                />
                <button className="skill-level-btn" onClick={() => updateRank(rank + 1)}>+</button>
                <span
                  className="skill-support-rank-hint"
                  style={{ marginLeft: 8, fontSize: 11, opacity: 0.75, cursor: 'help' }}
                  title="Rank scales the universal '+% additional damage for the supported skill' line: R1 0% / R2 4% / R3 8% / R4 14% / R5 20%."
                >= +{(rankAdditional(rank) * 100).toFixed(0)}% additional</span>
              </div>
            )
          })()}
          {/* Roll sliders — one per engine-modeled rolled line (today: Noble/Magnificent specific line). */}
          {existingSupport && (() => {
            const supItem = allItems.find(i => i.item_id === existingSupport.item_id)
            const rolls = modeledRolledLines(supItem, existingSupport.level)
            if (!rolls.length) return null
            const updateRoll = (identity: string, value: number) => {
              onSkillsChange(equippedSkills.map(sk =>
                sk.slot === focusedSlot
                  ? { ...sk, supports: sk.supports.map(s =>
                        s.support_index === focusedSupportIdx
                          ? { ...s, specific_rolls: { ...(s.specific_rolls ?? {}), [identity]: value } }
                          : s
                      )}
                  : sk
              ))
            }
            return rolls.map(r => {
              const cur = existingSupport.specific_rolls?.[r.identity] ?? r.mid
              return (
                <div key={r.identity} className="skill-level-controls" style={{ marginTop: 6, gap: 8 }}>
                  <span className="skill-level-label">Roll</span>
                  <input
                    type="range" className="gear-affix-slider" style={{ flex: 1 }}
                    min={r.min} max={r.max} step={(r.max - r.min) / 100 || 0.001}
                    value={cur}
                    onChange={e => updateRoll(r.identity, Number(e.target.value))}
                  />
                  <span style={{ minWidth: 92, textAlign: 'right', fontSize: 12, opacity: 0.85 }}>
                    {(cur * 100).toFixed(1)}% <span style={{ opacity: 0.5 }}>({(r.min * 100).toFixed(0)}–{(r.max * 100).toFixed(0)}%)</span>
                  </span>
                </div>
              )
            })
          })()}
          {/* Resolved contribution summary. */}
          {existingSupport && (
            <div style={{ marginTop: 8, fontSize: 11, opacity: 0.7, lineHeight: 1.5 }}>
              Skill Lv {focusedEquipped.level}
              {isRankedSupport(existingSupport.skill_type) &&
                ` · Universal +${(rankAdditional(existingSupport.rank) * 100).toFixed(0)}% (Rank ${existingSupport.rank ?? DEFAULT_SUPPORT_RANK})`}
            </div>
          )}
          {/* DPS you'd lose by unequipping this support (slot-1 main skill only). */}
          {existingSupport && focusedSlot === 1 && (
            <div style={{ marginTop: 6 }}>
              <DamageDeltaBand delta={equippedSupportDelta} label="If unequipped" />
            </div>
          )}
        </div>
        <div className="skill-panel-divider" />
        <div className="skill-search-bar">
          <input
            className="skill-search-input"
            placeholder="Search compatible supports…"
            value={supportSearch}
            onChange={e => setSupportSearch(e.target.value)}
          />
          {supportSearch && <button className="skill-search-clear" onClick={() => setSupportSearch('')}>×</button>}
        </div>
        <div className="skill-catalog-list" style={{ flex: 1 }}>
          {supportCatalogItems.length === 0 && (
            <div className="skill-catalog-empty">No compatible supports for this slot</div>
          )}
          {sortedSupportCatalog.map(item => (
            <SkillHoverTooltip key={item.item_id} name={item.name} descLines={item.description_lines}>
              {tp => (
                <div
                  {...tp}
                  className={`skill-catalog-item${selectedSupportId === item.item_id ? ' selected' : ''}`}
                  onClick={() => setSelectedSupportId(item.item_id)}
                >
                  <span className="skill-catalog-name">{item.name}</span>
                  {deltaInline(supportDeltaById[item.item_id])}
                  <div className="skill-catalog-tags">
                    {item.skill_tags.map(t => <span key={t} className={tagClass(t)}>{t}</span>)}
                  </div>
                </div>
              )}
            </SkillHoverTooltip>
          ))}
        </div>
        {selectedSupportItem && (
          <>
            <div className="skill-panel-divider" />
            <div className="skill-detail-desc" style={{ maxHeight: 120, overflowY: 'auto' }}>
              {getAdvancedLines(selectedSupportItem.description_lines).map((line, i) => (
                <p key={i} className={isSubHeader(line) ? 'skill-desc-subheader' : 'skill-desc-line'}>{line}</p>
              ))}
            </div>
            <button
              className="btn btn-primary"
              style={{ width: '100%', marginTop: 8 }}
              onClick={assignSupport}
              disabled={existingSupport?.item_id === selectedSupportId}
            >
              {existingSupport?.item_id === selectedSupportId
                ? 'Already equipped'
                : `Equip in Slot ${focusedSupportIdx}`}
            </button>
          </>
        )}
        <button
          className="btn btn-secondary"
          style={{ width: '100%', marginTop: 6 }}
          onClick={() => { setFocusedSupportIdx(null); setSelectedSupportId(null); setSupportSearch('') }}
        >
          Close
        </button>
      </>
    )
  }

  return (
    <>
    <div className="skills-screen">
      <div className="skills-header">
        <span className="skills-header-title">Skills</span>
      </div>

      <div className="skills-body">
        {/* Left: skill slots + energy footer */}
        <div className="skill-slots-panel">
          <div className="skill-slots-scroll">
            {renderSlotGroup(ACTIVE_SLOTS, 'Active Skills')}
            {renderSlotGroup(PASSIVE_SLOTS, 'Passive Skills')}
          </div>
          <div className="skills-left-footer">
            <div className="skills-energy-config">
              <label className="skills-energy-config-label">
                <input type="checkbox" checked={hasPrism} onChange={e => onHasPrismChange(e.target.checked)} style={{ marginRight: 4 }} />
                Prism
              </label>
            </div>
            <span className={`skills-energy-total${energyOver ? ' over' : ''}`}>
              {totalEnergyCost} / {maxEnergy} Energy
            </span>
          </div>
        </div>

        {/* Center: skill catalog or skill detail */}
        <div className="skill-center-panel">
          {renderCenterPanel()}
        </div>

        {/* Right: support catalog */}
        <div className="skill-support-panel">
          {renderSupportPanel()}
        </div>
      </div>
    </div>
    </>
  )
}
