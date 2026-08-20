// Shared Hero Trait UI pieces used by HeroTraitScreen.tsx (the fixed tier-column trait layout),
// HeroTraitTree.tsx (Selena's "Dance of the Deep" allocatable-tree layout), and
// PlayerStatsScreen.tsx (the equipped-trait tooltip). Extracted here so the two screen modules
// no longer import from each other (they used to form a circular dependency: HeroTraitScreen
// imported HeroTraitTree, and HeroTraitTree imported these pieces back from HeroTraitScreen).
import React from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { CreatedHeroMemory, MemorySlotSelection, MemoryRarity, MEMORY_RARITY_COLORS, HeroMemoryType, iconUrl,
  MAX_LEVEL_BY_RARITY, memoryTraitLevel, waxBaseStat, scaleSelValue, memoryRangeBounds } from '../api/client'
import { useFloatingTooltip } from './tooltip/useFloatingTooltip'
import { useDamageDelta, type StateTransform } from './tooltip/useDamageDelta'
import { TooltipContributions } from './tooltip/TooltipContributions'
import { dec } from '../utils/num'

export const MEMORY_TYPE_LABELS: Record<CreatedHeroMemory['memoryType'], string> = {
  origin: 'Origin',
  discipline: 'Discipline',
  progress: 'Progress',
}

export const RARITY_LABELS: Record<MemoryRarity, string> = {
  normal: 'Normal', magic: 'Magic', rare: 'Rare', epic: 'Epic', ultimate: 'Ultimate',
}

// Resolve a memory's type icon (bundled webp) from the memory_types catalog. Rows are named "Memory of Origin"
// etc.; pair each to our 'origin'|'discipline'|'progress' key via MEMORY_TYPE_LABELS. Returns null until the
// data-scraper lands per-type icons in tli-data (callers fall back to the ◈ glyph).
export function memoryTypeIconUrl(
  memoryTypes: HeroMemoryType[] | null | undefined, type: CreatedHeroMemory['memoryType'],
): string | null {
  const row = (memoryTypes ?? []).find(t => t.name === `Memory of ${MEMORY_TYPE_LABELS[type]}`)
  return iconUrl('hero_memory', row?.icon_url)
}

// Resolves one memory-slot selection (tier + optional rolled value) to its display text. Mirrors
// buildMemoryEffects.resolveModifier in api/client.ts — keep the two in sync.
export function resolveMemoryEffect(sel: MemorySlotSelection): string {
  // Ensure leading + for modifiers that start with a digit (handles legacy stored data)
  const mod = /^\d/.test(sel.modifier) ? '+' + sel.modifier : sel.modifier
  // Optional leading '-' on each bound so a negative range (base-slot penalty "(-60–-55) %") resolves too.
  const RANGE = /\(-?\d+(?:\.\d+)?[–\-]-?\d+(?:\.\d+)?\)/g
  const fmt = (v: number): string => Number.isInteger(v) ? String(v) : dec(v)
  // Multi-range combo affix (independent rolls): fill each "(lo–hi)" in order from rolledValues (null → max).
  if (sel.rolledValues && sel.rolledValues.length) {
    const bounds = memoryRangeBounds(sel.modifier)
    let i = 0
    return mod.replace(RANGE, () => { const j = i++; const c = sel.rolledValues![j]; return fmt(c != null ? c : (bounds[j]?.max ?? 0)) })
  }
  if (sel.rolledValue === null) return mod
  return mod.replace(RANGE, fmt(sel.rolledValue))
}

// The memory trait-level helpers now live in api/client.ts (pure value layer, shared with the payload builder).
// Re-export MAX_LEVEL_BY_RARITY for existing importers (HeroTraitScreen); others import from client directly.
export { MAX_LEVEL_BY_RARITY }

// Tier → rarity color (Compendium art): T0 ultimate/red, T1 epic/orange, T2 rare/purple, T3 magic/blue, T4+ normal/white.
export const TIER_RARITY = ['ultimate', 'epic', 'rare', 'magic'] as const
export const tierColor = (tier: number): string => MEMORY_RARITY_COLORS[TIER_RARITY[tier] ?? 'normal']

// A rarity-colored FILLED background behind the natural item art. In-game the ICON stays its natural color;
// RARITY is shown by the card background behind it — so we tint the background, not the image.
export function memoryRarityBg(tint: string): string {
  return `linear-gradient(155deg, ${tint}b0 0%, ${tint}4d 100%), #12121d`
}

