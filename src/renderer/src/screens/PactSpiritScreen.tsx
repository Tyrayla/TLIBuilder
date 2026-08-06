import React, { useEffect, useMemo, useRef, useState } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import {
  api, PactSpirit, PactSpiritSlot, iconUrl,
  FateCatalog, FateCatalogItem, InstalledFate, UndeterminedFate,
  FATE_MICRO_LIMIT, FATE_MEDIUM_LIMIT, fateRanges,
} from '../api/client'
import { useBuildStore } from '../store/buildStore'
import EditableRollValue from '../components/EditableRollValue'
import LoadingState from '../components/LoadingState'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { useDamageDeltaList } from '../components/tooltip/useDamageDelta'
import { TooltipShell } from '../components/tooltip/TooltipShell'
import { SpiritTooltipBody } from '../components/tooltip/bodies/SpiritTooltipBody'

interface Props {
  onBack: () => void
}

// A reordered slot carrying its ORIGINAL index in spirit.slots (the stable fate key — inner slots share names).
interface OrderedSlot { slot: PactSpiritSlot; idx: number }

// Which node the fate picker is open for: a spirit's inner/mid node, or an Undetermined extra slot (`extra`).
type PickerState = { spiritSlot: number; key: string; tier: 'micro' | 'medium'; extra?: boolean }

const NODE_COLS = 10
const fateKey = (spiritSlot: number, dataIdx: number) => `${spiritSlot}:${dataIdx}`

// Canonical pact order (positional): 2 micro, 1 medium, ×3, then outer — i.e. inner0,inner1,mid0,inner2,inner3,
// mid1,inner4,inner5,mid2,outer. (Data order within each ring is preserved.)
function reorderSlots(slots: PactSpiritSlot[]): OrderedSlot[] {
  const withIdx = slots.map((slot, idx) => ({ slot, idx }))
  const inner = withIdx.filter(s => s.slot.ring === 'inner')
  const mid = withIdx.filter(s => s.slot.ring === 'mid')
  const outer = withIdx.filter(s => s.slot.ring === 'outer')
  const result: OrderedSlot[] = []
  let mi = 0
  for (let i = 0; i < inner.length; i++) {
    result.push(inner[i])
    if (i % 2 === 1 && mi < mid.length) result.push(mid[mi++])   // a medium after every 2 micro
  }
  while (mi < mid.length) result.push(mid[mi++])                 // any leftover mediums
  result.push(...outer)
  return result
}

