import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { initApi, api, Build, TreeSlot, SavedSlate, ConditionValues, ConditionMaximums, EquippedGearItem, EquippedSkill } from './api/client'
import UpdateBanner, { UpdateInfo } from './components/UpdateBanner'
import HeroTraitScreen from './screens/HeroTraitScreen'
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

type Screen = 'build-select' | 'build-overview' | 'tree-selector' | 'tree-viewer' | 'preview-selector' | 'preview-viewer' | 'dev-tools' | 'slate-board' | 'stats' | 'gear' | 'skills' | 'hero-traits'

const DEFAULT_CONDITION_VALUES: ConditionValues = {
  tenacity_stacks: 0,
  agility_stacks: 0,
  focus_stacks: 0,
  channeled_stacks: 0,
  channeled_base_max: 0,
}

// Derive boolean condition keys from numeric condition values + computed maximums
function deriveNumericConditions(values: ConditionValues, maximums: ConditionMaximums | null): string[] {
  const derived: string[] = []
  if (values.tenacity_stacks > 0) derived.push('tenacity_active')
  if (values.agility_stacks > 0) derived.push('agility_active')
  if (values.focus_stacks > 0) derived.push('focus_active')
  const channeledMax = values.channeled_base_max + (maximums?.channeled_max_bonus ?? 0)
  if (channeledMax > 0 && values.channeled_stacks < channeledMax) derived.push('channeled_not_capped')
  return derived
}

// Keys managed by conditionValues sliders — excluded from the manual boolean toggle list
const NUMERIC_CONDITION_KEYS = new Set(['tenacity_active', 'agility_active', 'focus_active', 'channeled_not_capped'])

interface Session {
  buildId: string | null
  buildName: string
  slots: (TreeSlot | null)[]
  activeSlot: number
  slates: SavedSlate[]
  conditions: string[]
  conditionValues: ConditionValues
  gear: EquippedGearItem[]
  skills: EquippedSkill[]
  characterLevel: number
  hasPrism: boolean
  traitId: string | null
  traitSlotLevels: number[]  // [base, lv45, lv60, lv75], each 1–5
  advancedTraitSelections: string[]
}

interface CascadeModal {
  removingSlot: number
  shiftingTree: string
  shiftingFromSlot: number
  primaryName: string
}