export function MemoryIcon({ icon, tint, size, glyphSize }: {
  icon: string | null; tint: string; size: number; glyphSize?: number
}) {
  return (
    <span className="memory-icon-frame" style={{ width: size, height: size, background: memoryRarityBg(tint) }}>
      {icon
        ? <img src={icon} alt="" />
        : <span style={{ color: tint, fontSize: glyphSize ?? Math.round(size * 0.55), lineHeight: 1 }}>◈</span>}
    </span>
  )
}

// In-game-style memory card (Compendium layout, our rarity keywords). Used by the creator preview AND as the
// hover tooltip on inventory tiles + slot circles. Sections are split by grey dividers; body text is white,
// only the title/rarity keyword and the tier badges carry color. The "+N to Hero Trait Level" fixed mod shows
// as its own fixed line AND feeds the additive TRAIT LEVEL total. maxLevel defaults to the rarity cap.
export function MemoryPreviewCard({ memory, icon, maxLevel, footer, valueScale }: {
  memory: CreatedHeroMemory; icon: string | null; maxLevel?: number
  footer?: React.ReactNode   // e.g. the damage-delta contribution — rendered as a bottom divider section
  // Base/Special-slot penalty: multiply the Base Stat + Random affix display VALUES by this (e.g. 0.4 for −60%),
  // matching what the engine applies. Fixed affixes are shown unscaled. Omit (or 1) for a normal memory.
  valueScale?: number
}) {
  const rc = MEMORY_RARITY_COLORS[memory.rarity]
  const cap = maxLevel ?? MAX_LEVEL_BY_RARITY[memory.rarity]
  const level = memory.level ?? cap
  const traitLevel = memoryTraitLevel(memory)   // SET value, clamped 1..5 (same as the engine)
  const scale = valueScale ?? 1
  const scaled = (sel: MemorySlotSelection) => (scale !== 1 ? scaleSelValue(sel, scale) : sel)
  const baseSel = memory.baseStat
  // Wax & Wane: show the BOOSTED base value (×1.3, same helper the engine uses) + a blue "(+30%)" indicator.
  const waxed = !!baseSel && !!memory.revived && !!memory.waxAndWane
  const baseDisplay = baseSel ? scaled(waxed ? waxBaseStat(baseSel) : baseSel) : null
  const fixedLines = memory.fixedAffixes.filter((s): s is MemorySlotSelection => !!s)
  const randomLines = memory.randomAffixes.filter((s): s is MemorySlotSelection => !!s)
  // Base-slot penalty indicator, shown on each AFFECTED line (base stat + random affixes) — same blue "(±%)"
  // treatment as Wax & Wane, so it's clear which lines are reduced and by how much. Fixed affixes get none.
  const penaltyPct = Math.round((1 - scale) * 100)
  const penaltyTag = scale !== 1
    ? <span className="memory-card-wax" title="Base slot penalty">(-{penaltyPct}%)</span> : null
  const affixLine = (sel: MemorySlotSelection, key: string, penalized = false) => (
    <li key={key} className="memory-card-affix">
      <span className="memory-card-tierbadge" style={{ color: tierColor(sel.tier ?? 0), borderColor: `${tierColor(sel.tier ?? 0)}66` }}>
        T{sel.tier ?? 0}
      </span>
      <span>{resolveMemoryEffect(sel)}{penalized ? penaltyTag : null}</span>
    </li>
  )
  const hasBody = !!baseSel || fixedLines.length > 0 || randomLines.length > 0 || !!(memory.revived && memory.revivalMod)
  return (
    <div className="memory-card" style={{ borderColor: `${rc}55` }}>
      <div className="memory-card-head">
        <div className="memory-card-icon"><MemoryIcon icon={icon} tint={rc} size={52} glyphSize={30} /></div>
        <div className="memory-card-headtext">
          <div className="memory-card-title" style={{ color: rc }}>Memory of {MEMORY_TYPE_LABELS[memory.memoryType]}</div>
          <div className="memory-card-sub">
            <span className="memory-card-rarity" style={{ color: rc }}>{RARITY_LABELS[memory.rarity]}</span>
            <span className="memory-card-kind">HERO MEMORY</span>
          </div>
        </div>
      </div>
      <div className="memory-card-sec memory-card-meta">
        <span>ENHANCEMENT LEVEL <b>{level}/{cap}</b></span>
        <span>TRAIT LEVEL <b>+{traitLevel}</b></span>
      </div>
      {baseDisplay && (
        <div className="memory-card-sec">
          <div className="memory-card-line">
            {resolveMemoryEffect(baseDisplay)}
            {waxed && <span className="memory-card-wax" title="Wax & Wane">(+30%)</span>}
            {scale !== 1 && penaltyTag}
          </div>
        </div>
      )}
      {fixedLines.length > 0 && (
        <ul className="memory-card-sec memory-card-affixes">{fixedLines.map((s, i) => affixLine(s, `f${i}`))}</ul>
      )}
      {randomLines.length > 0 && (
        <ul className="memory-card-sec memory-card-affixes">{randomLines.map((s, i) => affixLine(scaled(s), `r${i}`, scale !== 1))}</ul>
      )}
      {memory.revived && memory.revivalMod && (
        <div className="memory-card-sec">
          <div className="memory-card-line"><span className="memory-card-revival-tag">REVIVAL</span> {resolveMemoryEffect(memory.revivalMod)}</div>
        </div>
      )}
      {!hasBody && <div className="memory-card-sec"><div className="memory-card-empty">Configure affixes to preview</div></div>}
      {/* No memory-card-sec divider here — TooltipContributions draws its own top divider, so this only
          supplies the horizontal padding (avoids a doubled line above the damage delta). */}
      {footer && <div className="memory-card-footer">{footer}</div>}
    </div>
  )
}

