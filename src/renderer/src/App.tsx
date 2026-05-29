import React, { useEffect, useRef, useState } from 'react'
import { initApi, api, Build, TreeSlot, EquippedGearItem, EquippedSupportSkill, CreatedHeroMemory, MemoryRarity, MemorySlotSelection, SelectedPactSpirit, ResolvedAffixFields } from './api/client'
import { migrateOldConditions, buildDefaultConditionState } from './utils/conditions'
import { useBuildStore } from './store/buildStore'
import { useBuildCalculation } from './store/useBuildCalculation'
import { useReferenceStore } from './store/referenceStore'
import UpdateBanner, { UpdateInfo } from './components/UpdateBanner'
import BuildSidebar from './components/BuildSidebar'
import ImportExportOverlay from './components/ImportExportOverlay'
import HeroTraitScreen from './screens/HeroTraitScreen'
import PactSpiritScreen from './screens/PactSpiritScreen'
import NotesScreen from './screens/NotesScreen'
import { getSubtrees, autoAssignSlot, isValidBuildState } from './treeGroups'
import BuildSelectScreen from './screens/BuildSelectScreen'
import BuildOverviewScreen from './screens/BuildOverviewScreen'
import TreeSelectorScreen from './screens/TreeSelectorScreen'
import TreeViewerScreen from './screens/TreeViewerScreen'
import DevToolsScreen from './screens/DevToolsScreen'
import SlateScreen from './screens/SlateScreen'
import StatsScreen from './screens/StatsScreen'
import GearScreen from './screens/GearScreen'
import SkillsScreen from './screens/SkillsScreen'
import CalcsScreen from './screens/CalcsScreen'

type Screen = 'build-select' | 'build-overview' | 'tree-selector' | 'tree-viewer' | 'preview-selector' | 'preview-viewer' | 'dev-tools' | 'slate-board' | 'stats' | 'calcs' | 'gear' | 'skills' | 'hero-traits' | 'pact-spirits' | 'notes' | 'import-export'

