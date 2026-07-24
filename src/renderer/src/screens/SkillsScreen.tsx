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
  hasEffortlessCommandEnergy,
  computeSkillSlotEligibility,
  computeInvalidSkillSlots,
} from '../api/client'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { useUiPrefs } from '../store/uiPrefsStore'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { TooltipShell } from '../components/tooltip/TooltipShell'
import { SkillTooltipBody } from '../components/tooltip/bodies/SkillTooltipBody'
import { StructuredSkillTooltipBody } from '../components/tooltip/bodies/StructuredSkillTooltipBody'
import { DamageDeltaBand } from '../components/tooltip/DamageDeltaBand'
import { useDamageDelta, useDamageDeltaList, withSupport, withSkill, type DeltaRequest, type DamageDelta } from '../components/tooltip/useDamageDelta'
import { buildEngineStatsPayload, type BuildState } from '../utils/statsPayload'
import { characterLevelFrom } from '../utils/conditions'
import { modeledRolledLines } from '../utils/supportRolls'
import { dec } from '../utils/num'
import { CoverageBadge } from '../components/CoverageBadge'
import { coverageRank, passesModeledOnly } from '../utils/coverage'

// djb2 string hash → short base36. Used to fingerprint the build slice the support-pick deltas depend on.
function hashStr(str: string): string {
  let h = 5381
  for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0
  return (h >>> 0).toString(36)
}

// Cursor-anchored skill / support hover tooltip via the shared primitive (informational —
// no contributions band). Render-prop hands triggerProps to the hovered element.
function SkillHoverTooltip({ name, item, level, specificRolls, descLines, children, deltaReq = null }: {
  name: string
  item?: SkillItem | null            // carries the structured `tooltip` spec (new path)
  level?: number                     // current level/tier; defaults to the spec's default_level
  specificRolls?: Record<string, number>
  descLines?: string[]               // fallback flat lines when no spec (older cached data)
  children: (triggerProps: Record<string, unknown>) => React.ReactNode
  deltaReq?: DeltaRequest | null   // when set, a DPS-delta band is computed on hover (e.g. equip preview)
}) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'top' })
  const delta = useDamageDelta(deltaReq, tip.open && !!deltaReq)
  const spec = item?.tooltip
  return (
    <>
      {children(tip.triggerProps)}
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--skill" {...tip.floatingProps}>
            <TooltipShell title={name} delta={deltaReq ? delta : undefined}>
              {spec
                ? <StructuredSkillTooltipBody spec={spec} level={level ?? spec.default_level} specificRolls={specificRolls} />
                : <SkillTooltipBody lines={getAdvancedLines(cleanDescLines(descLines ?? item?.description_lines ?? []))} />}
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

// Copy for an active-slot skill that's currently soft-invalidated (equipped, but its enabling talent/trait
// isn't). Only two skill tags can ever land here — see computeSkillSlotEligibility in api/client.ts.
function invalidSlotReason(skillTags: string[]): string {
  if (skillTags.includes('Focus')) {
    return 'Focus skills require the Knowledgeable talent to be equipped in an active slot. This skill stays ' +
      'equipped but contributes nothing until Knowledgeable is selected again or the skill is moved/removed.'
  }
  if (skillTags.includes('Spirit Magus')) {
    return "Spirit Magus skills require Iris's Vigilant Breeze or Growing Breeze base trait to be equipped " +
      'in an active slot. This skill stays equipped but contributes nothing until that trait is selected ' +
      'again or the skill is moved/removed.'
  }
  return 'This skill cannot occupy an active slot. It stays equipped but contributes nothing.'
}

// "Family" key: a base skill/support and its Precise variant collapse to the same family, so the catalog can
// keep only one of a family socketable at once. A Precise variant's item_id is `precise_<base_id>` — but ONLY
// when that base id actually exists, otherwise the name itself contains "Precise". E.g. "Precise Restrain"
// (precise_restrain) pairs with "Restrain" (restrain); but "Precise Projectiles" (precise_projectiles) is the
// BASE — its sibling is "Precise: Precise Projectiles" (precise_precise_projectiles), so precise_projectiles
// stays its own family. Strip the leading "precise_" only when the stripped id is a known skill.
function skillFamily(itemId: string, knownIds: Set<string>): string {
  const id = itemId.toLowerCase()
  if (id.startsWith('precise_')) {
    const base = id.slice('precise_'.length)
    if (knownIds.has(base)) return base
  }
  return id
}

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
        {d.percent > 0 ? '+' : ''}{dec(d.percent)}%
      </span>
    )
  }
  return null
}

// Icon-only refresh button for the catalog sort rows. The swap-delta baseline is frozen when a panel opens
// so the numbers stay stable while you tweak the equipped skill's level/rolls; this re-snapshots on demand.
function RefreshButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="skill-sort-refresh"
      title="Recompute the DPS deltas against the current build (level / roll changes)"
      onClick={onClick}
      style={{
        marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 22, height: 22, padding: 0, lineHeight: 1, fontSize: 13, cursor: 'pointer',
        background: 'transparent', border: '1px solid rgba(255,255,255,0.18)', borderRadius: 4,
        color: '#bbb',
      }}
    >↻</button>
  )
}

