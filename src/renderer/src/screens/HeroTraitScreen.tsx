import React, { useEffect, useMemo, useRef, useState } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { HeroTrait, HeroAdvancedTrait, HeroMemoryAffix, HeroMemoryType, CreatedHeroMemory, MemoryRarity, MemorySlotSelection, MEMORY_RARITY_COLORS, iconUrl,
  SkillItem, EquippedSupportSkill, isSupportCompatible, traitGrantsSkillSlot, TRAIT_SKILL_PARENT, genMemoryId,
  deriveTraitSlotLevels, activeBaseSlotEnabler, resolveBaseSlot, rarityWithinCap, heroMemoryBaseStatValue,
  memoryRangeCount, memoryRangeBounds } from '../api/client'
import { useReferenceStore } from '../store/referenceStore'
import { useBuildStore } from '../store/buildStore'
import { useUiPrefs } from '../store/uiPrefsStore'
import { characterLevelFrom } from '../utils/conditions'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { useDamageDelta } from '../components/tooltip/useDamageDelta'
import { TooltipContributions } from '../components/tooltip/TooltipContributions'
import LoadingState from '../components/LoadingState'
import { ModifierBadge, useTextModifierStatus } from '../components/ModifierBadge'
import { CoverageBadge } from '../components/CoverageBadge'
import { coverageRank, passesModeledOnly } from '../utils/coverage'
import { dec } from '../utils/num'
import { traitSlang, traitOrder } from '../utils/heroTraitOrder'
import EditableRollValue from '../components/EditableRollValue'
import { TraitTooltipBody, MemorySlotCircle, resolveMemoryEffect, MEMORY_TYPE_LABELS, RARITY_LABELS,
  MemoryPreviewCard, MemoryIcon, memoryRarityBg, tierColor, TIER_RARITY, MAX_LEVEL_BY_RARITY } from '../components/HeroTraitShared'
import HeroTraitTree from './HeroTraitTree'

interface Props {
  onBack: () => void
  // Called right after a brand-new build's DEFAULT trait is auto-selected (a default, not a user edit) so the
  // dirty tracker can re-baseline — otherwise the auto-select's buildVersion bump marks the fresh build dirty.
  onDefaultTraitApplied?: () => void
}

// A contiguous segment of the unified slider mapped to one tier's value range
interface TierRangeInfo {
  tier: number
  min: number    // actual game value at this tier's low end
  max: number    // actual game value at this tier's high end
  modifier: string
  startPos: number  // slider integer position where this tier begins
  endPos: number    // slider integer position where this tier ends (inclusive)
}

// Slot index constants
const SLOT_BASE = 0
const SLOT_LV45 = 1
const SLOT_LV60 = 2
const SLOT_LV75 = 3
const LEVEL_THRESHOLDS = [45, 60, 75]
const SLOT_IDX: Record<number, number> = { 45: SLOT_LV45, 60: SLOT_LV60, 75: SLOT_LV75 }

// Memory slot index: 0=origin(lv45), 1=discipline(lv60), 2=progress(lv75)
const THRESHOLD_TO_MEMORY_SLOT: Record<number, number> = { 45: 0, 60: 1, 75: 2 }
const MEMORY_SOURCES: Record<number, string> = {
  0: 'Memory of Origin',
  1: 'Memory of Discipline',
  2: 'Memory of Progress',
}
const MEMORY_TYPES: Record<number, CreatedHeroMemory['memoryType']> = {
  0: 'origin',
  1: 'discipline',
  2: 'progress',
}
// A memory's type determines which socket it goes into (inverse of MEMORY_TYPES) — used when socketing
// a memory straight from the inventory.
const MEMORY_TYPE_TO_SLOT: Record<CreatedHeroMemory['memoryType'], number> = {
  origin: 0,
  discipline: 1,
  progress: 2,
}
// MEMORY_TYPE_LABELS and RARITY_LABELS live in components/HeroTraitShared.tsx (also used by
// MemorySlotCircle there); RARITY_ORDER is only needed for the rarity <select> below.
const RARITY_ORDER: MemoryRarity[] = ['normal', 'magic', 'rare', 'epic', 'ultimate']

// Per-rarity affix structure (owner spec). Random affix slots unlock at RANDOM_UNLOCK_LEVELS. The per-rarity
// level cap (MAX_LEVEL_BY_RARITY) lives in HeroTraitShared, shared with the preview/tooltip card.
const RARITY_FIXED_COUNT: Record<MemoryRarity, number> = { normal: 0, magic: 1, rare: 1, epic: 2, ultimate: 2 }
const RARITY_RANDOM_COUNT: Record<MemoryRarity, number> = { normal: 0, magic: 1, rare: 1, epic: 2, ultimate: 2 }
const RANDOM_UNLOCK_LEVELS = [20, 40]   // random slot index i is available once level >= RANDOM_UNLOCK_LEVELS[i]
// Label for a socketed memory's slot (memory slots map to the 45/60/75 trait tiers).
const MEMORY_SLOT_LABELS: Record<number, string> = { 0: 'Level 45', 1: 'Level 60', 2: 'Level 75' }
// Affix-category colors (mirrors the in-game / Compendium slider: fixed = blue, random = gold, base = teal).
const AFFIX_CAT_COLOR = { base: '#5fb98c', fixed: '#4a9eff', random: '#e0a94f', revival: '#c98be0' } as const
// MemoryPreviewCard, MemoryIcon, memoryRarityBg, tierColor/TIER_RARITY, MAX_LEVEL_BY_RARITY and the
// trait-level helpers now live in HeroTraitShared (shared by the creator preview, slot-circle tooltips,
// and inventory-tile tooltips) — imported above.

// ── Affix / tier helper functions ─────────────────────────────────────────────

function getAffixName(modifier: string): string {
  // Group all tiers of a modifier under one name (this is the grouping key + dropdown label, NOT the resolved
  // value). Strip the leading value AND any EMBEDDED values — combo mods carry a second value that scales
  // across tiers (e.g. "+14% Attack and Cast Speed +14% Minion Attack and Cast Speed"), which would otherwise
  // fragment each tier into its own "modifier". Embedded fixed values require a leading '+' so incidental
  // numbers (e.g. "within 8m") aren't stripped.
  const name = modifier
    .replace(/^\+?(?:\d+(?:\.\d+)?|\([^)]+\))\s*%?\s*/, '')                 // leading value
    .replace(/\+?\(\d+(?:\.\d+)?[–\-]\d+(?:\.\d+)?\)\s*%?\s*/g, '')          // embedded ranges
    .replace(/\+\d+(?:\.\d+)?\s*%?\s*/g, '')                                // embedded fixed "+N%" values
    .replace(/\s+/g, ' ')
    .trim()
  return name ? name[0].toUpperCase() + name.slice(1) : name
}

function getAffixNames(pool: HeroMemoryAffix[], source: string): string[] {
  const seen = new Set<string>()
  const names: string[] = []
  for (const entry of pool) {
    if (entry.source !== source) continue
    const name = getAffixName(entry.modifier)
    if (!seen.has(name)) { seen.add(name); names.push(name) }
  }
  return names
}

function getTierOptions(pool: HeroMemoryAffix[], source: string, affixName: string): HeroMemoryAffix[] {
  return pool
    .filter(e => e.source === source && getAffixName(e.modifier) === affixName)
    .sort((a, b) => a.tier - b.tier)
}

// Optional leading '-' on each bound so negative ranges (the base-slot penalty mod's "(-60–-55) %") are
// recognized and roll like any other; positive ranges are unaffected.
function hasRange(modifier: string): boolean {
  return /\(-?\d+(?:\.\d+)?[–\-]-?\d+(?:\.\d+)?\)/.test(modifier)
}

function parseRange(modifier: string): { min: number; max: number } {
  const m = modifier.match(/\((-?\d+(?:\.\d+)?)[–\-](-?\d+(?:\.\d+)?)\)/)
  return m ? { min: parseFloat(m[1]), max: parseFloat(m[2]) } : { min: 0, max: 0 }
}

// Handles optional leading +, works for both integer and decimal values
function parseFixedVal(modifier: string): number {
  const m = modifier.match(/^\+?(\d+(?:\.\d+)?)/)
  return m ? parseFloat(m[1]) : 0
}

// Unified extractor: finds the numeric range (or fixed value) in any modifier format
function extractValueRange(modifier: string): { min: number; max: number } {
  if (hasRange(modifier)) return parseRange(modifier)
  const v = parseFixedVal(modifier)
  return { min: v, max: v }
}

/**
 * Build a flat list of slider segments, one per tier, sorted ascending by value.
 * Each segment covers [startPos, endPos] on the slider integer axis.
 * Within a segment, slider position maps linearly to the tier's actual [min, max] range.
 * Fixed-value tiers have width=1.
 */
function buildTierRanges(entries: HeroMemoryAffix[]): TierRangeInfo[] {
  const withValues = entries.map(entry => {
    const { min, max } = extractValueRange(entry.modifier)
    return { entry, min, max }
  })

  // Sort ascending by max value so slider goes left=low, right=high
  withValues.sort((a, b) => a.max !== b.max ? a.max - b.max : a.min - b.min)

  let pos = 0
  return withValues.map(({ entry, min, max }) => {
    const width = Math.max(1, max - min + 1)
    const seg: TierRangeInfo = {
      tier: entry.tier,
      min,
      max,
      modifier: entry.modifier,
      startPos: pos,
      endPos: pos + width - 1,
    }
    pos += width
    return seg
  })
}

function posToTierValue(ranges: TierRangeInfo[], pos: number): { tier: number; value: number; modifier: string } {
  for (const r of ranges) {
    if (pos >= r.startPos && pos <= r.endPos) {
      return { tier: r.tier, value: r.min + (pos - r.startPos), modifier: r.modifier }
    }
  }
  const last = ranges[ranges.length - 1]
  return { tier: last.tier, value: last.max, modifier: last.modifier }
}

function tierValueToPos(ranges: TierRangeInfo[], tier: number, rolledValue: number | null): number {
  const r = ranges.find(x => x.tier === tier)
  if (!r) return 0
  const v = rolledValue ?? r.min
  return r.startPos + Math.min(Math.max(v - r.min, 0), r.max - r.min)
}

// resolveMemoryEffect (used by AffixRow below) lives in components/HeroTraitShared.tsx.

// ── Shared trait helpers ──────────────────────────────────────────────────────

function groupByHero(traits: HeroTrait[]): Record<string, HeroTrait[]> {
  const out: Record<string, HeroTrait[]> = {}
  for (const t of traits) {
    if (!out[t.hero]) out[t.hero] = []
    out[t.hero].push(t)
  }
  return out
}

