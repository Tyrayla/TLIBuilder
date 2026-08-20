import React, { useCallback, useEffect, useRef, useState } from 'react'
import { initApi, api, Build, TreeSlot, EquippedGearItem, EquippedSupportSkill, CreatedHeroMemory, MemoryRarity, MemorySlotSelection, SelectedPactSpirit, ResolvedAffixFields, Loadout, genMemoryId } from './api/client'
import { MAX_LEVEL_BY_RARITY } from './components/HeroTraitShared'
import { migrateOldConditions, buildDefaultConditionState } from './utils/conditions'
import { snapshotAllAreas } from './utils/loadoutAreas'
import { DEFAULT_TARGET_CONFIG, sanitizeTargetConfig } from './utils/targetPresets'
import { getBuildPayload } from './utils/buildPayload'
import { useBuildStore } from './store/buildStore'
import type { LoadedBuild } from './store/buildStore'
import { useBuildCalculation } from './store/useBuildCalculation'
import { useReferenceStore } from './store/referenceStore'
import { migrateLegendaryItem } from './utils/gearItem'
import { useMappingStore } from './store/mappingStore'
import { useUiPrefs } from './store/uiPrefsStore'
import UpdateBanner, { UpdateInfo } from './components/UpdateBanner'
import ErrorBoundary from './components/ErrorBoundary'
import PerfProfiler, { PERF_ENABLED } from './components/PerfProfiler'
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
import PlayerStatsScreen from './screens/PlayerStatsScreen'
import GearScreen from './screens/GearScreen'
import SkillsScreen from './screens/SkillsScreen'
import VerificationDatabaseScreen from './screens/VerificationDatabaseScreen'

type Screen = 'build-select' | 'build-overview' | 'tree-selector' | 'tree-viewer' | 'preview-selector' | 'preview-viewer' | 'dev-tools' | 'slate-board' | 'stats' | 'gear' | 'skills' | 'hero-traits' | 'pact-spirits' | 'notes' | 'import-export' | 'verification'

// Where a build lands when created or opened — picking the character is the natural first step.
const BUILD_LANDING_SCREEN: Screen = 'hero-traits'

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

const genLoadoutId = (): string =>
  (globalThis.crypto?.randomUUID?.() ?? `lo${Date.now()}${Math.floor(Math.random() * 1e6)}`)

// Resolve a build's loadouts on load: restore saved loadouts (default-migrating pre-feature builds, which have
// none, into a single "New Loadout" snapshot of the loaded areas). `payload` is the LoadedBuild-shaped object.
function ensureLoadouts(
  payload: Record<string, unknown>,
  srcLoadouts?: Loadout[],
  srcActiveId?: string,
): { loadouts: Loadout[]; activeLoadoutId: string } {
  if (Array.isArray(srcLoadouts) && srcLoadouts.length > 0) {
    const loadouts = srcLoadouts
      .filter(l => l && typeof l.id === 'string')
      .map(l => ({ id: l.id, name: l.name ?? 'Loadout', data: l.data ?? {}, inherit: l.inherit ?? {} }))
    if (loadouts.length > 0) {
      // Migrate pre-`traitTreeAllocations`-area builds: the field used to be build-global, so an
      // older loadout's `trait` snapshot won't have it. Seed it from the top-level value for the
      // loadout(s) that share the build's trait; others default to [] (their value was never stored).
      const topAllocs = Array.isArray((payload as { traitTreeAllocations?: unknown }).traitTreeAllocations)
        ? (payload as { traitTreeAllocations: string[] }).traitTreeAllocations
        : []
      const topTraitId = (payload as { traitId?: unknown }).traitId
      // slateInventory used to be build-GLOBAL; it's now a per-loadout field in the `slates` area. Seed each
      // loadout that predates the change from the former global value so no saved palette is lost. memoryInventory
      // is brand new — seed from the (normally empty) top-level value (the memory-inventory UI that populates it
      // lands in a later step; until then it stays as imported/empty).
      const topSlateInv = Array.isArray((payload as { slateInventory?: unknown }).slateInventory)
        ? (payload as { slateInventory: unknown[] }).slateInventory : []
      const topMemInv = Array.isArray((payload as { memoryInventory?: unknown }).memoryInventory)
        ? (payload as { memoryInventory: unknown[] }).memoryInventory : []
      for (const l of loadouts) {
        const trait = l.data.trait as Record<string, unknown> | undefined
        if (trait && trait.traitTreeAllocations === undefined) {
          l.data = { ...l.data, trait: { ...trait, traitTreeAllocations: trait.traitId === topTraitId ? topAllocs : [] } }
        }
        const slates = l.data.slates as Record<string, unknown> | undefined
        if (slates && slates.slateInventory === undefined) {
          l.data = { ...l.data, slates: { ...slates, slateInventory: topSlateInv } }
        }
        const memories = l.data.memories as Record<string, unknown> | undefined
        if (memories && memories.memoryInventory === undefined) {
          l.data = { ...l.data, memories: { ...memories, memoryInventory: topMemInv } }
        }
      }
      const activeLoadoutId = loadouts.find(l => l.id === srcActiveId)?.id ?? loadouts[0].id
      return { loadouts, activeLoadoutId }
    }
  }
  const id = genLoadoutId()
  return { loadouts: [{ id, name: 'Loadout 1', data: snapshotAllAreas(payload), inherit: {} }], activeLoadoutId: id }
}

