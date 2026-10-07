// Anonymous build-composition reporting (plan: "Anonymous build-composition statistics").
//
// The report is a set of canonical catalog IDs plus a data version. It carries no build code, no
// user-written text, no account, installation, cookie, or device identifier. Every identifier is
// checked against a strict catalog-ID shape before it is included, so text a user typed (a build name,
// a custom label) can never ride along even if it ends up in an ID field by mistake.
//
// How each part is derived (see also docs/HOSTED_ACCOUNT_API_CONTRACT.md, "Composition statistics"):
//  - entities: the catalog item IDs in the saved build (skills, supports, legendary items, spirits, ...).
//  - mechanics: only the baseline flags the plan names, each proven by a field of the engine's own
//    calculation result (mechanicsFromStats). No tag guessing, no text matching.
//  - Hero Memory: type and rarity, plus the base stat by its catalog uuid and a revival choice by its
//    catalog name, only when the catalog identifies the selection (a resolver supplies this).

export interface CompositionBuild {
  traitId?: string | null
  skills?: {
    slot: number
    item_id: string
    skill_tags?: string[]
    enabled?: boolean
    supports?: { item_id: string; enabled?: boolean; skill_tags?: string[] }[]
  }[]
  gear?: { item_id: string; slot?: string | string[] | null; is_crafted?: boolean; base_type?: string }[]
  pactSpirits?: ({ itemId: string; rank?: number } | null)[]
  heroMemories?: (MemoryLike | null)[]
  /** The Base/Special-slot memory. */
  baseMemory?: MemoryLike | null
  slots?: ({ coreTalentSelections?: Record<string, string>; treeName?: string; nodeStates?: Record<string, number> } | null)[]
  slates?: { kind: string }[]
  prisms?: { kind: string }[]
}

export interface MemorySelectionLike {
  modifier: string
  tier: number
}

export interface MemoryLike {
  memoryType?: string
  rarity?: string
  baseStat?: MemorySelectionLike | null
  revived?: boolean
  revivalMod?: MemorySelectionLike | null
}

/** Maps a saved selection to a catalog identifier, or null when the catalog does not identify it. */
export interface MemoryResolver {
  baseStat: (selection: MemorySelectionLike, memoryType: string) => string | null
  revival: (selection: MemorySelectionLike) => string | null
}

export type EntityType =
  | 'hero_trait' | 'active_skill' | 'passive_skill' | 'support'
  | 'legendary_item' | 'legendary_slot' | 'crafted_base'
  | 'pact_spirit' | 'hero_memory' | 'memory_base_stat' | 'memory_revival'
  | 'core_talent' | 'slate' | 'prism'

export interface Composition {
  dataVersion: string
  entities: { type: EntityType; id: string }[]
  relations: { skillId: string; supportId: string }[]
  mechanics: string[]
}

const CATALOG_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$/

/** The only mechanic flags ever reported: the plan's baseline list, in sorted order. */
export const MECHANIC_IDS = [
  'channeling', 'damage_over_time', 'minion', 'reservation', 'shadow_strike', 'spell_burst', 'tangle', 'trigger',
]

const MAX_ENTITIES = 300

export interface ExtractOptions {
  mechanics?: string[]
  memory?: MemoryResolver
}

export function extractComposition(build: CompositionBuild, dataVersion: string, opts: ExtractOptions = {}): Composition {
  const seen = new Set<string>()
  const entities: Composition['entities'] = []
  const relations: Composition['relations'] = []

  const add = (type: EntityType, id: unknown): void => {
    if (typeof id !== 'string' || !CATALOG_ID.test(id)) return
    const key = `${type}\u0000${id}`
    if (seen.has(key) || entities.length >= MAX_ENTITIES) return
    seen.add(key)
    entities.push({ type, id })
  }

  add('hero_trait', build.traitId)

  for (const skill of build.skills ?? []) {
    if (skill.enabled === false || !CATALOG_ID.test(skill.item_id)) continue
    add(skill.slot >= 6 ? 'passive_skill' : 'active_skill', skill.item_id)
    for (const support of skill.supports ?? []) {
      if (support.enabled === false || !CATALOG_ID.test(support.item_id)) continue
      add('support', support.item_id)
      relations.push({ skillId: skill.item_id, supportId: support.item_id })
    }
  }

  for (const item of build.gear ?? []) {
    if (item.is_crafted) {
      // A crafted item's own id is generated per craft; only its base type is a catalog value.
      add('crafted_base', item.base_type)
      continue
    }
    add('legendary_item', item.item_id)
    for (const slot of Array.isArray(item.slot) ? item.slot : [item.slot]) add('legendary_slot', slot)
  }

  for (const spirit of build.pactSpirits ?? []) if (spirit) add('pact_spirit', spirit.itemId)

  for (const memory of [...(build.heroMemories ?? []), build.baseMemory ?? null]) {
    if (!memory?.memoryType || !memory.rarity) continue
    add('hero_memory', `${memory.memoryType}_${memory.rarity}`)
    if (memory.baseStat) add('memory_base_stat', opts.memory?.baseStat(memory.baseStat, memory.memoryType))
    if (memory.revived && memory.revivalMod) add('memory_revival', opts.memory?.revival(memory.revivalMod))
  }

  for (const tree of build.slots ?? []) {
    for (const talent of Object.values(tree?.coreTalentSelections ?? {})) add('core_talent', talent)
  }
  for (const slate of build.slates ?? []) add('slate', slate.kind)
  for (const prism of build.prisms ?? []) add('prism', prism.kind)

  const mechanics = [...new Set(opts.mechanics ?? [])].filter((m) => MECHANIC_IDS.includes(m)).sort()
  return { dataVersion, entities, relations, mechanics }
}

