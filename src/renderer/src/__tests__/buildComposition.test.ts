import { describe, it, expect, vi } from 'vitest'
import {
  mechanicsFromStats,
  MECHANIC_IDS,
  extractComposition,
  compositionKey,
  createCompositionReporter,
  type CompositionBuild,
} from '../utils/buildComposition'

const build = (over: Partial<CompositionBuild> = {}): CompositionBuild => ({
  traitId: 'trait_berserker',
  skills: [
    {
      slot: 1, item_id: 'skill_chain_lightning', skill_tags: ['Spell', 'Chain'],
      supports: [
        { item_id: 'support_added_fire', skill_tags: ['Support'] },
        { item_id: 'support_spell_burst', skill_tags: ['Support'] },
      ],
    },
    { slot: 6, item_id: 'skill_aura_one', skill_tags: ['Aura'], supports: [] },
  ],
  gear: [
    { item_id: 'leg_ring_1', slot: 'ring1', is_crafted: false },
    { item_id: 'crafted_user_item_7', slot: 'chest', is_crafted: true, base_type: 'base_chest_plate' },
  ],
  pactSpirits: [{ itemId: 'spirit_wolf', rank: 3 }, null, null],
  slots: [{ treeName: 'God_of_War', nodeStates: {}, coreTalentSelections: { '0': 'core_a' } }],
  slates: [{ kind: 'slate_fire' }],
  prisms: [{ kind: 'ethereal_prism' }],
  ...over,
})

describe('extractComposition', () => {
  it('lists canonical IDs by entity type with the data version', () => {
    const c = extractComposition(build(), 'season-9')
    expect(c.dataVersion).toBe('season-9')
    expect(c.entities).toContainEqual({ type: 'hero_trait', id: 'trait_berserker' })
    expect(c.entities).toContainEqual({ type: 'active_skill', id: 'skill_chain_lightning' })
    expect(c.entities).toContainEqual({ type: 'passive_skill', id: 'skill_aura_one' })
    expect(c.entities).toContainEqual({ type: 'support', id: 'support_added_fire' })
    expect(c.entities).toContainEqual({ type: 'legendary_item', id: 'leg_ring_1' })
    expect(c.entities).toContainEqual({ type: 'legendary_slot', id: 'ring1' })
    expect(c.entities).toContainEqual({ type: 'crafted_base', id: 'base_chest_plate' })
    expect(c.entities).toContainEqual({ type: 'pact_spirit', id: 'spirit_wolf' })
    expect(c.entities).toContainEqual({ type: 'core_talent', id: 'core_a' })
    expect(c.entities).toContainEqual({ type: 'slate', id: 'slate_fire' })
    expect(c.entities).toContainEqual({ type: 'prism', id: 'ethereal_prism' })
  })

  it('records a hero memory only as its coarse type and rarity', () => {
    const c = extractComposition(build({
      heroMemories: [{ memoryType: 'origin', rarity: 'ultimate', secretNote: 'x' }, null, null],
    } as Partial<CompositionBuild>), 'season-9')
    expect(c.entities).toContainEqual({ type: 'hero_memory', id: 'origin_ultimate' })
    expect(JSON.stringify(c)).not.toContain('secretNote')
  })

  it('records skill/support pairs', () => {
    const c = extractComposition(build(), 'season-9')
    expect(c.relations).toEqual([
      { skillId: 'skill_chain_lightning', supportId: 'support_added_fire' },
      { skillId: 'skill_chain_lightning', supportId: 'support_spell_burst' },
    ])
  })

  it('never reports a crafted item\'s own id, only its base type', () => {
    const c = extractComposition(build(), 'season-9')
    expect(JSON.stringify(c)).not.toContain('crafted_user_item_7')
  })

  it('drops any identifier that is not a plain catalog id (user text cannot leak)', () => {
    const c = extractComposition(build({
      traitId: 'My secret build name!',
      skills: [{ slot: 1, item_id: 'x'.repeat(200), skill_tags: [], supports: [] }],
      gear: [{ item_id: 'has space', slot: 'ring1', is_crafted: false }],
    }), 'season-9')
    expect(c.entities.filter((e) => e.type === 'hero_trait')).toEqual([])
    expect(c.entities.filter((e) => e.type === 'active_skill')).toEqual([])
    expect(c.entities.filter((e) => e.type === 'legendary_item')).toEqual([])
  })

  it('ignores unequipped slots and disabled skills', () => {
    const c = extractComposition(build({
      pactSpirits: [null, null, null],
      skills: [{ slot: 1, item_id: 'skill_off', skill_tags: [], supports: [], enabled: false }],
    }), 'season-9')
    expect(c.entities.some((e) => e.id === 'skill_off')).toBe(false)
    expect(c.entities.some((e) => e.type === 'pact_spirit')).toBe(false)
  })

  it('takes mechanic flags only from the allowlist passed in, never from tags or free text', () => {
    const c = extractComposition(build({
      skills: [{ slot: 1, item_id: 'skill_x', skill_tags: ['Summon', 'Spell', 'Whatever Custom Tag'], supports: [] }],
    }), 'season-9', { mechanics: ['minion', 'not_a_flag', 'spell_burst', 'minion'] })
    expect(c.mechanics).toEqual(['minion', 'spell_burst'])
    expect(extractComposition(build(), 'season-9').mechanics).toEqual([])
  })

  it('has no field that could carry text, accounts, or devices', () => {
    const c = extractComposition(build({ name: 'Private Name', notes: 'secret notes', customMods: ['custom'] } as Partial<CompositionBuild>), 'season-9')
    const json = JSON.stringify(c)
    for (const leak of ['Private Name', 'secret notes', 'custom']) expect(json).not.toContain(leak)
    expect(Object.keys(c).sort()).toEqual(['dataVersion', 'entities', 'mechanics', 'relations'])
  })

  it('dedupes repeated entities', () => {
    const c = extractComposition(build({ gear: [
      { item_id: 'leg_ring_1', slot: 'ring1', is_crafted: false },
      { item_id: 'leg_ring_1', slot: 'ring2', is_crafted: false },
    ] }), 'season-9')
    expect(c.entities.filter((e) => e.type === 'legendary_item')).toHaveLength(1)
  })
})