// Custom hero-trait dropdown — a native <select> can't style the per-substring lavender slang label, so this small
// floating menu (mirrors the loadout dropdown) shows each trait's name + its community slang ("Thea 1") and sorts by
// release order (heroes in release order; ascending within a hero).
function HeroTraitSelect({ traits, value, onChange }: {
  traits: HeroTrait[]; value: string | null; onChange: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const modeledOnly = useUiPrefs(s => s.modeledOnly)
  const toggleModeledOnly = useUiPrefs(s => s.toggleModeledOnly)
  const heroTraitSort = useUiPrefs(s => s.heroTraitSort)
  const setHeroTraitSort = useUiPrefs(s => s.setHeroTraitSort)
  const groups = useMemo(() => {
    // Never hide the CURRENTLY SELECTED trait behind the "Modeled only" filter — it's already
    // equipped, so hiding it from the list would just make the dropdown confusing.
    const visible = traits.filter(t => t.trait_id === value || passesModeledOnly(t.coverage, modeledOnly))
    const by = groupByHero(visible)
    return Object.entries(by)
      .map(([hero, variants]) => ({
        hero,
        variants: [...variants].sort((a, b) => heroTraitSort === 'coverage'
          ? (coverageRank(a.coverage) - coverageRank(b.coverage) || traitOrder(a.trait_id) - traitOrder(b.trait_id))
          : traitOrder(a.trait_id) - traitOrder(b.trait_id)),
        order: Math.min(...variants.map(v => traitOrder(v.trait_id))),
      }))
      .sort((a, b) => a.order - b.order)
  }, [traits, modeledOnly, heroTraitSort, value])
  const current = traits.find(t => t.trait_id === value) ?? null
  return (
    <div className="ht-dd">
      <button className="ht-dd-trigger" onClick={() => setOpen(o => !o)} title="Select hero trait">
        <span className="ht-dd-trigger-name">{current?.variant_name ?? 'Select trait'}</span>
        {current && traitSlang(current.trait_id) && (
          <span className="ht-dd-slang">{traitSlang(current.trait_id)}</span>
        )}
        <CoverageBadge coverage={current?.coverage} detail={current?.coverage_detail} />
        <span className="ht-dd-caret">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <>
          <div className="ht-dd-backdrop" onClick={() => setOpen(false)} />
          <div className="ht-dd-menu">
            <div className="ht-dd-controls">
              <select
                className="ht-dd-sort-select"
                value={heroTraitSort}
                onChange={e => setHeroTraitSort(e.target.value as 'release' | 'coverage')}
              >
                <option value="release">Release order</option>
                <option value="coverage">Coverage</option>
              </select>
              <label className="skill-modeled-only-label" title="Hide traits the engine doesn't model at all">
                <input type="checkbox" checked={modeledOnly} onChange={toggleModeledOnly} /> Modeled only
              </label>
            </div>
            {groups.map(g => (
              <div key={g.hero} className="ht-dd-group">
                <div className="ht-dd-group-label">{g.hero}</div>
                {g.variants.map(v => (
                  <button key={v.trait_id}
                    className={`ht-dd-item${v.trait_id === value ? ' active' : ''}`}
                    onClick={() => { onChange(v.trait_id); setOpen(false) }}>
                    <span className="ht-dd-item-name">{v.variant_name}</span>
                    {traitSlang(v.trait_id) && <span className="ht-dd-slang">{traitSlang(v.trait_id)}</span>}
                    <CoverageBadge coverage={v.coverage} detail={v.coverage_detail} />
                  </button>
                ))}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// resolveLevel and TraitTooltipBody (the `/`-separated Trait-Level 1–5 scaling text resolver and
// the tooltip content shared with HeroTraitTree.tsx and PlayerStatsScreen.tsx) live in
// components/HeroTraitShared.tsx.

// ── Tooltip content + trigger components (shared floating primitive) ───────────

// A trait circle (base or advanced) + its hover info tooltip. Hover-only — the tooltip shows
// only while the icon itself is hovered (non-interactive, so moving onto the card dismisses
// it), and clicking only selects the node (no pinning). Locked circles show no tooltip.
function TraitCircle({ className, name, icon, checked, locked, disabled, tipName, slotLevel, effects, moonEffects, onSelect, onContextMenu }: {
  className: string; name: string; icon?: string | null; checked: boolean; locked?: boolean; disabled?: boolean
  tipName: string; slotLevel: number; effects: string[]; moonEffects?: string[]
  onSelect?: () => void; onContextMenu?: () => void
}) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  // Icon fills the circle; the name sits as a caption below so it never overlaps the art. Falls back
  // to the name inside the circle if an icon is missing.
  const inner = (
    <div className="trait-circle-inner">
      {icon ? <img src={icon} className="trait-circle-img" alt="" /> : <span className="trait-circle-name">{name}</span>}
    </div>
  )
  if (locked) {
    return (
      <div className="trait-circle-wrap">
        <div className={className}>{inner}{checked && <span className="trait-circle-check">✓</span>}</div>
        <span className="trait-circle-caption">{name}</span>
      </div>
    )
  }
  return (
    <div className="trait-circle-wrap">
      <div {...tip.triggerProps}
        className={className}
        onClick={onSelect}
        onContextMenu={onContextMenu ? e => { e.preventDefault(); onContextMenu() } : undefined}>
        {inner}{checked && !disabled && <span className="trait-circle-check">✓</span>}
      </div>
      <span className="trait-circle-caption">{name}</span>
      {tip.open && (
        <FloatingPortal>
          <div className="trait-info-card" {...tip.floatingProps}>
            <TraitTooltipBody name={tipName} slotLevel={slotLevel} effects={effects} moonEffects={moonEffects} />
          </div>
        </FloatingPortal>
      )}
    </div>
  )
}

// Group a level's advanced nodes by group_id. A group is "guaranteed" (always granted) or "pick" (choose one).
// Falls back to is_pick_one_from_two for older data. Groups order top->bottom by id (guaranteed first on a tie).
interface NodeGroup { id: number; role: 'guaranteed' | 'pick'; nodes: HeroAdvancedTrait[] }
function buildGroups(nodes: HeroAdvancedTrait[]): NodeGroup[] {
  const map = new Map<string, NodeGroup>()
  for (const n of nodes) {
    const role: 'guaranteed' | 'pick' = n.group_role ?? (n.is_pick_one_from_two ? 'pick' : 'guaranteed')
    const id = n.group_id ?? 0
    const key = `${role}:${id}`
    if (!map.has(key)) map.set(key, { id, role, nodes: [] })
    map.get(key)!.nodes.push(n)
  }
  return [...map.values()].sort((a, b) => a.id - b.id || (a.role === 'guaranteed' ? -1 : 1))
}

// A "pick one" group rendered as a single split circle (vertical slices, one per option — matching the in-game
// merged look) that expands on click to the individual nodes for selection. The chosen slice is highlighted.
function PickGroup({ nodes, slotLevel, locked, tierDisabled, selectedNames, onSelect, onDisable }: {
  nodes: HeroAdvancedTrait[]; slotLevel: number; locked: boolean; tierDisabled: boolean
  selectedNames: string[]; onSelect: (name: string) => void; onDisable: () => void
}) {
  const [open, setOpen] = useState(false)
  const chosen = nodes.find(n => selectedNames.includes(n.name)) ?? null
  // When a node is chosen, hovering the collapsed split circle shows that node's full tooltip.
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  return (
    <div className="ht-pick">
      <div
        {...(chosen ? tip.triggerProps : {})}
        className={`ht-pick-circle${locked ? ' locked' : ''}${chosen && !tierDisabled ? ' selected' : ''}`}
        onClick={() => !locked && setOpen(o => !o)}
        onContextMenu={e => { e.preventDefault(); if (chosen && !locked) onDisable() }}
        title={chosen ? undefined : `Pick 1 of ${nodes.length}`}
      >
        <div className="ht-pick-slices">
          {nodes.map(n => {
            const icon = iconUrl('hero_trait', n.icon_url)
            const cls = chosen ? (chosen.name === n.name ? ' chosen' : ' dim') : ''
            return <div key={n.name} className={`ht-pick-slice${cls}`}
              style={icon ? { backgroundImage: `url(${icon})` } : undefined} />
          })}
        </div>
        {chosen && !tierDisabled && <span className="trait-circle-check">✓</span>}
        <span className="ht-pick-count">{open ? '▴' : `1/${nodes.length}`}</span>
      </div>
      <span className="ht-pick-caption">{chosen ? chosen.name : `Pick 1 of ${nodes.length}`}</span>
      {/* Hover tooltip for the chosen node (hidden while the fan is open — the options show their own). */}
      {chosen && !open && tip.open && (
        <FloatingPortal>
          <div className="trait-info-card" {...tip.floatingProps}>
            <TraitTooltipBody name={chosen.name} slotLevel={slotLevel} effects={chosen.effects ?? []} />
          </div>
        </FloatingPortal>
      )}
      {open && !locked && (
        <>
          {/* Click-catcher so clicking away closes the fan. */}
          <div className="ht-pick-backdrop" onClick={() => setOpen(false)} />
          {/* Options fan out horizontally as a floating popover (doesn't push the columns). */}
          <div className="ht-pick-options">
            {nodes.map(n => {
              const sel = selectedNames.includes(n.name)
              return <TraitCircle key={n.name}
                className={`trait-circle${sel ? ' selected' : ''}`}
                name={n.name} icon={iconUrl('hero_trait', n.icon_url)} checked={sel}
                disabled={sel && tierDisabled} tipName={n.name} slotLevel={slotLevel} effects={n.effects ?? []}
                onSelect={() => { onSelect(n.name); setOpen(false) }} />
            })}
          </div>
        </>
      )}
    </div>
  )
}

// MemorySlotCircle (the memory-slot circle + its hover tooltip, shared with HeroTraitTree.tsx's
// origin/discipline/progress rail) lives in components/HeroTraitShared.tsx.

// A searchable combobox for the memory affix rows (matches the searchable-dropdown pattern used elsewhere).
function SearchableAffixSelect({ value, options, badge, onChange }: {
  value: string; options: string[]; badge?: React.ReactNode; onChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [dropUp, setDropUp] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])
  const toggle = () => {
    // Flip the menu upward when the trigger is near the bottom of the viewport (bottom random-affix rows).
    const r = ref.current?.getBoundingClientRect()
    if (r) setDropUp(window.innerHeight - r.bottom < 280)
    setQuery(''); setOpen(o => !o)
  }
  const q = query.trim().toLowerCase()
  const filtered = q ? options.filter(o => o.toLowerCase().includes(q)) : options
  return (
    <div className="memory-affix-combo" ref={ref}>
      <div className={`memory-affix-combo-trigger${open ? ' open' : ''}`} onClick={toggle}>
        <span className={`memory-affix-combo-value${value ? '' : ' memory-affix-combo-placeholder'}`}>{value || '— None —'}</span>
        {badge}
        <span className="memory-affix-combo-caret">▾</span>
      </div>
      {open && (
        <div className={`memory-affix-combo-menu${dropUp ? ' up' : ''}`}>
          <input autoFocus className="memory-affix-combo-search" placeholder="Search…" value={query}
            onChange={e => setQuery(e.target.value)} />
          <div className="memory-affix-combo-list dark-scroll">
            <div className="memory-affix-combo-opt" onClick={() => { onChange(''); setOpen(false) }}>— None —</div>
            {filtered.map(o => (
              <div key={o} className={`memory-affix-combo-opt${o === value ? ' selected' : ''}`}
                onClick={() => { onChange(o); setOpen(false) }}>{o}</div>
            ))}
            {filtered.length === 0 && <div className="memory-affix-combo-empty">No matches</div>}
          </div>
        </div>
      )}
    </div>
  )
}

// Compendium-style segmented tier slider: one labeled pill per tier (T3|T2|…) laid out along the track,
// with a draggable dial; the tier the dial sits in is highlighted in the affix's category color. Replaces
// the native range input (which flashed/expanded when scroll-edited). Pointer-drag only — no wheel handler.
function TierSlider({ tiers, curTier, curValue, dp, onPick }: {
  tiers: { tier: number; min: number; max: number; modifier: string }[]
  curTier: number; curValue: number; dp: number
  onPick: (tier: number, value: number, modifier: string) => void
}) {
  const trackRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  // EQUAL-width segments (screen space is 1/N per tier regardless of value-range size, so segments never
  // resize as the value changes → no reflow/flash). Left→right = worst→best: tier number DESCENDING.
  const segs = [...tiers].sort((a, b) => b.tier - a.tier)
  const N = segs.length
  const idx = Math.max(0, segs.findIndex(s => s.tier === curTier))
  const seg = segs[idx] ?? segs[N - 1]
  const within = seg && seg.max > seg.min ? Math.max(0, Math.min(1, (curValue - seg.min) / (seg.max - seg.min))) : 0.5
  const dialPct = N > 0 ? Math.max(0, Math.min(100, ((idx + within) / N) * 100)) : 0
  const apply = (clientX: number) => {
    const el = trackRef.current
    if (!el || N === 0) return
    const r = el.getBoundingClientRect()
    const f = Math.max(0, Math.min(0.999999, (clientX - r.left) / r.width))
    const i = Math.min(N - 1, Math.floor(f * N))
    const w = f * N - i                             // fraction within the picked tier's value range
    const s = segs[i]
    const raw = s.min + w * (s.max - s.min)
    onPick(s.tier, dp > 0 ? parseFloat(raw.toFixed(dp)) : Math.round(raw), s.modifier)
  }
  const down = (e: React.PointerEvent) => { dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); apply(e.clientX) }
  const move = (e: React.PointerEvent) => { if (dragging.current) apply(e.clientX) }
  const up = (e: React.PointerEvent) => { dragging.current = false; try { e.currentTarget.releasePointerCapture(e.pointerId) } catch { /* ignore */ } }
  return (
    <div ref={trackRef} className="mem-tierslider" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
      {segs.map((s, i) => {
        const isCur = s.tier === curTier
        const tc = tierColor(s.tier)   // segment background reflects the tier's rarity color; abutting = clean boundaries
        return (
          <div key={s.tier} className={`mem-tierseg${isCur ? ' current' : ''}`}
            style={{
              left: `${(i / N) * 100}%`,
              width: `${100 / N}%`,
              background: isCur ? `${tc}40` : `${tc}1c`,
              borderColor: isCur ? tc : `${tc}55`,
              color: isCur ? tc : `${tc}bb`,
            }}>T{s.tier}</div>
        )
      })}
      <div className="mem-tierslider-dial" style={{ left: `${dialPct}%`, background: tierColor(curTier) }} />
    </div>
  )
}

// Attach the revival pool entry's full effect text to the picked selection. Name-only tier-0 mods ("Artificial
// Moon: Origin") store their real wording in `description`; carrying it on the selection lets the base-slot
// enabler parser (parseBaseSlotEnabler) read the type / rarity cap / penalty after save/load/import.
function withRevivalDescription(sel: MemorySlotSelection, pool: HeroMemoryAffix[]): MemorySlotSelection {
  const name = getAffixName(sel.modifier)
  const match = pool.find(a => getAffixName(a.modifier) === name)
  const desc = match?.description
  return desc && desc !== sel.modifier ? { ...sel, description: desc } : { ...sel, description: undefined }
}

// One unified-slider affix row in the memory creator + its hover tooltip (resolved text).
function AffixRow({ label, pool, source, current, excludeNames, color, hideSlider, minTier, onChange }: {
  label: string
  pool: HeroMemoryAffix[]
  source: string
  current: MemorySlotSelection | null
  excludeNames?: Set<string>   // affix names already chosen in sibling rows (a memory can't repeat a modifier)
  color: string                // category color (base/fixed/random) for the slider highlight + value
  hideSlider?: boolean         // base stat: no tier slider (its value is driven by the memory level)
  minTier?: number             // best tier the memory's rarity can reach (e.g. epic→T1): hide tiers below it
  onChange: (sel: MemorySlotSelection | null) => void
}) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'top' })
  const selectedName = current ? getAffixName(current.modifier) : ''
  // Drop names taken by other rows, but always keep this row's own current selection so it stays visible.
  const names = getAffixNames(pool, source)
    .filter(n => n === selectedName || !excludeNames?.has(n))
  // Only tiers this rarity can reach (e.g. an epic memory can't roll a T0 = ultimate-only tier).
  const tierEntries = selectedName ? getTierOptions(pool, source, selectedName).filter(e => e.tier >= (minTier ?? 0)) : []
  const tierRanges = buildTierRanges(tierEntries)
  const sliderMax = tierRanges.length > 0 ? tierRanges[tierRanges.length - 1].endPos : 0

  const currentPos = current && tierRanges.length > 0
    ? tierValueToPos(tierRanges, current.tier, current.rolledValue)
    : 0
  const currentTierInfo = tierRanges.length > 0 ? posToTierValue(tierRanges, currentPos) : null

  const resolvedText = current ? resolveMemoryEffect(current) : null
  // Base stat (hideSlider): the value lives in the modifier TEXT (rolledValue=null, level-driven), NOT in the
  // tier/rolledValue the slider path reads — so parse it directly for the read-only value display.
  const baseTextValue = current ? parseFloat(current.modifier.match(/^\+?(\d+(?:\.\d+)?)/)?.[1] ?? 'NaN') : NaN
  // The modeling-status badge depends only on the modifier TYPE, not the rolled value. Key it off a
  // value-INDEPENDENT text (the modifier template, value stripped) so dragging the slider doesn't re-request
  // the mapping and flap the badge — that flap reflowed the label and resized the flex slider (the flashing).
  // Strip BOTH roll forms so the badge key stays value-independent (a multi-range affix keeps rolledValues,
  // which would otherwise change the text on every range-slider drag → re-request the mapping → badge flap).
  const modStatus = useTextModifierStatus(current ? resolveMemoryEffect({ ...current, rolledValue: null, rolledValues: undefined }) : null, 'memory')

  const handleNameChange = (name: string) => {
    if (!name) { onChange(null); return }
    const entries = getTierOptions(pool, source, name).filter(e => e.tier >= (minTier ?? 0))
    if (entries.length === 0) { onChange(null); return }
    // Multi-range combo affix (independent rolls): pick the best reachable tier (smallest tier number) and
    // default each roll to its max (best), captured in rolledValues.
    if (memoryRangeCount(entries[0].modifier) >= 2) {
      const best = entries.reduce((a, b) => (a.tier <= b.tier ? a : b))
      onChange({ modifier: best.modifier, tier: best.tier, rolledValue: null, rolledValues: memoryRangeBounds(best.modifier).map(b => b.max) })
      return
    }
    const ranges = buildTierRanges(entries)
    const best = ranges[ranges.length - 1]
    const pos = Math.floor((best.startPos + best.endPos) / 2)
    const { tier, value, modifier } = posToTierValue(ranges, pos)
    onChange({ modifier, tier, rolledValue: hasRange(modifier) ? value : null })
  }

  // Click-to-edit an exact roll: pick the tier whose value range holds V (prefer the higher tier on overlap),
  // then set that tier + value. Mirrors the gear editors' tier-match (hero memories have no Desecration).
  const commitValue = (v: number) => {
    if (tierRanges.length === 0) return
    const containing = tierRanges.filter(r => v >= r.min - 1e-6 && v <= r.max + 1e-6)
    const target = containing.length
      ? containing.reduce((a, b) => (b.max >= a.max ? b : a))                     // higher tier on overlap
      : tierRanges.reduce((a, b) => (Math.abs(b.max - v) < Math.abs(a.max - v) ? b : a))  // nearest
    const clamped = Math.min(target.max, Math.max(target.min, v))
    onChange({ modifier: target.modifier, tier: target.tier, rolledValue: hasRange(target.modifier) ? clamped : null })
  }
  const editDp = Math.max(0, ...tierRanges.flatMap(r => [r.min, r.max].map(n => (String(n).split('.')[1] || '').length)))
  const editRange: [number, number] = tierRanges.length
    ? [Math.min(...tierRanges.map(r => r.min)), Math.max(...tierRanges.map(r => r.max))]
    : [0, 0]

  // Multi-range combo affix (e.g. Combo Starter speed + Combo Finisher crit dmg): two+ INDEPENDENT rolls on
  // one line, edited by a tier picker + one input per range (the single tier-slider can't represent them).
  const multiRange = tierEntries.length > 0 && memoryRangeCount(tierEntries[0].modifier) >= 2
  const setRangeValue = (i: number, v: number) => {
    if (!current) return
    const bounds = memoryRangeBounds(current.modifier)
    const b = bounds[i]; if (!b) return
    const next = [...(current.rolledValues ?? bounds.map(x => x.max))]
    next[i] = Math.min(b.max, Math.max(b.min, v))
    onChange({ ...current, rolledValue: null, rolledValues: next })
  }
  // Switch tier: adopt the new tier's template + clamp each existing roll into the new bounds (null → new max).
  const changeTier = (entry: HeroMemoryAffix) => {
    const bounds = memoryRangeBounds(entry.modifier)
    const prev = current?.rolledValues ?? []
    const next = bounds.map((b, i) => { const v = prev[i]; return v == null ? b.max : Math.min(b.max, Math.max(b.min, v)) })
    onChange({ modifier: entry.modifier, tier: entry.tier, rolledValue: null, rolledValues: next })
  }

  return (
    <>
      <div className="memory-affix-row" {...(resolvedText ? tip.triggerProps : {})}>
        <span className="memory-affix-label">{label}</span>
        <div className="memory-affix-controls">
          {/* Badge lives INSIDE the dropdown trigger (like gear creation) — the trigger is a fixed element,
              so a badge change never reflows anything outside it, and the slider below can't flash. */}
          <SearchableAffixSelect value={selectedName} options={names}
            badge={<ModifierBadge status={modStatus} />} onChange={handleNameChange} />

          {selectedName && !multiRange && tierRanges.length > 0 && currentTierInfo && (
            <div className="memory-tier-slider-row">
              {/* Base stat (hideSlider): value is driven by the memory level, shown read-only — no tier slider.
                  A single fixed value also has no positions to slide (sliderMax === 0). */}
              {!hideSlider && sliderMax > 0 && (
                <TierSlider tiers={tierRanges} curTier={current!.tier} curValue={currentTierInfo.value} dp={editDp}
                  onPick={(tier, value, modifier) => onChange({ modifier, tier, rolledValue: hasRange(modifier) ? value : null })} />
              )}
              {/* Fixed-width value column so digit changes never reflow the slider (a reflow source of the flash). */}
              <span className="memory-affix-value-col">
                {!hideSlider && sliderMax > 0
                  ? <EditableRollValue value={currentTierInfo.value} dp={editDp} range={editRange} color={color} onCommit={commitValue} />
                  : (() => {
                      // For the base stat, show the level-driven value from the modifier text; otherwise (a
                      // single fixed-value affix) the tier value is the value.
                      const v = hideSlider && !Number.isNaN(baseTextValue) ? baseTextValue : currentTierInfo.value
                      return <span className="memory-affix-slider-val" style={{ color }}>
                        {Number.isInteger(v) ? v : dec(v)}
                      </span>
                    })()}
              </span>
            </div>
          )}

          {/* Multi-range combo affix: a tier picker + one slider/input per INDEPENDENT range (they roll
              separately in-game, so a single tier-slider can't represent both). */}
          {selectedName && multiRange && current && (() => {
            const bounds = memoryRangeBounds(current.modifier)
            const vals = current.rolledValues ?? bounds.map(b => b.max)
            // Per-range label = the stat text following each range token (drop leading %, trailing "+").
            const labels = current.modifier.split(/\(-?\d+(?:\.\d+)?[–\-]-?\d+(?:\.\d+)?\)/).slice(1)
              .map(s => s.replace(/^\s*%?\s*/, '').replace(/\s*\+\s*$/, '').trim())
            const tierOpts = [...tierEntries].sort((a, b) => a.tier - b.tier)
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
                {tierOpts.length > 1 && (
                  <select className="gear-placeholder-select" value={current.tier}
                    onChange={e => { const t = tierOpts.find(x => x.tier === Number(e.target.value)); if (t) changeTier(t) }}>
                    {tierOpts.map(t => <option key={t.tier} value={t.tier}>{`T${t.tier}`}</option>)}
                  </select>
                )}
                {bounds.map((b, i) => {
                  const dp = Math.max((String(b.min).split('.')[1] || '').length, (String(b.max).split('.')[1] || '').length)
                  const step = dp > 0 ? parseFloat((1 / Math.pow(10, dp)).toFixed(dp)) : 1
                  const v = vals[i] ?? b.max
                  return (
                    <div key={i} className="memory-tier-slider-row">
                      <input type="range" className="gear-affix-slider" min={b.min} max={b.max} step={step} value={v}
                        onChange={e => setRangeValue(i, Number(e.target.value))} />
                      <span className="memory-affix-value-col">
                        <EditableRollValue value={v} dp={dp} range={[b.min, b.max]} color={color} onCommit={x => setRangeValue(i, x)} />
                      </span>
                      {labels[i] && <span style={{ fontSize: 11, color: 'var(--fg-muted)', flexBasis: '100%' }}>{labels[i]}</span>}
                    </div>
                  )
                })}
              </div>
            )
          })()}
        </div>
      </div>
      {resolvedText && tip.open && (
        <FloatingPortal>
          <div className="memory-affix-hover-tooltip" {...tip.floatingProps}>{resolvedText}</div>
        </FloatingPortal>
      )}
    </>
  )
}

