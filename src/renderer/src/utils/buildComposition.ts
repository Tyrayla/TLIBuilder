// Anonymous build-composition reporting (plan: "Anonymous build-composition statistics").
//
// The report is a set of canonical catalog IDs plus a data version. It carries no build code, no
// user-written text, no account, installation, cookie, or device identifier. Every identifier is
// checked against a strict catalog-ID shape before it is included, so text a user typed (a build name,
// a custom label) can never ride along even if it ends up in an ID field by mistake.

export interface CompositionBuild {
  traitId?: string | null
  skills?: {
    slot: number
    item_id: string
    skill_tags?: string[]
    enabled?: boolean
    supports?: { item_id: string; enabled?: boolean; [extra: string]: unknown }[]
  }[]
  gear?: { item_id: string; slot?: string | string[] | null; is_crafted?: boolean; base_type?: string }[]
  pactSpirits?: ({ itemId: string; [extra: string]: unknown } | null)[]
  heroMemories?: ({ memoryType?: string; rarity?: string } | null)[]
  slots?: { coreTalentSelections?: Record<string, string>; [extra: string]: unknown }[]
  slates?: { kind: string }[]
  prisms?: { kind: string }[]
}

export type EntityType =
  | 'hero_trait' | 'active_skill' | 'passive_skill' | 'support'
  | 'legendary_item' | 'legendary_slot' | 'crafted_base'
  | 'pact_spirit' | 'hero_memory' | 'core_talent' | 'slate' | 'prism'

export interface Composition {
  dataVersion: string
  entities: { type: EntityType; id: string }[]
  relations: { skillId: string; supportId: string }[]
  mechanics: string[]
}

const CATALOG_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$/

// Curated mechanic flags. Only these tags are ever reported; any other tag is ignored.
const MECHANIC_BY_TAG: Record<string, string> = {
  Summon: 'minion',
  Minion: 'minion',
  Spell: 'spell',
  Attack: 'attack',
  Aura: 'aura',
  Channeled: 'channeling',
  Focus: 'focus',
  Empower: 'empower',
  'Spirit Magus': 'spirit_magus',
}

const MAX_ENTITIES = 300

export function extractComposition(build: CompositionBuild, dataVersion: string): Composition {
  const seen = new Set<string>()
  const entities: Composition['entities'] = []
  const relations: Composition['relations'] = []
  const mechanics = new Set<string>()

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
    for (const tag of skill.skill_tags ?? []) {
      const mechanic = MECHANIC_BY_TAG[tag]
      if (mechanic) mechanics.add(mechanic)
    }
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

  for (const memory of build.heroMemories ?? []) {
    if (memory?.memoryType && memory.rarity) add('hero_memory', `${memory.memoryType}_${memory.rarity}`)
  }

  for (const tree of build.slots ?? []) {
    for (const talent of Object.values(tree?.coreTalentSelections ?? {})) add('core_talent', talent)
  }
  for (const slate of build.slates ?? []) add('slate', slate.kind)
  for (const prism of build.prisms ?? []) add('prism', prism.kind)

  return { dataVersion, entities, relations, mechanics: [...mechanics].sort() }
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

export interface CompositionReporter {
  onCalculated(event: { ok: boolean; build: CompositionBuild; dataVersion: string }): Promise<void>
}

export function createCompositionReporter(deps: {
  send: (composition: Composition) => Promise<void>
  /** The Privacy setting. Read on every call so turning it off takes effect immediately. */
  isEnabled: () => boolean
}): CompositionReporter {
  const reported = new Set<string>()
  const inFlight = new Set<string>()

  return {
    async onCalculated({ ok, build, dataVersion }) {
      if (!ok || !deps.isEnabled()) return
      const composition = extractComposition(build, dataVersion)
      if (composition.entities.length === 0) return
      const key = compositionKey(composition)
      if (reported.has(key) || inFlight.has(key)) return
      inFlight.add(key)
      try {
        await deps.send(composition)
        reported.add(key)
      } catch {
        // Reporting is best effort. A failure never reaches the user and the composition may retry later.
      } finally {
        inFlight.delete(key)
      }
    },
  }
}