// `text` may contain `(a/b/c/d/e)` Trait-Level 1–5 scaling segments — pick out the slot for `level`.
function resolveLevel(text: string, level: number): string {
  return text.replace(/\(([^)]+)\)/g, (_, inner) => {
    if (!inner.includes('/')) return `(${inner})`
    const parts = inner.split('/').map((p: string) => p.trim())
    return parts[Math.min(level - 1, parts.length - 1)]
  })
}

// ── Tooltip content shown for a base/advanced trait node or a tree node ──────────────────────────

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

// A memory slot circle + its hover info tooltip (only when a memory is socketed). Used by both
// HeroTraitScreen's fixed tier columns and HeroTraitTree's origin/discipline/progress rail.
export function MemorySlotCircle({ memory, rarityColor, slot, onOpen, icon, slotLabel, deltaStep, deltaKey, valueScale }: {
  memory: CreatedHeroMemory | null; rarityColor?: string; slot: number; onOpen: () => void
  icon?: string | null   // type icon (bundled webp); falls back to the ◈ glyph until icon data lands
  slotLabel?: string     // default slot name (Origin/Discipline/Progress) shown on top; a memory's label overrides it
  // Override the "remove this memory" damage-delta step (the Base slot clears baseMemory, not heroMemories[slot]).
  deltaStep?: StateTransform
  // Override the delta cache key. REQUIRED when `slot` isn't unique among sibling circles (the Base slot reuses
  // slot index 0, colliding with the Origin memory slot) — else both would share one cached contribution.
  deltaKey?: string
  valueScale?: number    // Base-slot penalty applied to the tooltip card's base + random values (e.g. 0.4 = −60%)
}) {
  // Anchor to the circle and open ABOVE it (flips/shifts to stay on-screen) — with the rail at the bottom
  // of the tree, 'top' opens up into the tree area rather than off the bottom/top edge.
  const tip = useFloatingTooltip({ anchor: 'element', side: 'top' })
  // Contribution of this socketed memory: remove it and diff vs the current build.
  const delta = useDamageDelta(
    tip.open && memory
      ? { key: deltaKey ?? `mem:rm:${slot}`, step: deltaStep ?? (s => ({ ...s, heroMemories: s.heroMemories.map((m, i) => i === slot ? null : m) as typeof s.heroMemories })) }
      : null,
    tip.open && !!memory,
  )
  // Top text = the memory's label if set, else the default slot name (Origin/Discipline/Progress).
  const topText = memory?.displayName ?? slotLabel ?? ''
  return (
    <>
      <div className="memory-slot">
        {topText ? <div className="memory-slot-name" title={topText}>{topText}</div> : null}
        <div
          {...(memory ? tip.triggerProps : {})}
          className={`memory-slot-circle${memory ? ' filled' : ''}`}
          style={memory ? { background: memoryRarityBg(rarityColor ?? '#888'), borderColor: `${rarityColor}cc`, boxShadow: `0 0 8px ${rarityColor}33` } : undefined}
          onClick={e => { e.stopPropagation(); onOpen() }}
        >
          {memory
            ? (icon
                ? <img src={icon} alt="" className="memory-slot-icon" />
                : <span style={{ color: rarityColor, fontSize: 26, lineHeight: 1 }}>◈</span>)
            : <span className="memory-slot-plus">+</span>}
        </div>
        {/* Bottom: memory level (no hammer icon), like in-game. */}
        <div className="memory-slot-level">{memory?.level ?? ''}</div>
      </div>
      {memory && tip.open && (
        <FloatingPortal>
          <div className="memory-tooltip-card" {...tip.floatingProps}>
            <MemoryPreviewCard memory={memory} icon={icon ?? null} valueScale={valueScale} footer={<TooltipContributions delta={delta} />} />
          </div>
        </FloatingPortal>
      )}
    </>
  )
}
