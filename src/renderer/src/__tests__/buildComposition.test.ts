import { describe, it, expect, vi } from 'vitest'
import {
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

  it('derives curated mechanic flags from skill tags and nothing else', () => {
    const c = extractComposition(build({
      skills: [{ slot: 1, item_id: 'skill_x', skill_tags: ['Summon', 'Spell', 'Whatever Custom Tag'], supports: [] }],
    }), 'season-9')
    expect(c.mechanics).toEqual(['minion', 'spell'])
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
})
