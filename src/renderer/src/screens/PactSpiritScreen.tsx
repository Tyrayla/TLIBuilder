import React, { useEffect, useRef, useState } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import { PactSpirit, PactSpiritSlot, iconUrl } from '../api/client'
import { useBuildStore } from '../store/buildStore'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { useDamageDeltaList } from '../components/tooltip/useDamageDelta'
import { TooltipShell } from '../components/tooltip/TooltipShell'
import { SpiritTooltipBody } from '../components/tooltip/bodies/SpiritTooltipBody'

interface Props {
  onBack: () => void
}

// A single pact-spirit node plus its hover tooltip, routed through the shared floating primitive.
// Two damage deltas are priced at once: "This node" (remove just this node's effect line(s) from the
// spirit) and "Spirit total" (remove the whole spirit). Spirits are still selected as a unit, but the
// per-node number shows what each node is worth within the spirit.
function PactNode({ ring, lines, spiritSlot, icon }: { ring: string; lines: string[]; spiritSlot: number; icon?: string | null }) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'top' })
  const deltas = useDamageDeltaList(
    tip.open
      ? [
          { key: `spirit:node:${spiritSlot}:${lines.join('|')}`,
            step: s => ({ ...s, spiritEffectExclude: lines }) },
          { key: `spirit:rm:${spiritSlot}`,
            step: s => ({ ...s, pactSpirits: s.pactSpirits.map((p, i) => i === spiritSlot ? null : p) as typeof s.pactSpirits }) },
        ]
      : null,
    tip.open,
  )
  const loading = { state: 'loading' as const }
  const banded = [
    { label: 'This node', delta: deltas[0] ?? loading },
    { label: 'Spirit total', delta: deltas[1] ?? loading },
  ]
  return (
    <>
      <div className={`pact-node node-${ring}`} {...tip.triggerProps}>
        {icon && <img src={icon} className="pact-node-img" alt="" />}
      </div>
      {tip.open && lines.length > 0 && (
        <FloatingPortal>
          <div className="tooltip tooltip--spirit" {...tip.floatingProps}>
            <TooltipShell deltas={banded}>
              <SpiritTooltipBody lines={lines} />
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

const STRIP_ROMAN = /\s+(I{1,4}|IV|VI{0,3}|IX|V)$/i
const NODE_COLS = 10

function getBaseName(name: string): string {
  return name.replace(STRIP_ROMAN, '').trim()
}

function reorderSlots(slots: PactSpiritSlot[]): PactSpiritSlot[] {
  const inner = slots.filter(s => s.ring === 'inner')
  const mid = slots.filter(s => s.ring === 'mid')
  const outer = slots.filter(s => s.ring === 'outer')
  const groups = new Map<string, PactSpiritSlot[]>()
  for (const slot of inner) {
    const arr = groups.get(slot.name) ?? []
    arr.push(slot)
    groups.set(slot.name, arr)
  }
  const remainingMid = [...mid]
  const result: PactSpiritSlot[] = []
  for (const [name, group] of groups) {
    result.push(...group)
    const base = getBaseName(name)
    const idx = remainingMid.findIndex(s => getBaseName(s.name) === base)
    if (idx >= 0) {
      result.push(remainingMid[idx])
      remainingMid.splice(idx, 1)
    }
  }
  result.push(...remainingMid)
  result.push(...outer)
  return result
}

export default function PactSpiritScreen(_props: Props) {
  const spiritData = useBuildStore(s => s.allSpirits)
  const pactSpirits = useBuildStore(s => s.pactSpirits)
  const setPactSpirits = useBuildStore(s => s.setPactSpirits)
  const [activeSlot, setActiveSlot] = useState<0 | 1 | 2 | null>(null)
  const [search, setSearch] = useState('')
  const [affinityFilter, setAffinityFilter] = useState<string | null>(null)

  const allAffinities = Array.from(new Set(spiritData.flatMap(s => s.affinities))).sort()

  const selectedItemId = activeSlot !== null ? (pactSpirits[activeSlot]?.itemId ?? null) : null

  // A spirit can only be equipped once — hide any spirit already chosen in a DIFFERENT slot
  // (the active slot's own pick stays in the list, pinned to the front below).
  const otherSelectedIds = new Set(
    pactSpirits
      .map((p, i) => (i !== activeSlot ? p?.itemId ?? null : null))
      .filter((id): id is string => !!id)
  )

  const filteredSpirits = spiritData.filter(s => {
    if (otherSelectedIds.has(s.item_id)) return false
    if (affinityFilter && !s.affinities.includes(affinityFilter)) return false
    if (search && !s.name.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const sortedSpirits = selectedItemId
    ? [...filteredSpirits.filter(s => s.item_id === selectedItemId), ...filteredSpirits.filter(s => s.item_id !== selectedItemId)]
    : filteredSpirits

  const selectSpirit = (spirit: PactSpirit) => {
    if (activeSlot === null) return
    const next = [...pactSpirits] as typeof pactSpirits
    next[activeSlot] = { itemId: spirit.item_id, rank: 1 }
    setPactSpirits(next)
    setActiveSlot(null)
  }

  const removeSpirit = (slotIdx: 0 | 1 | 2, e: React.MouseEvent) => {
    e.stopPropagation()
    const next = [...pactSpirits] as typeof pactSpirits
    next[slotIdx] = null
    setPactSpirits(next)
    if (activeSlot === slotIdx) setActiveSlot(null)
  }

  const changeRank = (slotIdx: 0 | 1 | 2, rank: number, e: React.ChangeEvent<HTMLSelectElement>) => {
    e.stopPropagation()
    const next = [...pactSpirits] as typeof pactSpirits
    const cur = next[slotIdx]
    if (!cur) return
    next[slotIdx] = { ...cur, rank }
    setPactSpirits(next)
  }

  const handleSlotClick = (slotIdx: 0 | 1 | 2) => {
    setActiveSlot(prev => prev === slotIdx ? null : slotIdx)
    setSearch('')
    setAffinityFilter(null)
  }

  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (activeSlot === null) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current?.contains(e.target as Node)) return
      if ((e.target as Element).closest('.pact-card-cell')) return
      setActiveSlot(null)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [activeSlot])

  // Build flat array of grid items: 3 rows × 12 cells each
  const gridItems: React.ReactNode[] = []

  ;([0, 1, 2] as const).forEach(slotIdx => {
    const sel = pactSpirits[slotIdx]
    const isActive = activeSlot === slotIdx
    const spirit = sel ? spiritData.find(s => s.item_id === sel.itemId) : null
    const reordered = spirit ? reorderSlots(spirit.slots) : []
    const rankData = spirit && sel
      ? (spirit.upgrade_ranks.find(r => r.rank === sel.rank) ?? spirit.upgrade_ranks[spirit.upgrade_ranks.length - 1])
      : null

    // Column 0: spirit card
    gridItems.push(
      <div
        key={`card-${slotIdx}`}
        className={`pact-card-cell${!sel ? ' empty' : ' filled'}${isActive ? ' active' : ''}`}
        onClick={() => handleSlotClick(slotIdx)}
      >
        {!sel ? (
          <>
            <span className="pact-card-plus">+</span>
            <span className="pact-card-add-label">Add Pactspirit</span>
          </>
        ) : spirit ? (
          <>
            <div className="pact-spirit-slot-header">
              <span className="pact-spirit-slot-name">{spirit.name}</span>
              <button className="pact-spirit-remove-btn" onClick={e => removeSpirit(slotIdx, e)}>×</button>
            </div>
            <div className="pact-spirit-affinities">
              {spirit.affinities.map(a => (
                <span key={a} className={`pact-affinity-tag affinity-${a.toLowerCase()}`}>{a}</span>
              ))}
            </div>
            <div className="pact-spirit-rank-row" onClick={e => e.stopPropagation()}>
              <span className="pact-spirit-rank-label">Rank</span>
              <select
                className="pact-spirit-rank-select"
                value={sel.rank}
                onChange={e => changeRank(slotIdx, Number(e.target.value), e)}
              >
                {[1, 2, 3, 4, 5, 6].map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            {spirit.portrait_url && (
              <div className="pact-spirit-portrait-wrap">
                <img src={iconUrl('pactspirit', spirit.portrait_url) ?? undefined} className="pact-spirit-portrait" alt="" />
              </div>
            )}
          </>
        ) : (
          <span style={{ color: '#666', fontSize: 12 }}>Loading…</span>
        )}
      </div>
    )

    // Columns 1–11: one node per column
    for (let col = 0; col < NODE_COLS; col++) {
      const slot = reordered[col]
      const tooltipLines = slot
        ? (slot.ring === 'outer' && rankData ? rankData.modifiers : slot.effect)
        : []

      gridItems.push(
        <div
          key={`node-${slotIdx}-${col}`}
          className={`pact-node-cell${slot ? ` has-node node-ring-${slot.ring}` : ''}`}
        >
          {slot && <PactNode ring={slot.ring} lines={tooltipLines} spiritSlot={slotIdx} icon={iconUrl('pactspirit', slot.icon_url)} />}
        </div>
      )
    }
  })

  return (
    <div className="screen pact-spirit-screen">
      <div className="pact-spirit-header">
        <h2 className="pact-spirit-title">Pact Spirits</h2>
      </div>

      <div className="pact-spirit-body">
        <div className="pact-spirit-grid">
          {gridItems}
        </div>

        {activeSlot !== null && (
          <div ref={panelRef} className="pact-spirit-right-panel">
            <div className="pact-spirit-search-row">
              <input
                className="pact-spirit-search"
                placeholder="Search spirits…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                autoFocus
              />
            </div>
            <div className="pact-spirit-affinity-filters">
              <button
                className={`pact-filter-btn${affinityFilter === null ? ' active' : ''}`}
                onClick={() => setAffinityFilter(null)}
              >All</button>
              {allAffinities.map(a => (
                <button
                  key={a}
                  className={`pact-filter-btn${affinityFilter === a ? ' active' : ''}`}
                  onClick={() => setAffinityFilter(a)}
                >{a}</button>
              ))}
            </div>
            <div className="pact-spirit-list">
              {sortedSpirits.map(spirit => {
                const isBound = spirit.item_id === selectedItemId
                return (
                  <div
                    key={spirit.item_id}
                    className={`pact-spirit-list-item${isBound ? ' selected' : ''}`}
                    onClick={() => selectSpirit(spirit)}
                  >
                    <div className="pact-spirit-list-main">
                      <div className="pact-spirit-list-header">
                        <span className="pact-spirit-list-name">{spirit.name}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {isBound && <span className="pact-spirit-bound-badge">✓ Bound</span>}
                          <div className="pact-spirit-affinities">
                            {spirit.affinities.map(a => (
                              <span key={a} className={`pact-affinity-tag affinity-${a.toLowerCase()}`}>{a}</span>
                            ))}
                          </div>
                        </div>
                      </div>
                      <span className="pact-spirit-list-desc">{spirit.description}</span>
                    </div>
                    {spirit.portrait_url && (
                      <img src={iconUrl('pactspirit', spirit.portrait_url) ?? undefined} className="pact-spirit-list-icon" alt="" />
                    )}
                  </div>
                )
              })}
              {sortedSpirits.length === 0 && (
                <div className="pact-spirit-empty-list">No spirits match.</div>
              )}
            </div>
          </div>
        )}
      </div>

    </div>
  )
}
