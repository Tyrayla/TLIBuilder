// Shared Hero Trait UI pieces used by HeroTraitScreen.tsx (the fixed tier-column trait layout),
// HeroTraitTree.tsx (Selena's "Dance of the Deep" allocatable-tree layout), and
// PlayerStatsScreen.tsx (the equipped-trait tooltip). Extracted here so the two screen modules
// no longer import from each other (they used to form a circular dependency: HeroTraitScreen
// imported HeroTraitTree, and HeroTraitTree imported these pieces back from HeroTraitScreen).
import React from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { CreatedHeroMemory, MemorySlotSelection, MemoryRarity } from '../api/client'
import { useFloatingTooltip } from './tooltip/useFloatingTooltip'
import { useDamageDelta } from './tooltip/useDamageDelta'
import { TooltipContributions } from './tooltip/TooltipContributions'
import { ModifierBadge, useTextModifierStatuses } from './ModifierBadge'
import { dec } from '../utils/num'

export const MEMORY_TYPE_LABELS: Record<CreatedHeroMemory['memoryType'], string> = {
  origin: 'Origin',
  discipline: 'Discipline',
  progress: 'Progress',
}

export const RARITY_LABELS: Record<MemoryRarity, string> = {
  normal: 'Normal', magic: 'Magic', rare: 'Rare', epic: 'Epic', ultimate: 'Ultimate',
}

// Resolves one memory-slot selection (tier + optional rolled value) to its display text.
export function resolveMemoryEffect(sel: MemorySlotSelection): string {
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
export function MemorySlotCircle({ memory, rarityColor, slot, onOpen }: {
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
