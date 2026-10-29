import { describe, expect, it } from 'vitest'
import { createReadStream } from 'node:fs'
import { Readable } from 'node:stream'
import { scanUeGameLog } from '../importers/ueLog/parse'
import { createUeLogBuild, groupUeLogCaptures } from '../importers/ueLog/toBuild'
import type { BeltBlend, CraftBaseItemGroup, CraftBaseType, Graft, LegendaryGearItem, SkillItem } from '../api/client'

const log = `prefix before dump\n----Socket RecvMessage STT----GetPlayerData----SynId = 1\n|+player+Level [98]\n|+player+HeroId [700]\n|+heroCharacterv3OverView+heroPurchaseId [3002]\n|+bag+wearItems+1+Index [7]\n|+bag+wearItems+1+Item+BaseId [380009]\n|+bag+wearItems+1+Item+Level [89]\n|+bag+wearItems+1+Item+UniqueItmId [0]\n|+bag+wearItems+1+Item+BaseAttrAffix+1+Id [800000]\n|+bag+wearItems+1+Item+BaseAffix+1+Id [172103200]\n|+bag+wearItems+1+Item+ChipAffix+1+Id [160567034]\n|+bag+wearItems+1+Item+EnchantAffixs+1+Id [3704005]\n|+bag+wearItems+1+Item+Corrode [true]\n|+bag+wearItems+1+Item+Prefix+1+Id [251471001]\n|+bag+wearItems+1+Item+Prefix+1+source [16]\n|+bag+wearItems+1+Item+Prefix+1+DynArgs+1 [2.0]\n|+bag+wearItems+1+Item+Prefix+1+DynArgs+2 [-3.0]\n|+bag+wearItems+1+Item+Suffix+1+Id [51533751]\n|+bag+wearItems+1+Item+Suffix+1+source [17]\n|+bag+wearItems+1+Item+Suffix+1+DynArgs+1 [1.0]\n|+bag+wearItems+1+Item+Suffix+1+DynArgs+2 [3.0]\n----Socket RecvMessage End----\ntail after dump\n`

const skillLog = `----Socket RecvMessage STT----GetPlayerData----SynId = 2
|+bag+dressSkillItems+1+Item+Id [7746_noble]
|+bag+dressSkillItems+1+Item+BaseId [7746]
|+bag+dressSkillItems+1+Item+Level [1]
|+bag+dressSkillItems+1+Item+SkillItemLevel [89]
|+bag+dressSkillItems+1+Item+Prefix+1+Id [771031022]
|+bag+dressSkillItems+1+Item+Prefix+1+DynArgs+1 [31.0]
|+bag+dressSkillItems+1+Index [305]
|+bag+dressSkillItems+1+PageId [-6]
|+skills+skills+1+Id [7018_whirlwind]
|+skills+skills+1+BaseId [7018]
|+skills+skills+1+Level [20]
|+skills+skills+1+SkillItemLevel [16]
|+skillLayout+slots+1+key [3]
|+skillLayout+slots+1+value+skillId [7018_whirlwind]
|+skillLayout+slots+2+key [305]
|+skillLayout+slots+2+value+skillId [7746_noble]
----Socket RecvMessage End----`

function chunkedFile(text: string, chunkSize = 17): File {
  const bytes = new TextEncoder().encode(text)
  return {
    size: bytes.length,
    stream: () => new ReadableStream<Uint8Array>({
      start(controller) {
        for (let offset = 0; offset < bytes.length; offset += chunkSize) {
          controller.enqueue(bytes.slice(offset, offset + chunkSize))
        }
        controller.close()
      },
    }),
  } as unknown as File
}

