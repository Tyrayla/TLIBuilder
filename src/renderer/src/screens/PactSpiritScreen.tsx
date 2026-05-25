import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { PactSpirit, PactSpiritSlot, SelectedPactSpirit } from '../api/client'
import { useBuildStore } from '../store/buildStore'

interface Props {
  pactSpirits: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]
  onPactSpiritsChange: (v: [SelectedPactSpirit | null, SelectedPactSpirit | null, SelectedPactSpirit | null]) => void
  onBack: () => void
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

export default function PactSpiritScreen({ pactSpirits, onPactSpiritsChange }: Props) {
  const spiritData = useBuildStore(s => s.allSpirits)
  const [activeSlot, setActiveSlot] = useState<0 | 1 | 2 | null>(null)
  const [search, setSearch] = useState('')
  const [affinityFilter, setAffinityFilter] = useState<string | null>(null)
  const [nodeTooltip, setNodeTooltip] = useState<{ lines: string[]; x: number; y: number } | null>(null)

  const allAffinities = Array.from(new Set(spiritData.flatMap(s => s.affinities))).sort()

  const selectedItemId = activeSlot !== null ? (pactSpirits[activeSlot]?.itemId ?? null) : null

  const filteredSpirits = spiritData.filter(s => {
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
    onPactSpiritsChange(next)
    setActiveSlot(null)
  }

  const removeSpirit = (slotIdx: 0 | 1 | 2, e: React.MouseEvent) => {
    e.stopPropagation()
    const next = [...pactSpirits] as typeof pactSpirits
    next[slotIdx] = null
    onPactSpiritsChange(next)
    if (activeSlot === slotIdx) setActiveSlot(null)
  }

  const changeRank = (slotIdx: 0 | 1 | 2, rank: number, e: React.ChangeEvent<HTMLSelectElement>) => {
    e.stopPropagation()
    const next = [...pactSpirits] as typeof pactSpirits
    const cur = next[slotIdx]
    if (!cur) return
    next[slotIdx] = { ...cur, rank }
    onPactSpiritsChange(next)
  }

  const handleSlotClick = (slotIdx: 0 | 1 | 2) => {
    setActiveSlot(prev => prev === slotIdx ? null : slotIdx)
    setSearch('')
    setAffinityFilter(null)
  }

  const tooltipRef = useRef<HTMLDivElement>(null)
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

  useLayoutEffect(() => {
    if (!nodeTooltip || !tooltipRef.current) return
    const el = tooltipRef.current
    const rect = el.getBoundingClientRect()
    const vw = window.innerWidth
    const overLeft = 8 - rect.left
    const overRight = rect.right - (vw - 8)
    if (overLeft > 0) {
      el.style.left = (parseFloat(el.style.left || '0') + overLeft) + 'px'
    } else if (overRight > 0) {
      el.style.left = (parseFloat(el.style.left || '0') - overRight) + 'px'
    }
    if (rect.top < 8) {
      el.style.top = (nodeTooltip.y + 60) + 'px'
      el.style.transform = 'translateX(-50%)'
    }
  }, [nodeTooltip])

  const handleNodeEnter = (lines: string[], e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setNodeTooltip({ lines, x: rect.left + rect.width / 2, y: rect.top - 8 })
  }

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
        ? (slot.ring === 'outer' && rankData ? rankData.modifiers : [slot.effect])
        : []

      gridItems.push(
        <div
          key={`node-${slotIdx}-${col}`}
          className={`pact-node-cell${slot ? ` has-node node-ring-${slot.ring}` : ''}`}
        >
          {slot && (
            <div
              className={`pact-node node-${slot.ring}`}
              onMouseEnter={e => handleNodeEnter(tooltipLines, e)}
              onMouseLeave={() => setNodeTooltip(null)}
            />
          )}
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
                )
              })}
              {sortedSpirits.length === 0 && (
                <div className="pact-spirit-empty-list">No spirits match.</div>
              )}
            </div>
          </div>
        )}
      </div>

      {nodeTooltip && (
        <div
          ref={tooltipRef}
          className="pact-spirit-node-tooltip"
          style={{ left: nodeTooltip.x, top: nodeTooltip.y }}
        >
          {nodeTooltip.lines.map((line, i) => (
            <div key={i} className={i === 0 ? 'pact-tooltip-main' : 'pact-tooltip-bonus'}>{line}</div>
          ))}
        </div>
      )}
    </div>
  )
}