// A single pact node (or fate-installed node). Inner=micro, mid=medium are fate-installable (click to open the
// picker); outer is not. Tooltip shows the installed fate's (mid-rolled) effect or the node's default effect, and
// prices the per-node + whole-spirit damage delta.
function PactNode({ ring, lines, spiritSlot, icon, fateable, installedFate, dualUnpaired, onClick }: {
  ring: string; lines: string[]; spiritSlot: number; icon?: string | null
  fateable?: boolean; installedFate?: InstalledFate | null; dualUnpaired?: boolean; onClick?: () => void
}) {
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
  const cls = `pact-node node-${ring}${fateable ? ' pact-node-fateable' : ''}${installedFate ? ' pact-node-fated' : ''}`
  return (
    <>
      <div className={cls} {...tip.triggerProps}
        style={installedFate ? { borderColor: dualUnpaired ? '#ff6b6b' : '#7a4ea0', background: '#1a1230' } : undefined}
        onClick={onClick}>
        {installedFate
          ? (iconUrl('destiny', installedFate.iconUrl)
              ? <img src={iconUrl('destiny', installedFate.iconUrl) ?? undefined} className="pact-node-img" alt="" />
              : <span className="pact-fate-mark" style={{ fontSize: 9, color: '#c79bff', textAlign: 'center', lineHeight: 1 }}>
                  {installedFate.shortName.slice(0, 8)}</span>)
          : icon && <img src={icon} className="pact-node-img" alt="" />}
      </div>
      {tip.open && lines.length > 0 && (
        <FloatingPortal>
          <div className="tooltip tooltip--spirit" {...tip.floatingProps}>
            <TooltipShell title={installedFate ? `Fate: ${installedFate.shortName}${dualUnpaired ? ' (Unpaired — needs 2)' : ''}` : undefined} deltas={banded}>
              <SpiritTooltipBody lines={lines} />
              {fateable && <div style={{ marginTop: 6, fontSize: 11, color: '#8a8aa5' }}>Click to {installedFate ? 'change/remove' : 'install'} a fate</div>}
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// Overlay to pick a fate for a node (filtered to the node's tier). Searchable; shows the global limit + dual pairing.
function FatePicker({ tier, pool, installed, microCount, medCount, dualCounts, ignoreLimit, onPick, onRemove, onSetRolls, onClose }: {
  tier: 'micro' | 'medium'; pool: FateCatalogItem[]; installed: InstalledFate | null
  microCount: number; medCount: number; dualCounts: Record<string, number>; ignoreLimit: boolean
  onPick: (f: FateCatalogItem) => void; onRemove: () => void
  onSetRolls: (vals: (number | null)[]) => void; onClose: () => void
}) {
  const [q, setQ] = useState('')
  const words = q.toLowerCase().split(/\s+/).filter(Boolean)
  const list = pool.filter(f => {
    const hay = (f.short_name + ' ' + f.effect_text).toLowerCase()
    return words.every(w => hay.includes(w))
  })
  const atCap = !ignoreLimit && (tier === 'micro' ? microCount >= FATE_MICRO_LIMIT : medCount >= FATE_MEDIUM_LIMIT)
  return (
    <div className="prism-overlay-backdrop" onClick={onClose}
      style={{ position: 'absolute', inset: 0, background: 'rgba(8,10,20,0.78)', zIndex: 40, display: 'flex',
        alignItems: 'flex-start', justifyContent: 'center', paddingTop: 56 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ background: '#12141f', border: '1px solid #2a2e44', borderRadius: 10, width: 560, maxWidth: '92%',
          maxHeight: '84%', overflow: 'auto', boxShadow: '0 12px 40px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid #2a2e44' }}>
          <span style={{ fontWeight: 600, color: '#cfd3ee' }}>Install {tier === 'micro' ? 'Micro' : 'Medium'} Fate{ignoreLimit ? ' (bonus slot)' : ''}</span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {!ignoreLimit && <span style={{ fontSize: 11, color: atCap ? '#ff6b6b' : '#8a8fb0' }}>
              Micro {microCount}/{FATE_MICRO_LIMIT} · Medium {medCount}/{FATE_MEDIUM_LIMIT}</span>}
            {installed && <button className="btn btn-sm" style={{ background: '#3a1a1a', color: '#ff8a8a' }} onClick={onRemove}>Remove</button>}
            <button className="btn btn-sm" style={{ background: '#2a1a1a', color: '#ff8a8a' }} onClick={onClose}>✕</button>
          </div>
        </div>
        <div style={{ padding: 12 }}>
          {installed && (() => {
            const ranges = fateRanges(installed.effectText)
            if (ranges.length === 0) return null
            const vals = installed.rolledValues ?? []
            const re = /\((\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)\)/g
            const parts: React.ReactNode[] = []
            let last = 0, i = 0, m: RegExpExecArray | null
            while ((m = re.exec(installed.effectText))) {
              parts.push(<span key={`t${i}`}>{installed.effectText.slice(last, m.index)}</span>)
              const idx = i
              const r = ranges[idx]
              const cur = vals[idx]
              const shown = (cur === null || cur === undefined) ? r.hi : cur
              parts.push(
                <EditableRollValue key={`v${idx}`} value={shown} dp={r.dp} range={[r.lo, r.hi]}
                  title={`Set roll (${r.lo}–${r.hi}); default = max`}
                  onCommit={v => {
                    const nv: (number | null)[] = [...vals]
                    while (nv.length < ranges.length) nv.push(null)
                    nv[idx] = v
                    onSetRolls(nv)
                  }} />
              )
              last = m.index + m[0].length
              i++
            }
            parts.push(<span key="tend">{installed.effectText.slice(last)}</span>)
            return (
              <div style={{ marginBottom: 10, padding: '8px 10px', borderRadius: 6, border: '1px solid #7a4ea0',
                background: '#1a1230' }}>
                <div style={{ fontSize: 10.5, color: '#b79ad6', textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 4 }}>
                  Installed: {installed.shortName} · click a value to set the roll
                </div>
                <div style={{ fontSize: 12.5, color: '#dfe3ff', lineHeight: 1.5 }}>{parts}</div>
              </div>
            )
          })()}
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search fates…" autoFocus
            style={{ width: '100%', background: '#0d0f18', color: '#dfe3ff', border: '1px solid #333', borderRadius: 4, padding: '6px 8px', fontSize: 12.5, marginBottom: 8 }} />
          {atCap && !installed && <div style={{ color: '#ff6b6b', fontSize: 12, marginBottom: 6 }}>{tier === 'micro' ? 'Micro' : 'Medium'} fate limit reached — remove one first.</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {list.map(f => {
              const dn = f.kind === 'dual_kismet'
              const paired = dn && (dualCounts[f.short_name] || 0) >= (installed?.shortName === f.short_name ? 2 : 1)
              const disabled = atCap && installed?.name !== f.name
              return (
                <div key={f.name} onClick={() => { if (!disabled) onPick(f) }}
                  style={{ padding: '6px 8px', borderRadius: 4, cursor: disabled ? 'not-allowed' : 'pointer',
                    opacity: disabled ? 0.4 : 1, border: '1px solid ' + (installed?.name === f.name ? '#7a4ea0' : '#2a2e44'),
                    background: installed?.name === f.name ? '#1a1230' : '#0d0f18' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ color: dn ? '#e0a050' : f.kind === 'kismet' ? '#9fc0ff' : '#cfd3ee', fontWeight: 600, fontSize: 12.5 }}>{f.short_name}</span>
                    {dn && <span style={{ fontSize: 9.5, color: paired ? '#6bcb77' : '#ff8a8a' }}>{paired ? 'Paired' : 'Needs 2'}</span>}
                  </div>
                  <div style={{ fontSize: 11.5, color: '#9aa', lineHeight: 1.35 }}>{f.effect_text}</div>
                </div>
              )
            })}
            {list.length === 0 && <div style={{ color: '#777', fontSize: 12, padding: '8px 0' }}>No fates match.</div>}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function PactSpiritScreen(_props: Props) {
  const spiritData = useBuildStore(s => s.allSpirits)
  const spiritsResolved = useBuildStore(s => s.spiritsResolved)
  const spiritsFetchFailed = useBuildStore(s => s.spiritsFetchFailed)
  const pactSpirits = useBuildStore(s => s.pactSpirits)
  const setPactSpirits = useBuildStore(s => s.setPactSpirits)
  const fates = useBuildStore(s => s.fates)
  const setFates = useBuildStore(s => s.setFates)
  const undetermined = useBuildStore(s => s.undetermined)
  const setUndetermined = useBuildStore(s => s.setUndetermined)
  const [activeSlot, setActiveSlot] = useState<0 | 1 | 2 | null>(null)
  const [search, setSearch] = useState('')
  const [affinityFilter, setAffinityFilter] = useState<string | null>(null)
  const [fateCat, setFateCat] = useState<FateCatalog | null>(null)
  // Open fate picker for a specific node. `extra` = an undetermined bonus slot (ignores the limit).
  const [picker, setPicker] = useState<PickerState | null>(null)
  const [undetOverlay, setUndetOverlay] = useState<number | null>(null)   // spirit slot whose Undetermined craft is open

  useEffect(() => { api.getDestiny().then(r => setFateCat(r.catalog ?? null)).catch(() => {}) }, [])

  const allAffinities = Array.from(new Set(spiritData.flatMap(s => s.affinities))).sort()
  const selectedItemId = activeSlot !== null ? (pactSpirits[activeSlot]?.itemId ?? null) : null

  // Global fate counts (undetermined bonus-slot fates do NOT count toward the 9/4 limit). Dual pairing is build-wide.
  const { microCount, medCount, dualCounts } = useMemo(() => {
    let micro = 0, med = 0
    const dual: Record<string, number> = {}
    for (const f of Object.values(fates)) {
      if (f.nodeTier === 'micro') micro++; else med++
      if (f.kind === 'dual_kismet') dual[f.shortName] = (dual[f.shortName] || 0) + 1
    }
    for (const u of undetermined) if (u) for (const f of u.slots) if (f && f.kind === 'dual_kismet') dual[f.shortName] = (dual[f.shortName] || 0) + 1
    return { microCount: micro, medCount: med, dualCounts: dual }
  }, [fates, undetermined])

  const otherSelectedIds = new Set(
    pactSpirits.map((p, i) => (i !== activeSlot ? p?.itemId ?? null : null)).filter((id): id is string => !!id)
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

  // Fate keys are slot-index-based, so changing/removing a spirit must clear that slot's fates + undetermined.
  const clearSlotFates = (slotIdx: number) => {
    const nextFates = Object.fromEntries(Object.entries(fates).filter(([k]) => !k.startsWith(`${slotIdx}:`)))
    if (Object.keys(nextFates).length !== Object.keys(fates).length) setFates(nextFates)
    if (undetermined[slotIdx]) { const u = [...undetermined]; u[slotIdx] = null; setUndetermined(u) }
  }
  const selectSpirit = (spirit: PactSpirit) => {
    if (activeSlot === null) return
    if (pactSpirits[activeSlot]?.itemId !== spirit.item_id) clearSlotFates(activeSlot)
    const next = [...pactSpirits] as typeof pactSpirits
    next[activeSlot] = { itemId: spirit.item_id, rank: 1 }
    setPactSpirits(next)
    setActiveSlot(null)
  }
  const removeSpirit = (slotIdx: 0 | 1 | 2, e: React.MouseEvent) => {
    e.stopPropagation()
    clearSlotFates(slotIdx)
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
    setSearch(''); setAffinityFilter(null)
  }

  // ── Fate install/remove ──────────────────────────────────────────────────────
  const toInstalled = (f: FateCatalogItem): InstalledFate => ({
    name: f.name, shortName: f.short_name, kind: f.kind as InstalledFate['kind'],
    nodeTier: (f.node_tier || 'micro') as 'micro' | 'medium', effectText: f.effect_text,
    iconUrl: f.icon_url ?? null,
  })
  const installFateOnNode = (key: string, f: FateCatalogItem) => setFates({ ...fates, [key]: toInstalled(f) })
  const removeFateOnNode = (key: string) => { const next = { ...fates }; delete next[key]; setFates(next) }
  const installFateInExtra = (spiritSlot: number, slotIdx: number, f: FateCatalogItem | null) => {
    const next = undetermined.map(u => u ? { ...u, slots: [...u.slots] } : u)
    const u = next[spiritSlot]
    if (!u) return
    u.slots[slotIdx] = f ? toInstalled(f) : null
    setUndetermined(next)
  }
  // Set the chosen per-range rolls on the currently-open picker's installed fate (node or extra slot).
  const setFateRollsFor = (p: PickerState, vals: (number | null)[]) => {
    if (p.extra) {
      const next = undetermined.map(u => u ? { ...u, slots: [...u.slots] } : u)
      const u = next[p.spiritSlot]; if (!u) return
      const cur = u.slots[Number(p.key)]; if (!cur) return
      u.slots[Number(p.key)] = { ...cur, rolledValues: vals }
      setUndetermined(next)
    } else {
      const cur = fates[p.key]; if (!cur) return
      setFates({ ...fates, [p.key]: { ...cur, rolledValues: vals } })
    }
  }

  // ── Undetermined craft ───────────────────────────────────────────────────────
  const setUndeterminedCfg = (spiritSlot: number, extraMicro: number, extraMedium: number) => {
    const next = [...undetermined]
    if (extraMicro === 0 && extraMedium === 0) { next[spiritSlot] = null }
    else {
      const prev = next[spiritSlot]
      const total = extraMicro + extraMedium
      const slots: (InstalledFate | null)[] = Array.from({ length: total }, (_, i) => prev?.slots?.[i] ?? null)
      next[spiritSlot] = { extraMicro, extraMedium, slots }
    }
    setUndetermined(next)
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

  // ── Grid (one row per spirit: card + 10 nodes; the Undetermined branch hangs BELOW the outer node) ──
  const undItemIcon = fateCat?.undetermined ? iconUrl('destiny', fateCat.undetermined.icon_url) : null   // when the item is placed
  const undDefaultIcon = iconUrl('destiny', 'UI_Contract_Small62_Icon_64.webp')                          // empty (generic +6/+6) spot
  const renderRow = (slotIdx: 0 | 1 | 2) => {
    const sel = pactSpirits[slotIdx]
    const isActive = activeSlot === slotIdx
    const spirit = sel ? spiritData.find(s => s.item_id === sel.itemId) : null
    const reordered = spirit ? reorderSlots(spirit.slots) : []
    const rankData = spirit && sel
      ? (spirit.upgrade_ranks.find(r => r.rank === sel.rank) ?? spirit.upgrade_ranks[spirit.upgrade_ranks.length - 1])
      : null
    const u = undetermined[slotIdx]
    return (
      <div className="pact-spirit-row" key={slotIdx}>
        <div className={`pact-card-cell${!sel ? ' empty' : ' filled'}${isActive ? ' active' : ''}`}
          onClick={() => handleSlotClick(slotIdx)}>
          {!sel ? (
            <><span className="pact-card-plus">+</span><span className="pact-card-add-label">Add Pactspirit</span></>
          ) : spirit ? (
            <>
              <div className="pact-spirit-slot-header">
                <span className="pact-spirit-slot-name">{spirit.name}</span>
                <button className="pact-spirit-remove-btn" onClick={e => removeSpirit(slotIdx, e)}>×</button>
              </div>
              <div className="pact-spirit-affinities">
                {spirit.affinities.map(a => <span key={a} className={`pact-affinity-tag affinity-${a.toLowerCase()}`}>{a}</span>)}
              </div>
              <div className="pact-spirit-rank-row" onClick={e => e.stopPropagation()}>
                <span className="pact-spirit-rank-label">Rank</span>
                <select className="pact-spirit-rank-select" value={sel.rank} onChange={e => changeRank(slotIdx, Number(e.target.value), e)}>
                  {[1, 2, 3, 4, 5, 6].map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
              {spirit.portrait_url && (
                <div className="pact-spirit-portrait-wrap">
                  <img src={iconUrl('pactspirit', spirit.portrait_url) ?? undefined} className="pact-spirit-portrait" alt="" />
                </div>
              )}
            </>
          ) : <span style={{ color: '#666', fontSize: 12 }}>Loading…</span>}
        </div>

        {/* Node area: a nested 10-col × 2-row grid (node row + Undetermined branch row) so branch slots align
            EXACTLY under the nodes above, with their connector lines meeting like the main row. */}
        <div className="pact-nodes-area">
          {Array.from({ length: NODE_COLS }, (_, col) => {
            const o = reordered[col]
            const slot = o?.slot
            const fateable = !!slot && slot.ring !== 'outer'
            const tier: 'micro' | 'medium' = slot?.ring === 'inner' ? 'micro' : 'medium'
            const key = o ? fateKey(slotIdx, o.idx) : ''
            const installed = o ? (fates[key] ?? null) : null
            const dualUnpaired = !!installed && installed.kind === 'dual_kismet' && (dualCounts[installed.shortName] || 0) < 2
            const lines = installed
              ? [installed.effectText]
              : slot ? (slot.ring === 'outer' && rankData ? rankData.modifiers : slot.effect) : []
            return (
              <div key={`node-${slotIdx}-${col}`} className={`pact-node-cell${slot ? ` has-node node-ring-${slot.ring}` : ''}`}
                style={{ gridColumn: col + 1, gridRow: 1 }}>
                {slot && (
                  <PactNode ring={slot.ring} lines={lines} spiritSlot={slotIdx} icon={iconUrl('pactspirit', slot.icon_url)}
                    fateable={fateable} installedFate={installed} dualUnpaired={dualUnpaired}
                    onClick={fateable ? () => setPicker({ spiritSlot: slotIdx, key, tier }) : undefined} />
                )}
              </div>
            )
          })}

          {sel && (() => {
            const outerIdx = reordered.findIndex(o => o.slot.ring === 'outer')
            const outerCol = (outerIdx >= 0 ? outerIdx : NODE_COLS - 1) + 1   // grid column under the outer node
            const hasExtra = !!u && u.slots.length > 0
            const cells: React.ReactNode[] = []
            cells.push(
              <div key="und" className={`pact-node-cell has-node node-ring-mid pact-branch-undet${hasExtra ? '' : ' pact-branch-solo'}`}
                style={{ gridColumn: outerCol, gridRow: 2 }}>
                <UndeterminedNode icon={u ? undItemIcon : undDefaultIcon} cfg={u} spiritSlot={slotIdx} onClick={() => setUndetOverlay(slotIdx)} />
              </div>
            )
            if (u) {
              const total = u.slots.length
              u.slots.forEach((f, k) => {
                const isMicro = k < u.extraMicro
                const col = Math.max(1, outerCol - 1 - k)            // grow leftward, aligned to columns above
                const dualUnpaired = !!f && f.kind === 'dual_kismet' && (dualCounts[f.shortName] || 0) < 2
                cells.push(
                  <div key={`ex-${k}`}
                    className={`pact-node-cell has-node node-ring-${isMicro ? 'inner' : 'mid'}${k === total - 1 ? ' pact-branch-first' : ''}`}
                    style={{ gridColumn: col, gridRow: 2 }}>
                    <PactNode ring={isMicro ? 'inner' : 'mid'} spiritSlot={slotIdx} fateable icon={undDefaultIcon}
                      lines={f ? [f.effectText] : ['+6 % Damage', '+6 % Minion Damage']}
                      installedFate={f} dualUnpaired={dualUnpaired}
                      onClick={() => setPicker({ spiritSlot: slotIdx, key: String(k), tier: isMicro ? 'micro' : 'medium', extra: true })} />
                  </div>
                )
              })
            }
            return cells
          })()}
        </div>
      </div>
    )
  }

  const pickerPool = picker ? (fateCat?.[picker.tier] ?? []) : []
  const pickerInstalled: InstalledFate | null = picker
    ? (picker.extra
        ? (undetermined[picker.spiritSlot]?.slots[Number(picker.key)] ?? null)
        : (fates[picker.key] ?? null))
    : null

  return (
    <div className="screen pact-spirit-screen">
      <div className="pact-spirit-header">
        <h2 className="pact-spirit-title">Pact Spirits</h2>
        <span style={{ marginLeft: 16, fontSize: 12, color: '#9aa' }}>
          Fates — Micro <b style={{ color: microCount > FATE_MICRO_LIMIT ? '#ff6b6b' : '#cfd3ee' }}>{microCount}/{FATE_MICRO_LIMIT}</b>
          {'  ·  '}Medium <b style={{ color: medCount > FATE_MEDIUM_LIMIT ? '#ff6b6b' : '#cfd3ee' }}>{medCount}/{FATE_MEDIUM_LIMIT}</b>
        </span>
      </div>

      <div className="pact-spirit-body">
        {/* Pre-load, the empty slot grid read as a confident "no spirits" board. Spirits come from
            App's getPactSpirits() fetch into the store — spinner until it settles, error if it failed. */}
        {!spiritsResolved ? (
          <LoadingState label="Loading pact spirits…" />
        ) : spiritsFetchFailed ? (
          <div className="panel-empty">Couldn't load pact spirits — restart to retry.</div>
        ) : (
        <div className="pact-spirit-grid">{([0, 1, 2] as const).map(renderRow)}</div>
        )}

        {activeSlot !== null && (
          <div ref={panelRef} className="pact-spirit-right-panel">
            {/* Mobile-only (hidden by CSS on desktop): the stacked picker fills the screen there,
                so it needs an explicit way out besides tapping another slot. */}
            <button className="pact-picker-close" onClick={() => setActiveSlot(null)}>✕ Close</button>
            <div className="pact-spirit-search-row">
              <input className="pact-spirit-search" placeholder="Search spirits…" value={search} onChange={e => setSearch(e.target.value)} autoFocus />
            </div>
            <div className="pact-spirit-affinity-filters">
              <button className={`pact-filter-btn${affinityFilter === null ? ' active' : ''}`} onClick={() => setAffinityFilter(null)}>All</button>
              {allAffinities.map(a => (
                <button key={a} className={`pact-filter-btn${affinityFilter === a ? ' active' : ''}`} onClick={() => setAffinityFilter(a)}>{a}</button>
              ))}
            </div>
            <div className="pact-spirit-list">
              {sortedSpirits.map(spirit => {
                const isBound = spirit.item_id === selectedItemId
                return (
                  <div key={spirit.item_id} className={`pact-spirit-list-item${isBound ? ' selected' : ''}`} onClick={() => selectSpirit(spirit)}>
                    <div className="pact-spirit-list-main">
                      <div className="pact-spirit-list-header">
                        <span className="pact-spirit-list-name">{spirit.name}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {isBound && <span className="pact-spirit-bound-badge">✓ Bound</span>}
                          <div className="pact-spirit-affinities">
                            {spirit.affinities.map(a => <span key={a} className={`pact-affinity-tag affinity-${a.toLowerCase()}`}>{a}</span>)}
                          </div>
                        </div>
                      </div>
                      <span className="pact-spirit-list-desc">{spirit.description}</span>
                    </div>
                    {spirit.portrait_url && <img src={iconUrl('pactspirit', spirit.portrait_url) ?? undefined} className="pact-spirit-list-icon" alt="" />}
                  </div>
                )
              })}
              {sortedSpirits.length === 0 && <div className="pact-spirit-empty-list">No spirits match.</div>}
            </div>
          </div>
        )}
      </div>

      {undetOverlay !== null && (
        <UndeterminedOverlay
          spiritSlot={undetOverlay}
          cfg={undetermined[undetOverlay] ?? null}
          spiritName={spiritData.find(s => s.item_id === pactSpirits[undetOverlay]?.itemId)?.name ?? 'Spirit'}
          onConfig={setUndeterminedCfg}
          onClose={() => setUndetOverlay(null)}
        />
      )}

      {picker && (
        <FatePicker
          tier={picker.tier} pool={pickerPool} installed={pickerInstalled}
          microCount={microCount} medCount={medCount} dualCounts={dualCounts} ignoreLimit={!!picker.extra}
          onPick={f => {
            if (picker.extra) installFateInExtra(picker.spiritSlot, Number(picker.key), f)
            else installFateOnNode(picker.key, f)
            setPicker(null)
          }}
          onRemove={() => {
            if (picker.extra) installFateInExtra(picker.spiritSlot, Number(picker.key), null)
            else removeFateOnNode(picker.key)
            setPicker(null)
          }}
          onSetRolls={vals => setFateRollsFor(picker, vals)}
          onClose={() => setPicker(null)}
        />
      )}
    </div>
  )
}

// The Undetermined Fate spot as a tree node (uses the undetermined fate icon): the +6%/+6% generic, or "expanded"
// when configured. Click → the craft overlay (set extra-slot counts). Plain tooltip (no NYI badge on the blurb).
function UndeterminedNode({ icon, cfg, spiritSlot, onClick }: {
  icon: string | null; cfg: UndeterminedFate | null; spiritSlot: number; onClick: () => void
}) {
  const tip = useFloatingTooltip({ anchor: 'element', side: 'top' })
  // When not expanded this node grants the generic +6%/+6%; when expanded the node itself adds nothing (its extra
  // slots carry the effect), so excluding [] yields a 0% "this node" delta — accurate.
  const lines = cfg ? [] : ['+6 % Damage', '+6 % Minion Damage']
  const deltas = useDamageDeltaList(
    tip.open
      ? [
          { key: `spirit:und:node:${spiritSlot}:${lines.join('|')}`,
            step: s => ({ ...s, spiritEffectExclude: lines }) },
          { key: `spirit:und:rm:${spiritSlot}`,
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
      <div className="pact-node node-mid pact-node-undet" {...tip.triggerProps} onClick={onClick}
        style={{ cursor: 'pointer', borderColor: cfg ? '#7a4ea0' : '#5a4a2a', background: cfg ? '#1a1230' : '#1c1a10' }}>
        {icon ? <img src={icon} className="pact-node-img" alt="" />
          : <span style={{ fontSize: 16, color: cfg ? '#c79bff' : '#e0a050', fontWeight: 700 }}>✦</span>}
      </div>
      {tip.open && (
        <FloatingPortal>
          <div className="tooltip tooltip--spirit" {...tip.floatingProps}>
            <TooltipShell title="Undetermined Fate" deltas={banded}>
              {cfg
                ? <div className="pact-tooltip-main">Expanded: {cfg.extraMicro} micro + {cfg.extraMedium} medium extra slots</div>
                : (<><div className="pact-tooltip-main">+6 % Damage</div><div className="pact-tooltip-bonus">+6 % Minion Damage</div></>)}
              <div style={{ marginTop: 6, fontSize: 11, color: '#8a8aa5' }}>Click to craft / expand fate slots</div>
            </TooltipShell>
          </div>
        </FloatingPortal>
      )}
    </>
  )
}

// Craft overlay for one spirit's Undetermined Fate: pick how many extra micro/medium slots it grants. The slots
// themselves are filled directly in the tree branch (right→left), so this is just the count config.
function UndeterminedOverlay({ spiritSlot, cfg, spiritName, onConfig, onClose }: {
  spiritSlot: number; cfg: UndeterminedFate | null; spiritName: string
  onConfig: (s: number, m: number, d: number) => void
  onClose: () => void
}) {
  return (
    <div className="prism-overlay-backdrop" onClick={onClose}
      style={{ position: 'absolute', inset: 0, background: 'rgba(8,10,20,0.78)', zIndex: 39, display: 'flex',
        alignItems: 'flex-start', justifyContent: 'center', paddingTop: 56 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ background: '#12141f', border: '1px solid #2a2e44', borderRadius: 10, width: 480, maxWidth: '92%', boxShadow: '0 12px 40px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid #2a2e44' }}>
          <span style={{ fontWeight: 600, color: '#cfd3ee' }}>Undetermined Fate — {spiritName}</span>
          <button className="btn btn-sm" style={{ background: '#2a1a1a', color: '#ff8a8a' }} onClick={onClose}>✕</button>
        </div>
        <div style={{ padding: 16 }}>
          <div style={{ fontSize: 12, color: '#9aa', marginBottom: 12 }}>
            Default node: <span style={{ color: '#e0a050' }}>+6% Damage / +6% Minion Damage</span>. Install an
            Undetermined Fate to expand it into extra fate slots (they ignore the 9/4 limit and default to the
            generic until filled). Set 0 / 0 to remove. Fill the new slots in the tree below the outer node.
          </div>
          <UndeterminedConfig spiritSlot={spiritSlot} extraMicro={cfg?.extraMicro ?? 0} extraMedium={cfg?.extraMedium ?? 0} onApply={onConfig} />
        </div>
      </div>
    </div>
  )
}

// Small inline editor for the undetermined fate's extra-slot counts (0–5 micro, 0–3 medium).
function UndeterminedConfig({ spiritSlot, extraMicro, extraMedium, onApply }: {
  spiritSlot: number; extraMicro: number; extraMedium: number; onApply: (s: number, m: number, d: number) => void
}) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#8a8fb0' }}>
      <label>+Micro
        <select value={extraMicro} onChange={e => onApply(spiritSlot, Number(e.target.value), extraMedium)}
          style={{ marginLeft: 3, background: '#0d0f18', color: '#dfe3ff', border: '1px solid #333', borderRadius: 4 }}>
          {[0, 1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
      <label>+Medium
        <select value={extraMedium} onChange={e => onApply(spiritSlot, extraMicro, Number(e.target.value))}
          style={{ marginLeft: 3, background: '#0d0f18', color: '#dfe3ff', border: '1px solid #333', borderRadius: 4 }}>
          {[0, 1, 2, 3].map(n => <option key={n} value={n}>{n}</option>)}
        </select>
      </label>
    </span>
  )
}
