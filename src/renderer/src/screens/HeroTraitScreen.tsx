import React, { useEffect, useMemo, useState } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { HeroTrait, HeroMemoryAffix, CreatedHeroMemory, MemoryRarity, MemorySlotSelection, MEMORY_RARITY_COLORS, iconUrl,
  SkillItem, EquippedSupportSkill, isSupportCompatible, traitGrantsSkillSlot, TRAIT_SKILL_PARENT } from '../api/client'
import { useReferenceStore } from '../store/referenceStore'
import { useBuildStore } from '../store/buildStore'
import { characterLevelFrom } from '../utils/conditions'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { useDamageDelta } from '../components/tooltip/useDamageDelta'
import { TooltipContributions } from '../components/tooltip/TooltipContributions'
import { ModifierBadge, useTextModifierStatuses, useTextModifierStatus } from '../components/ModifierBadge'
import { dec } from '../utils/num'
import { traitSlang, traitOrder } from '../utils/heroTraitOrder'

interface Props {
  onBack: () => void
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
const MEMORY_TYPE_LABELS: Record<CreatedHeroMemory['memoryType'], string> = {
  origin: 'Origin',
  discipline: 'Discipline',
  progress: 'Progress',
}
const RARITY_ORDER: MemoryRarity[] = ['normal', 'magic', 'rare', 'epic', 'ultimate']
const RARITY_LABELS: Record<MemoryRarity, string> = {
  normal: 'Normal', magic: 'Magic', rare: 'Rare', epic: 'Epic', ultimate: 'Ultimate',
}

// ── Affix / tier helper functions ─────────────────────────────────────────────

function getAffixName(modifier: string): string {
  // Strip leading optional + and numeric prefix (integer, decimal, or range notation)
  let name = modifier
    .replace(/^\+?(?:\d+(?:\.\d+)?|\([^)]+\))\s*%?\s*/, '')
    .trim()
  // If nothing was stripped (modifier starts with text), normalize any embedded ranges
  // to a stable placeholder so all tiers of the same affix group correctly
  if (name === modifier.trim()) {
    name = modifier.replace(/\+?\(\d+(?:\.\d+)?[–\-]\d+(?:\.\d+)?\)/g, '#').trim()
  }
  // Capitalize first letter to fix lowercase data entries
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

function hasRange(modifier: string): boolean {
  return /\(\d+(?:\.\d+)?[–\-]\d+(?:\.\d+)?\)/.test(modifier)
}

function parseRange(modifier: string): { min: number; max: number } {
  const m = modifier.match(/\((\d+(?:\.\d+)?)[–\-](\d+(?:\.\d+)?)\)/)
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

function resolveMemoryEffect(sel: MemorySlotSelection): string {
  // Ensure leading + for modifiers that start with a digit (handles legacy stored data)
  const mod = /^\d/.test(sel.modifier) ? '+' + sel.modifier : sel.modifier
  if (sel.rolledValue === null) return mod
  const val = Number.isInteger(sel.rolledValue) ? String(sel.rolledValue) : dec(sel.rolledValue)
  return mod.replace(/\(\d+(?:\.\d+)?[–\-]\d+(?:\.\d+)?\)/g, val)
}

function getMemoryAffixLines(memory: CreatedHeroMemory): { text: string; tier: number }[] {
  const out: { text: string; tier: number }[] = []
  const add = (sel: MemorySlotSelection | null) => { if (sel) out.push({ text: resolveMemoryEffect(sel), tier: sel.tier ?? 0 }) }
  add(memory.baseStat)
  for (const fa of memory.fixedAffixes) add(fa)
  for (const ra of memory.randomAffixes) add(ra)
  return out
}

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
  const groups = useMemo(() => {
    const by = groupByHero(traits)
    return Object.entries(by)
      .map(([hero, variants]) => ({
        hero,
        variants: [...variants].sort((a, b) => traitOrder(a.trait_id) - traitOrder(b.trait_id)),
        order: Math.min(...variants.map(v => traitOrder(v.trait_id))),
      }))
      .sort((a, b) => a.order - b.order)
  }, [traits])
  const current = traits.find(t => t.trait_id === value) ?? null
  return (
    <div className="ht-dd">
      <button className="ht-dd-trigger" onClick={() => setOpen(o => !o)} title="Select hero trait">
        <span className="ht-dd-trigger-name">{current?.variant_name ?? 'Select trait'}</span>
        {current && traitSlang(current.trait_id) && (
          <span className="ht-dd-slang">{traitSlang(current.trait_id)}</span>
        )}
        <span className="ht-dd-caret">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <>
          <div className="ht-dd-backdrop" onClick={() => setOpen(false)} />
          <div className="ht-dd-menu">
            {groups.map(g => (
              <div key={g.hero} className="ht-dd-group">
                <div className="ht-dd-group-label">{g.hero}</div>
                {g.variants.map(v => (
                  <button key={v.trait_id}
                    className={`ht-dd-item${v.trait_id === value ? ' active' : ''}`}
                    onClick={() => { onChange(v.trait_id); setOpen(false) }}>
                    <span className="ht-dd-item-name">{v.variant_name}</span>
                    {traitSlang(v.trait_id) && <span className="ht-dd-slang">{traitSlang(v.trait_id)}</span>}
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

function resolveLevel(text: string, level: number): string {
  return text.replace(/\(([^)]+)\)/g, (_, inner) => {
    if (!inner.includes('/')) return `(${inner})`
    const parts = inner.split('/').map((p: string) => p.trim())
    return parts[Math.min(level - 1, parts.length - 1)]
  })
}

// ── Tooltip content + trigger components (shared floating primitive) ───────────

export function TraitTooltipBody({ name, slotLevel, effects, moonEffects }: {
  name: string; slotLevel: number; effects: string[]; moonEffects?: string[]
}) {
  return (
    <>
      <div className="trait-info-name">{name}</div>
      <div className="trait-info-level-current">Level {slotLevel}</div>
      <ul className="trait-info-effects">
        {effects.map((line, i) =>
          /^Level \d+$/.test(line)
            ? <li key={i} className="trait-info-level-header">{line}</li>
            : <li key={i}>{resolveLevel(line, slotLevel)}</li>
        )}
      </ul>
      {moonEffects && moonEffects.length > 0 && (
        <>
          <div className="trait-info-level-header" style={{ color: '#7070cc', marginTop: 8 }}>Artificial Moon</div>
          <ul className="trait-info-effects">
            {moonEffects.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        </>
      )}
    </>
  )
}

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

// A memory slot circle + its hover info tooltip (only when a memory is socketed).
function MemorySlotCircle({ memory, rarityColor, slot, onOpen }: {
  memory: CreatedHeroMemory | null; rarityColor?: string; slot: number; onOpen: () => void
}) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
  const lines = memory ? getMemoryAffixLines(memory) : []
  const lineStatuses = useTextModifierStatuses(lines.map(l => ({ text: l.text, source: 'memory' as const })))
  // Contribution of this socketed memory: remove it and diff vs the current build.
  const delta = useDamageDelta(
    tip.open && memory
      ? { key: `mem:rm:${slot}`, step: s => ({ ...s, heroMemories: s.heroMemories.map((m, i) => i === slot ? null : m) as typeof s.heroMemories }) }
      : null,
    tip.open && !!memory,
  )
  return (
    <>
      <div
        {...(memory ? tip.triggerProps : {})}
        className={`memory-slot-circle${memory ? ' filled' : ''}`}
        style={memory ? { borderColor: rarityColor, boxShadow: `0 0 10px ${rarityColor}44` } : undefined}
        onClick={e => { e.stopPropagation(); onOpen() }}
      >
        {memory
          ? <span style={{ color: rarityColor, fontSize: 26, lineHeight: 1 }}>◈</span>
          : <span className="memory-slot-plus">+</span>}
      </div>
      {memory && tip.open && (
        <FloatingPortal>
          <div className="memory-info-card" {...tip.floatingProps}>
            <div className="memory-info-title" style={{ color: rarityColor }}>
              Memory of {MEMORY_TYPE_LABELS[memory.memoryType]}
            </div>
            <div className="memory-info-rarity" style={{ color: rarityColor }}>
              {RARITY_LABELS[memory.rarity]}
            </div>
            {lines.length > 0 ? (
              <ul className="memory-info-lines">
                {lines.map((line, i) => (
                  <li key={i}>
                    {line.text}
                    {line.tier > 0 && <span style={{ fontSize: 10, color: '#888' }}> (T{line.tier})</span>}
                    <ModifierBadge status={lineStatuses[i]} />
                  </li>
                ))}
              </ul>
            ) : (
              <div className="memory-info-empty">No affixes configured</div>
            )}
            <div className="memory-info-hint">Click to edit</div>
            <TooltipContributions delta={delta} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// One unified-slider affix row in the memory creator + its hover tooltip (resolved text).
function AffixRow({ label, pool, source, current, excludeNames, onChange }: {
  label: string
  pool: HeroMemoryAffix[]
  source: string
  current: MemorySlotSelection | null
  excludeNames?: Set<string>   // affix names already chosen in sibling rows (a memory can't repeat a modifier)
  onChange: (sel: MemorySlotSelection | null) => void
}) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'top' })
  const selectedName = current ? getAffixName(current.modifier) : ''
  // Drop names taken by other rows, but always keep this row's own current selection so it stays visible.
  const names = getAffixNames(pool, source)
    .filter(n => n === selectedName || !excludeNames?.has(n))
  const tierEntries = selectedName ? getTierOptions(pool, source, selectedName) : []
  const tierRanges = buildTierRanges(tierEntries)
  const sliderMax = tierRanges.length > 0 ? tierRanges[tierRanges.length - 1].endPos : 0

  const currentPos = current && tierRanges.length > 0
    ? tierValueToPos(tierRanges, current.tier, current.rolledValue)
    : 0
  const currentTierInfo = tierRanges.length > 0 ? posToTierValue(tierRanges, currentPos) : null

  const resolvedText = current ? resolveMemoryEffect(current) : null
  const modStatus = useTextModifierStatus(resolvedText, 'memory')

  const handleNameChange = (name: string) => {
    if (!name) { onChange(null); return }
    const entries = getTierOptions(pool, source, name)
    if (entries.length === 0) { onChange(null); return }
    const ranges = buildTierRanges(entries)
    const best = ranges[ranges.length - 1]
    const pos = Math.floor((best.startPos + best.endPos) / 2)
    const { tier, value, modifier } = posToTierValue(ranges, pos)
    onChange({ modifier, tier, rolledValue: hasRange(modifier) ? value : null })
  }

  const handleSliderChange = (pos: number) => {
    if (tierRanges.length === 0) return
    const { tier, value, modifier } = posToTierValue(tierRanges, pos)
    onChange({ modifier, tier, rolledValue: hasRange(modifier) ? value : null })
  }

  return (
    <>
      <div className="memory-affix-row" {...(resolvedText ? tip.triggerProps : {})}>
        <span className="memory-affix-label">{label}<ModifierBadge status={modStatus} /></span>
        <div className="memory-affix-controls">
          <select
            className="memory-affix-select"
            value={selectedName}
            onChange={e => handleNameChange(e.target.value)}
          >
            <option value="">— None —</option>
            {names.map(n => <option key={n} value={n}>{n}</option>)}
          </select>

          {selectedName && tierRanges.length > 0 && currentTierInfo && (
            <div className="memory-tier-slider-wrapper">
              <div className="memory-tier-label-pill">Tier {currentTierInfo.tier}</div>
              <div className="memory-tier-slider-row">
                {/* A single fixed value has no positions to slide (sliderMax === 0) — show just the value. */}
                {sliderMax > 0 && (
                  <input
                    type="range"
                    className="memory-affix-slider"
                    min={0}
                    max={sliderMax}
                    value={currentPos}
                    onChange={e => handleSliderChange(parseInt(e.target.value))}
                  />
                )}
                <span className="memory-affix-slider-val">
                  {Number.isInteger(currentTierInfo.value) ? currentTierInfo.value : dec(currentTierInfo.value)}
                </span>
              </div>
            </div>
          )}
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

// ── Main component ────────────────────────────────────────────────────────────

export default function HeroTraitScreen({ onBack: _onBack }: Props) {
  const traitId = useBuildStore(s => s.traitId)
  const traitSlotLevels = useBuildStore(s => s.traitSlotLevels)
  const advancedTraitSelections = useBuildStore(s => s.advancedTraitSelections)
  // Trait-tier unlocks use the `level` condition (default 90) — the single character-level source.
  const characterLevel = characterLevelFrom(useBuildStore(s => s.conditionState))
  const heroMemories = useBuildStore(s => s.heroMemories)
  const setTraitData = useBuildStore(s => s.setTraitData)
  const setHeroMemories = useBuildStore(s => s.setHeroMemories)
  const traitSkillSupports = useBuildStore(s => s.traitSkillSupports)
  const setTraitSkillSupports = useBuildStore(s => s.setTraitSkillSupports)
  const allSkills = useReferenceStore(s => s.skills) ?? []
  const allTraits = useReferenceStore(s => s.heroTraits) ?? []
  const memoryData = useReferenceStore(s => s.heroMemories)
  const referenceResolved = useReferenceStore(s => s.referenceResolved)
  const traitsFailed = useReferenceStore(s => s.failedCatalogs.has('heroTraits'))

  const [creatorSlot, setCreatorSlot] = useState<number | null>(null)
  const [draft, setDraft] = useState<CreatedHeroMemory | null>(null)

  const loading = !referenceResolved && allTraits.length === 0

  // Auto-select first trait when none selected
  useEffect(() => {
    if (!loading && traitId === null && allTraits.length > 0) {
      setTraitData(allTraits[0].trait_id, [1, 1, 1, 1], [])
    }
  }, [loading, traitId, allTraits])

  const selectedTrait = allTraits.find(t => t.trait_id === traitId) ?? null

  const safeSlotLevels = (
    Array.isArray(traitSlotLevels) && traitSlotLevels.length === 4
      ? traitSlotLevels
      : [1, 1, 1, 1]
  )

  // A negative slot level = the node is DISABLED (the magnitude is its remembered level).
  const nodeDisabled = (slotIdx: number) => safeSlotLevels[slotIdx] < 1
  const nodeLevel = (slotIdx: number) => Math.max(1, Math.min(5, Math.abs(safeSlotLevels[slotIdx])))
  const baseLevel = nodeLevel(SLOT_BASE)
  const baseDisabled = nodeDisabled(SLOT_BASE)
  const baseEffects = selectedTrait?.levels[baseLevel - 1]?.effects ?? []
  const showArtificialMoon = baseLevel === 5 && (selectedTrait?.artificial_moon?.effects?.length ?? 0) > 0

  function setSlotLevel(slotIdx: number, level: number) {
    if (!traitId) return
    const next = [...safeSlotLevels]
    next[slotIdx] = level
    setTraitData(traitId, next, advancedTraitSelections)
  }

  // Slot levels with `slotIdx` forced ENABLED (positive, remembered magnitude) — selecting/left-clicking enables.
  const withEnabled = (slotIdx: number) => {
    const n = [...safeSlotLevels]
    n[slotIdx] = Math.abs(n[slotIdx]) || 1
    return n
  }

  function selectPrimary(name: string, threshold: number) {
    if (!traitId || !selectedTrait) return
    const falseNames = selectedTrait.advanced_traits
      .filter(t => t.unlock_level === threshold && !t.is_pick_one_from_two)
      .map(t => t.name)
    const next = advancedTraitSelections.filter(n => !falseNames.includes(n))
    next.push(name)
    setTraitData(traitId, withEnabled(SLOT_IDX[threshold]), next)   // picking also (re)enables the tier
  }

  function selectSub(name: string, threshold: number) {
    if (!traitId || !selectedTrait) return
    const trueNames = selectedTrait.advanced_traits
      .filter(t => t.unlock_level === threshold && t.is_pick_one_from_two)
      .map(t => t.name)
    const next = advancedTraitSelections.filter(n => !trueNames.includes(n))
    next.push(name)
    setTraitData(traitId, withEnabled(SLOT_IDX[threshold]), next)   // picking also (re)enables the tier
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

  // ── Memory creator helpers ────────────────────────────────────────────────

  function openMemoryCreator(slotIdx: number) {
    const existing = heroMemories[slotIdx]
    const memoryType = MEMORY_TYPES[slotIdx]
    if (existing) {
      setDraft({
        ...existing,
        fixedAffixes: [existing.fixedAffixes[0], existing.fixedAffixes[1]],
        randomAffixes: [existing.randomAffixes[0], existing.randomAffixes[1]],
      })
    } else {
      setDraft({ memoryType, rarity: 'epic', baseStat: null, fixedAffixes: [null, null], randomAffixes: [null, null] })
    }
    setCreatorSlot(slotIdx)
  }

  function confirmMemory() {
    if (creatorSlot === null || !draft) return
    const next = [...heroMemories] as typeof heroMemories
    next[creatorSlot] = draft
    setHeroMemories(next)
    setCreatorSlot(null)
    setDraft(null)
  }

  function clearMemory() {
    if (creatorSlot === null) return
    const next = [...heroMemories] as typeof heroMemories
    next[creatorSlot] = null
    setHeroMemories(next)
    setCreatorSlot(null)
    setDraft(null)
  }

  if (loading) {
    return (
      <div className="hero-trait-screen">
        <div className="hero-trait-body"><div className="panel-empty">Loading traits…</div></div>
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

  // ── Creator modal ─────────────────────────────────────────────────────────

  const creatorModal = creatorSlot !== null && draft && memoryData && (
    <div className="modal-backdrop" onClick={() => { setCreatorSlot(null); setDraft(null) }}>
      <div className="modal-card memory-creator-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-accent" />
        <h3 className="modal-title">Memory of {MEMORY_TYPE_LABELS[draft.memoryType]}</h3>

        <div className="memory-rarity-row">
          <span className="memory-rarity-label">Rarity</span>
          <select
            className="memory-rarity-select"
            value={draft.rarity}
            onChange={e => setDraft({ ...draft, rarity: e.target.value as MemoryRarity })}
          >
            {RARITY_ORDER.map(r => (
              <option key={r} value={r}>{RARITY_LABELS[r]}</option>
            ))}
          </select>
          <span className="memory-rarity-dot" style={{ color: MEMORY_RARITY_COLORS[draft.rarity] }}>●</span>
        </div>

        <div className="memory-affix-list">
          {(() => {
            // A memory can't carry the same modifier twice — build each row's exclude set from the
            // affix names chosen in the OTHER rows (fixed/random pools share affixes like Minion Crit Dmg).
            const all = [draft.baseStat, draft.fixedAffixes[0], draft.fixedAffixes[1], draft.randomAffixes[0], draft.randomAffixes[1]]
            const excludeFor = (self: MemorySlotSelection | null) => new Set(
              all.filter(s => s !== self).map(s => s ? getAffixName(s.modifier) : null).filter((n): n is string => !!n)
            )
            return (
              <>
                <AffixRow label="Base Stat" pool={memoryData.base_stats} source={MEMORY_SOURCES[creatorSlot]}
                  current={draft.baseStat} excludeNames={excludeFor(draft.baseStat)}
                  onChange={sel => setDraft({ ...draft, baseStat: sel })} />
                <AffixRow label="Fixed 1" pool={memoryData.fixed_affixes} source={MEMORY_SOURCES[creatorSlot]}
                  current={draft.fixedAffixes[0]} excludeNames={excludeFor(draft.fixedAffixes[0])}
                  onChange={sel => setDraft({ ...draft, fixedAffixes: [sel, draft.fixedAffixes[1]] })} />
                <AffixRow label="Fixed 2" pool={memoryData.fixed_affixes} source={MEMORY_SOURCES[creatorSlot]}
                  current={draft.fixedAffixes[1]} excludeNames={excludeFor(draft.fixedAffixes[1])}
                  onChange={sel => setDraft({ ...draft, fixedAffixes: [draft.fixedAffixes[0], sel] })} />
                <AffixRow label="Random 1" pool={memoryData.random_affixes} source={MEMORY_SOURCES[creatorSlot]}
                  current={draft.randomAffixes[0]} excludeNames={excludeFor(draft.randomAffixes[0])}
                  onChange={sel => setDraft({ ...draft, randomAffixes: [sel, draft.randomAffixes[1]] })} />
                <AffixRow label="Random 2" pool={memoryData.random_affixes} source={MEMORY_SOURCES[creatorSlot]}
                  current={draft.randomAffixes[1]} excludeNames={excludeFor(draft.randomAffixes[1])}
                  onChange={sel => setDraft({ ...draft, randomAffixes: [draft.randomAffixes[0], sel] })} />
              </>
            )
          })()}
        </div>

        <div className="modal-actions">
          <button className="btn btn-primary" onClick={confirmMemory}>Confirm</button>
          {heroMemories[creatorSlot] && (
            <button className="btn btn-danger" onClick={clearMemory}>Remove</button>
          )}
          <button className="btn btn-secondary" onClick={() => { setCreatorSlot(null); setDraft(null) }}>Cancel</button>
        </div>
      </div>
    </div>
  )

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
      </div>

      {selectedTrait ? (
        <div className="hero-trait-body">
          <div className="trait-main-row">

            {/* Base trait — always selected */}
            <div className="trait-base-col">
              {/* Top slot reserved for future Revival Hero Memories. */}
              <div className="memory-slot-circle disabled" title="Coming Soon">
                <span className="memory-slot-coming-soon">Coming Soon</span>
              </div>
              <div className={`trait-tier-label${baseDisabled ? ' locked' : ''}`}>
                Base Trait{baseDisabled ? ' (off)' : ''}
              </div>
              <div className="trait-slot-level-row">
                {[1, 2, 3, 4, 5].map(lv => (
                  <button
                    key={lv}
                    className={`trait-slot-level-btn${nodeLevel(SLOT_BASE) === lv && !baseDisabled ? ' active' : ''}`}
                    onClick={e => { e.stopPropagation(); setSlotLevel(SLOT_BASE, lv) }}
                  >{lv}</button>
                ))}
              </div>
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
              {/* Holy Domain support slot — BELOW the trait, only when Invulnerability / Divine Intervention grants it. */}
              {traitGrantsSkillSlot(traitId, advancedTraitSelections) && (
                <div style={{ marginTop: 10 }}>
                  <div className="trait-tier-label" style={{ fontSize: 10, marginBottom: 4 }}>Support Slot</div>
                  <TraitSkillSlot supports={traitSkillSupports} allSkills={allSkills} onChange={setTraitSkillSupports} />
                </div>
              )}
            </div>

            <div className="trait-v-divider" />

            {/* Tier columns — one per unlock_level */}
            <div className="trait-tiers-row">
              {LEVEL_THRESHOLDS.map(threshold => {
                const group = selectedTrait.advanced_traits.filter(t => t.unlock_level === threshold)
                if (group.length === 0) return null
                const slotIdx = SLOT_IDX[threshold]
                const tierDisabled = nodeDisabled(slotIdx)
                const slotLevel = nodeLevel(slotIdx)
                const locked = characterLevel < threshold
                const primaries = group.filter(t => !t.is_pick_one_from_two)
                const subs = group.filter(t => t.is_pick_one_from_two)
                const memSlotIdx = THRESHOLD_TO_MEMORY_SLOT[threshold]
                const memory = heroMemories[memSlotIdx] ?? null
                const rarityColor = memory ? MEMORY_RARITY_COLORS[memory.rarity] : undefined

                return (
                  <div key={threshold} className="trait-tier-col">
                    {/* Memory slot circle */}
                    <MemorySlotCircle
                      memory={memory}
                      rarityColor={rarityColor}
                      slot={memSlotIdx}
                      onOpen={() => openMemoryCreator(memSlotIdx)}
                    />

                    <div className={`trait-tier-label${locked || tierDisabled ? ' locked' : ''}`}>
                      Level {threshold}{tierDisabled ? ' (off)' : ''}
                    </div>
                    <div className="trait-slot-level-row">
                      {[1, 2, 3, 4, 5].map(lv => (
                        <button
                          key={lv}
                          className={`trait-slot-level-btn${slotLevel === lv && !tierDisabled ? ' active' : ''}${locked ? ' locked' : ''}`}
                          onClick={e => { e.stopPropagation(); !locked && setSlotLevel(slotIdx, lv) }}
                        >{lv}</button>
                      ))}
                    </div>

                    <div className="trait-tier-primaries">
                      {primaries.map(t => {
                        const selected = advancedTraitSelections.includes(t.name)
                        return (
                          <TraitCircle
                            key={t.name}
                            className={`trait-circle${selected ? ' selected' : ''}${locked ? ' locked' : ''}`}
                            name={t.name}
                            icon={iconUrl('hero_trait', t.icon_url)}
                            checked={selected}
                            locked={locked}
                            disabled={selected && tierDisabled}
                            tipName={t.name}
                            slotLevel={slotLevel}
                            effects={t.effects ?? []}
                            onSelect={() => selectPrimary(t.name, threshold)}
                            onContextMenu={selected && !locked ? () => disableNode(slotIdx) : undefined}
                          />
                        )
                      })}
                    </div>

                    {subs.length > 0 && (
                      <div className="trait-tier-subs">
                        <div className="trait-tier-sub-label">Pick One</div>
                        {subs.map(t => {
                          const selected = advancedTraitSelections.includes(t.name)
                          return (
                            <TraitCircle
                              key={t.name}
                              className={`trait-circle${selected ? ' selected' : ''}${locked ? ' locked' : ''}`}
                              name={t.name}
                              icon={iconUrl('hero_trait', t.icon_url)}
                              checked={selected}
                              locked={locked}
                              disabled={selected && tierDisabled}
                              tipName={t.name}
                              slotLevel={slotLevel}
                              effects={t.effects ?? []}
                              onSelect={() => selectSub(t.name, threshold)}
                              onContextMenu={selected && !locked ? () => disableNode(slotIdx) : undefined}
                            />
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
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
        </div>
      ) : (
        <div className="hero-trait-body">
          <div className="panel-empty">Select a hero trait from the dropdown above.</div>
        </div>
      )}


      {creatorModal}
    </div>
  )
}