interface CascadeModal {
  removingSlot: number
  shiftingTree: string
  shiftingFromSlot: number
  primaryName: string
}

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
  const [treeColors, setTreeColors] = useState<Record<string, string>>({})
  const [cascadeModal, setCascadeModal] = useState<CascadeModal | null>(null)
  const [previewTree, setPreviewTree] = useState<string | null>(null)
  const [previewSource, setPreviewSource] = useState<Screen>('build-overview')
  const [devMode, setDevMode] = useState(false)
  const [deprecatedTools, setDeprecatedTools] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const [unsavedPromptOpen, setUnsavedPromptOpen] = useState(false)
  const [unsavedSaveName, setUnsavedSaveName] = useState('')
  const [unsavedSaving, setUnsavedSaving] = useState(false)
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [updateDownloading, setUpdateDownloading] = useState(false)
  const [updateProgress, setUpdateProgress] = useState(0)
  const [updateDownloaded, setUpdateDownloaded] = useState(false)

  const [saveModalOpen, setSaveModalOpen] = useState(false)
  const [saveModalMode, setSaveModalMode] = useState<'save' | 'save-as'>('save')
  const [saveModalName, setSaveModalName] = useState('')
  const [saveModalSaving, setSaveModalSaving] = useState(false)
  const loadedVersionRef = useRef(0)
  const refConditions = useReferenceStore(s => s.conditions)

  // Store reads — replaces session useState
  const buildId = useBuildStore(s => s.buildId)
  const buildName = useBuildStore(s => s.buildName)
  const slots = useBuildStore(s => s.slots)
  const activeSlot = useBuildStore(s => s.activeSlot)
  const buildVersion = useBuildStore(s => s.buildVersion)

  useEffect(() => { window.api?.notifyDirty?.(isDirty) }, [isDirty])

  // When condition definitions load, fill any empty conditionState with defaults.
  // This covers new builds and imported builds that predate the conditions system.
  useEffect(() => {
    if (!refConditions) return
    const cur = useBuildStore.getState().conditionState
    if (Object.keys(cur).length > 0) return
    const defs = Object.values(refConditions).flat()
    const defaults = buildDefaultConditionState(defs)
    if (Object.keys(defaults).length > 0) useBuildStore.getState().setConditionState(defaults)
  }, [refConditions])

  useEffect(() => {
    initApi()
      .then(() => {
        setAppReady(true)
        api.getTrees().then(trees => {
          const colors: Record<string, string> = {}
          trees.forEach(t => { colors[t.name] = t.color })
          setTreeColors(colors)
        })
        api.getPactSpirits()
          .then(res => {
            useBuildStore.getState().setAllSpirits(
              res.spirits.filter(s => !s.affinities.includes('Drop'))
            )
          })
          .catch(() => {
            useBuildStore.getState().setSpiritsFailure()
          })
        useReferenceStore.getState().loadReferenceData()
      })
      .catch(e => setAppError(String(e)))
  }, [])

  useEffect(() => {
    window.api?.onRequestSave?.(() => {
      const s = useBuildStore.getState()
      if (s.buildId) {
        const build = { id: s.buildId, name: s.buildName, slots: s.slots, slates: s.slates, conditionState: s.conditionState, gear: s.gear, skills: s.skills, characterLevel: s.characterLevel, hasPrism: s.hasPrism, traitId: s.traitId, traitSlotLevels: s.traitSlotLevels, advancedTraitSelections: s.advancedTraitSelections, heroMemories: s.heroMemories, pactSpirits: s.pactSpirits, notes: s.notes, customMods: s.customMods }
        api.postBuild(build)
          .then(saved => {
            useBuildStore.getState().setBuildId(saved.id ?? null)
            setIsDirty(false)
          })
          .catch(() => {})
          .finally(() => window.api?.notifySaveDone())
      } else {
        window.api?.notifySaveDone()
      }
    })
  }, [])

  useEffect(() => {
    window.api?.getIsDev?.().then(isDev => {
      if (isDev) setDevMode(localStorage.getItem('devMode') === '1')
    })
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!(e.ctrlKey && e.shiftKey && e.key === 'D')) return
      window.api?.getIsDev?.().then(isDev => {
        if (!isDev) return
        setDevMode(prev => {
          const next = !prev
          localStorage.setItem('devMode', next ? '1' : '0')
          return next
        })
      })
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => {
    window.api?.onUpdateAvailable?.(setUpdateInfo)
    window.api?.onUpdateProgress?.(setUpdateProgress)
    window.api?.onUpdateDownloaded?.(() => { setUpdateDownloaded(true); setUpdateDownloading(false) })
  }, [])

  const handleUpdateDownload = async () => {
    setUpdateDownloading(true)
    await window.api?.downloadUpdate?.()
  }

  useBuildCalculation()

  // isDirty: true whenever buildVersion advances past the version we loaded at
  useEffect(() => {
    if (buildVersion > loadedVersionRef.current) setIsDirty(true)
  }, [buildVersion])


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

  // ── Navigation ────────────────────────────────────────────────────────────

  const goToBuildSelect = () => {
    if (isDirty) {
      setUnsavedSaveName(useBuildStore.getState().buildName)
      setUnsavedPromptOpen(true)
    } else {
      setScreen('build-select')
    }
  }

  const handleUnsavedSave = async () => {
    const s = useBuildStore.getState()
    const name = s.buildId ? s.buildName : (unsavedSaveName.trim() || 'Untitled')
    setUnsavedSaving(true)
    try {
      await saveBuild(name)
      setUnsavedPromptOpen(false)
      setScreen('build-select')
    } catch { /* save failed — leave prompt open */ }
    finally { setUnsavedSaving(false) }
  }

  const handleUnsavedDiscard = () => {
    setIsDirty(false)
    setUnsavedPromptOpen(false)
    setScreen('build-select')
  }

  const startNewBuild = () => {
    useBuildStore.getState().loadBuild({
      buildId: null, buildName: '', activeSlot: 0,
      slots: [null, null, null, null], slates: [], conditionState: {},
      gear: [], skills: [], characterLevel: 100, hasPrism: false,
      traitId: null, traitSlotLevels: [1, 1, 1, 1], advancedTraitSelections: [],
      heroMemories: [null, null, null], pactSpirits: [null, null, null],
      notes: '', customMods: [],
    })
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
    setScreen('build-overview')
  }

  // ── Build import sanitizers ───────────────────────────────────────────────
  const sanitizeMemorySlot = (s: unknown): MemorySlotSelection | null => {
    if (!s || typeof s !== 'object') return null
    const o = s as Record<string, unknown>
    if (typeof o.modifier !== 'string' || typeof o.tier !== 'number') return null
    return { modifier: o.modifier, tier: o.tier, rolledValue: typeof o.rolledValue === 'number' ? o.rolledValue : null }
  }

  const sanitizeHeroMemory = (m: unknown): CreatedHeroMemory | null => {
    if (!m || typeof m !== 'object') return null
    const o = m as Record<string, unknown>
    if (o.memoryType !== 'origin' && o.memoryType !== 'discipline' && o.memoryType !== 'progress') return null
    const RARITIES: MemoryRarity[] = ['normal', 'magic', 'rare', 'epic', 'ultimate']
    const rarity: MemoryRarity = RARITIES.includes(o.rarity as MemoryRarity) ? o.rarity as MemoryRarity : 'epic'
    const fa = Array.isArray(o.fixedAffixes) ? o.fixedAffixes : []
    const ra = Array.isArray(o.randomAffixes) ? o.randomAffixes : []
    return {
      memoryType: o.memoryType,
      rarity,
      baseStat: sanitizeMemorySlot(o.baseStat),
      fixedAffixes: [sanitizeMemorySlot(fa[0]), sanitizeMemorySlot(fa[1])],
      randomAffixes: [sanitizeMemorySlot(ra[0]), sanitizeMemorySlot(ra[1])],
    }
  }

  const sanitizePactSpirit = (s: unknown): SelectedPactSpirit | null => {
    if (!s || typeof s !== 'object') return null
    const o = s as Record<string, unknown>
    if (typeof o.itemId !== 'string') return null
    const rank = typeof o.rank === 'number' ? Math.min(6, Math.max(1, Math.round(o.rank))) : 1
    return { itemId: o.itemId, rank }
  }

  const sanitizeSlot = (s: unknown): TreeSlot | null => {
    if (!s || typeof s !== 'object') return null
    const o = s as Record<string, unknown>
    if (typeof o.treeName !== 'string' || !o.treeName) return null
    const nodeStates: Record<string, number> = {}
    const raw = o.nodeStates
    if (raw && typeof raw === 'object') {
      for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
        if (typeof v === 'number') nodeStates[k] = v
      }
    }
    const coreTalentSelections: Record<string, string> = {}
    const core = o.coreTalentSelections
    if (core && typeof core === 'object' && !Array.isArray(core)) {
      for (const [k, v] of Object.entries(core as Record<string, unknown>)) {
        if (typeof v === 'string') coreTalentSelections[k] = v
      }
    }
    return { treeName: o.treeName, nodeStates, coreTalentSelections }
  }

  const openBuild = async (build: Build) => {
    const rawSlots = (build.slots ?? []) as unknown[]
    const slots: (TreeSlot | null)[] = Array.from({ length: 4 }, (_, i) => sanitizeSlot(rawSlots[i]))

    let gear: EquippedGearItem[] = (build.gear ?? []).map(g => ({
      ...g,
      affixes: Array.isArray(g.affixes) ? g.affixes : [],
      customizations: Array.isArray(g.customizations) ? g.customizations : [],
      corrosion_type: g.corrosion_type ?? 'none',
      corroded_explicit_indices: g.corroded_explicit_indices ?? [],
      mutation_affix_text: g.mutation_affix_text ?? null,
      mutation_resolved_affix: g.mutation_resolved_affix ?? null,
      selected_random_affixes: g.selected_random_affixes ?? {},
    }))

    // Re-resolve stat fields for crafted items — saved values can become stale
    // when override entries are added or the resolver improves.
    const craftedItems = gear.filter(g => g.is_crafted)
    if (craftedItems.length > 0) {
      const texts = [...new Set(
        craftedItems.flatMap(g => g.affixes
          .filter(a => a.affix_kind === 'numeric')
          .map(a => a.raw_text)
        )
      )]
      try {
        const { results } = await api.resolveGearAffixes(texts)
        gear = gear.map(item => {
          if (!item.is_crafted) return item
          return {
            ...item,
            affixes: item.affixes.map(aff => {
              const r: ResolvedAffixFields | undefined = results[aff.raw_text]
              if (!r) return aff
              return {
                ...aff,
                stat_key: r.stat_key ?? null,
                unit: r.unit ?? aff.unit ?? '',
                stat_keys: r.stat_keys,
                is_range_split: r.is_range_split,
                min_stat_keys: r.min_stat_keys,
                max_stat_keys: r.max_stat_keys,
                dual_stat_groups: r.dual_stat_groups,
              }
            })
          }
        })
      } catch {
        // Resolution failure is non-fatal — proceed with whatever was saved
      }
    }

    useBuildStore.getState().loadBuild({
      buildId: build.id ?? null,
      buildName: build.name,
      slots,
      activeSlot: firstEmptySlot(slots),
      slates: build.slates ?? [],
      conditionState: build.conditionState ?? migrateOldConditions(build.conditions, build.conditionValues),
      gear,
      skills: (build.skills ?? []).map(s => ({
        ...s,
        supports: (s.supports ?? []).map((sup: EquippedSupportSkill) => ({
          ...sup,
          skill_type: sup.skill_type ?? 'support_skill',
          level: sup.level ?? 20,
        })),
      })),
      characterLevel: build.characterLevel ?? 100,
      hasPrism: build.hasPrism ?? false,
      traitId: build.traitId ?? null,
      traitSlotLevels: build.traitSlotLevels ?? [build.traitLevel ?? 1, 1, 1, 1],
      advancedTraitSelections: build.advancedTraitSelections ?? [],
      heroMemories: [
        sanitizeHeroMemory((build.heroMemories ?? [])[0]),
        sanitizeHeroMemory((build.heroMemories ?? [])[1]),
        sanitizeHeroMemory((build.heroMemories ?? [])[2]),
      ],
      pactSpirits: [
        sanitizePactSpirit((build.pactSpirits ?? [])[0]),
        sanitizePactSpirit((build.pactSpirits ?? [])[1]),
        sanitizePactSpirit((build.pactSpirits ?? [])[2]),
      ],
      notes: typeof build.notes === 'string' ? build.notes : '',
      customMods: Array.isArray(build.customMods) ? (build.customMods as string[]).filter(m => typeof m === 'string') : [],
    })
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
    setScreen('build-overview')
  }

  const goToTreeSelector = () => {
    useBuildStore.getState().setActiveSlot(firstEmptySlot(useBuildStore.getState().slots))
    setScreen('tree-selector')
  }

  const goToPreview = () => {
    setPreviewSource(screen)
    setScreen('preview-selector')
  }

  const handlePreviewTree = (treeName: string) => {
    setPreviewTree(treeName)
    setScreen('preview-viewer')
  }

  // ── Tree selection ────────────────────────────────────────────────────────

  const handleSlotReorder = (fromSlot: number, toSlot: number) => {
    const store = useBuildStore.getState()
    const currentSlots = store.slots
    const moving = currentSlots[fromSlot]
    if (!moving) return
    const result = [...currentSlots] as (TreeSlot | null)[]
    result[fromSlot] = currentSlots[toSlot] ?? null
    result[toSlot] = moving
    if (!isValidBuildState(result)) return
    store.reorderSlots(fromSlot, toSlot)
    let next = store.activeSlot
    if (next === fromSlot) next = toSlot
    else if (next === toSlot && currentSlots[toSlot]) next = fromSlot
    store.setActiveSlot(next)
  }

  const handleSelectTree = (treeName: string) => {
    const store = useBuildStore.getState()
    const targetSlot = autoAssignSlot(treeName, store.slots)
    if (targetSlot === -1) return
    store.setSlot(targetSlot, { treeName, nodeStates: {} })
    store.setActiveSlot(targetSlot)
    setScreen('tree-viewer')
  }

  const handleRemoveTree = (slotIndex: number) => {
    if (slotIndex === 1) {
      const primary = slots[0]?.treeName
      if (primary) {
        const subtrees = getSubtrees(primary)
        for (const i of [2, 3]) {
          const candidate = slots[i]?.treeName
          if (candidate && subtrees.includes(candidate)) {
            setCascadeModal({ removingSlot: 1, shiftingTree: candidate, shiftingFromSlot: i, primaryName: primary })
            return
          }
        }
      }
    }
    doRemoveTree(slotIndex)
  }

  const doRemoveTree = (slotIndex: number) => {
    const store = useBuildStore.getState()
    const next = [...store.slots] as (TreeSlot | null)[]
    next[slotIndex] = null
    if (slotIndex === 0) next[1] = null
    store.setSlots(next)
    store.setActiveSlot(firstEmptySlot(next))
  }

  const handleCascadeYes = () => {
    if (!cascadeModal) return
    const store = useBuildStore.getState()
    const next = [...store.slots] as (TreeSlot | null)[]
    next[cascadeModal.removingSlot] = next[cascadeModal.shiftingFromSlot]
    next[cascadeModal.shiftingFromSlot] = null
    store.setSlots(next)
    store.setActiveSlot(firstEmptySlot(next))
    setCascadeModal(null)
  }

  const handleCascadeNo = () => {
    if (!cascadeModal) return
    doRemoveTree(cascadeModal.removingSlot)
    setCascadeModal(null)
  }

  const handleShiftUp = (fromSlot: number) => {
    useBuildStore.getState().shiftSlotUp(fromSlot)
  }

  const handleSlotClick = (slotIndex: number) => {
    useBuildStore.getState().setActiveSlot(slotIndex)
    if (slots[slotIndex]) {
      setScreen('tree-viewer')
    } else {
      setScreen('tree-selector')
    }
  }

  const handleReselect = () => {
    const store = useBuildStore.getState()
    const next = [...store.slots] as (TreeSlot | null)[]
    next[store.activeSlot] = null
    if (store.activeSlot === 0) next[1] = null
    store.setSlots(next)
    setScreen('tree-selector')
  }

  const saveBuild = async (name: string) => {
    const s = useBuildStore.getState()
    const build = { id: s.buildId ?? undefined, name, slots: s.slots, slates: s.slates, conditionState: s.conditionState, gear: s.gear, skills: s.skills, characterLevel: s.characterLevel, hasPrism: s.hasPrism, traitId: s.traitId, traitSlotLevels: s.traitSlotLevels, advancedTraitSelections: s.advancedTraitSelections, heroMemories: s.heroMemories, pactSpirits: s.pactSpirits, notes: s.notes, customMods: s.customMods }
    const saved = await api.postBuild(build)
    useBuildStore.getState().setBuildId(saved.id ?? null)
    useBuildStore.getState().setBuildName(name)
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
  }

  const saveAsBuild = async (name: string) => {
    const s = useBuildStore.getState()
    const build = { id: undefined, name, slots: s.slots, slates: s.slates, conditionState: s.conditionState, gear: s.gear, skills: s.skills, characterLevel: s.characterLevel, hasPrism: s.hasPrism, traitId: s.traitId, traitSlotLevels: s.traitSlotLevels, advancedTraitSelections: s.advancedTraitSelections, heroMemories: s.heroMemories, pactSpirits: s.pactSpirits, notes: s.notes, customMods: s.customMods }
    const saved = await api.postBuild(build)
    useBuildStore.getState().setBuildId(saved.id ?? null)
    useBuildStore.getState().setBuildName(name)
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
  }

  const handleSidebarSave = () => {
    const s = useBuildStore.getState()
    if (s.buildId) {
      saveBuild(s.buildName).catch(() => {})
    } else {
      setSaveModalName(s.buildName)
      setSaveModalMode('save')
      setSaveModalOpen(true)
    }
  }

  const handleSidebarSaveAs = () => {
    setSaveModalName(useBuildStore.getState().buildName)
    setSaveModalMode('save-as')
    setSaveModalOpen(true)
  }

  const handleSaveModalConfirm = async () => {
    const name = saveModalName.trim() || 'Untitled'
    setSaveModalSaving(true)
    try {
      if (saveModalMode === 'save-as') {
        await saveAsBuild(name)
      } else {
        await saveBuild(name)
      }
      setSaveModalOpen(false)
    } catch { /* leave modal open */ }
    finally { setSaveModalSaving(false) }
  }

  const getBuildPayload = () => {
    const s = useBuildStore.getState()
    return {
      name: s.buildName,
      characterLevel: s.characterLevel,
      hasPrism: s.hasPrism,
      slots: s.slots,
      slates: s.slates,
      conditionState: s.conditionState,
      gear: s.gear,
      skills: s.skills,
      traitId: s.traitId,
      traitSlotLevels: s.traitSlotLevels,
      advancedTraitSelections: s.advancedTraitSelections,
      heroMemories: s.heroMemories,
      pactSpirits: s.pactSpirits,
      notes: s.notes,
      customMods: s.customMods,
    }
  }

  const handleSidebarNav = (target: string) => {
    if (target === 'tree-selector') {
      goToTreeSelector()
    } else {
      setScreen(target as Screen)
    }
  }

  // ── Cascade overlay ───────────────────────────────────────────────────────

  const cascadeOverlay = cascadeModal && (
    <div className="modal-backdrop" onClick={handleCascadeNo}>
      <div className="modal-card" onClick={e => e.stopPropagation()}>
        <div className="modal-accent" />
        <h3 className="modal-title">Shift Subtree Up?</h3>
        <p style={{ padding: '10px 20px 16px', color: '#aaa', fontSize: 13, lineHeight: 1.6 }}>
          <strong style={{ color: '#e0e0e0' }}>{cascadeModal.shiftingTree}</strong> is also a subtree
          of <strong style={{ color: '#e0e0e0' }}>{cascadeModal.primaryName}</strong>.
          Move it up to Slot 2?
        </p>
        <div className="modal-actions">
          <button className="btn btn-primary" onClick={handleCascadeYes}>Yes, shift up</button>
          <button className="btn btn-danger" onClick={handleCascadeNo}>No, leave it</button>
        </div>
      </div>
    </div>
  )

  // ── Sidebar-less screens ──────────────────────────────────────────────────

  if (screen === 'dev-tools') {
    return <DevToolsScreen onBack={() => setScreen('build-select')} deprecatedTools={deprecatedTools} onToggleDeprecatedTools={() => setDeprecatedTools(d => !d)} onSeasonChange={() => {
          useReferenceStore.getState().clearReferenceData()
          useReferenceStore.getState().loadReferenceData()
        }} />
  }

  if (screen === 'build-select') {
    return (
      <>
        {updateInfo && <UpdateBanner info={updateInfo} downloading={updateDownloading} progress={updateProgress} downloaded={updateDownloaded} onDownload={handleUpdateDownload} onInstall={() => window.api?.installUpdate?.()} />}
        <BuildSelectScreen
          onNewBuild={startNewBuild}
          onOpenBuild={openBuild}
          devMode={devMode}
          onDevTools={() => setScreen('dev-tools')}
        />
      </>
    )
  }


  if (screen === 'preview-selector') {
    return (
      <TreeSelectorScreen
        treeColors={treeColors}
        onSelectTree={handlePreviewTree}
        onRemoveTree={() => {}}
        onSlotClick={() => {}}
        onSlotReorder={() => {}}
        onBack={() => setScreen(previewSource)}
        onGoToSelector={() => {}}
        onShiftUp={() => {}}
        onPreview={() => {}}
        previewMode
      />
    )
  }

  if (screen === 'preview-viewer' && previewTree) {
    return (
      <TreeViewerScreen
        treeName={previewTree}
        treeColor={treeColors[previewTree] ?? '#e94560'}
        treeColors={treeColors}
        onBack={() => setScreen('preview-selector')}
        onSlotClick={() => {}}
        onReselect={() => setScreen('preview-selector')}
        previewMode
      />
    )
  }


  // ── Screens with sidebar ──────────────────────────────────────────────────

  let screenContent: React.ReactNode = <div style={{ color: '#888', padding: 20 }}>Unknown screen state</div>

  if (screen === 'build-overview') {
    screenContent = <BuildOverviewScreen />
  } else if (screen === 'tree-selector') {
    screenContent = (
      <>
        <TreeSelectorScreen
          treeColors={treeColors}
          onSelectTree={handleSelectTree}
          onRemoveTree={handleRemoveTree}
          onSlotClick={handleSlotClick}
          onSlotReorder={handleSlotReorder}
          onGoToTree={handleSlotClick}
          onBack={() => setScreen('build-overview')}
          onGoToSelector={() => {}}
          onShiftUp={handleShiftUp}
          onPreview={goToPreview}
        />
        {cascadeOverlay}
      </>
    )
  } else if (screen === 'tree-viewer') {
    const slot = slots[activeSlot]
    if (!slot) {
      setScreen('tree-selector')
    } else {
      screenContent = (
        <>
          <TreeViewerScreen
            treeName={slot.treeName}
            treeColor={treeColors[slot.treeName] ?? '#e94560'}
            treeColors={treeColors}
            onBack={() => setScreen('tree-selector')}
            onSlotClick={handleSlotClick}
            onReselect={handleReselect}
            onSlotReorder={handleSlotReorder}
            onPreview={goToPreview}
            devMode={devMode}
            deprecatedTools={deprecatedTools}
          />
          {cascadeOverlay}
        </>
      )
    }
  } else if (screen === 'import-export') {
    screenContent = (
      <ImportExportOverlay
        isDirty={isDirty}
        buildId={buildId}
        buildName={buildName}
        getBuildPayload={getBuildPayload}
        onImport={openBuild}
        onSaveFirst={saveBuild}
        onClose={() => setScreen('build-overview')}
        asScreen
      />
    )
  } else if (screen === 'slate-board') {
    screenContent = (
      <SlateScreen
        treeColors={treeColors}
        onBack={() => setScreen('build-overview')}
      />
    )
  } else if (screen === 'stats') {
    screenContent = <StatsScreen />
  } else if (screen === 'calcs') {
    screenContent = <CalcsScreen />
  } else if (screen === 'gear') {
    screenContent = <GearScreen onBack={() => setScreen('build-overview')} />
  } else if (screen === 'skills') {
    screenContent = <SkillsScreen onBack={() => setScreen('build-overview')} />
  } else if (screen === 'hero-traits') {
    screenContent = <HeroTraitScreen onBack={() => setScreen('build-overview')} />
  } else if (screen === 'pact-spirits') {
    screenContent = <PactSpiritScreen onBack={() => setScreen('build-overview')} />
  } else if (screen === 'notes') {
    screenContent = <NotesScreen />
  }

  return (
    <>
      {updateInfo && <UpdateBanner info={updateInfo} downloading={updateDownloading} progress={updateProgress} downloaded={updateDownloaded} onDownload={handleUpdateDownload} onInstall={() => window.api?.installUpdate?.()} />}
      <div className="app-layout">
        <BuildSidebar
          screen={screen}
          buildName={buildName}
          isDirty={isDirty}
          onNav={handleSidebarNav}
          onSave={handleSidebarSave}
          onSaveAs={handleSidebarSaveAs}
          onGoBack={goToBuildSelect}
        />
        <div className="app-content">
          {screenContent}
        </div>
      </div>
      {cascadeOverlay}
      {unsavedPromptOpen && (
        <div className="modal-backdrop">
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">Unsaved Changes</h3>
            <p style={{ padding: '0 20px 12px', color: '#aaa', fontSize: 13, lineHeight: 1.6 }}>
              {buildId
                ? `Save "${buildName || 'this build'}" before leaving?`
                : 'This build has unsaved changes. Save it before leaving?'}
            </p>
            {!buildId && (
              <input
                className="modal-input"
                type="text"
                placeholder="Build name…"
                value={unsavedSaveName}
                onChange={e => setUnsavedSaveName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleUnsavedSave()}
                autoFocus
              />
            )}
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleUnsavedSave} disabled={unsavedSaving}>
                {unsavedSaving ? 'Saving…' : 'Save'}
              </button>
              <button className="btn btn-danger" onClick={handleUnsavedDiscard}>Discard</button>
              <button className="btn btn-secondary" onClick={() => setUnsavedPromptOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
      {saveModalOpen && (
        <div className="modal-backdrop" onClick={() => setSaveModalOpen(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-accent" />
            <h3 className="modal-title">{saveModalMode === 'save-as' ? 'Save As' : 'Save Build'}</h3>
            <input
              className="modal-input"
              type="text"
              placeholder="Build name…"
              value={saveModalName}
              onChange={e => setSaveModalName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSaveModalConfirm()}
              autoFocus
            />
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={handleSaveModalConfirm} disabled={saveModalSaving}>
                {saveModalSaving ? 'Saving…' : 'Save'}
              </button>
              <button className="btn btn-secondary" onClick={() => setSaveModalOpen(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

    </>
  )
}

export default App