// A typed exact-value input for a support's per-line roll (a signed fraction). Shows/accepts the value as a
// percentage (up to 2 decimals), with the tier's valid range beside it. Keeps local text state so partial
// typing isn't fought by clamping; commits (clamped to [min,max]) on blur / Enter. Re-syncs if the stored
// value changes externally (e.g. a tier change re-seeds the mid).
function RollInput(
  { value, min, max, onCommit, scale = 100, unit = '%' }:
  { value: number; min: number; max: number; onCommit: (frac: number) => void; scale?: number; unit?: string },
) {
  // Stored values are in engine units (fraction for %, seconds for a time roll); display is stored × scale.
  const fmt = (v: number) => dec(v * scale)
  const [text, setText] = useState(fmt(value))
  const [editing, setEditing] = useState(false)
  useEffect(() => { if (!editing) setText(fmt(value)) }, [value, editing])  // eslint-disable-line react-hooks/exhaustive-deps

  const commit = () => {
    setEditing(false)
    const shown = Number(text)
    if (Number.isNaN(shown)) { setText(fmt(value)); return }
    const stored = Math.min(max, Math.max(min, shown / scale))
    onCommit(stored)
    setText(fmt(stored))
  }
  return (
    <>
      <input
        type="number" className="skill-level-input" style={{ width: 70 }}
        min={min * scale} max={max * scale} step={0.01} value={text}
        onFocus={() => setEditing(true)}
        onChange={e => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
      />
      <span style={{ fontSize: 12, opacity: 0.5 }}>{unit} ({dec(min * scale)}–{dec(max * scale)}{unit})</span>
    </>
  )
}

// Build a fresh EquippedSupportSkill from a catalog item (default rank/tier + tier-mid rolls). Shared
// by assignSupport and the catalog DPS-delta preview transform.
function makeSupport(item: SkillItem, supportIndex: number, level?: number): EquippedSupportSkill {
  const range = supportLevelRange(item.skill_type)
  const seedLevel = level === undefined ? range.default : Math.max(range.min, Math.min(range.max, level))
  const rolls = modeledRolledLines(item, seedLevel)
  return {
    support_index: supportIndex,
    item_id: item.item_id,
    name: item.name,
    skill_type: item.skill_type ?? 'support_skill',
    level: seedLevel,
    skill_tags: item.skill_tags,
    description_lines: item.description_lines,
    ...(isRankedSupport(item.skill_type) ? { rank: DEFAULT_SUPPORT_RANK } : {}),
    ...(rolls.length ? { specific_rolls: Object.fromEntries(rolls.map(r => [r.identity, r.mid])) } : {}),
    // Seed each roll's tier (activation mediums have independent per-roll tiers).
    ...(rolls.some(r => (r.availableTiers?.length ?? 0) > 1)
      ? { specific_roll_tiers: Object.fromEntries(rolls.map(r => [r.identity, r.availableTiers?.[0] ?? seedLevel])) }
      : {}),
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
  const prisms = useBuildStore(s => s.prisms)
  const slots = useBuildStore(s => s.slots)
  const slates = useBuildStore(s => s.slates)
  const traitId = useBuildStore(s => s.traitId)
  const beltBlends = useReferenceStore(s => s.beltBlends)
  // +1000 Max Energy comes from a placed Effortless Command Ethereal Prism (≥24 pts) — not a manual toggle.
  const hasPrism = hasEffortlessCommandEnergy(prisms, slots)
  // Build-state-aware active-slot exemptions (Knowledgeable → Focus, Iris Vigilant Breeze/Growing Breeze →
  // Spirit Magus) + the resulting soft-invalidated active slots (equipped skill still there, but its
  // enabling talent/trait isn't) — computed once and shared by the catalog filter below and the per-slot
  // error UI. `sources` mirrors the four/five core-talent grant paths — see computeSkillSlotEligibility.
  const skillSlotEligibility = useMemo(
    () => computeSkillSlotEligibility(traitId, slots, { slates, gear, beltBlends: beltBlends ?? undefined, prisms }),
    [traitId, slots, slates, gear, beltBlends, prisms])
  const invalidSkillSlots = useMemo(
    () => new Set(computeInvalidSkillSlots(equippedSkills, skillSlotEligibility)),
    [equippedSkills, skillSlotEligibility])
  const cachedSkills = useReferenceStore(s => s.skills)
  const supportSort = useUiPrefs(s => s.supportSort)
  const setSupportSort = useUiPrefs(s => s.setSupportSort)
  const passiveSort = useUiPrefs(s => s.passiveSort)
  const setPassiveSort = useUiPrefs(s => s.setPassiveSort)
  const activeSkillSort = useUiPrefs(s => s.activeSkillSort)
  const setActiveSkillSort = useUiPrefs(s => s.setActiveSkillSort)
  const modeledOnly = useUiPrefs(s => s.modeledOnly)
  const toggleModeledOnly = useUiPrefs(s => s.toggleModeledOnly)
  const [fetchedItems, setFetchedItems] = useState<SkillItem[]>([])
  const [focusedSlot, setFocusedSlot] = useState<number | null>(null)
  const [centerView, setCenterView] = useState<'catalog' | 'detail'>('catalog')
  const [focusedSupportIdx, setFocusedSupportIdx] = useState<number | null>(null)
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [selectedSupportId, setSelectedSupportId] = useState<string | null>(null)
  const [pendingLevel, setPendingLevel] = useState(20)
  // Pre-equip level/tier for a support selected in the catalog but not yet slotted — separate from
  // pendingLevel (that one belongs to the active-skill assign flow, range 1-40 always).
  const [pendingSupportLevel, setPendingSupportLevel] = useState(20)
  const [search, setSearch] = useState('')
  const [supportSearch, setSupportSearch] = useState('')
  // Bumped by the catalog refresh button to re-snapshot the swap-delta baseline (which is otherwise frozen
  // when the panel opens, so tweaking the equipped skill's level/rolls doesn't recompute the catalog numbers).
  const [refreshNonce, setRefreshNonce] = useState(0)

  // Prefer the shared reference cache (already tooltip-enriched); fetch only if it isn't loaded yet.
  const allItems = cachedSkills ?? fetchedItems
  useEffect(() => {
    if (!cachedSkills) api.getSkills().then(r => setFetchedItems(r.skills))
  }, [cachedSkills])

  const getEquipped = (slot: number) => equippedSkills.find(s => s.slot === slot) ?? null
  const getSupport = (skill: EquippedSkill, idx: number) =>
    (skill.supports ?? []).find(s => s.support_index === idx) ?? null

  const focusedEquipped = focusedSlot !== null ? getEquipped(focusedSlot) : null

  // What you'd LOSE by unequipping the focused support (any slot). step = slot emptied, base = current,
  // so the delta is the negative drop and the % is relative to current DPS (how much of your damage this
  // support accounts for). Recomputes live as its rank/tier/roll change.
  const focusedEquippedSupport = (focusedSlot !== null && focusedSupportIdx !== null && focusedEquipped)
    ? getSupport(focusedEquipped, focusedSupportIdx) : null
  const equippedSupportDelta = useDamageDelta(
    focusedEquippedSupport && focusedSupportIdx !== null && focusedSlot !== null
      ? { key: `support-lose:${focusedSlot}:${focusedSupportIdx}:${focusedEquippedSupport.item_id}`,
          step: s => withSupport(s, focusedSlot, focusedSupportIdx, null), measureSlot: focusedSlot }
      : null,
    !!focusedEquippedSupport,
  )

  // ── catalog lists ──────────────────────────────────────────────────────────
  const skillCatalogItems = useMemo(() => {
    if (focusedSlot === null) return []
    let base = isPassiveSlot(focusedSlot)
      ? allItems.filter(isPassiveSkillItem)
      : allItems.filter(s => isActiveSkillItem(s, skillSlotEligibility))
    if (isPassiveSlot(focusedSlot)) {
      // Precise/base aura mutual exclusivity: a base aura and its "Precise: …" variant share a family and
      // can't both be socketed; same-name auras don't double-socket either. Exclude any candidate whose
      // family is already equipped in ANOTHER passive slot.
      const knownIds = new Set(allItems.map(i => i.item_id.toLowerCase()))
      const equippedFamilies = new Set(
        equippedSkills.filter(s => isPassiveSlot(s.slot) && s.slot !== focusedSlot)
          .map(s => skillFamily(s.item_id, knownIds)))
      base = base.filter(s => !equippedFamilies.has(skillFamily(s.item_id, knownIds)))
    }
    const matched = !search.trim() ? base : (() => {
      const q = search.toLowerCase()
      return base.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.skill_tags.some(t => t.toLowerCase().includes(q)) ||
        s.description_lines.some(l => l.toLowerCase().includes(q))
      )
    })()
    const visible = matched.filter(s => passesModeledOnly(s.coverage, modeledOnly))
    // Skills always sort alphabetically (a per-skill DPS sort would be inaccurate).
    return [...visible].sort((a, b) => a.name.localeCompare(b.name))
  }, [allItems, focusedSlot, search, equippedSkills, modeledOnly, skillSlotEligibility])

  const supportCatalogItems = useMemo(() => {
    if (focusedSlot === null || focusedSupportIdx === null || !focusedEquipped) return []
    const passive = isPassiveSlot(focusedSlot)
    // No duplicate support on one skill: a support already socketed in another slot of THIS skill can't be
    // socketed again — neither the same support nor its base/Precise sibling (e.g. Restrain ↔ Precise Restrain),
    // which collapse to the same family.
    const knownIds = new Set(allItems.map(i => i.item_id.toLowerCase()))
    const occupiedFamilies = new Set((focusedEquipped.supports ?? [])
      .filter(s => s.support_index !== focusedSupportIdx).map(s => skillFamily(s.item_id, knownIds)))
    const base = allItems.filter(s =>
      !occupiedFamilies.has(skillFamily(s.item_id, knownIds)) && isSupportCompatible(s, focusedEquipped, passive, focusedSupportIdx))
    const matched = !supportSearch.trim() ? base : (() => {
      const q = supportSearch.toLowerCase()
      return base.filter(s =>
        s.name.toLowerCase().includes(q) ||
        s.skill_tags.some(t => t.toLowerCase().includes(q)) ||
        s.description_lines.some(l => l.toLowerCase().includes(q))
      )
    })()
    return matched.filter(s => passesModeledOnly(s.coverage, modeledOnly))
  }, [allItems, focusedSlot, focusedSupportIdx, focusedEquipped, equippedSkills, supportSearch, modeledOnly])

  // Baseline signature FROZEN when the support panel opens (deps = focused slot/support only, NOT
  // buildVersion), capturing the current build incl. the equipped support at its open-time rolls. So
  // each pick-delta is the swap result vs the CURRENT support, computed once on open and cached — tweaking
  // the equipped support's roll/rank/tier afterward doesn't change or recompute the catalog numbers.
  const pickBaseSig = useMemo(() => {
    if (focusedSlot === null) return ''
    return hashStr(JSON.stringify(buildEngineStatsPayload(useBuildStore.getState() as unknown as BuildState)))
    // Re-snapshots when the focused slot/support changes OR the refresh button is pressed — NOT on every
    // build edit, so the catalog numbers stay stable while you tweak the equipped skill, then refresh on demand.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedSlot, focusedSupportIdx, refreshNonce])

  // Per-catalog-support DPS swap-delta (for the focused slot) vs the current support, used to label + sort
  // the list. base omitted → current build (only the focused slot's support index is swapped, others untouched).
  const supportPickReqs = useMemo<DeltaRequest[]>(() =>
    (focusedSlot !== null && focusedSupportIdx !== null)
      ? supportCatalogItems.map(item => ({
          key: `support-pick:${focusedSlot}:${item.item_id}:${focusedSupportIdx}:${pickBaseSig}`,
          step: (s) => withSupport(s, focusedSlot, focusedSupportIdx, makeSupport(item, focusedSupportIdx)),
          measureSlot: focusedSlot, stable: true,
        }))
      : [],
    [supportCatalogItems, focusedSlot, focusedSupportIdx, pickBaseSig])
  const supportPickDeltas = useDamageDeltaList(supportPickReqs.length ? supportPickReqs : null, supportPickReqs.length > 0)
  const supportDeltaById = useMemo(() => {
    const m: Record<string, DamageDelta> = {}
    supportCatalogItems.forEach((it, i) => { if (supportPickDeltas[i]) m[it.item_id] = supportPickDeltas[i] })
    return m
  }, [supportCatalogItems, supportPickDeltas])
  // Sort the support catalog by the user's chosen order (persisted). Alphabetical by default; DPS
  // contribution sorts by swap-delta (gain desc) with unresolved/nyi sinking, preserving order among equals.
  const sortedSupportCatalog = useMemo(() => {
    if (supportSort === 'alpha') {
      return [...supportCatalogItems].sort((a, b) => a.name.localeCompare(b.name))
    }
    if (supportSort === 'coverage') {
      return [...supportCatalogItems].sort((a, b) =>
        coverageRank(a.coverage) - coverageRank(b.coverage) || a.name.localeCompare(b.name))
    }
    const score = (i: number) => {
      const d = supportPickDeltas[i]
      return d && d.state === 'value' ? d.absolute : Number.NEGATIVE_INFINITY
    }
    return supportCatalogItems.map((it, i) => ({ it, i }))
      .sort((a, b) => score(b.i) - score(a.i))
      .map(x => x.it)
  }, [supportCatalogItems, supportPickDeltas, supportSort])

  // ── passive-skill catalog deltas (DPS contribution of equipping each candidate) ──────────────
  // Only for passive slots: a passive/aura buffs the whole build, so we measure each candidate's effect on
  // the MAIN skill's DPS (measureSlot omitted → headline offense), at the level you'd assign by default (20).
  // Baseline is the same frozen-on-open signature the supports use, so it refreshes via the same button.
  // A passive/aura buffs the whole build regardless of WHICH passive slot holds it, so the swap-in delta depends
  // only on the slot's current occupant (the skill being replaced, or "empty"), not the slot index. Keying by
  // occupant lets all empty passive slots (1-4) share one cached result set instead of recomputing all 75 deltas
  // each time you focus a different empty slot. (Support deltas stay slot-keyed — a support is skill-specific.)
  const passiveOccupant = focusedEquipped?.item_id ?? 'empty'
  const passivePickReqs = useMemo<DeltaRequest[]>(() =>
    (focusedSlot !== null && isPassiveSlot(focusedSlot))
      ? skillCatalogItems.map(item => ({
          key: `passive-pick:${passiveOccupant}:${item.item_id}:${pickBaseSig}`,
          step: (s) => withSkill(s, focusedSlot, item, 20),
          stable: true,
        }))
      : [],
    [skillCatalogItems, focusedSlot, passiveOccupant, pickBaseSig])
  const passivePickDeltas = useDamageDeltaList(passivePickReqs.length ? passivePickReqs : null, passivePickReqs.length > 0)
  const passiveDeltaById = useMemo(() => {
    const m: Record<string, DamageDelta> = {}
    skillCatalogItems.forEach((it, i) => { if (passivePickDeltas[i]) m[it.item_id] = passivePickDeltas[i] })
    return m
  }, [skillCatalogItems, passivePickDeltas])
  // Sort the skill catalog. Active skills stay alphabetical (a per-skill DPS sort is meaningless across
  // different main skills); passive skills honor passiveSort (DPS contribution sinks unresolved/nyi).
  const sortedSkillCatalog = useMemo(() => {
    const isPassive = focusedSlot !== null && isPassiveSlot(focusedSlot)
    const sortMode = isPassive ? passiveSort : activeSkillSort
    if (sortMode === 'alpha') {
      return [...skillCatalogItems].sort((a, b) => a.name.localeCompare(b.name))
    }
    if (sortMode === 'coverage') {
      return [...skillCatalogItems].sort((a, b) =>
        coverageRank(a.coverage) - coverageRank(b.coverage) || a.name.localeCompare(b.name))
    }
    // 'dps' — passive-only (active skills fall through to 'alpha'/'coverage' above; a per-skill DPS
    // sort across different main skills is meaningless).
    const score = (i: number) => {
      const d = passivePickDeltas[i]
      return d && d.state === 'value' ? d.absolute : Number.NEGATIVE_INFINITY
    }
    return skillCatalogItems.map((it, i) => ({ it, i }))
      .sort((a, b) => score(b.i) - score(a.i))
      .map(x => x.it)
  }, [skillCatalogItems, passivePickDeltas, passiveSort, activeSkillSort, focusedSlot])

  const selectedSkillItem  = allItems.find(i => i.item_id === selectedSkillId)  ?? null
  const selectedSupportItem = allItems.find(i => i.item_id === selectedSupportId) ?? null

  // Reset the pre-equip level/tier stepper to the newly-picked support's default whenever the
  // catalog selection changes, so it always starts sensible rather than carrying over the last pick.
  useEffect(() => {
    setPendingSupportLevel(supportLevelRange(selectedSupportItem?.skill_type).default)
  }, [selectedSupportId])  // eslint-disable-line react-hooks/exhaustive-deps

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

  // Include/exclude a (dps-eligible) skill from the sidebar's total DPS. Default on; persisted in the build.
  const toggleCountInDps = (slot: number) => {
    onSkillsChange(equippedSkills.map(s =>
      s.slot === slot ? { ...s, countInDps: s.countInDps === false } : s
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
    const newSupport = makeSupport(selectedSupportItem, focusedSupportIdx, pendingSupportLevel)
    const updated: EquippedSkill = {
      ...parent,
      supports: [
        ...(parent.supports ?? []).filter(s => s.support_index !== focusedSupportIdx),
        newSupport,
      ],
    }
    onSkillsChange(equippedSkills.map(s => s.slot === focusedSlot ? updated : s))
    // The panel stays open (focusedSupportIdx no longer clears), so pickBaseSig's memo deps never change
    // on their own — re-snapshot it here so the catalog DPS-delta numbers are relative to the
    // just-equipped state instead of stale pre-equip numbers until the user hits Refresh.
    setRefreshNonce(n => n + 1)
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

  // ── render helpers ─────────────────────────────────────────────────────────
  const renderSlotGroup = (slots: number[], label: string) => (
    <div className="skill-slot-group">
      <div className="skill-slots-section-label">{label}</div>
      {slots.map(slot => {
        const eq = getEquipped(slot)
        const isActive = focusedSlot === slot
        const invalid = !!eq && invalidSkillSlots.has(slot)
        return (
          <div
            key={slot}
            className={`skill-slot-row${eq ? ' occupied' : ''}${isActive ? ' active' : ''}${invalid ? ' invalid' : ''}`}
            onClick={() => selectSkillSlot(slot)}
          >
            <div className="skill-slot-info">
              <span className="skill-slot-label">{SLOT_LABEL[slot]}</span>
              {eq
                ? <span className="skill-slot-skill-name">
                    <span className="skill-slot-skill-name-text">{eq.name}</span>
                    <CoverageBadge coverage={allItems.find(i => i.item_id === eq.item_id)?.coverage}
                                   detail={allItems.find(i => i.item_id === eq.item_id)?.coverage_detail} />
                    {invalid && (
                      <span className="skill-slot-invalid-badge" title={invalidSlotReason(eq.skill_tags)}>!</span>
                    )}
                  </span>
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
            {/* Always rendered (never conditionally mounted) so the header's height is identical whether or
                not a skill is selected — hidden via visibility, not removed, to reserve its space. */}
            <div
              className="skill-level-controls"
              style={{
                marginLeft: 'auto',
                ...(selectedSkillItem ? null : { visibility: 'hidden', pointerEvents: 'none' }),
              }}
            >
              <span className="skill-level-label">Level</span>
              <button className="skill-level-btn" tabIndex={selectedSkillItem ? 0 : -1} onClick={() => setPendingLevel(l => Math.max(1, l - 1))}>−</button>
              <input
                type="number" className="skill-level-input" min={1} max={40} value={pendingLevel} tabIndex={selectedSkillItem ? 0 : -1}
                onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v)) setPendingLevel(Math.max(1, Math.min(40, v))) }}
              />
              <button className="skill-level-btn" tabIndex={selectedSkillItem ? 0 : -1} onClick={() => setPendingLevel(l => Math.min(40, l + 1))}>+</button>
            </div>
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
          <div className="skill-sort-row">
            <span className="skill-sort-label">Sort</span>
            <select
              className="skill-sort-select"
              value={isPassive ? passiveSort : activeSkillSort}
              onChange={e => (isPassive ? setPassiveSort : setActiveSkillSort)(e.target.value as 'alpha' | 'dps' | 'coverage')}
            >
              <option value="alpha">Alphabetical</option>
              {isPassive && <option value="dps">DPS Contribution</option>}
              <option value="coverage">Coverage</option>
            </select>
            {isPassive && <RefreshButton onClick={() => setRefreshNonce(n => n + 1)} />}
            <label className="skill-modeled-only-label" title="Hide skills the engine doesn't model at all">
              <input type="checkbox" checked={modeledOnly} onChange={toggleModeledOnly} /> Modeled only
            </label>
          </div>
          <div className="skill-catalog-list">
            {sortedSkillCatalog.length === 0 && (
              <div className="skill-catalog-empty">No skills match your search</div>
            )}
            {sortedSkillCatalog.map(item => (
              <SkillHoverTooltip key={item.item_id} name={item.name} item={item}>
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
                    <span className="skill-catalog-name">
                      {item.name}
                      <CoverageBadge coverage={item.coverage} detail={item.coverage_detail} />
                    </span>
                    {isPassive && deltaInline(passiveDeltaById[item.item_id])}
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
          <SkillHoverTooltip name={focusedEquipped.name}
                             item={allItems.find(i => i.item_id === focusedEquipped.item_id)}
                             level={focusedEquipped.level}
                             descLines={focusedEquipped.description_lines}>
            {tp => (
              <div {...tp} style={{ cursor: 'default', minWidth: 0 }}>
                <div className="skill-detail-name">{focusedEquipped.name}</div>
                <div className="skill-detail-tags">
                  {focusedEquipped.skill_tags.map(t => <span key={t} className={tagClass(t)}>{t}</span>)}
                </div>
              </div>
            )}
          </SkillHoverTooltip>
          <div className="skill-detail-header-actions">
            <button
              className={`btn btn-sm ${focusedEquipped.enabled === false ? 'btn-danger' : 'btn-success'}`}
              title="Enable/disable this skill (and its supports) in the calculation"
              onClick={() => toggleSkillEnabled(focusedSlot)}
            >{focusedEquipped.enabled === false ? 'Disabled' : 'Enabled'}</button>
            {allItems.find(i => i.item_id === focusedEquipped.item_id)?.dps_eligible && (
              <button
                className={`btn btn-sm ${focusedEquipped.countInDps === false ? 'btn-secondary' : 'btn-success'}`}
                title="Include this skill in the sidebar's total DPS"
                onClick={() => toggleCountInDps(focusedSlot)}
              >{focusedEquipped.countInDps === false ? 'Not in DPS' : 'In DPS'}</button>
            )}
            <button className="btn btn-secondary btn-sm" onClick={() => { setCenterView('catalog'); setSearch('') }}>Change</button>
            <button className="btn btn-danger btn-sm" onClick={() => removeSkill(focusedSlot)}>Remove</button>
            <div className="skill-level-controls" style={{ marginLeft: 'auto' }}>
              <span className="skill-level-label">Level</span>
              <button className="skill-level-btn" onClick={() => setEquippedLevel(focusedEquipped.level - 1)}>−</button>
              <input
                type="number" className="skill-level-input" min={1} max={40} value={focusedEquipped.level}
                onChange={e => setEquippedLevel(Number(e.target.value) || 1)}
              />
              <button className="skill-level-btn" onClick={() => setEquippedLevel(focusedEquipped.level + 1)}>+</button>
            </div>
          </div>
        </div>
        {invalidSkillSlots.has(focusedSlot) && (
          <div className="skill-invalid-banner">{invalidSlotReason(focusedEquipped.skill_tags)}</div>
        )}
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
              ? <SkillHoverTooltip key={idx} name={supItem.name} item={supItem} level={sup!.level}
                                   specificRolls={sup!.specific_rolls} descLines={supItem.description_lines}>{tp => renderRow(tp)}</SkillHoverTooltip>
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
          <div className="skill-support-current">
            <span className="skill-support-current-label">Equipped:</span>
            {existingSupport ? (
              <>
                <SkillHoverTooltip name={existingSupport.name}
                                   item={allItems.find(i => i.item_id === existingSupport.item_id)}
                                   level={existingSupport.level}
                                   specificRolls={existingSupport.specific_rolls}
                                   descLines={existingSupport.description_lines}>
                  {tp => <span {...tp} className="skill-support-current-name" style={{ cursor: 'help' }}>{existingSupport.name}</span>}
                </SkillHoverTooltip>
                <button
                  className={`btn btn-sm ${existingSupport.enabled === false ? 'btn-danger' : 'btn-success'}`}
                  style={{ marginLeft: 6 }}
                  title="Enable/disable this support in the calculation"
                  onClick={() => toggleSupportEnabled(focusedSupportIdx)}
                >{existingSupport.enabled === false ? 'Disabled' : 'Enabled'}</button>
                <button className="skill-slot-remove" onClick={e => removeSupport(focusedSupportIdx, e)}>×</button>
              </>
            ) : (
              <span className="skill-support-current-name" style={{ opacity: 0.5 }}>none</span>
            )}
          </div>
          {/* Single top-anchored level/tier control. Priority: a not-yet-equipped catalog pick (standard
              Level/Tier types only — pre-equip) > the equipped support's own control (standard stepper, or
              the activation-medium tier dropdown) > nothing, if neither applies. Rank and per-roll inputs
              below stay post-equip-only. */}
          {(() => {
            // Inner content only (no wrapper div) — the wrapper below is ALWAYS rendered with the same
            // class/style so this region's height never shifts as you select/equip/switch support types.
            const content = (() => {
              if (selectedSupportItem
                  && selectedSupportItem.item_id !== existingSupport?.item_id
                  && !selectedSupportItem.item_id.startsWith('activation_medium_')) {
                const range = supportLevelRange(selectedSupportItem.skill_type)
                const updatePendingSupportLevel = (newLevel: number) =>
                  setPendingSupportLevel(Math.max(range.min, Math.min(range.max, newLevel)))
                return (
                  <>
                    <span className="skill-level-label">{supportLevelLabel(selectedSupportItem.skill_type)}</span>
                    <button className="skill-level-btn" onClick={() => updatePendingSupportLevel(pendingSupportLevel - 1)}>−</button>
                    <input
                      className="skill-level-input"
                      type="number"
                      min={range.min}
                      max={range.max}
                      value={pendingSupportLevel}
                      onChange={e => updatePendingSupportLevel(Number(e.target.value) || range.min)}
                    />
                    <button className="skill-level-btn" onClick={() => updatePendingSupportLevel(pendingSupportLevel + 1)}>+</button>
                  </>
                )
              }
              if (!existingSupport) return null
              const supItem = allItems.find(i => i.item_id === existingSupport.item_id)
              // Activation mediums are TIERED (0–3) with independent per-roll tiers below — the top control is a
              // tX dropdown that sets the medium tier (base cooldown + the DEFAULT for each roll's tier).
              if (existingSupport.item_id.startsWith('activation_medium_')) {
                const rolls = modeledRolledLines(supItem, existingSupport.level)
                const tiers = [...new Set(rolls.flatMap(r => r.availableTiers ?? []))].sort((a, b) => a - b)
                if (!tiers.length) return null
                const setTier = (t: number) => {
                  const rs = modeledRolledLines(supItem, t)
                  const newTiers: Record<string, number> = {}
                  const newRolls: Record<string, number> = {}
                  for (const r of rs) {
                    const at = r.availableTiers ?? []
                    const rt = at.includes(t) ? t : (at.filter(x => x <= t).pop() ?? at[0] ?? t)
                    newTiers[r.identity] = rt
                    newRolls[r.identity] = r.rangesByTier?.[rt]?.mid ?? r.mid
                  }
                  onSkillsChange(equippedSkills.map(sk => sk.slot === focusedSlot
                    ? { ...sk, supports: sk.supports.map(s => s.support_index === focusedSupportIdx
                        ? { ...s, level: t, specific_roll_tiers: newTiers, specific_rolls: newRolls } : s) }
                    : sk))
                }
                return (
                  <>
                    <span className="skill-level-label" title="Medium tier — sets the base cooldown and the default tier of each roll below (each roll can still be re-tiered individually)">Tier</span>
                    <select className="skill-level-input" style={{ width: 60 }} value={existingSupport.level}
                      onChange={e => setTier(Number(e.target.value))}>
                      {tiers.map(t => <option key={t} value={t}>T{t}</option>)}
                    </select>
                  </>
                )
              }
              const lvlRange = supportLevelRange(existingSupport.skill_type)
              const updateLevel = (newLevel: number) => {
                const clamped = Math.max(lvlRange.min, Math.min(lvlRange.max, newLevel))
                // Re-seed each modeled roll to the new tier's midpoint — otherwise the explicit roll
                // overrides the tier and changing the tier alone wouldn't move DPS.
                const rolls = modeledRolledLines(supItem, clamped)
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
                <>
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
                </>
              )
            })()

            // Always-rendered wrapper (same class/style regardless of branch) reserves the row's space.
            // When nothing applies, fall back to a same-shaped placeholder hidden via visibility so the
            // "Equipped:" line above and Rank/roll controls below never shift.
            return (
              <div
                className="skill-level-controls"
                style={{ marginTop: 6, ...(content ? null : { visibility: 'hidden', pointerEvents: 'none' }) }}
              >
                {content ?? (
                  <>
                    <span className="skill-level-label">Level</span>
                    <button className="skill-level-btn" tabIndex={-1}>−</button>
                    <input className="skill-level-input" type="number" value={1} readOnly tabIndex={-1} />
                    <button className="skill-level-btn" tabIndex={-1}>+</button>
                  </>
                )}
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
          {/* Roll inputs — one slider per engine-modeled rolled line. Activation mediums also get a per-roll tier
              selector (independent per-affix tiers) and a Duration/Cooldown group selector. */}
          {existingSupport && (() => {
            const supItem = allItems.find(i => i.item_id === existingSupport.item_id)
            const rolls = modeledRolledLines(supItem, existingSupport.level)
            if (!rolls.length) return null
            const sup = existingSupport
            const isAM = sup.item_id.startsWith('activation_medium_')
            const patchSup = (patch: (s: EquippedSupportSkill) => EquippedSupportSkill) =>
              onSkillsChange(equippedSkills.map(sk => sk.slot === focusedSlot
                ? { ...sk, supports: sk.supports.map(s => s.support_index === focusedSupportIdx ? patch(s) : s) }
                : sk))
            const updateRoll = (identity: string, value: number) =>
              patchSup(s => ({ ...s, specific_rolls: { ...(s.specific_rolls ?? {}), [identity]: value } }))
            const tierOf = (r: typeof rolls[number]) =>
              sup.specific_roll_tiers?.[r.identity]
              ?? ((r.availableTiers?.includes(sup.level) ? sup.level : r.availableTiers?.[0]) ?? sup.level)
            const rangeOf = (r: typeof rolls[number]) =>
              (r.rangesByTier?.[tierOf(r)]) ?? { min: r.min, max: r.max, mid: r.mid }
            const updateTier = (r: typeof rolls[number], tier: number) => {
              const rng = r.rangesByTier?.[tier]
              patchSup(s => ({
                ...s,
                specific_roll_tiers: { ...(s.specific_roll_tiers ?? {}), [r.identity]: tier },
                specific_rolls: { ...(s.specific_rolls ?? {}), [r.identity]: rng ? rng.mid : (s.specific_rolls?.[r.identity] ?? r.mid) },
              }))
            }
            const groupChoice = (group: string, opts: typeof rolls) =>
              sup.roll_group_choice?.[group]
              ?? (opts.find(o => o.identity === 'duration_additional')?.identity ?? opts[0].identity)
            const setGroupChoice = (group: string, identity: string) =>
              patchSup(s => ({ ...s, roll_group_choice: { ...(s.roll_group_choice ?? {}), [group]: identity } }))

            const controls = (r: typeof rolls[number]) => {
              const rng = rangeOf(r)
              const cur = sup.specific_rolls?.[r.identity] ?? rng.mid
              return (<>
                {isAM && (r.availableTiers?.length ?? 0) > 1 && (
                  <select className="skill-level-input" style={{ width: 92 }} value={tierOf(r)}
                    title="Roll tier — each option shows that tier's mid value"
                    onChange={e => updateTier(r, Number(e.target.value))}>
                    {r.availableTiers!.map(t => {
                      const tr = r.rangesByTier?.[t]
                      const v = tr ? dec(tr.mid * (r.scale ?? 100)) : ''
                      return <option key={t} value={t}>T{t}{tr ? ` (${v}${r.unit})` : ''}</option>
                    })}
                  </select>
                )}
                <input type="range" className="gear-affix-slider" style={{ flex: 1 }}
                  min={rng.min} max={rng.max} step={(rng.max - rng.min) / 100 || 0.001}
                  value={cur} onChange={e => updateRoll(r.identity, Number(e.target.value))} />
                <RollInput value={cur} min={rng.min} max={rng.max} scale={r.scale} unit={r.unit}
                  onCommit={v => updateRoll(r.identity, v)} />
              </>)
            }

            const seen = new Set<string>()
            return rolls.map(r => {
              if (r.group) {
                if (seen.has(r.group)) return null
                seen.add(r.group)
                const opts = rolls.filter(x => x.group === r.group)
                const chosenId = groupChoice(r.group, opts)
                const chosen = opts.find(o => o.identity === chosenId) ?? opts[0]
                return (
                  <div key={r.group} className="skill-level-controls" style={{ marginTop: 6, gap: 8 }}>
                    <select className="skill-level-input" style={{ width: 130 }} value={chosen.identity}
                      title={chosen.desc} onChange={e => setGroupChoice(r.group!, e.target.value)}>
                      {opts.map(o => <option key={o.identity} value={o.identity} title={o.desc}>{o.label}</option>)}
                    </select>
                    {controls(chosen)}
                  </div>
                )
              }
              const hover = [r.desc, r.wired === false ? 'Recorded — not yet applied to the calc' : '']
                .filter(Boolean).join(' — ')
              return (
                <div key={r.identity} className="skill-level-controls" style={{ marginTop: 6, gap: 8 }}>
                  <span className="skill-level-label" title={hover || undefined}>
                    {(isAM ? (r.label ?? 'Roll') : 'Roll')}{r.wired === false ? ' *' : ''}
                  </span>
                  {controls(r)}
                </div>
              )
            })
          })()}
          {/* Resolved contribution summary. The rank's universal-damage contribution is already shown
              inline on the Rank control, so it isn't repeated here. */}
          {/* DPS you'd lose by unequipping this support (the focused skill's own offense). */}
          {existingSupport && (
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
        <div className="skill-sort-row">
          <span className="skill-sort-label">Sort</span>
          <select
            className="skill-sort-select"
            value={supportSort}
            onChange={e => setSupportSort(e.target.value as 'alpha' | 'dps' | 'coverage')}
          >
            <option value="alpha">Alphabetical</option>
            <option value="dps">DPS Contribution</option>
            <option value="coverage">Coverage</option>
          </select>
          <RefreshButton onClick={() => setRefreshNonce(n => n + 1)} />
          <label className="skill-modeled-only-label" title="Hide supports the engine doesn't model at all">
            <input type="checkbox" checked={modeledOnly} onChange={toggleModeledOnly} /> Modeled only
          </label>
        </div>
        <div className="skill-catalog-list" style={{ flex: 1 }}>
          {supportCatalogItems.length === 0 && (
            <div className="skill-catalog-empty">No compatible supports for this slot</div>
          )}
          {sortedSupportCatalog.map(item => (
            <SkillHoverTooltip key={item.item_id} name={item.name} item={item}>
              {tp => (
                <div
                  {...tp}
                  className={`skill-catalog-item${selectedSupportId === item.item_id ? ' selected' : ''}`}
                  onClick={() => setSelectedSupportId(item.item_id)}
                >
                  <span className="skill-catalog-name">
                    {item.name}
                    <CoverageBadge coverage={item.coverage} detail={item.coverage_detail} />
                  </span>
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