describe('compositionKey', () => {
  it('is stable across ordering and changes when the composition changes', () => {
    const a = extractComposition(build(), 'season-9')
    const b = extractComposition(build({ gear: [...build().gear!].reverse() }), 'season-9')
    expect(compositionKey(a)).toBe(compositionKey(b))
    const c = extractComposition(build({ traitId: 'trait_other' }), 'season-9')
    expect(compositionKey(c)).not.toBe(compositionKey(a))
  })
})

describe('createCompositionReporter', () => {
  const setup = (enabled = true) => {
    const send = vi.fn().mockResolvedValue(undefined)
    const reporter = createCompositionReporter({ send, isEnabled: () => enabled })
    return { send, reporter }
  }

  it('sends once after a successful calculation', async () => {
    const { send, reporter } = setup()
    await reporter.onCalculated({ ok: true, build: build(), dataVersion: 'season-9' })
    expect(send).toHaveBeenCalledTimes(1)
    expect(send.mock.calls[0][0].dataVersion).toBe('season-9')
  })

  it('does not send for a failed calculation', async () => {
    const { send, reporter } = setup()
    await reporter.onCalculated({ ok: false, build: build(), dataVersion: 'season-9' })
    expect(send).not.toHaveBeenCalled()
  })

  it('does not resend an unchanged composition in the same session', async () => {
    const { send, reporter } = setup()
    await reporter.onCalculated({ ok: true, build: build(), dataVersion: 'season-9' })
    await reporter.onCalculated({ ok: true, build: build({ name: 'renamed' } as Partial<CompositionBuild>), dataVersion: 'season-9' })
    expect(send).toHaveBeenCalledTimes(1)
  })

  it('sends again when the composition changes', async () => {
    const { send, reporter } = setup()
    await reporter.onCalculated({ ok: true, build: build(), dataVersion: 'season-9' })
    await reporter.onCalculated({ ok: true, build: build({ traitId: 'trait_other' }), dataVersion: 'season-9' })
    expect(send).toHaveBeenCalledTimes(2)
  })

  it('stops all network reporting when the user opts out', async () => {
    const { send, reporter } = setup(false)
    await reporter.onCalculated({ ok: true, build: build(), dataVersion: 'season-9' })
    expect(send).not.toHaveBeenCalled()
  })

  it('does not report an empty build', async () => {
    const { send, reporter } = setup()
    await reporter.onCalculated({ ok: true, build: { skills: [], gear: [] }, dataVersion: 'season-9' })
    expect(send).not.toHaveBeenCalled()
  })

  it('never lets a failed send disturb the app, and retries that composition later', async () => {
    const { send, reporter } = setup()
    send.mockRejectedValueOnce(new Error('offline'))
    await expect(reporter.onCalculated({ ok: true, build: build(), dataVersion: 'season-9' })).resolves.toBeUndefined()
    await reporter.onCalculated({ ok: true, build: build(), dataVersion: 'season-9' })
    expect(send).toHaveBeenCalledTimes(2)
  })

  it('a changed mechanic set counts as a changed composition', async () => {
    const { send, reporter } = setup()
    await reporter.onCalculated({ ok: true, build: build(), dataVersion: 's', mechanics: ['tangle'] })
    await reporter.onCalculated({ ok: true, build: build(), dataVersion: 's', mechanics: ['tangle', 'minion'] })
    expect(send).toHaveBeenCalledTimes(2)
  })
})

