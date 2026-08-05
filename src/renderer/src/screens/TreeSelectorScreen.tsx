import React, { useEffect, useState } from 'react'
import { api, iconUrl, TreeSlot } from '../api/client'
import { GROUPS, canAddTree, findShiftCandidate } from '../treeGroups'
import SlotSidebar from '../components/SlotSidebar'
import ScreenHeader from '../components/ScreenHeader'
import LoadingState from '../components/LoadingState'
import { useBuildStore } from '../store/buildStore'

const EMPTY_SLOTS: null[] = [null, null, null, null]

interface Props {
  treeColors: Record<string, string>
  treeIcons?: Record<string, string | null>
  onSelectTree: (treeName: string) => void
  onRemoveTree: (slotIndex: number) => void
  onSlotClick: (slotIndex: number) => void
  onSlotReorder: (fromSlot: number, toSlot: number) => void
  onGoToTree?: (slotIndex: number) => void
  onGoToSelector: () => void
  onShiftUp: (fromSlot: number) => void
  onPreview: () => void
  previewMode?: boolean
}

const ORDINALS = ['', '1st', '2nd', '3rd', '4th']

function slotOf(treeName: string, slots: (TreeSlot | null)[]): number {
  return slots.findIndex(s => s?.treeName === treeName)
}

function contextLabel(slots: (TreeSlot | null)[]): string {
  if (!slots[0]) return 'Choose your Primary — one of the 6 Gods or Goddesses'
  if (!slots[1]) return `Choose a Subtree for ${slots[0].treeName}`
  const filled = slots.filter(Boolean).length
  if (filled === 4) return 'All slots filled — Remove a tree to replace it'
  return `Select your ${ORDINALS[filled + 1]} tree`
}