describe('UE_game.log preview', () => {
  it('joins the three equipped skill lists by item ID and preserves the logged slot and level', async () => {
    const result = await scanUeGameLog(chunkedFile(skillLog))

    expect(result.characters[0].skills).toEqual([
      { baseId: 7018, logIndex: 3, level: 20, skillItemLevel: 16, prefixes: [] },
      { baseId: 7746, logIndex: 305, level: 1, skillItemLevel: 89, prefixes: [{ id: '771031022', source: null, values: [31] }] },
    ])
  })

  it('streams login dumps and returns the Vorax base, equipped slot, affix source, and rolled values', async () => {
    const result = await scanUeGameLog(chunkedFile(log))

    expect(result.errors).toEqual([])
    expect(result.characters).toHaveLength(1)
    expect(result.characters[0]).toMatchObject({
      dumpNumber: 1,
      characterName: null,
      level: 98,
      heroId: 700,
      heroPurchaseId: 3002,
      gear: [{
        baseId: 380009,
        itemLevel: 89,
        equippedSlot: 7,
        uniqueItemId: 0,
        baseAttrAffixIds: ['800000'],
        baseAffixIds: ['172103200'],
        prefixes: [{ id: '251471001', source: '16', values: [2, -3] }],
        suffixes: [{ id: '51533751', source: '17', values: [1, 3] }],
        chipAffixes: [{ id: '160567034', source: null, values: [] }],
        enchantAffixes: [{ id: '3704005', source: null, values: [] }],
        corroded: true,
      }],
      truncatedSections: [],
    })
    expect(JSON.stringify(result)).not.toContain('PlayerId')
    expect(JSON.stringify(result)).not.toContain('UserId')
  })

  it('reports a file with no login dump without returning file contents', async () => {
    const result = await scanUeGameLog(chunkedFile('personal text that is not a game dump'))

    expect(result.characters).toEqual([])
    expect(result.errors).toEqual(['No GetPlayerData login dumps were found in this file.'])
    expect(JSON.stringify(result)).not.toContain('personal text')
  })

  it.skipIf(!process.env.TLI_GAME_LOG)('can inspect a private real log without committing it as a fixture', async () => {
    const file = {
      stream: () => Readable.toWeb(createReadStream(process.env.TLI_GAME_LOG!)) as ReadableStream<Uint8Array>,
    } as File
    const result = await scanUeGameLog(file)
    const vorax = result.characters.flatMap(character => character.gear).filter(item => item.baseId === 380009)

    expect(result.errors).toEqual([])
    expect(result.characters.length).toBeGreaterThan(0)
    expect(result.characters.some(character => character.characterName !== null)).toBe(true)
    expect(vorax.length).toBeGreaterThan(0)
    expect(vorax[0].baseAffixIds).toContain('172103200')
    expect(vorax[0].prefixes.map(affix => affix.source)).toContain('16')
  })
})