// ── Mechanic flags from the engine result ────────────────────────────────────
interface OffenseLike {
  supported?: boolean
  spell_burst_count?: number
  tangle_count?: number
  shadow_count?: number
  channeled_max_stacks?: number
  trigger_interval?: number
  damage_rows?: { kind?: string }[]
}

export interface StatsLike {
  offense?: OffenseLike | null
  slot_offense?: Record<string, OffenseLike> | null
  minion_offense?: Record<string, OffenseLike> | null
  reservation?: { per_skill?: unknown[] } | null
}

/**
 * Flags the engine's own result proves, for any equipped active skill:
 *  - spell_burst: spell_burst_count > 0 (the skill is modeled as bursting)
 *  - tangle: tangle_count > 0 (the skill is cast by attached tangles)
 *  - shadow_strike: shadow_count > 0 (the skill summons Shadows)
 *  - channeling: channeled_max_stacks > 0 (a channeled skill with stacks)
 *  - trigger: trigger_interval > 0 (an activation medium triggers the skill)
 *  - damage_over_time: a damage row of kind "dot" (skill-DoT skills only; ailment damage is not counted)
 *  - minion: a modeled (supported) minion owner in minion_offense
 *  - reservation: at least one skill reserving mana or life (reservation.per_skill)
 */
export function mechanicsFromStats(stats: StatsLike): string[] {
  const found = new Set<string>()
  const offenses = [stats.offense, ...Object.values(stats.slot_offense ?? {})].filter(
    (o): o is OffenseLike => !!o && o.supported === true,
  )
  for (const o of offenses) {
    if ((o.spell_burst_count ?? 0) > 0) found.add('spell_burst')
    if ((o.tangle_count ?? 0) > 0) found.add('tangle')
    if ((o.shadow_count ?? 0) > 0) found.add('shadow_strike')
    if ((o.channeled_max_stacks ?? 0) > 0) found.add('channeling')
    if ((o.trigger_interval ?? 0) > 0) found.add('trigger')
    if ((o.damage_rows ?? []).some((r) => r.kind === 'dot')) found.add('damage_over_time')
  }
  if (Object.values(stats.minion_offense ?? {}).some((o) => o && o.supported === true)) found.add('minion')
  if ((stats.reservation?.per_skill?.length ?? 0) > 0) found.add('reservation')
  return [...found].sort()
}

/** Order-independent identity of a composition, used only to avoid re-reporting one in a session. */
export function compositionKey(c: Composition): string {
  const parts = [
    c.dataVersion,
    ...c.entities.map((e) => `e:${e.type}:${e.id}`),
    ...c.relations.map((r) => `r:${r.skillId}:${r.supportId}`),
    ...c.mechanics.map((m) => `m:${m}`),
  ]
  return parts.sort().join('|')
}

export interface CompositionEvent extends ExtractOptions {
  ok: boolean
  build: CompositionBuild
  dataVersion: string
}

export interface CompositionReporter {
  onCalculated(event: CompositionEvent): Promise<void>
  /** Abort anything still in flight. Used when the user turns reporting off. */
  cancelAll(): void
}

export function createCompositionReporter(deps: {
  send: (composition: Composition, signal?: AbortSignal) => Promise<void>
  /** The Privacy setting. Read on every call so turning it off takes effect immediately. */
  isEnabled: () => boolean
}): CompositionReporter {
  const reported = new Set<string>()
  const inFlight = new Map<string, AbortController>()

  return {
    async onCalculated({ ok, build, dataVersion, mechanics, memory }) {
      if (!ok || !deps.isEnabled()) return
      const composition = extractComposition(build, dataVersion, { mechanics, memory })
      if (composition.entities.length === 0) return
      const key = compositionKey(composition)
      if (reported.has(key) || inFlight.has(key)) return
      // Checked again immediately before sending, so a switch flipped meanwhile is honored.
      if (!deps.isEnabled()) return
      const controller = new AbortController()
      inFlight.set(key, controller)
      try {
        await deps.send(composition, controller.signal)
        if (!controller.signal.aborted) reported.add(key)
      } catch {
        // Reporting is best effort. A failure never reaches the user and the composition may retry later.
      } finally {
        inFlight.delete(key)
      }
    },
    cancelAll() {
      for (const controller of inFlight.values()) controller.abort()
      inFlight.clear()
    },
  }
}
