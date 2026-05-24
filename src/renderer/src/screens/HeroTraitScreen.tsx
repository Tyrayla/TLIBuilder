import React, { useEffect, useRef, useState } from 'react'
import { HeroTrait, HeroAdvancedTrait, HeroMemoryAffix, CreatedHeroMemory, MemoryRarity, MemorySlotSelection, MEMORY_RARITY_COLORS } from '../api/client'
import { useReferenceStore } from '../store/referenceStore'

interface Props {
  traitId: string | null
  traitSlotLevels: number[]   // [base, lv45, lv60, lv75], each 1–5
  advancedTraitSelections: string[]
  characterLevel: number
  heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]
  onTraitChange: (traitId: string, slotLevels: number[], advanced: string[]) => void
  onHeroMemoriesChange: (heroMemories: [CreatedHeroMemory | null, CreatedHeroMemory | null, CreatedHeroMemory | null]) => void
  onBack: () => void
}

interface TooltipState {
  isBase: boolean
  advancedTrait?: HeroAdvancedTrait
  x: number
  y: number
  pinned: boolean
}

interface MemoryData {
  base_stats: HeroMemoryAffix[]
  fixed_affixes: HeroMemoryAffix[]
  random_affixes: HeroMemoryAffix[]
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

const TIP_W = 284
const TIP_H_EST = 320

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
  const val = Number.isInteger(sel.rolledValue) ? String(sel.rolledValue) : sel.rolledValue.toFixed(1)
  return mod.replace(/\(\d+(?:\.\d+)?[–\-]\d+(?:\.\d+)?\)/g, val)
}

function getMemoryAffixLines(memory: CreatedHeroMemory): string[] {
  const lines: string[] = []
  if (memory.baseStat) lines.push(resolveMemoryEffect(memory.baseStat))
  for (const fa of memory.fixedAffixes) { if (fa) lines.push(resolveMemoryEffect(fa)) }
  for (const ra of memory.randomAffixes) { if (ra) lines.push(resolveMemoryEffect(ra)) }
  return lines
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

function resolveLevel(text: string, level: number): string {
  return text.replace(/\(([^)]+)\)/g, (_, inner) => {
    if (!inner.includes('/')) return `(${inner})`
    const parts = inner.split('/').map((p: string) => p.trim())
    return parts[Math.min(level - 1, parts.length - 1)]
  })
}

function clampTooltip(x: number, y: number, w = TIP_W, h = TIP_H_EST): { left: number; top: number } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const left = x + w > vw - 8 ? x - w - 14 : x
  const top = Math.max(8, Math.min(y, vh - h - 8))
  return { left, top }
}

// ── Main component ────────────────────────────────────────────────────────────