describe('UE_game.log build conversion', () => {
  it('groups captures by character and hero, then keeps the latest file for import', () => {
    const capture = (fileNumber: number, modifiedAt: number, characterName: string, heroId: number, level: number) => ({
      fileNumber,
      modifiedAt,
      preview: { dumpNumber: 1, characterName, level, heroId, heroPurchaseId: null, gear: [], skills: [], truncatedSections: [] },
    })
    const groups = groupUeLogCaptures([
      capture(1, 100, 'Sage', 1800, 94),
      capture(2, 200, 'sage', 1800, 98),
      capture(3, 150, 'Other', 1800, 90),
    ])
    expect(groups).toEqual([
      { fileNumber: 2, preview: { dumpNumber: 1, characterName: 'sage', level: 98, heroId: 1800, heroPurchaseId: null, gear: [], skills: [], truncatedSections: [] }, loginCount: 2 },
      { fileNumber: 3, preview: { dumpNumber: 1, characterName: 'Other', level: 90, heroId: 1800, heroPurchaseId: null, gear: [], skills: [], truncatedSections: [] }, loginCount: 1 },
    ])
  })

  it('merges capped skill lists across the same character’s login captures', () => {
    const capture = (dumpNumber: number, modifiedAt: number, skills: Array<{ baseId: number; logIndex: number; level: number | null; skillItemLevel: number | null; prefixes: Array<{ id: string; source: string | null; values: number[] }> }>) => ({
      fileNumber: 1,
      modifiedAt,
      preview: { dumpNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001, gear: [], skills, truncatedSections: [] },
    })
    const groups = groupUeLogCaptures([
      capture(1, 100, [
        { baseId: 7289, logIndex: 2, level: 19, skillItemLevel: 1, prefixes: [] },
        { baseId: 7018, logIndex: 3, level: 20, skillItemLevel: 16, prefixes: [] },
      ]),
      capture(2, 200, [
        { baseId: 7289, logIndex: 2, level: 20, skillItemLevel: 1, prefixes: [] },
      ]),
    ])

    expect(groups[0].preview.skills).toEqual([
      { baseId: 7289, logIndex: 2, level: 20, skillItemLevel: 1, prefixes: [] },
      { baseId: 7018, logIndex: 3, level: 20, skillItemLevel: 16, prefixes: [] },
    ])
  })

  it('maps equipped active skills and their supports through TLIDB game IDs and log slot indexes', () => {
    const character = {
      dumpNumber: 1,
      characterName: 'Sage',
      level: 98,
      heroId: 1800,
      heroPurchaseId: 18001,
      truncatedSections: [],
      gear: [],
      skills: [
        { baseId: 7018, logIndex: 3, level: 20, skillItemLevel: 16, prefixes: [] },
        { baseId: 7746, logIndex: 305, level: 1, skillItemLevel: 89, prefixes: [{ id: '771031022', source: null, values: [31] }] },
      ],
    }
    const catalog = [
      { item_id: 'whirlwind', name: 'Whirlwind', game_id: 7018, skill_type: 'active_skill', skill_tags: ['Attack'], description_lines: ['Deals weapon attack damage.'], raw_text: '', max_level: 20 },
      { item_id: 'whirlwind_whirling_blade_noble', name: 'Whirlwind: Whirling Blade (Noble)', game_id: 7746, skill_type: 'noble_support_skill', skill_tags: ['Support', 'Physical'], description_lines: ['Supports Whirlwind.'], raw_text: '', max_level: 5 },
    ] as SkillItem[]

    const result = createUeLogBuild(character, [], [], [], [], [], catalog)

    expect(result.build.skills).toEqual([{
      slot: 3,
      item_id: 'whirlwind',
      name: 'Whirlwind',
      level: 20,
      skill_tags: ['Attack'],
      description_lines: ['Deals weapon attack damage.'],
      supports: [{
        support_index: 5,
        item_id: 'whirlwind_whirling_blade_noble',
        name: 'Whirlwind: Whirling Blade (Noble)',
        skill_type: 'noble_support_skill',
        level: 1,
        rank: 1,
        skill_tags: ['Support', 'Physical'],
        description_lines: ['Supports Whirlwind.'],
      }],
    }])
    expect(result.warnings).toContain('Whirlwind: Whirling Blade (Noble): support modifier 771031022 is not mapped; its roll and rank use Builder defaults.')
  })

  it('creates an editable Vorax item with mapped affixes and exact rolls', () => {
    const graft = {
      item_id: 'vorax_limb_digits',
      game_id: 380009,
      name: 'Vorax Limb: Digits',
      legendary_items: [],
      base_affixes: [
        { modifier_id: '800000', raw_text: '0 Gear Armor', expression: '0 Gear Armor', condition: null, affix_kind: 'numeric', numeric_values: [], tier: 'Base', level: 0, weight: 0, affix_type: 'Base' },
        { modifier_id: '172103200', raw_text: 'Have Fervor', expression: 'Have Fervor', condition: null, affix_kind: 'special', numeric_values: [], tier: 'Base', level: 0, weight: 0, affix_type: 'Base Affix' },
      ],
      affixes: [
        { modifier_id: '251471001', raw_text: '+(#) Max Channeled Stacks, -(#) % additional damage', expression: '+(#) Max Channeled Stacks, -(#) % additional damage', condition: null, affix_kind: 'numeric', numeric_values: [{ kind: 'range', sign: '+', min: 1, max: 3, raw: '+(1-3)' }, { kind: 'range', sign: '-', min: 1, max: 3, raw: '-(1-3)' }], tier: '1', level: 1, weight: 1, affix_type: 'Ultimate Affix' },
        { modifier_id: '251181602', raw_text: '+(#) % damage', expression: '+(#) % damage', condition: null, affix_kind: 'numeric', numeric_values: [{ kind: 'range', sign: '+', min: 37, max: 50, raw: '+(37-50)' }], tier: '2', level: 1, weight: 1, affix_type: 'Basic Affix' },
        { modifier_id: '251181802', raw_text: 'Adds (#) - (#) Erosion Damage to Attacks and Spells', expression: 'Adds (#) - (#) Erosion Damage to Attacks and Spells', condition: null, affix_kind: 'numeric', numeric_values: [{ kind: 'range', sign: '+', min: 25, max: 27, raw: '+(25-27)' }, { kind: 'range', sign: '+', min: 33, max: 35, raw: '+(33-35)' }], tier: '2', level: 1, weight: 1, affix_type: 'Advanced Affix' },
        { modifier_id: '252181602', raw_text: '+(#) % additional damage for Main-Hand Weapons', expression: '+(#) % additional damage for Main-Hand Weapons', condition: null, affix_kind: 'numeric', numeric_values: [{ kind: 'range', sign: '+', min: 10, max: 15, raw: '+(10-15)' }], tier: '2', level: 1, weight: 1, affix_type: 'Ultimate Affix' },
        { modifier_id: '252180102', raw_text: '+(#) % Cold Resistance', expression: '+(#) % Cold Resistance', condition: null, affix_kind: 'numeric', numeric_values: [{ kind: 'range', sign: '+', min: 16, max: 19, raw: '+(16-19)' }], tier: '2', level: 1, weight: 1, affix_type: 'Basic Affix' },
      ],
    } as Graft
    const character = {
      dumpNumber: 1,
      characterName: null,
      level: 98,
      heroId: 1800,
      heroPurchaseId: 18001,
      truncatedSections: [],
      gear: [{
        baseId: 380009,
        itemLevel: 89,
        equippedSlot: 7,
        uniqueItemId: null,
        baseAttrAffixIds: ['800000'],
        baseAffixIds: ['172103200'],
        prefixes: [
          { id: '251471001', source: '16', values: [2, -3] },
          { id: '251181602', source: '15', values: [41] },
          { id: '251181802', source: '15', values: [25, 35] },
        ],
        suffixes: [
          { id: '252181602', source: '16', values: [13] },
          { id: '252180102', source: '15', values: [18] },
          { id: '51533751', source: '17', values: [1, 3] },
        ],
        chipAffixes: [],
        enchantAffixes: [],
        corroded: false,
      }],
      skills: [],
    }
    const dawnBreak = {
      item_id: 'dawn_break', name: 'Dawn Break', game_id: 113337, base_type: 'Ring', required_level: 1,
      drop_level: null, flavor_text: null, drop_sources: [], glossary: {}, random_affixes: {},
      variants: { default: { implicits: [], explicits: [{
        raw_text: '+(#) % additional damage per (#) Fervor Rating', modifier_id: '51533751',
        expression: '+(#) % additional damage per (#) Fervor Rating', condition: null, affix_kind: 'numeric',
        numeric_values: [{ kind: 'range', sign: '+', min: 2, max: 3, raw: '+(2-3)' }, { kind: 'fixed', sign: '+', value: 1, raw: '+1' }],
      }] } },
    } as unknown as LegendaryGearItem
    const { build, warnings } = createUeLogBuild(character, [graft], [dawnBreak])
    expect(build.gear).toHaveLength(1)
    expect(build.gear?.[0]).toMatchObject({ item_id: 'vorax_limb_digits', slot: 'ring2', is_vorax: true, legendary_source: 'Dawn Break', legendary_affix_count: 1 })
    expect(build.gear?.[0].affixes.map(affix => affix.modifier_id)).toEqual(['800000', '172103200', '251471001', '251181602', '251181802', '252181602', '252180102', '51533751'])
    expect(build.gear?.[0].customizations).toEqual([
      { affix_index: 2, chosen_values: { 0: 2, 1: -3 }, chosen_placeholder_key: null },
      { affix_index: 3, chosen_values: { 0: 41 }, chosen_placeholder_key: null },
      { affix_index: 4, chosen_values: { 0: 25, 1: 35 }, chosen_placeholder_key: null },
      { affix_index: 5, chosen_values: { 0: 13 }, chosen_placeholder_key: null },
      { affix_index: 6, chosen_values: { 0: 18 }, chosen_placeholder_key: null },
      { affix_index: 7, chosen_values: { 0: 1, 1: 3 }, chosen_placeholder_key: null },
    ])
    expect(build.gear?.[0].craft_slot_positions).toEqual([2, 3, 4, 5, 6, 7])
    expect(warnings).not.toContain('Vorax Limb: Digits: base affix 172103200 is not in the current Builder catalogs and was left out.')
    expect(build.characterLevel).toBe(98)
  })

  it('maps ordinary gear by game_id and applies logged modifier_id rolls', () => {
    const character = {
      dumpNumber: 1,
      characterName: null,
      level: 98,
      heroId: 1800,
      heroPurchaseId: null,
      truncatedSections: [],
      gear: [{
        baseId: 3600,
        itemLevel: 89,
        equippedSlot: 1,
        uniqueItemId: 0,
        baseAttrAffixIds: ['580000'],
        baseAffixIds: [],
        prefixes: [{ id: '104210001', source: '10', values: [90] }],
        suffixes: [],
        chipAffixes: [{ id: '160419009', source: null, values: [20] }],
        enchantAffixes: [],
        corroded: false,
      }],
      skills: [],
    }
    const baseItems = [{ item_id: 'str_helmet', name: 'STR Helmet', base_items: [{
      name: "Brute's Helm", game_id: 3600, implicit_modifier_ids: ['580000'], required_level: 1,
      armor: null, implicits: ['+168 Gear Armor'],
    }] }] as CraftBaseItemGroup[]
    const craftTypes = [{ item_id: 'str_helmet', name: 'STR Helmet', base_items: [], affixes: [{
      modifier_id: '104210001', raw_text: '+(#) Max Life', expression: '+(#) Max Life', condition: null,
      affix_kind: 'numeric', numeric_values: [{ kind: 'fixed', sign: '+', value: 1, raw: '+1' }],
      source: 'STR Helmet', affix_type: 'Basic Pre-fix', tier: '1',
    }] }] as unknown as CraftBaseType[]

    const result = createUeLogBuild(character, [], [], baseItems, craftTypes, [
      { affix: '+20 % additional damage on Critical Strike Intermediate Sequence 1|2|5', source: 'Bow', modifier_id: '160419009' },
    ])

    expect(result.build.gear).toHaveLength(1)
    expect(result.build.gear?.[0]).toMatchObject({
      item_id: 'brute_s_helm', name: "Brute's Helm (Crafted)", base_type: "Brute's Helm",
      required_level: 1, slot: 'helmet', is_crafted: true, implicit_count: 1,
      craft_slot_positions: [2],
    })
    expect(result.build.gear?.[0].affixes.map(affix => affix.modifier_id)).toEqual(['580000', '104210001'])
    expect(result.build.gear?.[0].customizations).toEqual([
      { affix_index: 1, chosen_values: { 0: 90 }, chosen_placeholder_key: null },
    ])
    expect(result.build.gear?.[0].towerSequence).toBe('+20 % additional damage on Critical Strike Intermediate Sequence 1|2|5')
    const unmatched = createUeLogBuild({ ...character, gear: [{ ...character.gear[0], chipAffixes: [{ id: '160419013', source: null, values: [20] }] }] }, [], [], baseItems, craftTypes, [
      { affix: '+20 % additional damage on Critical Strike Intermediate Sequence 1|2|5', source: 'Bow', modifier_id: '160419009' },
    ])
    expect(unmatched.warnings).toContain("Brute's Helm (Crafted): chip affix 160419013 is not in the current Builder Tower Sequence catalog and was left out.")
    expect(result.warnings).not.toContain("Brute's Helm: chip affix 160419013 is not in the current Builder catalogs and was left out.")
  })

  it('resolves unique gear by game_id when its base item is not in the craft list', () => {
    const unique = {
      item_id: 'omniscient_prototype', name: 'Omniscient Prototype', game_id: 112145, base_type: 'Divine Body',
      required_level: 1, drop_level: null, flavor_text: null, drop_sources: [], glossary: {}, random_affixes: {},
      variants: {
        base: { implicits: [], explicits: [] },
        corroded: { implicits: [], explicits: [{
          raw_text: '+(#) Gear Armor', modifier_id: '45100001', expression: '+(#) Gear Armor', condition: null,
          affix_kind: 'numeric', numeric_values: [{ kind: 'fixed', sign: '+', value: 1, raw: '+1' }],
        }] },
      },
    } as unknown as LegendaryGearItem
    const character = {
      dumpNumber: 1, characterName: null, level: 54, heroId: 1800, heroPurchaseId: null,
      truncatedSections: [], skills: [], gear: [{
        baseId: 3299, itemLevel: 54, equippedSlot: 4, uniqueItemId: 112145,
        baseAttrAffixIds: [], baseAffixIds: [], prefixes: [],
        suffixes: [{ id: '45100001', source: '6', values: [5] }],
        chipAffixes: [], enchantAffixes: [], corroded: true,
      }],
    }

    const result = createUeLogBuild(character, [], [unique])

    expect(result.build.gear?.[0]).toMatchObject({
      item_id: 'omniscient_prototype', name: 'Omniscient Prototype', base_type: 'Divine Body',
      slot: 'chest', implicit_count: 0, craft_slot_positions: [5],
    })
    expect(result.build.gear?.[0].affixes.map(affix => affix.modifier_id)).toEqual(['45100001'])
    expect(result.build.gear?.[0].customizations).toEqual([
      { affix_index: 0, chosen_values: { 0: 5 }, chosen_placeholder_key: null },
    ])
  })

  it('maps unique affixes across TLIDB variants and keeps the base item implicit by modifier_id', () => {
    const unique = {
      item_id: 'deaths_touch', name: "Death's Touch", game_id: 112346, base_type: "Ranger's Rusted Gauntlets",
      required_level: 58, drop_level: 58, flavor_text: null, drop_sources: [], glossary: {},
      random_affixes: { base: [{ placeholder: '<A Random Critical Strike or Weapon Damage Affix>', options: [
        { raw_text: '+(#) Critical Strike Damage', modifier_id: '51434661', expression: '+(#) Critical Strike Damage', condition: null, affix_kind: 'numeric', numeric_values: [] },
      ] }] },
      variants: {
        base: { implicits: [], explicits: [
          { raw_text: '+(#) Critical Strike Rating', modifier_id: '51434611', expression: '+(#) Critical Strike Rating', condition: null, affix_kind: 'numeric', numeric_values: [] },
        ] },
        corroded: { implicits: [], explicits: [] },
      },
    } as unknown as LegendaryGearItem
    const baseItems = [{ item_id: 'dex_gloves', name: 'DEX Gloves', base_items: [{
      name: "Ranger's Rusted Gauntlets", game_id: 3311, required_level: 58, armor: null,
      implicit_modifier_ids: ['580011'], implicits: ['+1920 Gear Armor'],
    }] }] as CraftBaseItemGroup[]
    const character = {
      dumpNumber: 1, characterName: null, level: 98, heroId: 1800, heroPurchaseId: null,
      truncatedSections: [], skills: [], gear: [{
        baseId: 3311, itemLevel: 58, equippedSlot: 9, uniqueItemId: 112346,
        baseAttrAffixIds: ['580011'], baseAffixIds: [], prefixes: [{ id: '51434611', source: null, values: [263] }],
        suffixes: [{ id: '51434661', source: null, values: [86] }], chipAffixes: [], enchantAffixes: [], corroded: true,
      }],
    }

    const result = createUeLogBuild(character, [], [unique], baseItems)

    expect(result.build.gear?.[0].affixes.map(affix => affix.modifier_id)).toEqual(['51434611', '51434661', '580011'])
    expect(result.build.gear?.[0].customizations).toEqual([
      { affix_index: 0, chosen_values: { 0: 263 }, chosen_placeholder_key: null },
      { affix_index: 1, chosen_values: { 0: 86 }, chosen_placeholder_key: null },
    ])
    expect(result.warnings).toEqual(['Hero, talents, memories, and other character settings are not imported yet.'])
  })

  it('maps a logged belt enchant on unique gear to the equipped blend talent_id', () => {
    const unique = {
      item_id: 'belt_unique', name: 'Belt Unique', game_id: 104725, base_type: 'Belt',
      required_level: 90, drop_level: 90, flavor_text: null, drop_sources: [], glossary: {},
      variants: { base: { implicits: [], explicits: [] } }, random_affixes: {},
    } as unknown as LegendaryGearItem
    const blends = [{ talent_id: '340002', modifier_id: '3401001', talent_type: 'medium', talent_level: 0,
      talent_name: null, effect_text: 'Restores 3 % of Life on defeat', effect_raw: 'Restores 3 % of Life on defeat' }] as BeltBlend[]
    const character = {
      dumpNumber: 1, characterName: null, level: 98, heroId: 1800, heroPurchaseId: null,
      truncatedSections: [], skills: [], gear: [{
        baseId: 4725, itemLevel: 90, equippedSlot: 8, uniqueItemId: 104725,
        baseAttrAffixIds: [], baseAffixIds: [], prefixes: [], suffixes: [], chipAffixes: [],
        enchantAffixes: [{ id: '3401001', source: '13', values: [] }], corroded: false,
      }],
    }

    const result = createUeLogBuild(character, [], [unique], [], [], [], [], blends)

    expect(result.build.gear?.[0]).toMatchObject({ item_id: 'belt_unique', beltBlend: '340002' })
    expect(result.warnings).toEqual(['Hero, talents, memories, and other character settings are not imported yet.'])
  })

  it('maps a logged belt enchant modifier to the equipped blend talent_id', () => {
    const baseItems = [{ item_id: 'belt', name: 'Belt', base_items: [{
      name: 'Omni-Elixir Notes', game_id: 4725, required_level: 90, armor: null,
      implicit_modifier_ids: [], implicits: [],
    }] }] as CraftBaseItemGroup[]
    const blends = [{ talent_id: '340002', modifier_id: '3401001', talent_type: 'medium', talent_level: 0,
      talent_name: null, effect_text: 'Restores 3 % of Life on defeat', effect_raw: 'Restores 3 % of Life on defeat' }] as BeltBlend[]
    const character = {
      dumpNumber: 1, characterName: null, level: 98, heroId: 1800, heroPurchaseId: null,
      truncatedSections: [], skills: [], gear: [{
        baseId: 4725, itemLevel: 90, equippedSlot: 8, uniqueItemId: null,
        baseAttrAffixIds: [], baseAffixIds: [], prefixes: [], suffixes: [], chipAffixes: [],
        enchantAffixes: [{ id: '3401001', source: '13', values: [] }], corroded: false,
      }],
    }

    const result = createUeLogBuild(character, [], [], baseItems, [{ item_id: 'belt', name: 'Belt', affixes: [], base_items: [] }], [], [], blends)

    expect(result.build.gear?.[0]).toMatchObject({ item_id: 'omni_elixir_notes', beltBlend: '340002' })
    expect(result.warnings).toEqual(['Hero, talents, memories, and other character settings are not imported yet.'])
  })
})
