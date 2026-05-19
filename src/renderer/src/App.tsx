import React, { useEffect, useState } from 'react'
import { initApi, api, Build, TreeSlot } from './api/client'
import { isPrimary, getSubtrees } from './treeGroups'
import BuildSelectScreen from './screens/BuildSelectScreen'
import BuildOverviewScreen from './screens/BuildOverviewScreen'
import TreeSelectorScreen from './screens/TreeSelectorScreen'
import TreeViewerScreen from './screens/TreeViewerScreen'

type Screen = 'build-select' | 'build-overview' | 'tree-selector' | 'tree-viewer'

interface Session {
  buildId: string | null
  buildName: string
  slots: (TreeSlot | null)[]
  activeSlot: number
}

const emptySession = (): Session => ({
  buildId: null,
  buildName: '',
  slots: [null, null, null, null],
  activeSlot: 0,
})

function firstEmptySlot(slots: (TreeSlot | null)[], from = 0): number {
  for (let i = from; i < slots.length; i++) {
    if (!slots[i]) return i
  }
  return 0
}

function App() {
  const [appReady, setAppReady] = useState(false)
  const [appError, setAppError] = useState('')
  const [screen, setScreen] = useState<Screen>('build-select')
  const [session, setSession] = useState<Session>(emptySession())
  const [treeColors, setTreeColors] = useState<Record<string, string>>({})

  useEffect(() => {
    initApi()
      .then(() => {
        setAppReady(true)
        api.getTrees().then(trees => {
          const colors: Record<string, string> = {}
          trees.forEach(t => { colors[t.name] = t.color })
          setTreeColors(colors)
        })
      })
      .catch(e => setAppError(String(e)))
  }, [])

  if (!appReady) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100vh', background: '#1a1a2e',
        color: appError ? '#ff6b6b' : '#888', flexDirection: 'column', gap: 8,
      }}>
        <span>{appError || 'Starting backend…'}</span>
        {appError && <pre style={{ fontSize: 11, color: '#555' }}>{appError}</pre>}
      </div>
    )
  }

  // ── Navigation helpers ────────────────────────────────────────────────────

  const goToBuildSelect = () => setScreen('build-select')

  const startNewBuild = () => {
    setSession(emptySession())
    setScreen('build-overview')
  }

  const openBuild = (build: Build) => {
    const rawSlots = build.slots ?? []
    const slots: (TreeSlot | null)[] = Array.from({ length: 4 }, (_, i) => rawSlots[i] ?? null)
    setSession({
      buildId: build.id ?? null,
      buildName: build.name,
      slots,
      activeSlot: firstEmptySlot(slots),
    })
    setScreen('build-overview')
  }

  const goToTreeSelector = () => {
    setSession(s => ({ ...s, activeSlot: firstEmptySlot(s.slots) }))
    setScreen('tree-selector')
  }

  // ── Tree selection ────────────────────────────────────────────────────────

  const canSelectInSlot = (treeName: string, slot: number, slots: (TreeSlot | null)[]): boolean => {
    if (slot === 0) return isPrimary(treeName)
    if (slot === 1) {
      const primary = slots[0]?.treeName
      return !!primary && getSubtrees(primary).includes(treeName)
    }
    return true
  }

  const handleSelectTree = (treeName: string) => {
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      const target = s.activeSlot
      if (!canSelectInSlot(treeName, target, slots)) return s
      slots[target] = { treeName, nodeStates: {} }
      return { ...s, slots, activeSlot: target }
    })
    // Navigate to viewer for the newly selected tree
    setScreen('tree-viewer')
  }

  const handleRemoveTree = (slotIndex: number) => {
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      slots[slotIndex] = null
      // Removing slot 1 (primary) cascades to slot 2
      if (slotIndex === 0) slots[1] = null
      return { ...s, slots, activeSlot: slotIndex }
    })
  }

  // Sidebar slot click: empty → go to tree-selector targeting that slot; filled → go to viewer
  const handleSlotClick = (slotIndex: number) => {
    setSession(s => ({ ...s, activeSlot: slotIndex }))
    const slot = session.slots[slotIndex]
    if (slot) {
      setScreen('tree-viewer')
    } else {
      setScreen('tree-selector')
    }
  }

  const updateNodeStates = (nodeStates: Record<string, number>) => {
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      const current = slots[s.activeSlot]
      if (current) slots[s.activeSlot] = { ...current, nodeStates }
      return { ...s, slots }
    })
  }

  const saveBuild = async (name: string) => {
    const build = {
      id: session.buildId ?? undefined,
      name,
      slots: session.slots,
    }
    const saved = await api.postBuild(build)
    setSession(s => ({ ...s, buildId: saved.id ?? null, buildName: name }))
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (screen === 'build-select') {
    return <BuildSelectScreen onNewBuild={startNewBuild} onOpenBuild={openBuild} />
  }

  if (screen === 'build-overview') {
    return (
      <BuildOverviewScreen
        buildName={session.buildName}
        buildId={session.buildId}
        slots={session.slots}
        onBack={goToBuildSelect}
        onTalentTree={goToTreeSelector}
        onSave={saveBuild}
      />
    )
  }

  if (screen === 'tree-selector') {
    return (
      <TreeSelectorScreen
        slots={session.slots}
        targetSlot={session.activeSlot}
        treeColors={treeColors}
        onSelectTree={handleSelectTree}
        onRemoveTree={handleRemoveTree}
        onSlotClick={handleSlotClick}
        onBack={() => setScreen('build-overview')}
      />
    )
  }

  if (screen === 'tree-viewer') {
    const slot = session.slots[session.activeSlot]
    if (!slot) {
      setScreen('tree-selector')
      return null
    }
    return (
      <TreeViewerScreen
        treeName={slot.treeName}
        treeColor={treeColors[slot.treeName] ?? '#e94560'}
        initialNodeStates={slot.nodeStates}
        slots={session.slots}
        activeSlot={session.activeSlot}
        onBack={() => setScreen('tree-selector')}
        onSlotClick={handleSlotClick}
        onNodeStatesChange={updateNodeStates}
      />
    )
  }

  return <div style={{ color: '#888', padding: 20 }}>Unknown screen state</div>
}

export default App