// The Holy Domain trait-skill slot: a circular button (memory-slot style) that opens a centered overlay to
// socket ONE support (a Support Skill or Activation Medium support) into the trait skill. Inert until the
// Barrier/Guard systems land — but slotting Guard here will then auto-grant Barrier with no Rosa revisit.
function TraitSkillSlot({ supports, allSkills, onChange }: {
  supports: EquippedSupportSkill[]; allSkills: SkillItem[]; onChange: (s: EquippedSupportSkill[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const socketed = supports[0] ?? null

  const compatible = useMemo(() => {
    const base = allSkills.filter(it =>
      ((it.skill_type ?? '').includes('support') || (it.skill_tags ?? []).includes('Activation Medium'))
      && isSupportCompatible(it, TRAIT_SKILL_PARENT, false, 1, true))
    if (!search.trim()) return base
    const q = search.toLowerCase()
    return base.filter(it => it.name.toLowerCase().includes(q)
      || (it.skill_tags ?? []).some(t => t.toLowerCase().includes(q)))
  }, [allSkills, search])

  const pick = (it: SkillItem) => {
    onChange([{
      support_index: 1, item_id: it.item_id, name: it.name,
      skill_type: it.skill_type ?? 'support_skill', level: 20,
      skill_tags: it.skill_tags ?? [], description_lines: it.description_lines ?? [], enabled: true,
    }])
    setOpen(false); setSearch('')
  }

  return (
    <>
      <div
        className={`memory-slot-circle${socketed ? ' filled' : ''}`}
        style={socketed ? { borderColor: '#c8a86a', boxShadow: '0 0 10px #c8a86a44' } : undefined}
        title="Holy Domain — Support Slot"
        onClick={e => { e.stopPropagation(); setOpen(true) }}
      >
        {socketed
          ? <span style={{ color: '#e0c890', fontSize: 10, fontWeight: 700, textAlign: 'center', padding: '0 2px', lineHeight: 1.05 }}>{socketed.name}</span>
          : <span className="memory-slot-plus">+</span>}
      </div>
      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()} style={{ maxWidth: 460, width: '90%' }}>
            <div className="modal-accent" />
            <h3 className="modal-title">Holy Domain — Support Slot</h3>
            <div style={{ fontSize: 11, color: '#888', marginBottom: 8 }}>
              Install a Support Skill or Activation Medium support to modify the Holy Domain trait skill.
            </div>
            <input
              autoFocus value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search supports…"
              style={{ width: '100%', padding: '6px 8px', marginBottom: 8, background: '#0d0d1e',
                border: '1px solid #3a3a5a', borderRadius: 4, color: '#ddd', fontSize: 12 }}
            />
            {socketed && (
              <button className="btn btn-danger" style={{ marginBottom: 8 }}
                onClick={() => { onChange([]); setOpen(false) }}>
                Remove {socketed.name}
              </button>
            )}
            <div style={{ maxHeight: 360, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
              {compatible.length === 0
                ? <div style={{ color: '#777', fontSize: 12, padding: 8 }}>No compatible supports found.</div>
                : compatible.map(it => (
                  <div key={it.item_id} onClick={() => pick(it)}
                    style={{ padding: '6px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 12,
                      background: socketed?.item_id === it.item_id ? 'rgba(200,168,106,0.18)' : 'rgba(255,255,255,0.03)',
                      color: '#ddd' }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(200,168,106,0.12)')}
                    onMouseLeave={e => (e.currentTarget.style.background = socketed?.item_id === it.item_id ? 'rgba(200,168,106,0.18)' : 'rgba(255,255,255,0.03)')}>
                    <div style={{ fontWeight: 600 }}>{it.name}</div>
                    <div style={{ fontSize: 10, color: '#888' }}>{(it.skill_tags ?? []).join(' · ')}</div>
                  </div>
                ))}
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setOpen(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// A single memory tile in the inventory overlay. The box is FILLED by the rarity color (rarity is read
// from the color, not text — no rarity/affix-count line), with the natural type icon on its rarity glow,
// its equipped state ("Equipped · <slot>") or an Equip action, plus edit / duplicate / remove controls.
function MemoryInventoryTile({ memory, equippedSlot, icon, onEquip, onUnequip, onEdit, onDelete, onDuplicate, onRename,
  baseEquipped, canEquipBase, onEquipBase, onUnequipBase }: {
  memory: CreatedHeroMemory
  equippedSlot: number | null   // socketed slot index, or null if not equipped
  icon?: string | null          // type icon (bundled webp); falls back to ◈ until icon data lands
  onEquip: () => void; onUnequip: () => void; onEdit: () => void; onDelete: () => void; onDuplicate: () => void
  onRename: (next: string) => void   // sets the DISPLAY label only (true "Memory of <Type>" name kept in the card)
  // Base/Special slot: this memory is currently in the base slot, and/or is eligible to be equipped there.
  baseEquipped?: boolean; canEquipBase?: boolean; onEquipBase?: () => void; onUnequipBase?: () => void
}) {
  const color = MEMORY_RARITY_COLORS[memory.rarity]
  const iconBtn: React.CSSProperties = { fontSize: 11, lineHeight: 1, padding: '2px 6px', background: 'rgba(0,0,0,0.35)', border: '1px solid rgba(255,255,255,0.14)', borderRadius: 4, color: '#ddd', cursor: 'pointer' }
  const equipped = equippedSlot !== null
  const label = memory.displayName ?? MEMORY_TYPE_LABELS[memory.memoryType]
  // Hover the icon/name to see the full in-game-style card; click it to edit.
  const tip = useFloatingTooltip({ anchor: 'element', side: 'right' })
  // Inline rename (mirrors gear's Rename): swaps the action row into an input; commit sets the label only.
  const [renaming, setRenaming] = useState(false)
  const [renameDraft, setRenameDraft] = useState('')
  const commitRename = () => { onRename(renameDraft); setRenaming(false) }
  return (
    <>
    <div style={{ position: 'relative', width: 152, border: `1px solid ${color}`, borderRadius: 8,
      background: `linear-gradient(160deg, ${color}33, ${color}12), #14141f`, padding: '8px 10px',
      boxShadow: equipped ? `0 0 9px ${color}66` : undefined }}>
      <div {...tip.triggerProps} onClick={onEdit} title="Edit"
        style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5, cursor: 'pointer' }}>
        <MemoryIcon icon={icon ?? null} tint={color} size={28} glyphSize={16} />
        <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {label}
          {memory.level ? <span style={{ fontWeight: 400, color: 'rgba(255,255,255,0.7)' }}> · Lv {memory.level}</span> : null}
        </span>
      </div>
      {(memory.revived || memory.waxAndWane) && (
        <div style={{ fontSize: 9, color: '#f0d0a0', marginBottom: 4 }}>
          {[memory.revived ? 'Revived' : '', memory.waxAndWane ? 'Wax & Wane' : ''].filter(Boolean).join(' · ')}
        </div>
      )}
      <div style={{ fontSize: 10, marginBottom: 6, color: equipped || baseEquipped ? '#bff0bf' : 'rgba(255,255,255,0.55)', fontWeight: equipped || baseEquipped ? 700 : 400 }}>
        {baseEquipped ? 'Equipped · Base slot' : equipped ? `Equipped · ${MEMORY_SLOT_LABELS[equippedSlot!] ?? `Slot ${equippedSlot! + 1}`}` : 'Not equipped'}
      </div>
      {renaming ? (
        <input className="gear-build-rename-input" autoFocus value={renameDraft} placeholder="Display name…"
          onChange={e => setRenameDraft(e.target.value)} onBlur={commitRename}
          onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setRenaming(false) }} />
      ) : (
        // Two rows so the (wider) Equip/Unequip button + the 3 icon buttons never overflow the 152px tile.
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          {equipped
            ? <button className="btn btn-secondary" style={{ fontSize: 10, padding: '3px 10px', alignSelf: 'flex-start' }} onClick={onUnequip}>Unequip</button>
            : <button className="btn btn-primary" style={{ fontSize: 10, padding: '3px 10px', alignSelf: 'flex-start' }} onClick={onEquip}>Equip</button>}
          {baseEquipped
            ? <button className="btn btn-secondary" style={{ fontSize: 10, padding: '3px 10px', alignSelf: 'flex-start' }} onClick={onUnequipBase}>Unequip Base</button>
            : canEquipBase
              ? <button className="btn btn-secondary" style={{ fontSize: 10, padding: '3px 10px', alignSelf: 'flex-start' }} onClick={onEquipBase}>Equip → Base</button>
              : null}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button title="Rename" style={iconBtn} onClick={() => { setRenameDraft(memory.displayName ?? ''); setRenaming(true) }}>✎</button>
            <button title="Duplicate" style={iconBtn} onClick={onDuplicate}>⧉</button>
            <button title="Remove from inventory" style={{ ...iconBtn, color: '#e59' }} onClick={onDelete}>✕</button>
          </div>
        </div>
      )}
    </div>
    {tip.open && (
      <FloatingPortal>
        <div className="memory-tooltip-card" {...tip.floatingProps}>
          <MemoryPreviewCard memory={memory} icon={icon ?? null} />
        </div>
      </FloatingPortal>
    )}
    </>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function HeroTraitScreen({ onBack: _onBack, onDefaultTraitApplied }: Props) {
  const traitId = useBuildStore(s => s.traitId)
  const traitSlotLevels = useBuildStore(s => s.traitSlotLevels)
  const advancedTraitSelections = useBuildStore(s => s.advancedTraitSelections)
  const traitTreeAllocations = useBuildStore(s => s.traitTreeAllocations)
  const setTraitTreeAllocations = useBuildStore(s => s.setTraitTreeAllocations)
  // Trait-tier unlocks use the `level` condition (default 90) — the single character-level source.
  const characterLevel = characterLevelFrom(useBuildStore(s => s.conditionState))
  const heroMemories = useBuildStore(s => s.heroMemories)
  const baseMemory = useBuildStore(s => s.baseMemory)
  const setBaseMemory = useBuildStore(s => s.setBaseMemory)
  const memoryInventory = useBuildStore(s => s.memoryInventory)
  const setMemoryInventory = useBuildStore(s => s.setMemoryInventory)
  const loadouts = useBuildStore(s => s.loadouts)
  const activeLoadoutId = useBuildStore(s => s.activeLoadoutId)
  const setTraitData = useBuildStore(s => s.setTraitData)
  const setHeroMemories = useBuildStore(s => s.setHeroMemories)
  const traitSkillSupports = useBuildStore(s => s.traitSkillSupports)
  const setTraitSkillSupports = useBuildStore(s => s.setTraitSkillSupports)
  // Licorice Note (Sage) — the Empower/Curse the trait "prepares" (Pungent cross-apply target).
  const skills = useBuildStore(s => s.skills)
  const licoricePreparedSkill = useBuildStore(s => s.licoricePreparedSkill)
  const setLicoricePreparedSkill = useBuildStore(s => s.setLicoricePreparedSkill)
  const elixirIngredients = useBuildStore(s => s.elixirIngredients)
  const setElixirIngredients = useBuildStore(s => s.setElixirIngredients)
  const traitWarnings = (useBuildStore(s => (s.computedStats as { warnings?: { kind: string; text: string }[] | null }).warnings) ?? [])
    .filter(w => w.kind === 'trait')
  const allSkills = useReferenceStore(s => s.skills) ?? []
  const allTraits = useReferenceStore(s => s.heroTraits) ?? []
  const memoryData = useReferenceStore(s => s.heroMemories)
  const memoryRevival = useReferenceStore(s => s.memoryRevival) ?? []
  // Local <memoryType> → bundled icon URL. memory_types rows are named "Memory of Origin" etc.; pair each
  // to our 'origin'|'discipline'|'progress' key via MEMORY_TYPE_LABELS, then resolve the CDN url → bundled webp.
  // Returns null until the data-scraper lands per-type icons in tli-data (graceful: buttons fall back to a glyph).
  const memoryTypeIcon = useMemo(() => {
    const byName = new Map((memoryData?.memory_types ?? []).map((t: HeroMemoryType) => [t.name, t.icon_url]))
    const out = {} as Record<CreatedHeroMemory['memoryType'], string | null>
    ;(['origin', 'discipline', 'progress'] as const).forEach(k => {
      out[k] = iconUrl('hero_memory', byName.get(`Memory of ${MEMORY_TYPE_LABELS[k]}`))
    })
    return out
  }, [memoryData])
  const referenceResolved = useReferenceStore(s => s.referenceResolved)
  const traitsFailed = useReferenceStore(s => s.failedCatalogs.has('heroTraits'))

  const [creatorSlot, setCreatorSlot] = useState<number | null>(null)
  const [creatorBase, setCreatorBase] = useState(false)   // creating/editing the Base/Special-slot memory
  const [draft, setDraft] = useState<CreatedHeroMemory | null>(null)
  const [inventoryOpen, setInventoryOpen] = useState(false)
  const [inventoryView, setInventoryView] = useState<'current' | 'all'>('current')

  const loading = !referenceResolved && allTraits.length === 0

  // Auto-select the first trait only for a brand-new (never-saved) build. Builds now LAND on
  // this screen when opened, so an unconditional auto-select would silently write a trait into
  // an opened trait-less build — marking it dirty and clearing tree allocations for a
  // DPS-affecting change the user never made.
  const buildId = useBuildStore(s => s.buildId)
  useEffect(() => {
    if (!loading && traitId === null && buildId === null && allTraits.length > 0) {
      setTraitData(allTraits[0].trait_id, [1, 1, 1, 1], [])
      // This is a DEFAULT, not a user edit — let App re-baseline the dirty tracker so the fresh build
      // isn't flagged dirty by the auto-select's buildVersion bump.
      onDefaultTraitApplied?.()
    }
  }, [loading, traitId, buildId, allTraits, setTraitData, onDefaultTraitApplied])

  const selectedTrait = allTraits.find(t => t.trait_id === traitId) ?? null

  const safeSlotLevels = (
    Array.isArray(traitSlotLevels) && traitSlotLevels.length === 4
      ? traitSlotLevels
      : [1, 1, 1, 1]
  )

  // Phase B: the advanced slots (45/60/75) are DERIVED from the socketed memories (SET to the memory's trait
  // level; 0 = inactive when empty) so the DISPLAY matches the engine payload (same deriveTraitSlotLevels) —
  // uniformly for every trait, including tree-styled ones (they differ only in allocation). Base slot [0] is
  // passed through. The mutation helpers below still write the STORED array (selection/base only).
  const displaySlotLevels = deriveTraitSlotLevels(heroMemories, safeSlotLevels, baseMemory)

  // Base/Special slot: the enabler is the base-slot mod on the equipped revived memory (if any); the base slot
  // is available only while an enabler is equipped. `baseSlot` is the validly-socketed base memory (type + rarity
  // match the enabler), else null even if `baseMemory` holds a now-invalid one (e.g. the enabler was removed).
  const baseEnabler = activeBaseSlotEnabler(heroMemories)
  const baseSlot = resolveBaseSlot(heroMemories, baseMemory)

  // A slot level < 1 = the node is INACTIVE/disabled (empty memory slot, or a remembered-disabled base tier).
  const nodeDisabled = (slotIdx: number) => displaySlotLevels[slotIdx] < 1
  const nodeLevel = (slotIdx: number) => Math.max(1, Math.min(5, Math.abs(displaySlotLevels[slotIdx])))
  const baseLevel = nodeLevel(SLOT_BASE)
  const baseDisabled = nodeDisabled(SLOT_BASE)
  const baseEffects = selectedTrait?.levels[baseLevel - 1]?.effects ?? []
  const showArtificialMoon = baseLevel === 5 && (selectedTrait?.artificial_moon?.effects?.length ?? 0) > 0

  // NOTE: the manual 1–5 trait-slot-level selector was removed (owner) — the level will be DERIVED from the
  // socketed memory's rarity/trait-level in Phase B. Until then slot levels stay at their stored/default value.

  // Slot levels with `slotIdx` forced ENABLED (positive, remembered magnitude) — selecting/left-clicking enables.
  const withEnabled = (slotIdx: number) => {
    const n = [...safeSlotLevels]
    n[slotIdx] = Math.abs(n[slotIdx]) || 1
    return n
  }

  // Pick a node within its group: clear the group's other selections, add this one, and (re)enable the tier.
  function selectInGroup(name: string, threshold: number, groupNames: string[]) {
    if (!traitId) return
    const next = advancedTraitSelections.filter(n => !groupNames.includes(n))
    next.push(name)
    setTraitData(traitId, withEnabled(SLOT_IDX[threshold]), next)
  }

  // Enable a tier (left-clicking a guaranteed node, which has no choice, just (re)enables its tier).
  function enableTier(threshold: number) {
    if (!traitId) return
    setTraitData(traitId, withEnabled(SLOT_IDX[threshold]), advancedTraitSelections)
  }

  function switchTrait(newTraitId: string) {
    setTraitData(newTraitId, [1, 1, 1, 1], [])
    setTraitSkillSupports([])
  }

  // A DISABLED node is stored as a NEGATIVE slot level (remembers the magnitude); the engine skips tiers whose
  // level < 1. LEFT-click enables/selects a node; RIGHT-click disables it.
  function enableNode(slotIdx: number) {
    if (!traitId) return
    setTraitData(traitId, withEnabled(slotIdx), advancedTraitSelections)
  }

  function disableNode(slotIdx: number) {
    if (!traitId) return
    const next = [...safeSlotLevels]
    next[slotIdx] = -(Math.abs(next[slotIdx]) || 1)
    setTraitData(traitId, next, advancedTraitSelections)
  }

  // ── Memory creator / inventory helpers ────────────────────────────────────
  // The creator is shared by three entry points: a slot's "+" (type preset; auto-equips on create if the
  // slot is empty), the overlay's "Create Hero Memory" (type selectable), and editing an existing memory.

  const freshDraft = (memoryType: CreatedHeroMemory['memoryType']): CreatedHeroMemory => ({
    id: genMemoryId(), memoryType, rarity: 'epic', level: MAX_LEVEL_BY_RARITY.epic,
    baseStat: null, fixedAffixes: [null, null], randomAffixes: [null, null],
    revived: false, revivalMod: null, waxAndWane: false,
  })
  const editDraft = (m: CreatedHeroMemory): CreatedHeroMemory => ({
    ...m, fixedAffixes: [m.fixedAffixes[0], m.fixedAffixes[1]], randomAffixes: [m.randomAffixes[0], m.randomAffixes[1]],
  })

  function openMemoryCreator(slotIdx: number) {
    const existing = heroMemories[slotIdx]
    if (existing) {
      // Socketed → open the editor for it.
      setDraft(editDraft(existing)); setCreatorSlot(slotIdx); setInventoryOpen(false)
      return
    }
    // Empty slot: if the loadout already owns a memory of this type, open the inventory to equip one instead
    // of jumping straight to Create. (Any type-T memory in inventory is unequipped here, since slot T is empty.)
    const type = MEMORY_TYPES[slotIdx]
    if (memoryInventory.some(m => m.memoryType === type)) {
      setInventoryView('current'); setInventoryOpen(true); setDraft(null); setCreatorSlot(null)
      return
    }
    setDraft(freshDraft(type)); setCreatorSlot(slotIdx); setInventoryOpen(false)
  }
  function openMemoryCreatorNew() { setDraft(freshDraft('origin')); setCreatorSlot(null); setCreatorBase(false) }
  function openMemoryEditor(mem: CreatedHeroMemory) { setDraft(editDraft(mem)); setCreatorSlot(null); setCreatorBase(false) }
  function closeCreator() { setCreatorSlot(null); setCreatorBase(false); setDraft(null) }

  // Whether an inventory memory may go in the Base/Special slot: an enabler is equipped, the memory is
  // NON-revived, its type matches the enabler's, its rarity is within the enabler's cap, and it isn't already
  // socketed in a normal slot (the same id can't occupy both — that would double-count it in the engine).
  const baseEligible = (m: CreatedHeroMemory): boolean =>
    !!baseEnabler && !m.revived && m.memoryType === baseEnabler.type && rarityWithinCap(m.rarity, baseEnabler.rarityCap)
    && !heroMemories.some(hm => hm?.id === m.id)

  function confirmMemory() {
    if (!draft) return
    // Upsert into the inventory by id (covers both create and edit).
    const inv = useBuildStore.getState().memoryInventory
    const byId = new Map(inv.map(m => [m.id, m]))
    byId.set(draft.id, draft)
    setMemoryInventory([...byId.values()])
    // Keep the equipped copy in sync (normal slot OR base slot); else auto-equip into the "+"-targeted slot.
    const socketIdx = heroMemories.findIndex(m => m?.id === draft.id)
    if (baseMemory?.id === draft.id) {
      setBaseMemory(draft)
    } else if (socketIdx >= 0) {
      const next = [...heroMemories] as typeof heroMemories
      next[socketIdx] = draft
      setHeroMemories(next)
    } else if (creatorBase && !baseMemory && baseEligible(draft)) {
      setBaseMemory(draft)
    } else if (creatorSlot !== null && !heroMemories[creatorSlot]) {
      const next = [...heroMemories] as typeof heroMemories
      next[creatorSlot] = draft
      setHeroMemories(next)
    }
    closeCreator()
  }

  // Unequip: remove the memory from its slot (the copy stays in the inventory). Used by the slot-flow Remove.
  function clearMemory() {
    if (creatorSlot === null) return
    const next = [...heroMemories] as typeof heroMemories
    next[creatorSlot] = null
    setHeroMemories(next)
    closeCreator()
  }

  // Auto-keep every socketed memory in the loadout's inventory (mirrors SlateScreen's placed→inventory
  // sync). Upsert by id; only write when something actually changed so it can't loop. On a freshly loaded
  // build the socketed memories already share ids with the inventory, so this no-ops (no spurious dirty).
  useEffect(() => {
    const socketed = [...heroMemories, baseMemory].filter((m): m is CreatedHeroMemory => !!m)
    if (socketed.length === 0) return
    const inv = useBuildStore.getState().memoryInventory
    const byId = new Map(inv.map(m => [m.id, m]))
    let changed = false
    for (const m of socketed) {
      const prev = byId.get(m.id)
      if (!prev || JSON.stringify(prev) !== JSON.stringify(m)) { byId.set(m.id, m); changed = true }
    }
    if (changed) setMemoryInventory([...byId.values()])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [heroMemories, baseMemory])

  // Equip a memory from the inventory into the slot matching its type (replacing whatever's there).
  function equipMemory(mem: CreatedHeroMemory) {
    const slot = MEMORY_TYPE_TO_SLOT[mem.memoryType]
    if (slot === undefined) return
    const next = [...heroMemories] as typeof heroMemories
    next[slot] = mem
    setHeroMemories(next)
    // The same id can't occupy both a normal slot and the base slot (would double-count) — vacate the base slot.
    if (useBuildStore.getState().baseMemory?.id === mem.id) setBaseMemory(null)
  }
  // Unequip a memory (clear it from its socket); it stays in the inventory.
  function unequipMemory(mem: CreatedHeroMemory) {
    const socketed = useBuildStore.getState().heroMemories
    setHeroMemories(socketed.map(m => (m?.id === mem.id ? null : m)) as typeof socketed)
  }

  // ── Base/Special slot equip flow ──────────────────────────────────────────────
  function equipBaseMemory(mem: CreatedHeroMemory) { if (baseEligible(mem)) setBaseMemory(mem) }
  function unequipBaseMemory() { setBaseMemory(null) }
  // The base "+": edit the socketed base memory, or (no base yet) open the inventory to equip an eligible one,
  // or create a fresh memory locked to the enabler's type + rarity cap (non-revived).
  function openBaseCreator() {
    if (!baseEnabler) return
    if (baseMemory) { setDraft(editDraft(baseMemory)); setCreatorBase(true); setCreatorSlot(null); setInventoryOpen(false); return }
    if (memoryInventory.some(baseEligible)) { setInventoryView('current'); setInventoryOpen(true); setDraft(null); setCreatorSlot(null); return }
    const rarity: MemoryRarity = rarityWithinCap('epic', baseEnabler.rarityCap) ? 'epic' : baseEnabler.rarityCap
    setDraft({ ...freshDraft(baseEnabler.type), rarity, level: MAX_LEVEL_BY_RARITY[rarity] })
    setCreatorBase(true); setCreatorSlot(null); setInventoryOpen(false)
  }

  function deleteFromInventory(id: string) {
    // If the memory is socketed (normal OR base slot), unequip it too — otherwise the socketed→inventory
    // auto-sync re-adds it (the tile would vanish yet the memory keeps contributing and reappears).
    const socketed = useBuildStore.getState().heroMemories
    if (socketed.some(m => m?.id === id)) {
      setHeroMemories(socketed.map(m => (m?.id === id ? null : m)) as typeof socketed)
    }
    if (useBuildStore.getState().baseMemory?.id === id) setBaseMemory(null)
    setMemoryInventory(useBuildStore.getState().memoryInventory.filter(m => m.id !== id))
  }
  function duplicateInInventory(id: string) {
    const inv = useBuildStore.getState().memoryInventory
    const src = inv.find(m => m.id === id)
    if (!src) return
    const copy: CreatedHeroMemory = { ...(JSON.parse(JSON.stringify(src)) as CreatedHeroMemory), id: genMemoryId() }
    setMemoryInventory([...inv, copy])
  }
  // Rename sets the DISPLAY label only (mirrors gear's renameBuildItem): strip control chars, cap 60, and
  // clear when empty or equal to the default type name. Updates both the inventory copy and any equipped copy.
  function renameMemory(id: string, nextRaw: string) {
    const next = nextRaw.replace(/\p{C}/gu, '').trim().slice(0, 60)
    const relabel = (m: CreatedHeroMemory): CreatedHeroMemory =>
      ({ ...m, displayName: next && next !== MEMORY_TYPE_LABELS[m.memoryType] ? next : undefined })
    const inv = useBuildStore.getState().memoryInventory
    setMemoryInventory(inv.map(m => (m.id === id ? relabel(m) : m)))
    const socketed = useBuildStore.getState().heroMemories
    if (socketed.some(m => m?.id === id)) {
      setHeroMemories(socketed.map(m => (m?.id === id ? relabel(m) : m)) as typeof socketed)
    }
    const bm = useBuildStore.getState().baseMemory
    if (bm?.id === id) setBaseMemory(relabel(bm))
  }

  // All-loadouts view GROUPED by the owning loadout's name (a header per loadout), deduped by id. The
  // ACTIVE loadout is processed FIRST (and uses its LIVE inventory) so its up-to-date copy wins on an id
  // collision — e.g. a duplicated loadout shares memory ids; the stale non-active copy must not shadow it.
  const aggregateGroups = useMemo(() => {
    const seen = new Set<string>()
    const groups: { name: string; memories: CreatedHeroMemory[] }[] = []
    const ordered = [...loadouts].sort((a, b) => (a.id === activeLoadoutId ? -1 : b.id === activeLoadoutId ? 1 : 0))
    for (const l of ordered) {
      const inv = l.id === activeLoadoutId
        ? memoryInventory
        : ((l.data?.memories as { memoryInventory?: CreatedHeroMemory[] } | undefined)?.memoryInventory ?? [])
      const mems: CreatedHeroMemory[] = []
      for (const m of inv) if (m?.id && !seen.has(m.id)) { seen.add(m.id); mems.push(m) }
      if (mems.length) groups.push({ name: l.name, memories: mems })
    }
    return groups
  }, [memoryInventory, loadouts, activeLoadoutId])
  // id → the slot index a memory is currently equipped in (for the tile's "Equipped · <slot>" label).
  const equippedSlotById = new Map<string, number>()
  heroMemories.forEach((m, i) => { if (m) equippedSlotById.set(m.id, i) })

  // Live damage-delta of the memory being built, for the creator preview footer — as if the draft were
  // equipped in its type's slot. Keyed on the draft's content so it recomputes as affixes/level change.
  const draftPreviewKey = draft
    ? JSON.stringify({ t: draft.memoryType, lv: draft.level, b: draft.baseStat, f: draft.fixedAffixes, r: draft.randomAffixes, w: draft.waxAndWane, rv: draft.revivalMod })
    : ''
  const draftPreviewDelta = useDamageDelta(
    draft
      ? { key: `mem:prev:${draftPreviewKey}`, step: s => ({ ...s, heroMemories: s.heroMemories.map((m, i) => i === MEMORY_TYPE_TO_SLOT[draft.memoryType] ? draft : m) as typeof s.heroMemories }) }
      : null,
    !!draft,
  )

  if (loading) {
    return (
      <div className="hero-trait-screen">
        <div className="hero-trait-body"><LoadingState label="Loading hero traits…" /></div>
      </div>
    )
  }

  if (traitsFailed && allTraits.length === 0) {
    return (
      <div className="hero-trait-screen">
        <div className="hero-trait-body">
          <div className="panel-empty" style={{ color: '#ff6b6b' }}>Couldn't load trait data — restart to retry.</div>
        </div>
      </div>
    )
  }

  // Compute a base-stat selection for (type, stat name, rarity, level) from the season-stable scaling table
  // (source: MinMaxedARPG), interpolated piecewise-linearly between the per-rarity anchors. Keeps a tier's
  // modifier text as a FORMATTING TEMPLATE and substitutes the computed value into its leading +N; the value
  // lives in the text (rolledValue=null, matching the pool's fixed base-stat shape) so wax/penalty scaling
  // operates on the +N. Rounds to 1 decimal (source precision; anchor levels exact, between-anchor interpolated).
  // Falls back to the old coarse tier-ladder heuristic only if the table lacks the stat (e.g. an old backend).
  // Shared by the creator's live edits AND rarity/level changes so the base value always tracks all three axes.
  const scaleBaseStat = (memoryType: CreatedHeroMemory['memoryType'], name: string, rarity: MemoryRarity, lvl: number): MemorySlotSelection | null => {
    if (!memoryData) return null
    const affixSource = MEMORY_SOURCES[MEMORY_TYPE_TO_SLOT[memoryType]]
    const opts = getTierOptions(memoryData.base_stats, affixSource, name)
    if (!opts.length) return null
    const scaled = heroMemoryBaseStatValue(memoryData.base_stat_scaling, memoryType, name, rarity, lvl)
    if (scaled != null) {
      const minTier = rarity === 'normal' ? 4 : TIER_RARITY.indexOf(rarity)
      const modifier = opts[0].modifier.replace(/^\+?\d+(?:\.\d+)?/, '+' + String(Math.round(scaled * 10) / 10))
      return { modifier, tier: minTier, rolledValue: null }
    }
    // Fallback: coarse memory-level FRACTION → tier ladder (worst→best by value).
    const ranges = buildTierRanges(opts)
    if (!ranges.length) return null
    const byVal = [...ranges].sort((a, b) => a.max - b.max)
    const maxLv = MAX_LEVEL_BY_RARITY[rarity]
    const frac = maxLv > 1 ? (lvl - 1) / (maxLv - 1) : 1
    const r = byVal[Math.max(0, Math.min(byVal.length - 1, Math.round(frac * (byVal.length - 1))))]
    const value = Math.round((r.min + r.max) / 2)
    return { modifier: r.modifier, tier: r.tier, rolledValue: hasRange(r.modifier) ? value : null }
  }

  // ── Creator modal (shared by slot "+", the overlay's Create, and Edit) ──────
  const setDraftRarity = (rarity: MemoryRarity) => {
    if (!draft) return
    const maxLv = MAX_LEVEL_BY_RARITY[rarity]
    // Changing rarity defaults the level to the new rarity's MAX (owner) — going up raises to the new cap,
    // going down lands on the lower cap; the user can then dial it back down if they want.
    const newLevel = maxLv
    const fixedN = RARITY_FIXED_COUNT[rarity], randomN = RARITY_RANDOM_COUNT[rarity]
    setDraft({
      ...draft, rarity, level: newLevel,
      // Base stat re-scales to the new rarity's curve (at the new max level).
      baseStat: draft.baseStat ? (scaleBaseStat(draft.memoryType, getAffixName(draft.baseStat.modifier), rarity, newLevel) ?? draft.baseStat) : null,
      // Trim affix selections the new rarity can't hold.
      fixedAffixes: [fixedN >= 1 ? draft.fixedAffixes[0] : null, fixedN >= 2 ? draft.fixedAffixes[1] : null],
      randomAffixes: [randomN >= 1 ? draft.randomAffixes[0] : null, randomN >= 2 ? draft.randomAffixes[1] : null],
    })
  }

  const creatorModal = draft && memoryData ? (() => {
    const d = draft
    const rarity = d.rarity
    const maxLv = MAX_LEVEL_BY_RARITY[rarity]
    const level = d.level ?? maxLv
    const fixedN = RARITY_FIXED_COUNT[rarity], randomN = RARITY_RANDOM_COUNT[rarity]
    // Best tier this rarity can reach: ultimate→T0, epic→T1, rare→T2, magic→T3, normal→T4+. Tiers below are hidden.
    const minTier = rarity === 'normal' ? 4 : TIER_RARITY.indexOf(rarity)
    // Type is locked from a slot "+" (preset), from the base slot (fixed to the enabler's type), and for an
    // already-equipped memory (changing its type would orphan it). Free only for an unequipped inventory memory.
    const typeLocked = creatorSlot !== null || creatorBase || heroMemories.some(m => m?.id === d.id)
    // Base/Special-slot memories are capped at the enabler's rarity and are always non-revived.
    const rarityCapForDraft = creatorBase ? baseEnabler?.rarityCap : undefined
    const affixSource = MEMORY_SOURCES[MEMORY_TYPE_TO_SLOT[d.memoryType]]
    const revivalPool: HeroMemoryAffix[] = memoryRevival.map(a => ({ ...a, source: 'revival' }))
    // Only one EQUIPPED memory may be revived at a time — warn if another already is.
    const otherEquippedRevived = heroMemories.some(m => m && m.id !== d.id && m.revived)
    // A memory can't carry the same modifier twice within a pool group.
    const excludeIn = (group: (MemorySlotSelection | null)[], self: MemorySlotSelection | null) => new Set(
      group.filter(s => s !== self).map(s => s ? getAffixName(s.modifier) : null).filter((n): n is string => !!n)
    )
    // Locked-random placeholder — reserve the same height as an unlocked (unselected) row so toggling the
    // level doesn't shrink/grow the modal (jarring). Rendered as a disabled dropdown-height box.
    const lockedHint = (n: number) => (
      <div className="memory-affix-row" style={{ opacity: 0.5 }}>
        <span className="memory-affix-label">Random {n}</span>
        <div className="memory-affix-controls">
          <div className="memory-affix-combo-trigger" style={{ cursor: 'default' }}>
            <span className="memory-affix-combo-placeholder">Unlocks at level {RANDOM_UNLOCK_LEVELS[n - 1]}</span>
          </div>
        </div>
      </div>
    )
    // Base stat scales off the memory LEVEL (and rarity) via the shared scaling helper (source: MinMaxedARPG).
    const baseStatForLevel = (name: string, lvl: number): MemorySlotSelection | null =>
      scaleBaseStat(d.memoryType, name, rarity, lvl)
    return (
    <div className="modal-backdrop" onClick={closeCreator}>
      <div className="modal-card memory-creator-modal" onClick={e => e.stopPropagation()}>
        <div className="memory-creator-cols">
        <div className="memory-creator-form">
        <div className="memory-rarity-row">
          <span className="memory-rarity-label">Type</span>
          <div className="memory-type-btns">
            {(['origin', 'discipline', 'progress'] as const).map(t => {
              const active = d.memoryType === t
              const icon = memoryTypeIcon[t]
              return (
                <button key={t} type="button" disabled={typeLocked && !active}
                  className={`memory-type-btn${active ? ' active' : ''}`}
                  title={MEMORY_TYPE_LABELS[t]}
                  onClick={() => { if (!typeLocked) setDraft({ ...d, memoryType: t }) }}>
                  {icon
                    ? <span className="memory-icon-frame memory-type-btn-icon" style={{ background: memoryRarityBg(MEMORY_RARITY_COLORS[rarity]) }}><img src={icon} alt="" /></span>
                    : <span className="memory-type-btn-glyph" style={{ color: MEMORY_RARITY_COLORS[rarity], borderColor: `${MEMORY_RARITY_COLORS[rarity]}66`, background: memoryRarityBg(MEMORY_RARITY_COLORS[rarity]) }}>{MEMORY_TYPE_LABELS[t][0]}</span>}
                  <span className="memory-type-btn-label">{MEMORY_TYPE_LABELS[t]}</span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="memory-rarity-row">
          <span className="memory-rarity-label">Rarity</span>
          <div className="memory-rarity-pills">
            {RARITY_ORDER.map(r => {
              const capped = rarityCapForDraft ? !rarityWithinCap(r, rarityCapForDraft) : false
              return (
              <button key={r} type="button" disabled={capped}
                className={`memory-rarity-pill${rarity === r ? ' active' : ''}`}
                title={capped ? `The Base slot enabler allows ${RARITY_LABELS[rarityCapForDraft!]} or lower` : undefined}
                style={{ color: MEMORY_RARITY_COLORS[r], borderColor: rarity === r ? MEMORY_RARITY_COLORS[r] : 'transparent',
                  background: rarity === r ? `${MEMORY_RARITY_COLORS[r]}26` : 'var(--bg-deep)', opacity: capped ? 0.35 : 1 }}
                onClick={() => { if (!capped) setDraftRarity(r) }}>{RARITY_LABELS[r]}</button>
              )
            })}
          </div>
        </div>

        <div className="memory-rarity-row">
          <span className="memory-rarity-label">Level</span>
          <input type="number" min={1} max={maxLv} value={level} className="memory-level-input"
            onChange={e => {
              const lv = Math.max(1, Math.min(maxLv, Math.floor(Number(e.target.value) || 1)))
              // Clear any random affix the new (lower) level no longer unlocks, so a hidden selection can't linger.
              setDraft({ ...d, level: lv,
                // Base stat scales with level; clear randoms the new (lower) level no longer unlocks.
                baseStat: d.baseStat ? (baseStatForLevel(getAffixName(d.baseStat.modifier), lv) ?? d.baseStat) : null,
                randomAffixes: [
                  lv >= RANDOM_UNLOCK_LEVELS[0] ? d.randomAffixes[0] : null,
                  lv >= RANDOM_UNLOCK_LEVELS[1] ? d.randomAffixes[1] : null,
                ] })
            }} />
          <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>/ {maxLv}</span>
        </div>

        <div className="memory-affix-list">
          {fixedN > 0 && <div className="memory-affix-section">Base Stat</div>}
          <AffixRow label="Base Stat" pool={memoryData.base_stats} source={affixSource} color={AFFIX_CAT_COLOR.base} hideSlider
            current={d.baseStat} excludeNames={excludeIn([d.baseStat], d.baseStat)}
            onChange={sel => setDraft({ ...d, baseStat: sel ? (baseStatForLevel(getAffixName(sel.modifier), level) ?? sel) : null })} />
          {fixedN > 0 && <div className="memory-affix-section">Fixed Affixes ({d.fixedAffixes.filter(Boolean).length}/{fixedN})</div>}
          {fixedN >= 1 && <AffixRow label="Fixed 1" pool={memoryData.fixed_affixes} source={affixSource} color={AFFIX_CAT_COLOR.fixed} minTier={minTier}
            current={d.fixedAffixes[0]} excludeNames={excludeIn(d.fixedAffixes, d.fixedAffixes[0])}
            onChange={sel => setDraft({ ...d, fixedAffixes: [sel, d.fixedAffixes[1]] })} />}
          {fixedN >= 2 && <AffixRow label="Fixed 2" pool={memoryData.fixed_affixes} source={affixSource} color={AFFIX_CAT_COLOR.fixed} minTier={minTier}
            current={d.fixedAffixes[1]} excludeNames={excludeIn(d.fixedAffixes, d.fixedAffixes[1])}
            onChange={sel => setDraft({ ...d, fixedAffixes: [d.fixedAffixes[0], sel] })} />}
          {randomN > 0 && <div className="memory-affix-section">Random Affixes ({d.randomAffixes.filter(Boolean).length}/{randomN})</div>}
          {randomN >= 1 && (level >= RANDOM_UNLOCK_LEVELS[0]
            ? <AffixRow label="Random 1" pool={memoryData.random_affixes} source={affixSource} color={AFFIX_CAT_COLOR.random} minTier={minTier}
                current={d.randomAffixes[0]} excludeNames={excludeIn(d.randomAffixes, d.randomAffixes[0])}
                onChange={sel => setDraft({ ...d, randomAffixes: [sel, d.randomAffixes[1]] })} />
            : lockedHint(1))}
          {randomN >= 2 && (level >= RANDOM_UNLOCK_LEVELS[1]
            ? <AffixRow label="Random 2" pool={memoryData.random_affixes} source={affixSource} color={AFFIX_CAT_COLOR.random} minTier={minTier}
                current={d.randomAffixes[1]} excludeNames={excludeIn(d.randomAffixes, d.randomAffixes[1])}
                onChange={sel => setDraft({ ...d, randomAffixes: [d.randomAffixes[0], sel] })} />
            : lockedHint(2))}
        </div>

        {/* Revival: an extra implicit-like affix from the revival pool. Only a revived memory can have a
            revival mod OR enable Wax & Wane. A Base/Special-slot memory is always non-revived, so hide it there. */}
        {!creatorBase && (
        <div style={{ borderTop: '1px solid #2a2a44', marginTop: 8, paddingTop: 8 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#ddd', cursor: 'pointer' }}>
            <input type="checkbox" checked={!!d.revived}
              onChange={e => setDraft({ ...d, revived: e.target.checked, revivalMod: e.target.checked ? (d.revivalMod ?? null) : null, waxAndWane: e.target.checked ? d.waxAndWane : false })} />
            Revived <span style={{ fontSize: 11, color: '#888' }}>(adds a revival mod + enables Wax &amp; Wane)</span>
          </label>
          {d.revived && otherEquippedRevived && (
            <div style={{ fontSize: 11, color: '#e0a94f', marginTop: 4 }}>⚠ Another equipped memory is already revived — only one equipped memory can be revived.</div>
          )}
          {d.revived && (
            <>
              <AffixRow label="Revival Mod" pool={revivalPool} source="revival" color={AFFIX_CAT_COLOR.revival}
                current={d.revivalMod ?? null}
                onChange={sel => setDraft({ ...d, revivalMod: sel ? withRevivalDescription(sel, revivalPool) : null })} />
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#ddd', marginTop: 6, cursor: 'pointer' }}>
                <input type="checkbox" checked={!!d.waxAndWane} onChange={e => setDraft({ ...d, waxAndWane: e.target.checked })} />
                Wax &amp; Wane <span style={{ fontSize: 11, color: '#888' }}>(base stat ×1.3)</span>
              </label>
            </>
          )}
        </div>
        )}
        </div>{/* /memory-creator-form */}
        <div className="memory-creator-preview">
          <MemoryPreviewCard memory={d} icon={memoryTypeIcon[d.memoryType]} maxLevel={maxLv}
            footer={<TooltipContributions delta={draftPreviewDelta} />} />
        </div>
        </div>{/* /memory-creator-cols */}

        <div className="modal-actions">
          <button className="btn btn-primary" onClick={confirmMemory}>
            {(creatorBase && !baseMemory) || (creatorSlot !== null && !heroMemories[creatorSlot]) ? 'Create & Equip' : 'Save'}
          </button>
          {creatorSlot !== null && heroMemories[creatorSlot] && (
            <button className="btn btn-danger" onClick={clearMemory}>Unequip</button>
          )}
          {creatorBase && baseMemory && (
            <button className="btn btn-danger" onClick={() => { unequipBaseMemory(); closeCreator() }}>Unequip</button>
          )}
          <button className="btn btn-secondary" onClick={closeCreator}>Cancel</button>
        </div>
      </div>
    </div>
    )
  })() : null

  // ── Hero Memory inventory overlay (Create at top + owned memories below) ─────
  const inventoryOverlay = inventoryOpen ? (
    <div className="modal-backdrop" onClick={() => setInventoryOpen(false)}>
      <div className="modal-card" style={{ maxWidth: 560, width: '90%', background: 'var(--bg-abyss)' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <h3 className="modal-title" style={{ margin: 0, color: 'var(--fg-body)' }}>Hero Memories</h3>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['current', 'all'] as const).map(v => (
              <button key={v} className={`btn ${inventoryView === v ? 'btn-primary' : 'btn-secondary'}`}
                style={{ fontSize: 11, padding: '3px 10px' }} onClick={() => setInventoryView(v)}>
                {v === 'current' ? 'This loadout' : 'All loadouts'}
              </button>
            ))}
          </div>
        </div>
        <button className="btn btn-primary" style={{ fontSize: 12, marginBottom: 12 }} onClick={openMemoryCreatorNew}>
          + Create Hero Memory
        </button>
        {(() => {
          const renderTile = (mem: CreatedHeroMemory) => (
            <MemoryInventoryTile key={mem.id} memory={mem} equippedSlot={equippedSlotById.get(mem.id) ?? null}
              icon={memoryTypeIcon[mem.memoryType]}
              onEquip={() => equipMemory(mem)}
              onUnequip={() => unequipMemory(mem)}
              onEdit={() => openMemoryEditor(mem)}
              onDelete={() => deleteFromInventory(mem.id)}
              onDuplicate={() => duplicateInInventory(mem.id)}
              onRename={(next) => renameMemory(mem.id, next)}
              baseEquipped={baseMemory?.id === mem.id}
              canEquipBase={!!baseEnabler && baseMemory?.id !== mem.id && baseEligible(mem)}
              onEquipBase={() => equipBaseMemory(mem)}
              onUnequipBase={unequipBaseMemory} />
          )
          const empty = inventoryView === 'all' ? aggregateGroups.length === 0 : memoryInventory.length === 0
          if (empty) {
            return (
              <div style={{ fontSize: 13, color: '#666', padding: '8px 0' }}>
                No memories yet — click <b style={{ color: '#888' }}>Create Hero Memory</b> above, or the + on a memory slot.
              </div>
            )
          }
          if (inventoryView === 'all') {
            return (
              <div style={{ maxHeight: '52vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
                {aggregateGroups.map(g => (
                  <div key={g.name}>
                    <div className="memory-loadout-group-header">{g.name}</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>{g.memories.map(renderTile)}</div>
                  </div>
                ))}
              </div>
            )
          }
          return (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, maxHeight: '52vh', overflowY: 'auto' }}>
              {memoryInventory.map(renderTile)}
            </div>
          )
        })()}
        <div className="modal-actions" style={{ marginTop: 12 }}>
          <button className="btn btn-secondary" onClick={() => setInventoryOpen(false)}>Close</button>
        </div>
      </div>
    </div>
  ) : null

  return (
    <div className="hero-trait-screen">
      {/* Header */}
      <div className="hero-trait-header">
        <HeroTraitSelect traits={allTraits} value={traitId} onChange={switchTrait} />
        {selectedTrait && (
          <span className="hero-trait-variant-label">
            {selectedTrait.hero} · {selectedTrait.variant_name}
          </span>
        )}
        {/* Opens the Hero Memory inventory overlay. Lives in the always-visible header so it stays clickable
            in tree-mode (the tree SVG fills the body and would otherwise sit over a body-level button). */}
        {selectedTrait && (
          <button className="btn btn-secondary" style={{ fontSize: 12, marginLeft: 'auto' }} onClick={() => setInventoryOpen(true)}>
            ◈ Hero Memory Inventory ({memoryInventory.length})
          </button>
        )}
      </div>

      {selectedTrait ? (
        <div className="hero-trait-body">
          <div className="trait-main-row">

            {/* Base trait — always selected. Tree-mode traits (Dance of the Deep and onward) hide this
                column + the divider entirely: the base trait appears ONLY as the always-allocated root
                node inside HeroTraitTree, so this whole block (and the trait-v-divider next to it) is
                skipped in that mode. Level-selection state itself is untouched — the trait just stays
                at whatever level it defaults to (1) since there's no UI here to change it in tree mode. */}
            {/* Dance of the Deep (Selena 2) and any future tree-mode trait: an allocatable tree replaces
                the fixed grid entirely (the base trait appears as the always-allocated root node inside it). */}
            {selectedTrait.allocation_mode === 'tree' ? (
              <HeroTraitTree
                trait={selectedTrait}
                heroMemories={heroMemories}
                baseMemory={baseMemory}
                openMemoryCreator={openMemoryCreator}
                openBaseCreator={openBaseCreator}
                traitTreeAllocations={traitTreeAllocations}
                setTraitTreeAllocations={setTraitTreeAllocations}
                characterLevel={characterLevel}
                resolveLevelAt={baseLevel}
              />
            ) : (
            // Fixed-trait GRID: the base trait + the 3 memory slots sit on ONE aligned row (tg-mid); each
            // level's trait options split — the first ABOVE the memory, the rest BELOW. Grid rows sync heights
            // across columns so the memory/base row lines up no matter how many options a level has.
            <div className="trait-grid">
              {/* Base column: the base TRAIT sits on the memory row (tg-mid), inline with the 3 memory slots;
                  the Base ("Special") memory placeholder is below it. No header label (owner). */}
              <div className="tg-base" />
              <div className="tg-above tg-base" />
              <div className="tg-mid tg-base">
                <div>
                  <TraitCircle
                    className="trait-circle selected trait-circle-base"
                    name={selectedTrait.variant_name}
                    icon={iconUrl('hero_trait', selectedTrait.icon_url)}
                    checked
                    disabled={baseDisabled}
                    tipName={selectedTrait.variant_name}
                    slotLevel={baseLevel}
                    effects={baseEffects}
                    moonEffects={showArtificialMoon ? selectedTrait.artificial_moon.effects : undefined}
                    onSelect={baseDisabled ? () => enableNode(SLOT_BASE) : undefined}
                    onContextMenu={() => disableNode(SLOT_BASE)}
                  />
                </div>
              </div>
              <div className="tg-below tg-base">
                {/* Base ("Special") memory slot — opened by a revived memory's enabler mod (Artificial Moon /
                    Base Trait slot). HIDDEN entirely until an enabler is equipped; then it accepts one non-revived
                    memory of the enabler's type, up to its rarity cap, at the enabler's value penalty, and levels
                    the base trait (→ Artificial Moon at lv5). Labelled by the allowed type (Origin/Discipline/Progress). */}
                {baseEnabler && (
                  <MemorySlotCircle memory={baseSlot?.memory ?? null} slot={SLOT_BASE}
                    rarityColor={baseSlot ? MEMORY_RARITY_COLORS[baseSlot.memory.rarity] : undefined}
                    slotLabel={MEMORY_TYPE_LABELS[baseEnabler.type]}
                    icon={baseSlot ? memoryTypeIcon[baseSlot.memory.memoryType] : null}
                    valueScale={baseSlot ? baseSlot.enabler.factor : undefined}
                    deltaKey="mem:rm:base"
                    deltaStep={s => ({ ...s, baseMemory: null })}
                    onOpen={openBaseCreator} />
                )}
                {traitGrantsSkillSlot(traitId, advancedTraitSelections) && (
                  <div>
                    <div className="trait-tier-label" style={{ fontSize: 10, marginBottom: 4 }}>Support Slot</div>
                    <TraitSkillSlot supports={traitSkillSupports} allSkills={allSkills} onChange={setTraitSkillSupports} />
                  </div>
                )}
              </div>

              {/* One column per unlock level */}
              {LEVEL_THRESHOLDS.map(threshold => {
                const group = selectedTrait.advanced_traits.filter(t => t.unlock_level === threshold)
                if (group.length === 0) return null
                const slotIdx = SLOT_IDX[threshold]
                const tierDisabled = nodeDisabled(slotIdx)
                const slotLevel = nodeLevel(slotIdx)
                const locked = characterLevel < threshold
                const groups = buildGroups(group)
                // Split-circle bubbles are ONLY for levels with multiple option groups (i.e. Creative Genius).
                const multiGroup = groups.length > 1
                const memSlotIdx = THRESHOLD_TO_MEMORY_SLOT[threshold]
                const memory = heroMemories[memSlotIdx] ?? null
                const rarityColor = memory ? MEMORY_RARITY_COLORS[memory.rarity] : undefined

                const renderGranted = (t: HeroAdvancedTrait) => (
                  <TraitCircle key={t.name} className={`trait-circle selected${locked ? ' locked' : ''}`}
                    name={t.name} icon={iconUrl('hero_trait', t.icon_url)} checked={!tierDisabled} locked={locked}
                    disabled={tierDisabled} tipName={t.name} slotLevel={slotLevel} effects={t.effects ?? []}
                    onSelect={() => !locked && enableTier(threshold)}
                    onContextMenu={!tierDisabled && !locked ? () => disableNode(slotIdx) : undefined} />
                )
                const renderPick = (t: HeroAdvancedTrait, groupNames: string[]) => {
                  const sel = advancedTraitSelections.includes(t.name)
                  // Once a pick has been made in this group, fade the un-chosen options so the active one is clear.
                  const faded = !sel && groupNames.some(n => advancedTraitSelections.includes(n))
                  return (
                    <TraitCircle key={t.name} className={`trait-circle${sel ? ' selected' : ''}${locked ? ' locked' : ''}${faded ? ' faded' : ''}`}
                      name={t.name} icon={iconUrl('hero_trait', t.icon_url)} checked={sel} locked={locked}
                      disabled={sel && tierDisabled} tipName={t.name} slotLevel={slotLevel} effects={t.effects ?? []}
                      onSelect={() => selectInGroup(t.name, threshold, groupNames)}
                      onContextMenu={sel && !locked ? () => disableNode(slotIdx) : undefined} />
                  )
                }

                // First option ABOVE the memory, the rest BELOW (owner). Creative Genius (multiGroup) keeps its
                // combined split-circles together above.
                let aboveContent: React.ReactNode = null
                let belowContent: React.ReactNode = null
                // Hide the "Granted"/"Pick One" caption once the tier is satisfied (granted is auto-active
                // unless the tier is off; pick-one once a node is chosen).
                const labelFor = (g: ReturnType<typeof buildGroups>[number]): string | null => {
                  // "Pick One" removed (owner) — clicking once makes it obvious. "Granted" only shows when the
                  // tier is off (so a disabled tier still reads as auto-granted once re-enabled).
                  if (g.role === 'guaranteed') return tierDisabled ? 'Granted' : null
                  return null
                }
                if (multiGroup) {
                  aboveContent = (
                    <div className="ht-groups">
                      {groups.map(g => (
                        <div className="ht-group" key={`${g.role}-${g.id}`}>
                          {labelFor(g) && <div className="ht-group-label">{labelFor(g)}</div>}
                          {g.role === 'guaranteed'
                            ? g.nodes.map(renderGranted)
                            : <PickGroup nodes={g.nodes} slotLevel={slotLevel} locked={locked} tierDisabled={tierDisabled}
                                selectedNames={advancedTraitSelections}
                                onSelect={name => selectInGroup(name, threshold, g.nodes.map(n => n.name))}
                                onDisable={() => disableNode(slotIdx)} />}
                        </div>
                      ))}
                    </div>
                  )
                } else {
                  const g = groups[0]
                  const isGranted = g.role === 'guaranteed'
                  const groupNames = g.nodes.map(n => n.name)
                  const render = (t: HeroAdvancedTrait) => isGranted ? renderGranted(t) : renderPick(t, groupNames)
                  aboveContent = (
                    <div className="ht-group">
                      {labelFor(g) && <div className="ht-group-label">{labelFor(g)}</div>}
                      {render(g.nodes[0])}
                    </div>
                  )
                  belowContent = g.nodes.length > 1
                    ? <div className="ht-group">{g.nodes.slice(1).map(render)}</div>
                    : null
                }

                return (
                  <React.Fragment key={threshold}>
                    <div className={`trait-tier-label${locked || tierDisabled ? ' locked' : ''}`}>
                      Level {threshold}{tierDisabled ? ' (off)' : ''}
                    </div>
                    <div className="tg-above">{aboveContent}</div>
                    <div className="tg-mid">
                      <MemorySlotCircle memory={memory} rarityColor={rarityColor} slot={memSlotIdx}
                        slotLabel={MEMORY_TYPE_LABELS[MEMORY_TYPES[memSlotIdx]]}
                        icon={memory ? memoryTypeIcon[memory.memoryType] : null}
                        onOpen={() => openMemoryCreator(memSlotIdx)} />
                    </div>
                    <div className="tg-below">{belowContent}</div>
                  </React.Fragment>
                )
              })}
            </div>
            )}
          </div>

          {/* Artificial Moon — only at base level 5 */}
          {showArtificialMoon && (
            <div className="trait-moon-row">
              <div className="trait-moon-label">◈ Artificial Moon</div>
              <div className="trait-moon-effects">
                {selectedTrait.artificial_moon.effects.map((line, i) => (
                  <span key={i} className="trait-moon-effect">{line}</span>
                ))}
              </div>
            </div>
          )}

          {/* Licorice Note — Pungent prepares ONE Empower/Curse; user designates it when >1 eligible. */}
          {traitId === 'licorice_note' && (traitSlotLevels[1] ?? 0) >= 1 && (() => {
            const eligible = (skills || []).filter(sk => sk.slot >= 1 && sk.slot <= 5 && (sk.enabled ?? true)
              && sk.skill_tags?.some(t => t === 'Empower' || t === 'Curse'))
            return (
              <div className="trait-moon-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
                <div className="trait-moon-label">⚗ Pungent — Prepared Empower / Curse</div>
                {eligible.length === 0 ? (
                  <span className="trait-moon-effect" style={{ color: '#888' }}>
                    No Empower or Curse equipped — Pungent has nothing to prepare.
                  </span>
                ) : eligible.length === 1 ? (
                  <span className="trait-moon-effect" style={{ color: '#9ad' }}>
                    Auto: <b>{eligible[0].name}</b> (only eligible skill) receives the cross-applied Elixir Effect.
                  </span>
                ) : (
                  <>
                    <select
                      value={eligible.some(e => e.item_id === licoricePreparedSkill) ? (licoricePreparedSkill ?? '') : ''}
                      onChange={e => setLicoricePreparedSkill(e.target.value || null)}
                      style={{ background: '#1a1a2e', color: '#ddd', border: '1px solid #444', borderRadius: 4, padding: '3px 6px', fontSize: 12 }}
                    >
                      <option value="">— Select prepared skill —</option>
                      {eligible.map(e => (
                        <option key={e.item_id} value={e.item_id}>
                          {e.name} ({e.skill_tags.includes('Empower') ? 'Empower' : 'Curse'}, slot {e.slot})
                        </option>
                      ))}
                    </select>
                    {!eligible.some(e => e.item_id === licoricePreparedSkill) && (
                      <span className="trait-moon-effect" style={{ color: '#d09a4a' }}>
                        Select which skill the trait prepares — no cross-apply bonus applies until one is chosen.
                      </span>
                    )}
                  </>
                )}
                {traitWarnings.map((w, i) => (
                  <span key={i} className="trait-moon-effect" style={{ color: '#d09a4a' }}>⚠ {w.text}</span>
                ))}
              </div>
            )
          })()}

          {/* Licorice Note — Ingredients: category-locked picker per Scent Bottle (Basic = slot 2, Special = slot 3). */}
          {traitId === 'licorice_note' && (() => {
            const catalog = selectedTrait.ingredients ?? []
            const itemsFor = (group: string, cat: string) =>
              catalog.find(g => g.trait_name === group)?.categories.find(c => c.category === cat)?.items ?? []
            const pungent = (traitSlotLevels[1] ?? 0) >= 1
            const special = advancedTraitSelections.includes('Licorice Tincture Blend') && (traitSlotLevels[3] ?? 0) >= 1
            // Each Scent Bottle slot → the category slots it offers (category label → available items).
            const bottles: { slot: number; label: string; cats: { cat: string; items: { name: string; effect: string }[] }[] }[] = [
              { slot: 2, label: 'Basic Scent Bottle (slot 2)', cats: [
                { cat: 'Damage Ingredient', items: itemsFor('Licorice Note', 'Damage Ingredient') },
                { cat: 'Defense Ingredient', items: itemsFor('Licorice Note', 'Defense Ingredient') },
                ...(pungent ? [{ cat: 'Functional Ingredient', items: itemsFor('Pungent Stimulant Salt', 'Functional Ingredient') }] : []),
              ] },
              ...(special ? [{ slot: 3, label: 'Special Scent Bottle (slot 3)', cats: [
                { cat: 'Special Ingredient', items: itemsFor('Licorice Tincture Blend', 'Special Ingredient') },
                ...(pungent ? [{ cat: 'Functional Ingredient', items: itemsFor('Pungent Stimulant Salt', 'Functional Ingredient') }] : []),
              ] }] : []),
            ]
            const pick = (slot: number, cat: string, name: string) => {
              const next = { ...elixirIngredients, [slot]: { ...(elixirIngredients[slot] ?? {}) } }
              if (name) next[slot][cat] = name
              else delete next[slot][cat]
              setElixirIngredients(next)
            }
            if (!catalog.length) return null
            return (
              <div className="trait-moon-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
                <div className="trait-moon-label">🧪 Scent Bottle Ingredients</div>
                {bottles.map(b => (
                  <div key={b.slot} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 11, color: '#9ad', minWidth: 150 }}>{b.label}</span>
                    {b.cats.map(c => (
                      <select key={c.cat} value={elixirIngredients[b.slot]?.[c.cat] ?? ''}
                        onChange={e => pick(b.slot, c.cat, e.target.value)}
                        title={c.cat}
                        style={{ background: '#1a1a2e', color: '#ddd', border: '1px solid #444', borderRadius: 4, padding: '3px 6px', fontSize: 11 }}>
                        <option value="">— {c.cat.replace(' Ingredient', '')} —</option>
                        {c.items.map(it => <option key={it.name} value={it.name}>{it.name}</option>)}
                      </select>
                    ))}
                  </div>
                ))}
                <span className="trait-moon-effect" style={{ color: '#777', fontSize: 10 }}>
                  Ingredients add their base effect to that Scent Bottle's elixir (scaled by Elixir Effect). Defensive / restoration / charge effects are surfaced but not yet modeled.
                </span>
              </div>
            )
          })()}
        </div>
      ) : (
        <div className="hero-trait-body">
          <div className="panel-empty">Select a hero trait from the dropdown above.</div>
        </div>
      )}


      {inventoryOverlay}
      {creatorModal}
    </div>
  )
}