describe('mechanicsFromStats (derived from the engine result, never guessed)', () => {
  const off = (over: Record<string, unknown> = {}) => ({ supported: true, spell_burst_count: 0, tangle_count: 0, shadow_count: 0, channeled_max_stacks: 0, trigger_interval: 0, damage_rows: [], ...over })

  it('reports nothing for an empty or unsupported result', () => {
    expect(mechanicsFromStats({})).toEqual([])
    expect(mechanicsFromStats({ offense: off({ spell_burst_count: 3, supported: false }) })).toEqual([])
  })

  it('requires explicit support on both main and slot offense results', () => {
    // Deliberately omit supported, rather than using the off() fixture's true default.
    const missing = { spell_burst_count: 2, tangle_count: 3, shadow_count: 1, channeled_max_stacks: 4, trigger_interval: 1, damage_rows: [{ kind: 'dot' }] }
    expect(mechanicsFromStats({ offense: missing, reservation: { per_skill: [{}] } })).toEqual(['reservation'])
    expect(mechanicsFromStats({ slot_offense: { '2': missing }, reservation: { per_skill: [{}] } })).toEqual(['reservation'])
    expect(mechanicsFromStats({ offense: { ...missing, supported: true } })).toEqual([
      'channeling', 'damage_over_time', 'shadow_strike', 'spell_burst', 'tangle', 'trigger',
    ])
    expect(mechanicsFromStats({ slot_offense: { '2': { ...missing, supported: true } } })).toEqual([
      'channeling', 'damage_over_time', 'shadow_strike', 'spell_burst', 'tangle', 'trigger',
    ])
  })

  it('maps each baseline flag to the engine field that proves it', () => {
    expect(mechanicsFromStats({ offense: off({ spell_burst_count: 2 }) })).toEqual(['spell_burst'])
    expect(mechanicsFromStats({ offense: off({ tangle_count: 3 }) })).toEqual(['tangle'])
    expect(mechanicsFromStats({ offense: off({ shadow_count: 2 }) })).toEqual(['shadow_strike'])
    expect(mechanicsFromStats({ offense: off({ channeled_max_stacks: 6 }) })).toEqual(['channeling'])
    expect(mechanicsFromStats({ offense: off({ trigger_interval: 0.5 }) })).toEqual(['trigger'])
    expect(mechanicsFromStats({ offense: off({ damage_rows: [{ kind: 'hit' }, { kind: 'dot' }] }) })).toEqual(['damage_over_time'])
    expect(mechanicsFromStats({ reservation: { per_skill: [{}] } })).toEqual(['reservation'])
    expect(mechanicsFromStats({ minion_offense: { owner: off() } })).toEqual(['minion'])
  })

  const reportFullMechanics = async (minionSupported?: boolean) => {
    const send = vi.fn().mockResolvedValue(undefined)
    const reporter = createCompositionReporter({ send, isEnabled: () => true })
    const offense = off({
      spell_burst_count: 1,
      tangle_count: 1,
      shadow_count: 1,
      channeled_max_stacks: 1,
      trigger_interval: 1,
      damage_rows: [{ kind: 'dot' }],
    })
    const minionOwner = minionSupported === undefined ? {} : off({ supported: minionSupported })
    await reporter.onCalculated({
      ok: true,
      build: { traitId: 'trait_berserker' },
      dataVersion: 'season-9',
      mechanics: mechanicsFromStats({
        offense,
        reservation: { per_skill: [{}] },
        minion_offense: { owner: minionOwner },
      }),
    })
    expect(send).toHaveBeenCalledTimes(1)
    return send.mock.calls[0][0]
  }

  it('does not report minion when the minion owner has no supported flag', async () => {
    expect(await reportFullMechanics()).toEqual({
      dataVersion: 'season-9',
      entities: [{ type: 'hero_trait', id: 'trait_berserker' }],
      relations: [],
      mechanics: ['channeling', 'damage_over_time', 'reservation', 'shadow_strike', 'spell_burst', 'tangle', 'trigger'],
    })
  })

  it('does not report minion when the minion owner is unsupported', async () => {
    expect(await reportFullMechanics(false)).toEqual({
      dataVersion: 'season-9',
      entities: [{ type: 'hero_trait', id: 'trait_berserker' }],
      relations: [],
      mechanics: ['channeling', 'damage_over_time', 'reservation', 'shadow_strike', 'spell_burst', 'tangle', 'trigger'],
    })
  })

  it('reports minion when the minion owner is supported', async () => {
    expect(await reportFullMechanics(true)).toEqual({
      dataVersion: 'season-9',
      entities: [{ type: 'hero_trait', id: 'trait_berserker' }],
      relations: [],
      mechanics: ['channeling', 'damage_over_time', 'minion', 'reservation', 'shadow_strike', 'spell_burst', 'tangle', 'trigger'],
    })
  })

  it('looks across every equipped skill slot, not only the main skill', () => {
    expect(mechanicsFromStats({ offense: off(), slot_offense: { '1': off(), '2': off({ tangle_count: 2 }) } })).toEqual(['tangle'])
  })

  it('reports only allowlisted flags, sorted', () => {
    const all = mechanicsFromStats({
      offense: off({ spell_burst_count: 1, tangle_count: 1, shadow_count: 1, channeled_max_stacks: 1, trigger_interval: 1, damage_rows: [{ kind: 'dot' }] }),
      reservation: { per_skill: [{}] }, minion_offense: { a: off() },
    })
    expect(all).toEqual([...all].sort())
    expect(all.every((m) => MECHANIC_IDS.includes(m))).toBe(true)
    expect(MECHANIC_IDS).toEqual(['channeling', 'damage_over_time', 'minion', 'reservation', 'shadow_strike', 'spell_burst', 'tangle', 'trigger'])
  })
})