// Editing screens kept mounted across navigation so in-progress edit state survives. Calcs (stats)
// is excluded — it's the one heavy screen and its view state already persists via uiPrefsStore; the
// tree/preview flow stays swap-rendered (its content is slot-dependent).
const KEEPALIVE_SCREENS: Screen[] = [
  'build-overview', 'gear', 'skills', 'hero-traits', 'pact-spirits', 'slate-board', 'notes', 'import-export',
]

function App() {
  const [appReady, setAppReady] = useState(false)
  const [appError, setAppError] = useState('')
  const [screen, setScreen] = useState<Screen>('build-select')
  // Which keep-alive screens have been visited (and are thus mounted-and-hidden rather than unmounted).
  const [visitedKeepAlive, setVisitedKeepAlive] = useState<Set<Screen>>(() => new Set())
  // NOTE: these effects MUST stay above the `if (!appReady)` early return below — a hook placed after it
  // is conditional and crashes with React #310 ("more hooks than previous render") once appReady flips.
  // Track visited keep-alive screens so each mounts once on first visit and then persists (hidden).
  useEffect(() => {
    if (KEEPALIVE_SCREENS.includes(screen)) {
      setVisitedKeepAlive(prev => (prev.has(screen) ? prev : new Set(prev).add(screen)))
    }
  }, [screen])
  // Perf-spec drivers (gated on PERF_ENABLED) — let the E2E perf harness drive navigation + recompute
  // edits deterministically, without fragile UI selectors. Absent entirely in a normal (unflagged) run.
  useEffect(() => {
    if (!PERF_ENABLED) return
    window.__perfNav = (s: string) => setScreen(s as Screen)
    window.__perfEdit = () => {
      const st = useBuildStore.getState()
      st.setCharacterLevel(st.characterLevel >= 100 ? 99 : 100)
    }
    window.__perfBuildState = () => {
      const st = useBuildStore.getState()
      return { buildVersion: st.buildVersion, computedVersion: st.computedVersion, statsLoading: st.statsLoading }
    }
    return () => { delete window.__perfNav; delete window.__perfEdit; delete window.__perfBuildState }
  }, [])
  const [treeColors, setTreeColors] = useState<Record<string, string>>({})
  const [treeIcons, setTreeIcons] = useState<Record<string, string | null>>({})
  const [cascadeModal, setCascadeModal] = useState<CascadeModal | null>(null)
  const [previewTree, setPreviewTree] = useState<string | null>(null)
  const [previewSource, setPreviewSource] = useState<Screen>('build-overview')
  const [devMode, setDevMode] = useState(false)
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
  // Build-folders: which folder a NEW build (started via BuildSelectScreen's "+ New Build" from inside a
  // folder) should be assigned into on its first successful save. Cleared once consumed (or on opening an
  // existing build, which cancels any pending new-build folder intent).
  const pendingNewBuildFolderRef = useRef<string | null>(null)
  const refConditions = useReferenceStore(s => s.conditions)

  // Store reads — replaces session useState
  const buildId = useBuildStore(s => s.buildId)
  const buildName = useBuildStore(s => s.buildName)
  const slots = useBuildStore(s => s.slots)
  const activeSlot = useBuildStore(s => s.activeSlot)
  const buildVersion = useBuildStore(s => s.buildVersion)

  // Only report "dirty" to the main process while a build is actually open. On the build-list menu there's
  // nothing to save, so the native close/quit guard must never prompt there (it was firing on update-install).
  useEffect(() => { window.api?.notifyDirty?.(isDirty && screen !== 'build-select') }, [isDirty, screen])

  // Global UI zoom (Settings → Display). Applied as CSS zoom on the document root so the whole interface scales.
  const uiScale = useUiPrefs(s => s.uiScale)
  useEffect(() => { document.documentElement.style.zoom = String(uiScale || 1) }, [uiScale])

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
          const icons: Record<string, string | null> = {}
          trees.forEach(t => { colors[t.name] = t.color; icons[t.name] = t.icon_url ?? null })
          setTreeColors(colors)
          setTreeIcons(icons)
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
      useBuildStore.getState().flushActiveLoadout()
      const s = useBuildStore.getState()
      if (s.buildId) {
        const build = { id: s.buildId, name: s.buildName, slots: s.slots, slates: s.slates, slateInventory: s.slateInventory, prisms: s.prisms, prismInventory: s.prismInventory, conditionState: s.conditionState, gear: s.gear, skills: s.skills, characterLevel: s.characterLevel, traitId: s.traitId, traitSlotLevels: s.traitSlotLevels, advancedTraitSelections: s.advancedTraitSelections, traitTreeAllocations: s.traitTreeAllocations, traitSkillSupports: s.traitSkillSupports, licoricePreparedSkill: s.licoricePreparedSkill, elixirIngredients: s.elixirIngredients, heroMemories: s.heroMemories, pactSpirits: s.pactSpirits, fates: s.fates, undetermined: s.undetermined, notes: s.notes, customMods: s.customMods, targetConfig: s.targetConfig, loadouts: s.loadouts, activeLoadoutId: s.activeLoadoutId }
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

  // Re-baseline the dirty tracker after a brand-new build's DEFAULT trait auto-selects on the landing screen.
  // That auto-select bumps buildVersion (it IS a DPS change → needs recompute) but is NOT a user edit, so we
  // move the baseline forward and keep the fresh build clean. Stable identity so it can sit in the screen's deps.
  const rebaselineForDefault = useCallback(() => {
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
  }, [])


  if (!appReady) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100%', background: '#1a1a2e',
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

  const startNewBuild = (folderId?: string) => {
    pendingNewBuildFolderRef.current = folderId ?? null
    const payload = {
      buildId: null, buildName: '', activeSlot: 0,
      slots: [null, null, null, null] as (TreeSlot | null)[], slates: [], slateInventory: [], prisms: [], prismInventory: [], conditionState: {},
      gear: [], skills: [], characterLevel: 100,
      traitId: null, traitSlotLevels: [1, 1, 1, 1], advancedTraitSelections: [], traitTreeAllocations: [], traitSkillSupports: [], licoricePreparedSkill: null, elixirIngredients: {},
      heroMemories: [null, null, null] as [null, null, null], baseMemory: null, memoryInventory: [], pactSpirits: [null, null, null] as [null, null, null], fates: {}, undetermined: [null, null, null],
      notes: '', customMods: [], targetConfig: DEFAULT_TARGET_CONFIG,
    }
    useBuildStore.getState().loadBuild({ ...payload, ...ensureLoadouts(payload) })
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
    setScreen(BUILD_LANDING_SCREEN)
  }

  // ── Build import sanitizers ───────────────────────────────────────────────
  const sanitizeMemorySlot = (s: unknown): MemorySlotSelection | null => {
    if (!s || typeof s !== 'object') return null
    const o = s as Record<string, unknown>
    if (typeof o.modifier !== 'string' || typeof o.tier !== 'number') return null
    return {
      modifier: o.modifier, tier: o.tier, rolledValue: typeof o.rolledValue === 'number' ? o.rolledValue : null,
      // Preserve the independent per-range rolls of a multi-range combo affix (each entry a number or null →
      // that range's max) so they survive save/load/import; dropping it would collapse both halves to one value.
      ...(Array.isArray(o.rolledValues) ? { rolledValues: o.rolledValues.map(v => typeof v === 'number' ? v : null) } : {}),
      // Preserve the enabler description (name-only revival mods) so base-slot parsing survives save/load/import.
      ...(typeof o.description === 'string' && o.description ? { description: o.description } : {}),
    }
  }

  const sanitizeHeroMemory = (m: unknown): CreatedHeroMemory | null => {
    if (!m || typeof m !== 'object') return null
    const o = m as Record<string, unknown>
    if (o.memoryType !== 'origin' && o.memoryType !== 'discipline' && o.memoryType !== 'progress') return null
    const RARITIES: MemoryRarity[] = ['normal', 'magic', 'rare', 'epic', 'ultimate']
    const rarity: MemoryRarity = RARITIES.includes(o.rarity as MemoryRarity) ? o.rarity as MemoryRarity : 'epic'
    const fa = Array.isArray(o.fixedAffixes) ? o.fixedAffixes : []
    const ra = Array.isArray(o.randomAffixes) ? o.randomAffixes : []
    // `revived` was formerly named `revivaled` — migrate the old key on load so pre-rename builds still read.
    const revived = o.revived === true || o.revivaled === true
    return {
      id: typeof o.id === 'string' && o.id ? o.id : genMemoryId(),   // backfill stable id for pre-inventory builds
      memoryType: o.memoryType,
      rarity,
      // Clamp to the rarity's cap so legacy/hand-edited data can't yield "50/40" or an over-cap trait baseline.
      level: typeof o.level === 'number' ? Math.max(1, Math.min(MAX_LEVEL_BY_RARITY[rarity], Math.floor(o.level))) : undefined,
      baseStat: sanitizeMemorySlot(o.baseStat),
      fixedAffixes: [sanitizeMemorySlot(fa[0]), sanitizeMemorySlot(fa[1])],
      randomAffixes: [sanitizeMemorySlot(ra[0]), sanitizeMemorySlot(ra[1])],
      // waxAndWane can only be enabled on a revived memory (see CreatedHeroMemory).
      revived,
      revivalMod: revived ? sanitizeMemorySlot(o.revivalMod) : null,
      waxAndWane: revived && o.waxAndWane === true,
      // Preserve the user's DISPLAY label (sanitized like the rename path) so it survives save/load/import.
      displayName: typeof o.displayName === 'string' && o.displayName.replace(/\p{C}/gu, '').trim()
        ? o.displayName.replace(/\p{C}/gu, '').trim().slice(0, 60) : undefined,
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
    // Opening an existing build cancels any pending new-build folder assignment from an abandoned
    // "+ New Build" flow started (but never saved) from inside a folder.
    pendingNewBuildFolderRef.current = null
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

    // Migrate OLD saved legendary items onto the CURRENT catalog layout: re-derive each affix array from the
    // catalog (matched by item_id) so index-based desecration/corrosion lines up again. Older saves can carry a
    // stale affix layout (from a prior app/catalog version) that made the corrosion toggle swap the wrong slot or
    // silently no-op; fresh items already match, so re-deriving them is a no-op. Rolls (customizations), corrosion
    // state, slot, and enable flag are preserved. Crafted/Vorax items have no catalog entry → left untouched.
    const legendaryCatalog = useReferenceStore.getState().legendaryCatalog
    if (legendaryCatalog) {
      const byId = new Map(legendaryCatalog.map(c => [c.item_id, c]))
      gear = gear.map(item => {
        if (item.is_crafted || item.is_vorax) return item
        const cat = byId.get(item.item_id)
        return cat ? migrateLegendaryItem(item, cat) : item
      })
    }

    // Re-resolve stat fields for ALL gear (crafted, legendary, graft) — saved values can become stale
    // when override entries are added or the resolver improves (e.g. a dual-pool combo like
    // "Max Life and Max Energy Shield" that previously resolved to only one stat). Keyed purely on
    // raw_text, which maps deterministically through the same resolver the catalog serve uses.
    if (gear.length > 0) {
      const texts = [...new Set(
        gear.flatMap(g => g.affixes
          .filter(a => a.affix_kind === 'numeric')
          .map(a => a.raw_text)
        )
      )]
      try {
        const { results } = await api.resolveGearAffixes(texts)
        gear = gear.map(item => {
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

    const loadPayload: Omit<LoadedBuild, 'loadouts' | 'activeLoadoutId'> = {
      buildId: build.id ?? null,
      buildName: build.name,
      slots,
      activeSlot: firstEmptySlot(slots),
      slates: build.slates ?? [],
      slateInventory: build.slateInventory ?? [],
      prisms: build.prisms ?? [],
      prismInventory: build.prismInventory ?? [],
      conditionState: build.conditionState ?? migrateOldConditions(build.conditions, build.conditionValues),
      gear,
      // Mapped verbatim — a saved/imported skill placement is never dropped or auto-repaired here, even one
      // that's illegal for the current trait/talent state (e.g. a Focus skill in an active slot without
      // Knowledgeable). Soft-invalidation is a live derivation of (skills, traitId, slots) — see
      // computeSkillSlotEligibility / computeInvalidSkillSlots in api/client.ts — so it recomputes correctly
      // for whatever traitId/slots this same payload carries below, with no separate pass needed here.
      skills: (build.skills ?? []).map(s => ({
        ...s,
        supports: (s.supports ?? []).map((sup: EquippedSupportSkill) => ({
          ...sup,
          skill_type: sup.skill_type ?? 'support_skill',
          level: sup.level ?? 20,
        })),
      })),
      characterLevel: build.characterLevel ?? 100,
      traitId: build.traitId ?? null,
      traitSlotLevels: build.traitSlotLevels ?? [build.traitLevel ?? 1, 1, 1, 1],
      advancedTraitSelections: build.advancedTraitSelections ?? [],
      traitTreeAllocations: Array.isArray(build.traitTreeAllocations) ? build.traitTreeAllocations : [],
      traitSkillSupports: build.traitSkillSupports ?? [],
      licoricePreparedSkill: build.licoricePreparedSkill ?? null,
      elixirIngredients: build.elixirIngredients ?? {},
      heroMemories: [
        sanitizeHeroMemory((build.heroMemories ?? [])[0]),
        sanitizeHeroMemory((build.heroMemories ?? [])[1]),
        sanitizeHeroMemory((build.heroMemories ?? [])[2]),
      ],
      baseMemory: sanitizeHeroMemory(build.baseMemory),
      memoryInventory: (Array.isArray(build.memoryInventory) ? build.memoryInventory : [])
        .map(sanitizeHeroMemory).filter((m): m is CreatedHeroMemory => m !== null),
      pactSpirits: [
        sanitizePactSpirit((build.pactSpirits ?? [])[0]),
        sanitizePactSpirit((build.pactSpirits ?? [])[1]),
        sanitizePactSpirit((build.pactSpirits ?? [])[2]),
      ],
      fates: (build.fates && typeof build.fates === 'object') ? build.fates : {},
      undetermined: Array.isArray(build.undetermined) ? build.undetermined : [null, null, null],
      notes: typeof build.notes === 'string' ? build.notes : '',
      customMods: Array.isArray(build.customMods) ? (build.customMods as string[]).filter(m => typeof m === 'string') : [],
      targetConfig: sanitizeTargetConfig(build.targetConfig),
    }
    // Restore loadouts (default-migrating pre-feature builds into one "New Loadout"); then reconcile the active
    // loadout's snapshot with the freshly-loaded (crafted-re-resolved) store so saved data stays consistent.
    useBuildStore.getState().loadBuild({ ...loadPayload, ...ensureLoadouts(loadPayload, build.loadouts, build.activeLoadoutId) })
    useBuildStore.getState().flushActiveLoadout()
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
    setScreen(BUILD_LANDING_SCREEN)
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

  // Build folders: the first time a build with no prior id gets saved, drop the returned id into whatever
  // folder was pending (set by startNewBuild when "+ New Build" was clicked from inside a folder). Best-effort
  // only — a folder-assign failure must never surface as a save failure or block the save flow.
  const assignNewBuildToFolder = async (savedBuildId: string) => {
    const folderId = pendingNewBuildFolderRef.current
    if (!folderId) return
    pendingNewBuildFolderRef.current = null
    try {
      const manifest = await api.getBuildFolders()
      manifest.assignments[savedBuildId] = folderId
      await api.putBuildFolders(manifest)
    } catch {
      // Folder assignment is best-effort — leave the build unassigned (it lands at root) on failure.
    }
  }

  const saveBuild = async (name: string) => {
    useBuildStore.getState().flushActiveLoadout()
    const s = useBuildStore.getState()
    const build = { id: s.buildId ?? undefined, name, slots: s.slots, slates: s.slates, slateInventory: s.slateInventory, prisms: s.prisms, prismInventory: s.prismInventory, conditionState: s.conditionState, gear: s.gear, skills: s.skills, characterLevel: s.characterLevel, traitId: s.traitId, traitSlotLevels: s.traitSlotLevels, advancedTraitSelections: s.advancedTraitSelections, traitTreeAllocations: s.traitTreeAllocations, traitSkillSupports: s.traitSkillSupports, licoricePreparedSkill: s.licoricePreparedSkill, elixirIngredients: s.elixirIngredients, heroMemories: s.heroMemories, pactSpirits: s.pactSpirits, fates: s.fates, undetermined: s.undetermined, notes: s.notes, customMods: s.customMods, targetConfig: s.targetConfig, loadouts: s.loadouts, activeLoadoutId: s.activeLoadoutId }
    const saved = await api.postBuild(build)
    useBuildStore.getState().setBuildId(saved.id ?? null)
    useBuildStore.getState().setBuildName(name)
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
    if (!build.id && saved.id) await assignNewBuildToFolder(saved.id)
  }

  const saveAsBuild = async (name: string) => {
    useBuildStore.getState().flushActiveLoadout()
    const s = useBuildStore.getState()
    const build = { id: undefined, name, slots: s.slots, slates: s.slates, slateInventory: s.slateInventory, prisms: s.prisms, prismInventory: s.prismInventory, conditionState: s.conditionState, gear: s.gear, skills: s.skills, characterLevel: s.characterLevel, traitId: s.traitId, traitSlotLevels: s.traitSlotLevels, advancedTraitSelections: s.advancedTraitSelections, traitTreeAllocations: s.traitTreeAllocations, traitSkillSupports: s.traitSkillSupports, licoricePreparedSkill: s.licoricePreparedSkill, elixirIngredients: s.elixirIngredients, heroMemories: s.heroMemories, pactSpirits: s.pactSpirits, fates: s.fates, undetermined: s.undetermined, notes: s.notes, customMods: s.customMods, targetConfig: s.targetConfig, loadouts: s.loadouts, activeLoadoutId: s.activeLoadoutId }
    const saved = await api.postBuild(build)
    useBuildStore.getState().setBuildId(saved.id ?? null)
    useBuildStore.getState().setBuildName(name)
    loadedVersionRef.current = useBuildStore.getState().buildVersion
    setIsDirty(false)
    if (saved.id) await assignNewBuildToFolder(saved.id)
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

  const handleSidebarNav = (target: string) => {
    if (target === 'tree-selector') {
      // Reopen the last-viewed tree instead of always dropping to the selector: the store's activeSlot
      // still points at the tree the user last opened, so jump straight into its viewer when it exists.
      const store = useBuildStore.getState()
      if (store.slots[store.activeSlot]) {
        setScreen('tree-viewer')
      } else {
        goToTreeSelector()
      }
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
    return <DevToolsScreen onBack={() => setScreen('build-select')} onSeasonChange={() => {
          useReferenceStore.getState().clearReferenceData()
          useReferenceStore.getState().loadReferenceData()
          useMappingStore.getState().clear() // modifier->stat mapping is per data version
        }} />
  }

  if (screen === 'build-select') {
    return (
      <div className="app-shell">
        {updateInfo && <UpdateBanner info={updateInfo} downloading={updateDownloading} progress={updateProgress} downloaded={updateDownloaded} onDownload={handleUpdateDownload} onInstall={() => window.api?.installUpdate?.()} />}
        <BuildSelectScreen
          onNewBuild={startNewBuild}
          onOpenBuild={openBuild}
          devMode={devMode}
          onDevTools={() => setScreen('dev-tools')}
          onOpenVerification={() => setScreen('verification')}
        />
      </div>
    )
  }

  if (screen === 'verification') {
    return (
      <div className="app-shell">
        <VerificationDatabaseScreen onBack={() => setScreen('build-select')} />
      </div>
    )
  }


  // ── Screens with sidebar ──────────────────────────────────────────────────

  // Keep-alive screens render from this single map (one instance each, kept mounted). Everything the
  // screen needs is closed over here, so there is no duplicate JSX between this and the swap chain below.
  const renderKeepAliveScreen = (id: Screen): React.ReactNode => {
    switch (id) {
      case 'build-overview': return <BuildOverviewScreen />
      case 'gear': return <GearScreen onBack={() => setScreen('build-overview')} />
      case 'skills': return <SkillsScreen onBack={() => setScreen('build-overview')} />
      case 'hero-traits': return <HeroTraitScreen onBack={() => setScreen('build-overview')} onDefaultTraitApplied={rebaselineForDefault} />
      case 'pact-spirits': return <PactSpiritScreen onBack={() => setScreen('build-overview')} />
      case 'slate-board': return <SlateScreen treeColors={treeColors} onBack={() => setScreen('build-overview')} />
      case 'notes': return <NotesScreen />
      case 'import-export': return (
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
      default: return null
    }
  }

  // Swap-rendered screens only (Calcs + the slot-dependent tree/preview flow); keep-alive screens are
  // handled by renderKeepAliveScreen above.
  let screenContent: React.ReactNode = <div style={{ color: '#888', padding: 20 }}>Unknown screen state</div>

  if (screen === 'tree-selector') {
    screenContent = (
      <>
        <TreeSelectorScreen
          treeColors={treeColors}
          treeIcons={treeIcons}
          onSelectTree={handleSelectTree}
          onRemoveTree={handleRemoveTree}
          onSlotClick={handleSlotClick}
          onSlotReorder={handleSlotReorder}
          onGoToTree={handleSlotClick}
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
            treeIcons={treeIcons}
            onBack={() => setScreen('tree-selector')}
            onSlotClick={handleSlotClick}
            onReselect={handleReselect}
            onSlotReorder={handleSlotReorder}
            onPreview={goToPreview}
          />
          {cascadeOverlay}
        </>
      )
    }
  } else if (screen === 'preview-selector') {
    screenContent = (
      <TreeSelectorScreen
        treeColors={treeColors}
        treeIcons={treeIcons}
        onSelectTree={handlePreviewTree}
        onRemoveTree={() => {}}
        onSlotClick={() => {}}
        onSlotReorder={() => {}}
        onGoToSelector={() => {}}
        onShiftUp={() => {}}
        onPreview={() => setScreen(previewSource)}
        previewMode
      />
    )
  } else if (screen === 'preview-viewer' && previewTree) {
    screenContent = (
      <TreeViewerScreen
        treeName={previewTree}
        treeColor={treeColors[previewTree] ?? '#e94560'}
        treeColors={treeColors}
        treeIcons={treeIcons}
        onBack={() => setScreen('preview-selector')}
        onSlotClick={() => {}}
        onReselect={() => setScreen('preview-selector')}
        onPreview={() => setScreen(previewSource)}
        previewMode
      />
    )
  } else if (screen === 'stats') {
    screenContent = <PlayerStatsScreen />
  }

  return (
    <>
      <div className="app-shell">
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
            {/* Inner boundaries — defense-in-depth on top of the root boundary in main.tsx; the
                persistent BuildSidebar/nav stays alive throughout. The swap-rendered branch is keyed
                on screen, so a crash recovers by navigating away (remount). Keep-alive screens stay
                mounted, so instead their boundary EVICTS the crashed screen from visitedKeepAlive
                (onError below) — it unmounts and remounts fresh on the next visit. */}
            <PerfProfiler id="screens">
              {/* Keep-alive editing screens: mounted on first visit, then hidden (display:none) when
                  inactive instead of unmounting, so in-progress edit state survives navigation. The
                  active one uses display:contents so it lays out as a direct child of .app-content. */}
              {KEEPALIVE_SCREENS.filter(id => visitedKeepAlive.has(id) || id === screen).map(id => (
                <div key={id} style={{ display: screen === id ? 'contents' : 'none' }}>
                  <ErrorBoundary onError={() => setVisitedKeepAlive(prev => {
                    if (!prev.has(id)) return prev
                    const next = new Set(prev)
                    next.delete(id)
                    return next
                  })}>{renderKeepAliveScreen(id)}</ErrorBoundary>
                </div>
              ))}
              {/* Swap-rendered screens (Calcs + the slot-dependent tree/preview flow): rendered only
                  while active, remounting on entry as before (keyed on screen). */}
              {!KEEPALIVE_SCREENS.includes(screen) && (
                <ErrorBoundary key={screen}>{screenContent}</ErrorBoundary>
              )}
            </PerfProfiler>
          </div>
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