export default function TreeSelectorScreen({
  treeColors, treeIcons = {}, onSelectTree, onRemoveTree, onSlotClick,
  onSlotReorder, onGoToTree, onGoToSelector, onShiftUp, onPreview, previewMode = false,
}: Props) {
  const slots = useBuildStore(s => s.slots)
  const activeSlot = useBuildStore(s => s.activeSlot)
  const [localColors, setLocalColors] = useState<Record<string, string>>(treeColors)
  const [localIcons, setLocalIcons] = useState<Record<string, string | null>>(treeIcons)

  // Cross-tree node search: matches maps tree name → match count (null = not searching).
  const [search, setSearch] = useState('')
  const [matches, setMatches] = useState<Map<string, number> | null>(null)
  useEffect(() => {
    const q = search.trim()
    if (!q) { setMatches(null); return }
    const t = setTimeout(() => {
      api.searchTrees(q)
        .then(res => setMatches(new Map(res.map(r => [r.name, r.match_count]))))
        .catch(() => setMatches(new Map()))
    }, 250)
    return () => clearTimeout(t)
  }, [search])

  const [treesFailed, setTreesFailed] = useState(false)
  const [treesResolved, setTreesResolved] = useState(false)
  useEffect(() => {
    if (Object.keys(treeColors).length === 0) {
      api.getTrees().then(trees => {
        const colors: Record<string, string> = {}
        const icons: Record<string, string | null> = {}
        trees.forEach(t => { colors[t.name] = t.color; icons[t.name] = t.icon_url ?? null })
        setLocalColors(colors)
        setLocalIcons(icons)
        setTreesResolved(true)
      }).catch(() => setTreesFailed(true))
    } else {
      setLocalColors(treeColors)
      setLocalIcons(treeIcons)
      setTreesResolved(true)
    }
  }, [treeColors, treeIcons])
  // The card grid's names come from the hardcoded GROUPS registry, but colors/art/validity come
  // from the catalog — rendering the grid before that lands shows wrong-colored, art-less,
  // clickable stand-ins. Show a spinner until the fetch actually settles (an explicit resolved
  // flag, not emptiness — a legitimately empty catalog must not spin forever).
  const treesLoading = !treesFailed && !treesResolved

  const shiftCandidate = findShiftCandidate(slots)

  // Preview mode renders through the same ScreenHeader now — no bespoke header, no background
  // watermark on this screen (the card grid fills nearly the whole area, so a tiled watermark
  // barely showed through anyway). The header text alone is the preview signal here.
  const header = (
    <ScreenHeader
      left={
        <h2 style={{ fontSize: 16, color: '#aaa', fontWeight: 500, margin: 0 }}>
          {previewMode
            ? <><strong style={{ color: '#bbaaff' }}>Preview Mode</strong> — browse freely, nothing is saved to your build</>
            : contextLabel(slots)}
        </h2>
      }
    />
  )

  return (
    <div className="screen tree-selector">
      {header}
      <div className="selector-body">
        <SlotSidebar
          slots={previewMode ? EMPTY_SLOTS : slots}
          activeSlot={previewMode ? -1 : activeSlot}
          treeColors={localColors}
          treeIcons={localIcons}
          onOverview={onGoToSelector}
          onSlotClick={onSlotClick}
          onPreview={onPreview}
          inPreview={previewMode}
          dragDropEnabled={!previewMode}
          onSlotReorder={onSlotReorder}
        />
        <div className="tree-main">
          <div className="tree-overview-search">
            <div className="tree-search-bar">
              <input
                className="tree-search-input"
                placeholder="Search nodes across all trees…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              {search && <button className="tree-search-clear" onClick={() => setSearch('')}>✕</button>}
            </div>
            {search && (
              <span className="tree-overview-search-status">
                {matches === null ? 'Searching…'
                  : matches.size === 0 ? 'No trees match'
                  : `${matches.size} tree${matches.size === 1 ? '' : 's'} match`}
              </span>
            )}
          </div>
          {treesLoading ? (
            <LoadingState label="Loading talent trees…" />
          ) : treesFailed ? (
            <div className="panel-empty">Couldn't load the tree catalog — restart to retry.</div>
          ) : (
          <div className="tree-grid">
            {GROUPS.map(({ primary, trees }) => (
              <div key={primary} className="tree-group-col">
                <TreeCard
                  name={primary}
                  color={localColors[primary] || '#e94560'}
                  icon={iconUrl('talent_tree_selector', localIcons[primary])}
                  isPrimary
                  selectedSlot={previewMode ? -1 : slotOf(primary, slots)}
                  selectable={previewMode ? true : canAddTree(primary, slots)}
                  onSelect={() => onSelectTree(primary)}
                  onRemove={() => onRemoveTree(slotOf(primary, slots))}
                  onGoToTree={onGoToTree ? () => onGoToTree(slotOf(primary, slots)) : undefined}
                  previewMode={previewMode}
                  searchActive={matches !== null}
                  searchMatchCount={matches?.get(primary) ?? 0}
                />
                <div className="tree-subtrees">
                  {trees.map(name => {
                    const isShiftTarget = !previewMode && shiftCandidate?.treeName === name
                    return (
                      <TreeCard
                        key={name}
                        name={name}
                        color={localColors[name] || '#0f3460'}
                        icon={iconUrl('talent_tree_selector', localIcons[name])}
                        selectedSlot={previewMode ? -1 : slotOf(name, slots)}
                        selectable={previewMode ? true : canAddTree(name, slots)}
                        onSelect={() => onSelectTree(name)}
                        onRemove={() => onRemoveTree(slotOf(name, slots))}
                        onGoToTree={onGoToTree ? () => onGoToTree(slotOf(name, slots)) : undefined}
                        shiftCandidate={isShiftTarget ? shiftCandidate : null}
                        onShiftUp={onShiftUp}
                        previewMode={previewMode}
                        searchActive={matches !== null}
                        searchMatchCount={matches?.get(name) ?? 0}
                      />
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
          )}
        </div>
      </div>
    </div>
  )
}

function TreeCard({
  name, color, icon, isPrimary: isPrim, selectedSlot, selectable,
  onSelect, onRemove, onGoToTree, shiftCandidate, onShiftUp, previewMode = false,
  searchActive = false, searchMatchCount = 0,
}: {
  name: string
  color: string
  icon?: string | null
  isPrimary?: boolean
  selectedSlot: number
  selectable: boolean
  onSelect: () => void
  onRemove: () => void
  onGoToTree?: () => void
  shiftCandidate?: { treeName: string; fromSlot: number } | null
  onShiftUp?: (fromSlot: number) => void
  previewMode?: boolean
  searchActive?: boolean
  searchMatchCount?: number
}) {
  const isSelected = !previewMode && selectedSlot !== -1
  const isLocked = !isSelected && !selectable
  const isSelectable = selectable && !isSelected
  const isClickable = isSelectable || (isSelected && !!onGoToTree)
  // Search highlighting: when a search is active, trees with matches glow; the rest dim.
  const isSearchHit = searchActive && searchMatchCount > 0
  const isSearchMiss = searchActive && searchMatchCount === 0

  function handleClick() {
    if (isSelectable) onSelect()
    else if (isSelected && onGoToTree) onGoToTree()
  }

  return (
    <div
      className={`tree-card${isPrim ? ' tree-card-primary' : ''}${isSelected ? ' tree-card-selected' : ''}${isLocked ? ' tree-card-locked' : ''}${isSelectable ? ' tree-card-selectable' : ''}${isSearchHit ? ' tree-card-search-hit' : ''}${isSearchMiss ? ' tree-card-search-miss' : ''}${icon ? ' tree-card-has-icon' : ''}`}
      style={{ cursor: isClickable ? 'pointer' : 'default', '--tree-accent': color } as React.CSSProperties}
      onClick={isClickable ? handleClick : undefined}
    >
      {icon && <img className="tree-card-bg-icon" src={icon} alt="" />}
      <div className="tree-card-accent" style={{ background: color }} />
      <div className="tree-card-name" style={{ color: isLocked ? '#8a97a6' : '#ffffff' }}>
        {name}
      </div>
      {isSearchHit && <span className="tree-card-match-badge">{searchMatchCount}</span>}
      {/* Shift renders above Remove — Remove always sits last/at the very bottom of the card,
          whether or not a shift candidate is also present on this card. */}
      {shiftCandidate && onShiftUp && (
        <div
          className="tree-card-shift"
          onClick={e => { e.stopPropagation(); onShiftUp(shiftCandidate.fromSlot) }}
        >
          ↑ Move to Slot 2
        </div>
      )}
      {isSelected && (
        <div
          className="tree-card-btn tree-card-btn-remove"
          onClick={e => { e.stopPropagation(); onRemove() }}
        >
          Remove
        </div>
      )}
    </div>
  )
}