const emptySession = (): Session => ({
  buildId: null,
  buildName: '',
  slots: [null, null, null, null],
  activeSlot: 0,
  slates: [],
  conditions: [],
  conditionValues: DEFAULT_CONDITION_VALUES,
  gear: [],
  skills: [],
  characterLevel: 100,
  hasPrism: false,
  traitId: null,
  traitSlotLevels: [1, 1, 1, 1],
  advancedTraitSelections: [],
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
  const [cascadeModal, setCascadeModal] = useState<CascadeModal | null>(null)
  const [previewTree, setPreviewTree] = useState<string | null>(null)
  const [previewSource, setPreviewSource] = useState<Screen>('build-overview')
  const [devMode, setDevMode] = useState(false)
  const [deprecatedTools, setDeprecatedTools] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const [unsavedPromptOpen, setUnsavedPromptOpen] = useState(false)
  const [unsavedSaveName, setUnsavedSaveName] = useState('')
  const [unsavedSaving, setUnsavedSaving] = useState(false)
  const [conditionMaximums, setConditionMaximums] = useState<ConditionMaximums | null>(null)
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [updateDownloading, setUpdateDownloading] = useState(false)
  const [updateProgress, setUpdateProgress] = useState(0)
  const [updateDownloaded, setUpdateDownloaded] = useState(false)
  const sessionRef = useRef(session)

  useEffect(() => { sessionRef.current = session }, [session])

  // Sync dirty state to main process for the native close dialog
  useEffect(() => { window.api?.notifyDirty?.(isDirty) }, [isDirty])

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

  // Handle save request from main process (native close dialog "Save" button)
  useEffect(() => {
    window.api?.onRequestSave?.(() => {
      const sess = sessionRef.current
      if (sess.buildId) {
        const build = { id: sess.buildId, name: sess.buildName, slots: sess.slots, slates: sess.slates, conditions: sess.conditions, conditionValues: sess.conditionValues, gear: sess.gear, skills: sess.skills, characterLevel: sess.characterLevel, hasPrism: sess.hasPrism, traitId: sess.traitId, traitSlotLevels: sess.traitSlotLevels, advancedTraitSelections: sess.advancedTraitSelections }
        api.postBuild(build)
          .then(saved => {
            setSession(s => ({ ...s, buildId: saved.id ?? null, buildName: sess.buildName }))
            setIsDirty(false)
          })
          .catch(() => {})
          .finally(() => window.api?.notifySaveDone())
      } else {
        // New unsaved build — can't auto-save without a name, just proceed
        window.api?.notifySaveDone()
      }
    })
  }, [])

  // Initialize devMode from main process — false in packaged builds, localStorage in dev
  useEffect(() => {
    window.api?.getIsDev?.().then(isDev => {
      if (isDev) setDevMode(localStorage.getItem('devMode') === '1')
    })
  }, [])

  // Ctrl+Shift+D toggles dev mode — only active when running in dev (not packaged)
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

  // Subscribe to auto-updater events from main process (registered once, never unmounts)
  useEffect(() => {
    window.api?.onUpdateAvailable?.(setUpdateInfo)
    window.api?.onUpdateProgress?.(setUpdateProgress)
    window.api?.onUpdateDownloaded?.(() => { setUpdateDownloaded(true); setUpdateDownloading(false) })
  }, [])

  const handleUpdateDownload = async () => {
    setUpdateDownloading(true)
    await window.api?.downloadUpdate?.()
  }

  // useMemo/useCallback must be before the early return to satisfy React's hooks rules.
  // effectiveConditions: prevents new array ref every render → stops infinite stats useEffect loop.
  const effectiveConditions = useMemo(() => [
    ...session.conditions.filter(c => !NUMERIC_CONDITION_KEYS.has(c)),
    ...deriveNumericConditions(session.conditionValues, conditionMaximums),
  ], [session.conditions, session.conditionValues, conditionMaximums])

  // Stable setter: bails out if maximums values are unchanged, preventing unnecessary re-renders.
  const handleConditionMaximumsChange = useCallback((maximums: ConditionMaximums) => {
    setConditionMaximums(prev => {
      if (prev &&
        prev.tenacity_max === maximums.tenacity_max &&
        prev.agility_max === maximums.agility_max &&
        prev.focus_max === maximums.focus_max &&
        prev.channeled_max_bonus === maximums.channeled_max_bonus
      ) return prev
      return maximums
    })
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

  // ── Navigation ────────────────────────────────────────────────────────────

  const goToBuildSelect = () => {
    if (isDirty) {
      setUnsavedSaveName(session.buildName)
      setUnsavedPromptOpen(true)
    } else {
      setScreen('build-select')
    }
  }

  const handleUnsavedSave = async () => {
    const name = session.buildId ? session.buildName : (unsavedSaveName.trim() || 'Untitled')
    setUnsavedSaving(true)
    try {
      await saveBuild(name)        // already calls setIsDirty(false)
      setUnsavedPromptOpen(false)
      setScreen('build-select')
    } catch { /* save failed — leave prompt open so user can retry */ }
    finally { setUnsavedSaving(false) }
  }

  const handleUnsavedDiscard = () => {
    setIsDirty(false)
    setUnsavedPromptOpen(false)
    setScreen('build-select')
  }

  const startNewBuild = () => {
    setSession(emptySession())
    setIsDirty(false)
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
      slates: build.slates ?? [],
      conditions: build.conditions ?? [],
      conditionValues: build.conditionValues ?? DEFAULT_CONDITION_VALUES,
      gear: build.gear ?? [],
      skills: (build.skills ?? []).map(s => ({ ...s, supports: s.supports ?? [] })),
      characterLevel: build.characterLevel ?? 100,
      hasPrism: build.hasPrism ?? false,
      traitId: build.traitId ?? null,
      traitSlotLevels: build.traitSlotLevels ?? [build.traitLevel ?? 1, 1, 1, 1],
      advancedTraitSelections: build.advancedTraitSelections ?? [],
    })
    setIsDirty(false)
    setScreen('build-overview')
  }

  const goToTreeSelector = () => {
    setSession(s => ({ ...s, activeSlot: firstEmptySlot(s.slots) }))
    setScreen('tree-selector')
  }

  const goToSlates = () => setScreen('slate-board')
  const goToStats = () => setScreen('stats')
  const goToGear = () => setScreen('gear')
  const goToSkills = () => setScreen('skills')
  const goToHeroTraits = () => setScreen('hero-traits')

  const goToPreview = () => {
    setPreviewSource(screen)
    setScreen('preview-selector')
  }

  const handlePreviewTree = (treeName: string) => {
    setPreviewTree(treeName)
    setScreen('preview-viewer')
  }

  // ── Tree selection ────────────────────────────────────────────────────────

  const markDirty = () => setIsDirty(true)

  const handleSlotReorder = (fromSlot: number, toSlot: number) => {
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      const moving = slots[fromSlot]
      if (!moving) return s

      const target = slots[toSlot]
      const result = [...slots] as (TreeSlot | null)[]
      result[fromSlot] = target ?? null
      result[toSlot] = moving

      if (!isValidBuildState(result)) return s

      let { activeSlot } = s
      if (activeSlot === fromSlot) activeSlot = toSlot
      else if (activeSlot === toSlot && target) activeSlot = fromSlot

      return { ...s, slots: result, activeSlot }
    })
    markDirty()
  }

  const handleSelectTree = (treeName: string) => {
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      const targetSlot = autoAssignSlot(treeName, slots)
      if (targetSlot === -1) return s
      slots[targetSlot] = { treeName, nodeStates: {} }
      return { ...s, slots, activeSlot: targetSlot }
    })
    markDirty()
    setScreen('tree-viewer')
  }

  const handleRemoveTree = (slotIndex: number) => {
    // Removing slot 1 (index 1): check if a qualifying subtree exists in slots 2/3
    if (slotIndex === 1) {
      const primary = session.slots[0]?.treeName
      if (primary) {
        const subtrees = getSubtrees(primary)
        for (const i of [2, 3]) {
          const candidate = session.slots[i]?.treeName
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
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      slots[slotIndex] = null
      if (slotIndex === 0) slots[1] = null  // removing primary cascades slot 2
      return { ...s, slots, activeSlot: firstEmptySlot(slots) }
    })
    markDirty()
  }

  const handleCascadeYes = () => {
    if (!cascadeModal) return
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      slots[cascadeModal.removingSlot] = slots[cascadeModal.shiftingFromSlot]
      slots[cascadeModal.shiftingFromSlot] = null
      return { ...s, slots, activeSlot: firstEmptySlot(slots) }
    })
    setCascadeModal(null)
  }

  const handleCascadeNo = () => {
    if (!cascadeModal) return
    doRemoveTree(cascadeModal.removingSlot)
    setCascadeModal(null)
  }

  const handleShiftUp = (fromSlot: number) => {
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      slots[1] = slots[fromSlot]
      slots[fromSlot] = null
      return { ...s, slots }
    })
    markDirty()
  }

  // Sidebar slot click: empty → tree-selector; filled → tree-viewer
  const handleSlotClick = (slotIndex: number) => {
    setSession(s => ({ ...s, activeSlot: slotIndex }))
    if (session.slots[slotIndex]) {
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
    markDirty()
  }

  const updateCoreTalentSelections = (coreTalentSelections: Record<number, string>) => {
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      const current = slots[s.activeSlot]
      if (current) slots[s.activeSlot] = { ...current, coreTalentSelections }
      return { ...s, slots }
    })
    markDirty()
  }

  const handleReselect = () => {
    setSession(s => {
      const slots = [...s.slots] as (TreeSlot | null)[]
      slots[s.activeSlot] = null
      if (s.activeSlot === 0) slots[1] = null  // cascade
      return { ...s, slots }
    })
    setScreen('tree-selector')
  }

  const handleConditionsChange = (conditions: string[]) => {
    setSession(s => ({ ...s, conditions }))
    markDirty()
  }

  const handleConditionValuesChange = (values: ConditionValues) => {
    setSession(s => ({ ...s, conditionValues: values }))
    markDirty()
  }

  const saveBuild = async (name: string) => {
    const build = { id: session.buildId ?? undefined, name, slots: session.slots, slates: session.slates, conditions: session.conditions, conditionValues: session.conditionValues, gear: session.gear, skills: session.skills, characterLevel: session.characterLevel, hasPrism: session.hasPrism, traitId: session.traitId, traitSlotLevels: session.traitSlotLevels, advancedTraitSelections: session.advancedTraitSelections }
    const saved = await api.postBuild(build)
    setSession(s => ({ ...s, buildId: saved.id ?? null, buildName: name }))
    setIsDirty(false)
  }

  const saveAsBuild = async (name: string) => {
    const build = { id: undefined, name, slots: session.slots, slates: session.slates, conditions: session.conditions, conditionValues: session.conditionValues, gear: session.gear, skills: session.skills, characterLevel: session.characterLevel, hasPrism: session.hasPrism, traitId: session.traitId, traitSlotLevels: session.traitSlotLevels, advancedTraitSelections: session.advancedTraitSelections }
    const saved = await api.postBuild(build)
    setSession(s => ({ ...s, buildId: saved.id ?? null, buildName: name }))
    setIsDirty(false)
  }

  const handleGearChange = (gear: EquippedGearItem[]) => {
    setSession(s => ({ ...s, gear }))
    markDirty()
  }

  const handleSkillsChange = (skills: EquippedSkill[]) => {
    setSession(s => ({ ...s, skills }))
    markDirty()
  }

  const handleTraitChange = (traitId: string, slotLevels: number[], advanced: string[]) => {
    setSession(s => ({ ...s, traitId, traitSlotLevels: slotLevels, advancedTraitSelections: advanced }))
    markDirty()
  }

  // ── Render ────────────────────────────────────────────────────────────────

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

  if (screen === 'dev-tools') {
    return <DevToolsScreen onBack={() => setScreen('build-select')} deprecatedTools={deprecatedTools} onToggleDeprecatedTools={() => setDeprecatedTools(d => !d)} onSeasonChange={() => setSession(s => ({ ...s }))} />
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

  if (screen === 'build-overview') {
    return (
      <>
        {updateInfo && <UpdateBanner info={updateInfo} downloading={updateDownloading} progress={updateProgress} downloaded={updateDownloaded} onDownload={handleUpdateDownload} onInstall={() => window.api?.installUpdate?.()} />}
        <BuildOverviewScreen
          buildName={session.buildName}
          buildId={session.buildId}
          slots={session.slots}
          slates={session.slates}
          conditions={session.conditions}
          conditionValues={session.conditionValues}
          conditionMaximums={conditionMaximums}
          effectiveConditions={effectiveConditions}
          onConditionsChange={handleConditionsChange}
          onConditionValuesChange={handleConditionValuesChange}
          onConditionMaximumsChange={handleConditionMaximumsChange}
          gear={session.gear}
          characterLevel={session.characterLevel}
          hasPrism={session.hasPrism}
          onBack={goToBuildSelect}
          onTalentTree={goToTreeSelector}
          onSlates={goToSlates}
          onGear={goToGear}
          onSkills={goToSkills}
          onGoToHeroTraits={goToHeroTraits}
          traitId={session.traitId}
          onSave={saveBuild}
          onSaveAs={saveAsBuild}
          getBuildPayload={() => ({
            name: session.buildName,
            characterLevel: session.characterLevel,
            hasPrism: session.hasPrism,
            slots: session.slots,
            slates: session.slates,
            conditions: session.conditions,
            conditionValues: session.conditionValues,
            gear: session.gear,
            skills: session.skills,
            traitId: session.traitId,
            traitSlotLevels: session.traitSlotLevels,
            advancedTraitSelections: session.advancedTraitSelections,
          })}
          devMode={devMode}
        />
        {cascadeOverlay}
        {unsavedPromptOpen && (
          <div className="modal-backdrop">
            <div className="modal-card" onClick={e => e.stopPropagation()}>
              <div className="modal-accent" />
              <h3 className="modal-title">Unsaved Changes</h3>
              <p style={{ padding: '0 20px 12px', color: '#aaa', fontSize: 13, lineHeight: 1.6 }}>
                {session.buildId
                  ? `Save "${session.buildName || 'this build'}" before leaving?`
                  : 'This build has unsaved changes. Save it before leaving?'}
              </p>
              {!session.buildId && (
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
      </>
    )
  }

  if (screen === 'slate-board') {
    return (
      <>
        <SlateScreen
          treeColors={treeColors}
          initialSlates={session.slates}
          onBack={(slates) => {
            setSession(s => ({ ...s, slates }))
            markDirty()
            setScreen('build-overview')
          }}
        />
      </>
    )
  }

  if (screen === 'stats') {
    return (
      <>
        <StatsScreen
          slots={session.slots}
          slates={session.slates}
          onBack={() => setScreen('build-overview')}
        />
      </>
    )
  }

  if (screen === 'gear') {
    return (
      <GearScreen
        equippedItems={session.gear}
        onGearChange={handleGearChange}
        onBack={() => setScreen('build-overview')}
      />
    )
  }

  if (screen === 'skills') {
    return (
      <SkillsScreen
        equippedSkills={session.skills}
        onSkillsChange={handleSkillsChange}
        gear={session.gear}
        characterLevel={session.characterLevel}
        hasPrism={session.hasPrism}
        onCharacterLevelChange={v => setSession(s => ({ ...s, characterLevel: v }))}
        onHasPrismChange={v => setSession(s => ({ ...s, hasPrism: v }))}
        onBack={() => setScreen('build-overview')}
      />
    )
  }

  if (screen === 'hero-traits') {
    return (
      <HeroTraitScreen
        traitId={session.traitId}
        traitSlotLevels={session.traitSlotLevels}
        advancedTraitSelections={session.advancedTraitSelections}
        characterLevel={session.characterLevel}
        onTraitChange={handleTraitChange}
        onBack={() => setScreen('build-overview')}
      />
    )
  }

  if (screen === 'tree-selector') {
    return (
      <>
        <TreeSelectorScreen
          slots={session.slots}
          activeSlot={session.activeSlot}
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
  }

  if (screen === 'preview-selector') {
    return (
      <TreeSelectorScreen
        slots={[null, null, null, null]}
        activeSlot={0}
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
        initialNodeStates={{}}
        slots={[null, null, null, null]}
        activeSlot={0}
        onBack={() => setScreen('preview-selector')}
        onSlotClick={() => {}}
        onNodeStatesChange={() => {}}
        onReselect={() => setScreen('preview-selector')}
        previewMode
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
      <>
        <TreeViewerScreen
          treeName={slot.treeName}
          treeColor={treeColors[slot.treeName] ?? '#e94560'}
          treeColors={treeColors}
          initialNodeStates={slot.nodeStates}
          initialCoreTalentSelections={slot.coreTalentSelections}
          slots={session.slots}
          activeSlot={session.activeSlot}
          onBack={() => setScreen('tree-selector')}
          onSlotClick={handleSlotClick}
          onNodeStatesChange={updateNodeStates}
          onCoreTalentSelectionsChange={updateCoreTalentSelections}
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

  return <div style={{ color: '#888', padding: 20 }}>Unknown screen state</div>
}

export default App
