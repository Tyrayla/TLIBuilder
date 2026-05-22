import React, { useEffect, useRef, useState } from 'react'
import { api, HeroTrait, HeroAdvancedTrait } from '../api/client'

interface Props {
  traitId: string | null
  traitSlotLevels: number[]   // [base, lv45, lv60, lv75], each 1–5
  advancedTraitSelections: string[]
  characterLevel: number
  onTraitChange: (traitId: string, slotLevels: number[], advanced: string[]) => void
  onBack: () => void
}

interface TooltipState {
  isBase: boolean
  advancedTrait?: HeroAdvancedTrait
  x: number
  y: number
  pinned: boolean
}

// Slot index constants
const SLOT_BASE = 0
const SLOT_LV45 = 1
const SLOT_LV60 = 2
const SLOT_LV75 = 3
const LEVEL_THRESHOLDS = [45, 60, 75]
const SLOT_IDX: Record<number, number> = { 45: SLOT_LV45, 60: SLOT_LV60, 75: SLOT_LV75 }

// Tooltip card width in px — used for edge clamping
const TIP_W = 284
const TIP_H_EST = 320

function groupByHero(traits: HeroTrait[]): Record<string, HeroTrait[]> {
  const out: Record<string, HeroTrait[]> = {}
  for (const t of traits) {
    if (!out[t.hero]) out[t.hero] = []
    out[t.hero].push(t)
  }
  return out
}

// Replace (v1/v2/v3/v4/v5) range notation with the value at the given level
function resolveLevel(text: string, level: number): string {
  return text.replace(/\(([^)]+)\)/g, (_, inner) => {
    if (!inner.includes('/')) return `(${inner})`
    const parts = inner.split('/').map((p: string) => p.trim())
    return parts[Math.min(level - 1, parts.length - 1)]
  })
}

function clampTooltip(x: number, y: number): { left: number; top: number } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const left = x + TIP_W > vw - 8 ? x - TIP_W - 14 : x
  const top = Math.max(8, Math.min(y, vh - TIP_H_EST - 8))
  return { left, top }
}

export default function HeroTraitScreen({
  traitId,
  traitSlotLevels,
  advancedTraitSelections,
  characterLevel,
  onTraitChange,
  onBack,
}: Props) {
  const [allTraits, setAllTraits] = useState<HeroTrait[]>([])
  const [loading, setLoading] = useState(true)
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const screenRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.getHeroTraits()
      .then(res => setAllTraits(res.traits))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

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

  // ── Tooltip helpers ───────────────────────────────────────────────────────

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

  if (loading) {
    return (
      <div className="hero-trait-screen">
        <div className="hero-trait-header">
          <button className="btn-back" onClick={onBack}>← Back</button>
        </div>
        <div className="hero-trait-body"><div className="panel-empty">Loading traits…</div></div>
      </div>
    )
  }

  return (
    <div className="hero-trait-screen" ref={screenRef} onClick={() => tooltip?.pinned && setTooltip(null)}>
      {/* Header */}
      <div className="hero-trait-header">
        <button className="btn-back" onClick={onBack}>← Back</button>
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

                return (
                  <div key={threshold} className="trait-tier-col">
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

      {/* Floating tooltip — clamped to window edges */}
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
    </div>
  )
}