describe('Hero Memory base and revival choices', () => {
  const resolver = {
    baseStat: (sel: { modifier: string; tier: number }) => (sel.modifier === '+90 Strength' ? 'a65f0fbf-bc8f-5e90-a594-7b70b6fb7a63' : null),
    revival: (sel: { modifier: string; tier: number }) => (sel.modifier === 'Furious Roar' ? 'furious_roar' : null),
  }
  const memory = (over: Record<string, unknown> = {}) => ({
    memoryType: 'origin', rarity: 'ultimate',
    baseStat: { modifier: '+90 Strength', tier: 1, rolledValue: 90 },
    revived: true, revivalMod: { modifier: 'Furious Roar', tier: 0, rolledValue: null, description: 'free text' },
    ...over,
  })
  const withMemories = (heroMemories: unknown[], extra: Record<string, unknown> = {}) =>
    build({ heroMemories, ...extra } as unknown as Partial<CompositionBuild>)

  it('reports the base stat by its catalog id and a revival choice by its catalog name id', () => {
    const c = extractComposition(withMemories([memory(), null, null]), 'season-9', { memory: resolver })
    expect(c.entities).toContainEqual({ type: 'hero_memory', id: 'origin_ultimate' })
    expect(c.entities).toContainEqual({ type: 'memory_base_stat', id: 'a65f0fbf-bc8f-5e90-a594-7b70b6fb7a63' })
    expect(c.entities).toContainEqual({ type: 'memory_revival', id: 'furious_roar' })
  })

  it('also reads the Base/Special slot memory', () => {
    const c = extractComposition(withMemories([], { baseMemory: memory({ memoryType: 'discipline' }) }), 'season-9', { memory: resolver })
    expect(c.entities).toContainEqual({ type: 'hero_memory', id: 'discipline_ultimate' })
  })

  it('reports a choice only when the catalog identifies it', () => {
    const c = extractComposition(withMemories([memory({
      baseStat: { modifier: 'unknown text', tier: 1, rolledValue: 5 },
      revivalMod: { modifier: 'Some tiered row text', tier: 2, rolledValue: 7, description: 'free text' },
    }), null, null]), 'season-9', { memory: resolver })
    expect(c.entities.some((e) => e.type === 'memory_base_stat')).toBe(false)
    expect(c.entities.some((e) => e.type === 'memory_revival')).toBe(false)
  })

  it('never sends the modifier text, the roll, or the description', () => {
    const json = JSON.stringify(extractComposition(withMemories([memory(), null, null]), 'season-9', { memory: resolver }))
    for (const leak of ['free text', '+90 Strength', 'rolledValue', 'Furious Roar']) expect(json).not.toContain(leak)
  })

  it('an unrevived memory reports no revival', () => {
    const c = extractComposition(withMemories([memory({ revived: false, revivalMod: null }), null, null]), 'season-9', { memory: resolver })
    expect(c.entities.some((e) => e.type === 'memory_revival')).toBe(false)
  })

  it('without a catalog resolver only the coarse memory type and rarity are reported', () => {
    const c = extractComposition(withMemories([memory(), null, null]), 'season-9')
    expect(c.entities.filter((e) => e.type.startsWith('memory_'))).toEqual([])
    expect(c.entities).toContainEqual({ type: 'hero_memory', id: 'origin_ultimate' })
  })
})

describe('opt-out stops in-flight and retrying reports', () => {
  it('cancelAll aborts a send that is still in flight', async () => {
    let seen: AbortSignal | undefined
    const send = vi.fn((_c: unknown, signal?: AbortSignal) => new Promise<void>((_res, rej) => {
      seen = signal
      signal?.addEventListener('abort', () => rej(new Error('aborted')))
    }))
    const reporter = createCompositionReporter({ send: send as never, isEnabled: () => true })
    const pending = reporter.onCalculated({ ok: true, build: build(), dataVersion: 's' })
    await Promise.resolve()
    reporter.cancelAll()
    await pending
    expect(seen?.aborted).toBe(true)
  })

  it('does not send when the switch is off at the moment the send would start', async () => {
    let calls = 0
    const send = vi.fn().mockResolvedValue(undefined)
    // enabled for the first check (entry), off for the second (just before sending)
    const reporter = createCompositionReporter({ send, isEnabled: () => ++calls === 1 })
    await reporter.onCalculated({ ok: true, build: build(), dataVersion: 's' })
    expect(send).not.toHaveBeenCalled()
  })
})