export default function HeroTraitScreen({
  traitId,
  traitSlotLevels,
  advancedTraitSelections,
  characterLevel,
  heroMemories,
  onTraitChange,
  onHeroMemoriesChange,
  onBack,
}: Props) {
  const allTraits = useReferenceStore(s => s.heroTraits) ?? []
  const memoryData = useReferenceStore(s => s.heroMemories)
  const referenceResolved = useReferenceStore(s => s.referenceResolved)
  const traitsFailed = useReferenceStore(s => s.failedCatalogs.has('heroTraits'))

  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [creatorSlot, setCreatorSlot] = useState<number | null>(null)
  const [draft, setDraft] = useState<CreatedHeroMemory | null>(null)
  // Memory slot hover tooltip
  const [memHoverSlot, setMemHoverSlot] = useState<number | null>(null)
  const [memTooltipPos, setMemTooltipPos] = useState<{ x: number; y: number } | null>(null)
  // Affix row hover tooltip (inside creator modal)
  const [affixHoverText, setAffixHoverText] = useState<string | null>(null)
  const [affixHoverPos, setAffixHoverPos] = useState<{ x: number; y: number } | null>(null)
  const screenRef = useRef<HTMLDivElement>(null)

  const loading = !referenceResolved && allTraits.length === 0

  // Auto-select first trait when none selected
  useEffect(() => {
    if (!loading && traitId === null && allTraits.length > 0) {
      onTraitChange(allTraits[0].trait_id, [1, 1, 1, 1], [])
    }
  }, [loading, traitId, allTraits])

  const selectedTrait = allTraits.find(t => t.trait_id === traitId) ?? null
  const byHero = groupByHero(allTraits)

  const safeSlotLevels = (
    Array.isArray(traitSlotLevels) && traitSlotLevels.length === 4
      ? traitSlotLevels
      : [1, 1, 1, 1]
  )

  const baseLevel = safeSlotLevels[SLOT_BASE]
  const baseEffects = selectedTrait?.levels[baseLevel - 1]?.effects ?? []
  const showArtificialMoon = baseLevel === 5 && (selectedTrait?.artificial_moon?.effects?.length ?? 0) > 0

  function setSlotLevel(slotIdx: number, level: number) {
    if (!traitId) return
    const next = [...safeSlotLevels]
    next[slotIdx] = level
    onTraitChange(traitId, next, advancedTraitSelections)
  }

  function selectPrimary(name: string, threshold: number) {
    if (!traitId || !selectedTrait) return
    const falseNames = selectedTrait.advanced_traits
      .filter(t => t.unlock_level === threshold && !t.is_pick_one_from_two)
      .map(t => t.name)
    const next = advancedTraitSelections.filter(n => !falseNames.includes(n))
    next.push(name)
    onTraitChange(traitId, safeSlotLevels, next)
  }

  function selectSub(name: string, threshold: number) {
    if (!traitId || !selectedTrait) return
    const trueNames = selectedTrait.advanced_traits
      .filter(t => t.unlock_level === threshold && t.is_pick_one_from_two)
      .map(t => t.name)
    const next = advancedTraitSelections.filter(n => !trueNames.includes(n))
    next.push(name)
    onTraitChange(traitId, safeSlotLevels, next)
  }

  function switchTrait(newTraitId: string) {
    onTraitChange(newTraitId, [1, 1, 1, 1], [])
    setTooltip(null)
  }

  // ── Trait tooltip helpers ─────────────────────────────────────────────────

  function openTooltip(e: React.MouseEvent, state: Omit<TooltipState, 'x' | 'y'>) {
    setTooltip({ ...state, x: e.clientX + 14, y: e.clientY - 8 })
  }

  function trackTooltip(e: React.MouseEvent) {
    if (tooltip && !tooltip.pinned) {
      setTooltip(prev => prev ? { ...prev, x: e.clientX + 14, y: e.clientY - 8 } : null)
    }
  }

  function closeTooltip() {
    if (tooltip && !tooltip.pinned) setTooltip(null)
  }

  function clickCircle(
    e: React.MouseEvent,
    state: Omit<TooltipState, 'x' | 'y'>,
    onSelect?: () => void,
  ) {
    e.stopPropagation()
    const sameCircle = tooltip?.pinned
      && tooltip.isBase === state.isBase
      && tooltip.advancedTrait?.name === state.advancedTrait?.name
    if (sameCircle) { setTooltip(null); return }
    setTooltip({ ...state, x: e.clientX + 14, y: e.clientY - 8, pinned: true })
    onSelect?.()
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
    setTooltip(null)
    setMemHoverSlot(null)
    setMemTooltipPos(null)
  }

  function confirmMemory() {
    if (creatorSlot === null || !draft) return
    const next = [...heroMemories] as typeof heroMemories
    next[creatorSlot] = draft
    onHeroMemoriesChange(next)
    setCreatorSlot(null)
    setDraft(null)
  }

  function clearMemory() {
    if (creatorSlot === null) return
    const next = [...heroMemories] as typeof heroMemories
    next[creatorSlot] = null
    onHeroMemoriesChange(next)
    setCreatorSlot(null)
    setDraft(null)
  }

  // ── Unified-slider affix row ──────────────────────────────────────────────

  function renderAffixRow(
    label: string,
    pool: HeroMemoryAffix[],
    source: string,
    current: MemorySlotSelection | null,
    onChange: (sel: MemorySlotSelection | null) => void,
  ) {
    const names = getAffixNames(pool, source)
    const selectedName = current ? getAffixName(current.modifier) : ''
    const tierEntries = selectedName ? getTierOptions(pool, source, selectedName) : []
    const tierRanges = buildTierRanges(tierEntries)
    const sliderMax = tierRanges.length > 0 ? tierRanges[tierRanges.length - 1].endPos : 0

    // Current slider position → derive from stored (tier, rolledValue)
    const currentPos = current && tierRanges.length > 0
      ? tierValueToPos(tierRanges, current.tier, current.rolledValue)
      : 0
    const currentTierInfo = tierRanges.length > 0 ? posToTierValue(tierRanges, currentPos) : null

    const resolvedText = current ? resolveMemoryEffect(current) : null

    const handleNameChange = (name: string) => {
      if (!name) { onChange(null); return }
      const entries = getTierOptions(pool, source, name)
      if (entries.length === 0) { onChange(null); return }
      const ranges = buildTierRanges(entries)
      // Default to midpoint of the highest-value tier (best)
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
      <div
        className="memory-affix-row"
        onMouseEnter={resolvedText ? e => { setAffixHoverText(resolvedText); setAffixHoverPos({ x: e.clientX, y: e.clientY }) } : undefined}
        onMouseMove={resolvedText ? e => setAffixHoverPos({ x: e.clientX, y: e.clientY }) : undefined}
        onMouseLeave={() => { setAffixHoverText(null); setAffixHoverPos(null) }}
      >
        <span className="memory-affix-label">{label}</span>
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
                <input
                  type="range"
                  className="memory-affix-slider"
                  min={0}
                  max={sliderMax}
                  value={currentPos}
                  onChange={e => handleSliderChange(parseInt(e.target.value))}
                />
                <span className="memory-affix-slider-val">
                  {Number.isInteger(currentTierInfo.value) ? currentTierInfo.value : currentTierInfo.value.toFixed(1)}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    )
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
          {renderAffixRow('Base Stat', memoryData.base_stats, MEMORY_SOURCES[creatorSlot],
            draft.baseStat,
            sel => setDraft({ ...draft, baseStat: sel }))}
          {renderAffixRow('Fixed 1', memoryData.fixed_affixes, MEMORY_SOURCES[creatorSlot],
            draft.fixedAffixes[0],
            sel => setDraft({ ...draft, fixedAffixes: [sel, draft.fixedAffixes[1]] }))}
          {renderAffixRow('Fixed 2', memoryData.fixed_affixes, MEMORY_SOURCES[creatorSlot],
            draft.fixedAffixes[1],
            sel => setDraft({ ...draft, fixedAffixes: [draft.fixedAffixes[0], sel] }))}
          {renderAffixRow('Random 1', memoryData.random_affixes, MEMORY_SOURCES[creatorSlot],
            draft.randomAffixes[0],
            sel => setDraft({ ...draft, randomAffixes: [sel, draft.randomAffixes[1]] }))}
          {renderAffixRow('Random 2', memoryData.random_affixes, MEMORY_SOURCES[creatorSlot],
            draft.randomAffixes[1],
            sel => setDraft({ ...draft, randomAffixes: [draft.randomAffixes[0], sel] }))}
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
    <div className="hero-trait-screen" ref={screenRef} onClick={() => tooltip?.pinned && setTooltip(null)}>
      {/* Header */}
      <div className="hero-trait-header">
        <select
          className="hero-trait-select"
          value={traitId ?? ''}
          onChange={e => switchTrait(e.target.value)}
        >
          {Object.entries(byHero).map(([hero, variants]) => (
            <optgroup key={hero} label={hero}>
              {variants.map(v => (
                <option key={v.trait_id} value={v.trait_id}>{v.variant_name}</option>
              ))}
            </optgroup>
          ))}
        </select>
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
              {/* Disabled memory slot — Revival Memories (future) */}
              <div className="memory-slot-circle disabled" title="Coming Soon">
                <span className="memory-slot-coming-soon">Coming Soon</span>
              </div>
              <div className="trait-tier-label">Base Trait</div>
              <div className="trait-slot-level-row">
                {[1, 2, 3, 4, 5].map(lv => (
                  <button
                    key={lv}
                    className={`trait-slot-level-btn${safeSlotLevels[SLOT_BASE] === lv ? ' active' : ''}`}
                    onClick={e => { e.stopPropagation(); setSlotLevel(SLOT_BASE, lv) }}
                  >{lv}</button>
                ))}
              </div>
              <div
                className="trait-circle selected trait-circle-base"
                onMouseEnter={e => openTooltip(e, { isBase: true, pinned: false })}
                onMouseMove={trackTooltip}
                onMouseLeave={closeTooltip}
                onClick={e => clickCircle(e, { isBase: true, pinned: true })}
              >
                <div className="trait-circle-inner">
                  <span className="trait-circle-name">{selectedTrait.variant_name}</span>
                </div>
                <span className="trait-circle-check">✓</span>
              </div>
            </div>

            <div className="trait-v-divider" />

            {/* Tier columns — one per unlock_level */}
            <div className="trait-tiers-row">
              {LEVEL_THRESHOLDS.map(threshold => {
                const group = selectedTrait.advanced_traits.filter(t => t.unlock_level === threshold)
                if (group.length === 0) return null
                const slotIdx = SLOT_IDX[threshold]
                const slotLevel = safeSlotLevels[slotIdx]
                const locked = characterLevel < threshold
                const primaries = group.filter(t => !t.is_pick_one_from_two)
                const subs = group.filter(t => t.is_pick_one_from_two)
                const memSlotIdx = THRESHOLD_TO_MEMORY_SLOT[threshold]
                const memory = heroMemories[memSlotIdx] ?? null
                const rarityColor = memory ? MEMORY_RARITY_COLORS[memory.rarity] : undefined

                return (
                  <div key={threshold} className="trait-tier-col">
                    {/* Memory slot circle */}
                    <div
                      className={`memory-slot-circle${memory ? ' filled' : ''}`}
                      style={memory ? { borderColor: rarityColor, boxShadow: `0 0 10px ${rarityColor}44` } : undefined}
                      onClick={e => { e.stopPropagation(); openMemoryCreator(memSlotIdx) }}
                      onMouseEnter={memory ? e => { setMemHoverSlot(memSlotIdx); setMemTooltipPos({ x: e.clientX, y: e.clientY }) } : undefined}
                      onMouseMove={memory ? e => setMemTooltipPos({ x: e.clientX, y: e.clientY }) : undefined}
                      onMouseLeave={memory ? () => { setMemHoverSlot(null); setMemTooltipPos(null) } : undefined}
                    >
                      {memory
                        ? <span style={{ color: rarityColor, fontSize: 26, lineHeight: 1 }}>◈</span>
                        : <span className="memory-slot-plus">+</span>
                      }
                    </div>

                    <div className={`trait-tier-label${locked ? ' locked' : ''}`}>
                      Level {threshold}
                    </div>
                    <div className="trait-slot-level-row">
                      {[1, 2, 3, 4, 5].map(lv => (
                        <button
                          key={lv}
                          className={`trait-slot-level-btn${slotLevel === lv ? ' active' : ''}${locked ? ' locked' : ''}`}
                          onClick={e => { e.stopPropagation(); !locked && setSlotLevel(slotIdx, lv) }}
                        >{lv}</button>
                      ))}
                    </div>

                    <div className="trait-tier-primaries">
                      {primaries.map(t => {
                        const selected = advancedTraitSelections.includes(t.name)
                        return (
                          <div
                            key={t.name}
                            className={`trait-circle${selected ? ' selected' : ''}${locked ? ' locked' : ''}`}
                            onMouseEnter={e => !locked && openTooltip(e, { isBase: false, advancedTrait: t, pinned: false })}
                            onMouseMove={trackTooltip}
                            onMouseLeave={closeTooltip}
                            onClick={e => !locked && clickCircle(
                              e,
                              { isBase: false, advancedTrait: t, pinned: true },
                              () => selectPrimary(t.name, threshold),
                            )}
                          >
                            <div className="trait-circle-inner">
                              <span className="trait-circle-name">{t.name}</span>
                            </div>
                            {selected && <span className="trait-circle-check">✓</span>}
                          </div>
                        )
                      })}
                    </div>

                    {subs.length > 0 && (
                      <div className="trait-tier-subs">
                        <div className="trait-tier-sub-label">Pick One</div>
                        {subs.map(t => {
                          const selected = advancedTraitSelections.includes(t.name)
                          return (
                            <div
                              key={t.name}
                              className={`trait-circle${selected ? ' selected' : ''}${locked ? ' locked' : ''}`}
                              onMouseEnter={e => !locked && openTooltip(e, { isBase: false, advancedTrait: t, pinned: false })}
                              onMouseMove={trackTooltip}
                              onMouseLeave={closeTooltip}
                              onClick={e => !locked && clickCircle(
                                e,
                                { isBase: false, advancedTrait: t, pinned: true },
                                () => selectSub(t.name, threshold),
                              )}
                            >
                              <div className="trait-circle-inner">
                                <span className="trait-circle-name">{t.name}</span>
                              </div>
                              {selected && <span className="trait-circle-check">✓</span>}
                            </div>
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

      {/* Trait info tooltip */}
      {tooltip && selectedTrait && (() => {
        const pos = clampTooltip(tooltip.x, tooltip.y)
        const slotLevel = tooltip.isBase
          ? safeSlotLevels[SLOT_BASE]
          : safeSlotLevels[SLOT_IDX[tooltip.advancedTrait?.unlock_level ?? 45] ?? SLOT_LV45]
        const effects = tooltip.isBase
          ? baseEffects
          : (tooltip.advancedTrait?.effects ?? [])

        return (
          <div
            className="trait-info-card"
            style={{ left: pos.left, top: pos.top }}
            onClick={e => e.stopPropagation()}
          >
            <div className="trait-info-name">
              {tooltip.isBase ? selectedTrait.variant_name : tooltip.advancedTrait!.name}
            </div>
            <div className="trait-info-level-current">Level {slotLevel}</div>
            <ul className="trait-info-effects">
              {effects.map((line, i) =>
                /^Level \d+$/.test(line)
                  ? <li key={i} className="trait-info-level-header">{line}</li>
                  : <li key={i}>{resolveLevel(line, slotLevel)}</li>
              )}
            </ul>
            {tooltip.isBase && showArtificialMoon && (
              <>
                <div className="trait-info-level-header" style={{ color: '#7070cc', marginTop: 8 }}>Artificial Moon</div>
                <ul className="trait-info-effects">
                  {selectedTrait.artificial_moon.effects.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )
      })()}

      {/* Memory slot hover tooltip */}
      {memHoverSlot !== null && memTooltipPos && heroMemories[memHoverSlot] && (() => {
        const memory = heroMemories[memHoverSlot]!
        const lines = getMemoryAffixLines(memory)
        const rarityColor = MEMORY_RARITY_COLORS[memory.rarity]
        const pos = clampTooltip(memTooltipPos.x + 14, memTooltipPos.y - 8, 220, 200)
        return (
          <div
            className="memory-info-card"
            style={{ left: pos.left, top: pos.top }}
            onMouseEnter={() => { setMemHoverSlot(null); setMemTooltipPos(null) }}
          >
            <div className="memory-info-title" style={{ color: rarityColor }}>
              Memory of {MEMORY_TYPE_LABELS[memory.memoryType]}
            </div>
            <div className="memory-info-rarity" style={{ color: rarityColor }}>
              {RARITY_LABELS[memory.rarity]}
            </div>
            {lines.length > 0 ? (
              <ul className="memory-info-lines">
                {lines.map((line, i) => <li key={i}>{line}</li>)}
              </ul>
            ) : (
              <div className="memory-info-empty">No affixes configured</div>
            )}
            <div className="memory-info-hint">Click to edit</div>
          </div>
        )
      })()}

      {/* Affix row hover tooltip (inside creator) */}
      {affixHoverText && affixHoverPos && (
        <div
          className="memory-affix-hover-tooltip"
          style={{
            left: Math.min(affixHoverPos.x + 14, window.innerWidth - 240),
            top: Math.max(8, affixHoverPos.y - 36),
          }}
        >
          {affixHoverText}
        </div>
      )}

      {creatorModal}
    </div>
  )
}
