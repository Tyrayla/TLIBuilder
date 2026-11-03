import { describe, expect, it } from 'vitest'
import { createReadStream } from 'node:fs'
import { Readable } from 'node:stream'
import { scanUeGameLog } from '../importers/ueLog/parse'
import type { UeLogCharacterPreview, UeLogSlate } from '../importers/ueLog/parse'
import { createUeLogBuild, describeUeLogCaptureMerge, groupUeLogCaptures, resolveSlatePlacements } from '../importers/ueLog/toBuild'
import { migrateLegendaryItem } from '../utils/gearItem'
import type { BeltBlend, CraftBaseItemGroup, CraftBaseType, Graft, LegendaryGearItem, PactSpirit, SkillItem, CreatedHeroMemory } from '../api/client'

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
  it('describes how repeated login captures are combined', () => {
    expect(describeUeLogCaptureMerge(2)).toBe(
      'This character has 2 login captures. The latest complete entry provides the slate board; if the slate section is truncated, the earlier slate board is kept. Gear, skills, memories, contracts, and scent bottle slots merge across entries, with later entries replacing earlier slots. Talent allocations and servant inventory are combined; later core talent choices replace earlier choices for the same tree.',
    )
  })

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

  it('does not confuse legacy SP3 IDs with allocated talent-tree nodes', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+SP3Base+TalentTree+1+key [12228]
|+SP3Base+TalentTree+1+value [1]
|+SP3Base+TalentTree+2+key [10409]
|+SP3Base+TalentTree+2+value [2]
----Socket RecvMessage End----`))

    expect(result.characters[0].talentTrees).toEqual([])
  })

  it('records the parent section for list truncation markers', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+bag+dressingTalentBlocks+30+Index [63]
|+31+...
|+ServantInfos+servantData+30+servantId [19330]
|+31+...
----Socket RecvMessage End----`))

    expect(result.characters[0]?.truncatedSections).toEqual([
      '+bag+dressingTalentBlocks+...', '+ServantInfos+...',
    ])
  })

  it('reads allocated genius nodes and careers separately from legacy SP3 talent IDs', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+geniusInfos+info+1+geniusCareerId [12]
|+geniusInfos+info+1+geniusList+1+geniusId [12010100]
|+geniusInfos+info+1+geniusList+1+rank [2]
|+geniusInfos+info+1+geniusList+1+inPrismArea [true]
|+geniusInfos+info+1+geniusList+2+geniusId [12020100]
|+geniusInfos+info+1+geniusList+2+rank [1]
|+SP3Base+TalentTree+1+key [12228]
|+SP3Base+TalentTree+1+value [1]
----Socket RecvMessage End----`))

    expect(result.characters[0].talentTrees).toEqual([{
      careerId: 12,
      allocations: [{ id: '12010100', rank: 2 }, { id: '12020100', rank: 1 }],
      coreTalentSelections: [],
    }])
  })

  it('clears earlier core choices when a complete later genius record has no bonus choices', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+geniusInfos+info+1+geniusCareerId [4]
----Socket RecvMessage End----`))
    const [group] = groupUeLogCaptures([
      { fileNumber: 1, modifiedAt: 100, preview: { ...result.characters[0]!, dumpNumber: 1,
        talentTrees: [{ careerId: 4, allocations: [], coreTalentSelections: ['40001200'] }] } },
      { fileNumber: 2, modifiedAt: 200, preview: { ...result.characters[0]!, dumpNumber: 2 } },
    ])

    expect(group.preview.talentTrees?.[0]?.coreTalentSelections).toEqual([])
  })

  it('omits genius nodes without an explicit positive allocation count', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+geniusInfos+info+1+geniusCareerId [4]
|+geniusInfos+info+1+geniusList+1+geniusId [40010300]
|+geniusInfos+info+1+geniusList+1+point [3]
|+geniusInfos+info+1+geniusList+2+geniusId [40020200]
|+geniusInfos+info+1+geniusList+2+prePointNeed [-1]
|+geniusInfos+info+1+geniusList+2+position+x [2]
|+geniusInfos+info+1+geniusList+2+position+y [2]
----Socket RecvMessage End----`))

    expect(result.characters[0]?.talentTrees).toEqual([{
      careerId: 4, allocations: [{ id: '40010300', rank: 3 }], coreTalentSelections: [],
    }])
  })

  it('reads selected core talents from each genius info and skips Prism replacement talents', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+geniusInfos+info+1+geniusCareerId [4]
|+geniusInfos+info+1+bonusGeniusInfo+1+value+geniusId [40001200]
|+geniusInfos+info+1+bonusGeniusInfo+2+value+geniusId [40002200]
|+geniusInfos+info+1+bonusGeniusInfo+3+value+geniusId [80001400]
|+geniusInfos+info+1+bonusGeniusInfo+3+value+isPrismSkill [true]
----Socket RecvMessage End----`))

    expect(result.characters[0]?.talentTrees).toEqual([{
      careerId: 4, allocations: [], coreTalentSelections: ['40001200', '40002200'],
    }])
  })

  it('reads equipped slate item identity, board index, effects, and prism placement fields', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+bag+dressingTalentBlocks+1+Index [22]
|+bag+dressingTalentBlocks+1+PageId [-4]
|+bag+dressingTalentBlocks+1+Item+BaseId [260504]
|+bag+dressingTalentBlocks+1+Item+ShapeId [1035]
|+bag+dressingTalentBlocks+1+Item+Direction [1]
|+bag+dressingTalentBlocks+1+Item+BaseTalentList+1 [42070500]
|+bag+dressingTalentBlocks+1+Item+EnchantTalentList+1 [43060400]
|+bag+dressingTalentBlocks+1+Item+talentSlotList+1+color [Blue]
|+bag+dressingTalentBlocks+1+Item+talentSlotList+2+talentId [42070500]
|+geniusInfos+info+1+geniusCareerId [12]
|+geniusInfos+info+1+geniusList+1+geniusId [12060300]
|+geniusInfos+info+1+geniusList+1+rank [2]
|+geniusInfos+info+1+geniusList+1+inPrismArea [true]
|+geniusInfos+info+1+prismInfo+geniusId [12060400]
|+geniusInfos+info+1+prismInfo+item+BaseId [360620]
|+geniusInfos+info+1+prismInfo+item+RareValue [3]
|+geniusInfos+info+1+prismInfo+item+Prefix+1+Id [12040001]
|+geniusInfos+info+1+prismInfo+item+BaseAttrAffix+1+Id [12040002]
|+geniusInfos+info+1+prismEffectPositions+1+x [3]
|+geniusInfos+info+1+prismEffectPositions+1+y [6]
|+geniusInfos+info+1+prismGeniusId [80002000]
----Socket RecvMessage End----`))

    expect(result.characters[0].slates).toEqual([{
      index: 22, pageId: -4, baseId: 260504, uniqueItemId: null, shapeId: 1035, direction: 1, rarityValue: null,
      baseTalentIds: ['42070500'], enchantTalentIds: ['43060400'], talentSlots: [
        { color: 'Blue', talentId: null, rarity: null, slotIndex: 0 },
        { color: null, talentId: '42070500', rarity: null, slotIndex: 1 },
      ],
    }])
    expect(result.characters[0].talentTrees?.[0]).toMatchObject({
      careerId: 12,
      prism: {
        anchorTalentId: '12060400', baseId: 360620, rarityValue: 3, uniqueItemId: null,
        prefixAffixes: [{ id: '12040001', source: null, values: [] }],
        baseAttrAffixes: [{ id: '12040002', source: null, values: [] }],
        effectPositions: [{ x: 3, y: 6 }], replacementTalentId: '80002000',
      },
    })
    const trees = [{ name: 'Onslaughter', nodes: [
      { id: 'onslaughter_c5_r3', column: 5, row: 3 },
      { id: 'onslaughter_c5_r2', column: 5, row: 2 },
    ] }]
    const catalog = { season: 'SS14', items: [], base_affixes: [], random_affixes: [], base_affix_modifiers: [{ modifier_id: '12040002', modifier: '+12% Max Life' }], catalog: {
      items: [{ name: 'Ethereal Prism: Miraculous Touch', game_id: 360620, short_name: 'Miraculous Touch', kind: 'ethereal_prism',
        icon_url: '', tags: [], detail: [], rarities: ['rare'], default_rarity: 'rare', tint_when_rare: true,
        implicit: { kind: 'add_choice' }, replace_description: 'Effect' }],
      area_size: [], middle: [], advanced: [], do_not_replace: {}, penalties: [],
    } }
    const imported = createUeLogBuild(result.characters[0]!, [], [], [], [], [], [], [], trees as any, [],
      { etherealPrisms: catalog as any }).build
    expect(imported.slots?.[0]).toMatchObject({ treeName: 'Onslaughter', nodeStates: { onslaughter_c5_r2: 2 } })
    expect(imported.prisms?.[0]).toMatchObject({ anchorCol: 5, anchorRow: 3, boxAllocations: {},
      ethereal: { replacementTalentId: '80002000', implicit: '+12% Max Life' } })
  })

  it('leaves the slate snapshot absent when the log has no bag section', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+player+Name [Sage]
----Socket RecvMessage End----`))

    expect(result.characters[0]).not.toHaveProperty('slates')
  })

  it('retains follower and servant IDs for import auditing', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+player+FollowServant [11230]
|+ServantInfos+servantData+1+servantId [16130]
----Socket RecvMessage End----`))

    expect(result.characters[0].followServantId).toBe(11230)
    expect(result.characters[0].servantIds).toContain(16130)
  })

  it('reads the live memory, hero-trait, and contract field nesting', async () => {
    const result = await scanUeGameLog(chunkedFile(`----Socket RecvMessage STT----GetPlayerData
|+heroCharacterv3OverView+pointOverView+activeId+1 [1800011]
|+heroCharacterv3OverView+pointOverView+activeId+2 [1800022]
|+heroCharacterv3OverView+pointOverView+activeId+3 [1800031]
|+heroCharacterv3OverView+reminiscenceOverView+reminiscence+1+index [1]
|+heroCharacterv3OverView+reminiscenceOverView+reminiscence+1+detail+BaseId [71001]
|+heroCharacterv3OverView+reminiscenceOverView+reminiscence+1+detail+RareValue [4]
|+heroCharacterv3OverView+reminiscenceOverView+reminiscence+1+detail+ReminiscenceLevel [40]
|+heroCharacterv3OverView+reminiscenceOverView+reminiscence+1+detail+BaseAttrAffix+1+Id [403101411]
|+heroCharacterv3OverView+reminiscenceOverView+reminiscence+1+detail+BaseAffix+1+Id [402151902]
|+heroCharacterv3OverView+reminiscenceOverView+reminiscence+1+detail+Suffix+1+Id [402165201]
|+heroCharacterv3OverView+defaultReminis+rarityRequire [3]
|+heroCharacterv3OverView+defaultReminis+typeRequire [3]
|+heroCharacterv3OverView+defaultReminis+affixBoost [-34]
|+heroCharacterv3OverView+defaultReminis+detail+BaseId [71003]
|+heroCharacterv3OverView+defaultReminis+detail+RareValue [3]
|+heroCharacterv3OverView+defaultReminis+detail+ReminiscenceLevel [30]
|+heroCharacterv3OverView+defaultReminis+detail+BaseAffix+1+DynArgs+1 [24.0]
|+heroCharacterv3OverView+defaultReminis+detail+BaseAffix+1+Id [402155802]
|+heroCharacterv3OverView+defaultReminis+detail+Suffix+1+DynArgs+1 [30.0]
|+heroCharacterv3OverView+defaultReminis+detail+Suffix+1+Id [402170202]
|+heroCharacterv3OverView+defaultReminis+detail+BaseAttrAffix+1+DynArgs+1 [19.2]
|+heroCharacterv3OverView+defaultReminis+detail+BaseAttrAffix+1+Id [403113321]
|+ContractInfosV2+ContractDatas+1+areaId [1]
|+ContractInfosV2+ContractDatas+1+servantId [5330]
|+ContractInfosV2+ContractDatas+2+areaId [2]
|+ContractInfosV2+ContractDatas+2+servantId [18230]
|+ContractInfosV2+ContractDatas+3+areaId [3]
|+ContractInfosV2+ContractDatas+3+servantId [19230]
|+ServantInfos+servantData+1+servantId [18230]
|+ServantInfos+servantData+1+starLevel [5]
|+ServantInfos+servantData+2+servantId [19230]
|+customSkillSlots+customSkillSlots+1+id [2]
|+customSkillSlots+customSkillSlots+1+customId [1]
|+customSkillSlots+customSkillSlots+1+state [CustomSlotState_Active]
|+customSkillSlots+customSkillSlots+1+materialSlots+1+key [1]
|+customSkillSlots+customSkillSlots+1+materialSlots+1+value+index [1]
|+customSkillSlots+customSkillSlots+1+materialSlots+1+value+chooseOptionId [1132]
|+customSkillSlots+customSkillSlots+1+materialSlots+2+key [2]
|+customSkillSlots+customSkillSlots+1+materialSlots+2+value+index [2]
|+customSkillSlots+customSkillSlots+1+materialSlots+2+value+chooseOptionId [1232]
|+customSkillSlots+customSkillSlots+1+materialSlots+3+key [3]
|+customSkillSlots+customSkillSlots+1+materialSlots+3+value+index [3]
|+customSkillSlots+customSkillSlots+1+materialSlots+3+value+chooseOptionId [1312]
----Socket RecvMessage End----`))

    expect(result.characters[0].activeTraitIds).toEqual([1800011, 1800022, 1800031])
    expect(result.characters[0].memories).toEqual([{
      slot: 1,
      baseId: 71001,
      rarityValue: 4,
      level: 40,
      baseAttrAffixes: [{ id: '403101411', source: null, values: [] }],
      fixedAffixes: [{ id: '402151902', source: null, values: [] }],
      randomAffixes: [{ id: '402165201', source: null, values: [] }],
      awakenAffixes: [],
    }])
    expect(result.characters[0].baseMemory).toEqual({
      slot: null,
      baseId: 71003,
      rarityValue: 3,
      level: 30,
      baseAttrAffixes: [{ id: '403113321', source: null, values: [19.2] }],
      fixedAffixes: [{ id: '402155802', source: null, values: [24] }],
      randomAffixes: [{ id: '402170202', source: null, values: [30] }],
      awakenAffixes: [],
      rarityRequire: 3,
      typeRequire: 3,
      affixBoost: -34,
    })
    expect(result.characters[0].pactContracts).toEqual([
      { areaId: 1, servantId: 5330, rank: null },
      { areaId: 2, servantId: 18230, rank: 6 },
      { areaId: 3, servantId: 19230, rank: 1 },
    ])
    expect(result.characters[0].ingredientChoices).toEqual([
      { bottleSlot: 2, materialSlot: 1, optionId: '1132' },
      { bottleSlot: 2, materialSlot: 2, optionId: '1232' },
      { bottleSlot: 2, materialSlot: 3, optionId: '1312' },
    ])
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
    expect(result.characters.some(character => (character.talentTrees?.length ?? 0) > 0)).toBe(true)
    expect(result.characters[0].truncatedSections.length).toBeGreaterThan(0)
    const sage = result.characters.find(character => character.heroId === 1800)
    expect(sage?.ingredientChoices?.map(choice => `${choice.bottleSlot}:${choice.materialSlot}`).sort()).toEqual([
      '2:1', '2:2', '2:3', '3:1', '3:2',
    ])
  })
})

describe('UE_game.log build conversion', () => {
  it('keeps the best-known slate layout when the placement search reaches its limit', () => {
    const result = resolveSlatePlacements([{
      sourceIndex: 0, row: { index: 33 } as UeLogSlate, indexCell: [2, 2],
      layouts: [
        { cells: [[0, 0]], orientationIndex: 0 },
        { cells: [[0, 1]], orientationIndex: 1 },
        { cells: [[1, 0]], orientationIndex: 2 },
      ],
    }], 3)

    expect(result.searchLimitReached).toBe(true)
    expect(result.placements.get(0)).toEqual({ anchor: [2, 2], cells: [[2, 2]], orientationIndex: 0 })
    expect(result.ambiguousPlacements.has(0)).toBe(true)
  })

  it('imports Sage memory rolls and the Licorice Note selections shown by the current log', () => {
    const character = {
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001,
      gear: [], skills: [], truncatedSections: [], activeTraitIds: [1800031, 1800011, 1800022],
      ingredientChoices: [
        { bottleSlot: 2, materialSlot: 1, optionId: '1132' },
        { bottleSlot: 2, materialSlot: 2, optionId: '1232' },
        { bottleSlot: 2, materialSlot: 3, optionId: '1312' },
        { bottleSlot: 3, materialSlot: 1, optionId: '2122' },
        { bottleSlot: 3, materialSlot: 2, optionId: '2231' },
      ],
      memories: [
        { slot: 1, baseId: 71001, rarityValue: 4, level: 40, baseAttrAffixes: [{ id: '403101411', source: null, values: [90] }],
          fixedAffixes: [{ id: '402151902', source: null, values: [23] }, { id: '402153003', source: null, values: [14] }],
          randomAffixes: [{ id: '402165201', source: null, values: [46] }, { id: '402165001', source: null, values: [38] }], awakenAffixes: [] },
        { slot: 2, baseId: 71002, rarityValue: 4, level: 40, baseAttrAffixes: [{ id: '403106411', source: null, values: [330] }],
          fixedAffixes: [{ id: '402154501', source: null, values: [48] }, { id: '402153901', source: null, values: [30] }],
          randomAffixes: [{ id: '402167601', source: null, values: [43] }, { id: '402168401', source: null, values: [80] }], awakenAffixes: [] },
        { slot: 3, baseId: 71003, rarityValue: 4, level: 40, baseAttrAffixes: [{ id: '403113411', source: null, values: [24.7] }],
          fixedAffixes: [{ id: '402156403', source: null, values: [24] }, { id: '402155801', source: null, values: [30] }],
          randomAffixes: [{ id: '402170401', source: null, values: [52] }, { id: '402171001', source: null, values: [80] }],
          awakenAffixes: [{ id: '500101701', source: null, values: [-34] }] },
      ],
      baseMemory: { slot: null, baseId: 71003, rarityValue: 3, level: 30,
        baseAttrAffixes: [{ id: '403113321', source: null, values: [19.2] }],
        fixedAffixes: [{ id: '402155802', source: null, values: [24] }],
        randomAffixes: [{ id: '402170202', source: null, values: [30] }], awakenAffixes: [],
        rarityRequire: 3, typeRequire: 3, affixBoost: -34 },
    }
    const memories = {
      season: 'SS14', memory_types: [], base_stat_scaling: { stats: [] },
      base_stats: [
        { source: 'Memory of Origin', modifier: '+90 Strength', tier: 1 },
        { source: 'Memory of Discipline', modifier: '+330 Max Life', tier: 1 },
        { source: 'Memory of Progress', modifier: '+24.7 % Movement Speed', tier: 9 },
        { source: 'Memory of Progress', modifier: '+19.3 % Movement Speed', tier: 18 },
      ],
      log_base_stats: [
        { log_modifier_id: '403101411', source: 'Memory of Origin', stat_name: 'Strength' },
        { log_modifier_id: '403106411', source: 'Memory of Discipline', stat_name: 'Max Life' },
        { log_modifier_id: '403113411', source: 'Memory of Progress', stat_name: 'Movement Speed' },
        { log_modifier_id: '403113321', source: 'Memory of Progress', stat_name: 'Movement Speed' },
      ],
      fixed_affixes: [
        { modifier_id: '402151902', source: 'Memory of Origin', modifier: '+(20–26) % Critical Strike Damage', tier: 2 },
        { modifier_id: '402153003', source: 'Memory of Origin', modifier: '+(12–18) % Evasion', tier: 3 },
        { modifier_id: '402155802', source: 'Memory of Progress', modifier: '+24 % Projectile Speed', tier: 2 },
      ],
      random_affixes: [
        { modifier_id: '402165201', source: 'Memory of Origin', modifier: '+(43–53) % Physical Skill Critical Strike Damage', tier: 1 },
        { modifier_id: '402165001', source: 'Memory of Origin', modifier: '+(36–44) % attack Critical Strike Damage', tier: 1 },
        { modifier_id: '402170202', source: 'Memory of Progress', modifier: '+(26–34) % attack Critical Strike Damage', tier: 2 },
      ],
    }
    const traits = [{ trait_id: 'licorice_note', hero: 'Sage', variant_name: 'Licorice Note', description: '', levels: [],
      advanced_traits: [
        { name: 'Pungent Stimulant Salt', unlock_level: 45, is_pick_one_from_two: false, effects: [] },
        { name: 'Scent of Ambition', unlock_level: 60, is_pick_one_from_two: true, effects: [] },
        { name: 'Everlasting Nectar', unlock_level: 75, is_pick_one_from_two: true, effects: [] },
      ], ingredients: [
        { trait_name: 'Licorice Note', categories: [
          { category: 'Damage Ingredient', items: [{ name: 'Razor Leaf', effect: '' }, { name: 'Twinspine Flower', effect: '' }, { name: 'Scattered Spore', effect: '' }] },
          { category: 'Defense Ingredient', items: [{ name: 'Resilient Moss', effect: '' }, { name: 'Spectral Stamen', effect: '' }, { name: 'Prismatic Vine', effect: '' }] },
        ] },
        { trait_name: 'Pungent Stimulant Salt', categories: [
          { category: 'Functional Ingredient', items: [{ name: 'Husk', effect: '' }, { name: 'Sword Lily Leaf', effect: '' }, { name: 'Tumbleweed Seed', effect: '' }] },
        ] },
        { trait_name: 'Licorice Tincture Blend', categories: [
          { category: 'Special Ingredient', items: [{ name: 'Pixie Tear', effect: '' }, { name: 'Thunder Dragon Scale', effect: '' }, { name: 'Gargoyle Horn', effect: '' }] },
        ] },
      ] }]
    const revivalAffixes = [{ source: 'Memory Revival',
      modifier: 'Base Traits now have Base Trait slots that can be installed with a Rare or lower Progress Memory. Base Stats and the value of Random Affixes of the Memory installed in this slot: (-35–-30) %',
      tier: null, tier_known: false }]

    const { build, warnings } = createUeLogBuild(character, [], [], [], [], [], [], [], [], [], { memories, traits, revivalAffixes } as any)

    expect(build.traitId).toBe('licorice_note')
    expect(build.advancedTraitSelections).toEqual(['Scent of Ambition', 'Everlasting Nectar'])
    expect(build.elixirIngredients).toEqual({ 2: {
      'Damage Ingredient': 'Scattered Spore',
      'Defense Ingredient': 'Prismatic Vine',
      'Functional Ingredient': 'Husk',
    }, 3: {
      'Special Ingredient': 'Thunder Dragon Scale',
      'Functional Ingredient': 'Tumbleweed Seed',
    } })
    expect(build.traitSlotLevels).toEqual([2, 2, 2, 2])
    expect(build.heroMemories?.[0]).toMatchObject({
      memoryType: 'origin', rarity: 'epic', level: 40,
      baseStat: { modifier: '+90 Strength', tier: 1, rolledValue: null },
      fixedAffixes: [
        { modifier: '+(20–26) % Critical Strike Damage', tier: 2, rolledValue: 23 },
        { modifier: '+(12–18) % Evasion', tier: 3, rolledValue: 14 },
      ],
      randomAffixes: [
        { modifier: '+(43–53) % Physical Skill Critical Strike Damage', tier: 1, rolledValue: 46 },
        { modifier: '+(36–44) % attack Critical Strike Damage', tier: 1, rolledValue: 38 },
      ],
    })
    expect(build.heroMemories?.[1]).toMatchObject({
      memoryType: 'discipline', baseStat: { modifier: '+330 Max Life', tier: 1, rolledValue: null },
    })
    expect(build.heroMemories?.[2]).toMatchObject({
      memoryType: 'progress', baseStat: { modifier: '+24.7 % Movement Speed', tier: 9, rolledValue: null },
    })
    expect(build.baseMemory).toMatchObject({
      memoryType: 'progress', rarity: 'rare', level: 30,
      baseStat: { modifier: '+19.2 % Movement Speed', tier: 18, rolledValue: null },
      fixedAffixes: [{ modifier: '+24 % Projectile Speed', tier: 2, rolledValue: 24 }, null],
      randomAffixes: [{ modifier: '+(26–34) % attack Critical Strike Damage', tier: 2, rolledValue: 30 }, null],
    })
    expect(build.heroMemories?.[2]).toMatchObject({ revived: true, revivalMod: {
      modifier: revivalAffixes[0].modifier, tierKnown: false, rolledValue: -34,
    } })
    expect(warnings.some(w => /base stat/i.test(w))).toBe(false)
  })

  it('matches log-only memory affix IDs through the TLIDB UUID crosswalk', () => {
    const uuid = 'fb9a7ce9-d199-5093-ad56-dc400b786e55'
    const result = createUeLogBuild({
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [], memories: [{ slot: 1, baseId: 71001, rarityValue: 3, level: 40,
        baseAttrAffixes: [{ id: '403101411', source: null, values: [90] }],
        fixedAffixes: [{ id: '402151902', source: null, values: [23] }], randomAffixes: [], awakenAffixes: [],
      }],
    }, [], [], [], [], [], [], [], [], [], { memories: {
      memory_types: [], base_stat_scaling: { stats: [] },
      base_stats: [{ source: 'Memory of Origin', modifier: '+90 Strength', tier: 1 }],
      fixed_affixes: [{ uuid, source: 'Memory of Origin', modifier: '+(20?26) % Critical Strike Damage', tier: 2 }],
      random_affixes: [],
      log_base_stats: [{ log_modifier_id: '403101411', source: 'Memory of Origin', stat_name: 'Strength' }],
      log_affixes: [{ log_modifier_id: '402151902', source: 'Memory of Origin', group: 'fixed_affixes', affix_uuid: uuid }],
    } } as any)
    expect((result.build.heroMemories?.[0] as CreatedHeroMemory).fixedAffixes[0]).toEqual({
      modifier: '+(20?26) % Critical Strike Damage', tier: 2, rolledValue: 23,
    })
    expect(result.warnings.some(warning => warning.includes('logged memory affix'))).toBe(false)
  })

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
      { fileNumber: 2, preview: { dumpNumber: 1, characterName: 'sage', level: 98, heroId: 1800, heroPurchaseId: null, gear: [], skills: [], followServantId: null, servantIds: [], truncatedSections: [] }, loginCount: 2 },
      { fileNumber: 3, preview: { dumpNumber: 1, characterName: 'Other', level: 90, heroId: 1800, heroPurchaseId: null, gear: [], skills: [], followServantId: null, servantIds: [], truncatedSections: [] }, loginCount: 1 },
    ])
  })

  it('uses the latest core talent choices for a tree when captures disagree', () => {
    const capture = (dumpNumber: number, modifiedAt: number, coreTalentSelections: string[]) => ({
      fileNumber: dumpNumber,
      modifiedAt,
      preview: { dumpNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null, gear: [], skills: [],
        talentTrees: [{ careerId: 4, allocations: [], coreTalentSelections }], truncatedSections: [] },
    })
    const [group] = groupUeLogCaptures([capture(1, 100, ['40001200']), capture(2, 200, ['40002200'])])

    expect(group.preview.talentTrees).toEqual([{ careerId: 4, allocations: [], coreTalentSelections: ['40002200'] }])
  })

  it('uses the latest slate board snapshot instead of retaining removed slates', () => {
    const slate = { index: 13, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 1,
      rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }
    const capture = (dumpNumber: number, modifiedAt: number, slates?: typeof slate[]) => ({
      fileNumber: dumpNumber,
      modifiedAt,
      preview: { dumpNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null, gear: [], skills: [],
        ...(slates === undefined ? {} : { slates }), truncatedSections: [] },
    })
    const [group] = groupUeLogCaptures([capture(1, 100, [slate]), capture(2, 200, [])])

    expect(group.preview.slates).toEqual([])
  })

  it('keeps the latest available slate snapshot when a later capture omits the bag section', () => {
    const slate = { index: 13, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 1,
      rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }
    const capture = (dumpNumber: number, modifiedAt: number, slates?: typeof slate[]) => ({
      fileNumber: dumpNumber,
      modifiedAt,
      preview: { dumpNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null, gear: [], skills: [],
        ...(slates === undefined ? {} : { slates }), truncatedSections: [] },
    })
    const [group] = groupUeLogCaptures([capture(1, 100, [slate]), capture(2, 200)])

    expect(group.preview.slates).toEqual([slate])
  })

  it('keeps the earlier slate board when a truncated later capture has no slate entries', () => {
    const slate = { index: 13, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 1,
      rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }
    const capture = (dumpNumber: number, modifiedAt: number, slates: typeof slate[], truncatedSections: string[]) => ({
      fileNumber: dumpNumber,
      modifiedAt,
      preview: { dumpNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null, gear: [], skills: [], slates, truncatedSections },
    })
    const [group] = groupUeLogCaptures([capture(1, 100, [slate], []), capture(2, 200, [], ['+bag+dressingTalentBlocks+...'])])

    expect(group.preview.slates).toEqual([slate])
  })

  it('does not replace a full slate board with a partial truncated slate list', () => {
    const slate = { index: 13, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 1,
      rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }
    const partialSlate = { ...slate, index: 24 }
    const capture = (dumpNumber: number, modifiedAt: number, slates: typeof slate[], truncatedSections: string[]) => ({
      fileNumber: dumpNumber, modifiedAt,
      preview: { dumpNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
        gear: [], skills: [], slates, truncatedSections },
    })
    const [group] = groupUeLogCaptures([
      capture(1, 100, [slate], []), capture(2, 200, [partialSlate], ['+bag+dressingTalentBlocks+...']),
    ])

    expect(group.preview.slates).toEqual([slate])
  })

  it('does not let truncation in an unrelated section preserve stale slates or talents', () => {
    const slate = { index: 13, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 1,
      rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }
    const capture = (dumpNumber: number, modifiedAt: number, preview: Partial<UeLogCharacterPreview>) => ({
      fileNumber: dumpNumber, modifiedAt,
      preview: { dumpNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
        gear: [], skills: [], truncatedSections: [], ...preview },
    })
    const [group] = groupUeLogCaptures([
      capture(1, 100, { slates: [slate], talentTrees: [{ careerId: 12, allocations: [],
        coreTalentSelections: ['12010100'], prism: { anchorTalentId: '12060400', baseId: 360620, uniqueItemId: null,
          rarityValue: 3, prefixAffixes: [], baseAffixes: [], baseAttrAffixes: [], effectPositions: [], replacementTalentId: null } }] }),
      capture(2, 200, { slates: [], talentTrees: [{ careerId: 12, allocations: [], coreTalentSelections: [] }],
        truncatedSections: ['+ServantInfos+servantData+...'] }),
    ])

    expect(group.preview.slates).toEqual([])
    expect(group.preview.talentTrees?.[0]?.coreTalentSelections).toEqual([])
    expect(group.preview.talentTrees?.[0]?.prism).toBeUndefined()
  })

  it('maps logged talent game IDs into Builder tree slots and node states', () => {
    const result = createUeLogBuild({
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001,
      gear: [], skills: [], talentTrees: [{ careerId: 12, allocations: [{ id: '12010100', rank: 2 }] }], truncatedSections: [],
    }, [], [], [], [], [], [], [], [{ name: 'Onslaughter', nodes: [{ id: 'onslaughter_c0_r0', game_id: '12010100' }] }])

    expect(result.build.slots).toEqual([
      { treeName: 'Onslaughter', nodeStates: { onslaughter_c0_r0: 2 } }, null, null, null,
    ])
  })

  it('warns when a logged talent is matched by its inferred grid coordinates', () => {
    const result = createUeLogBuild({
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001,
      gear: [], skills: [], talentTrees: [{ careerId: 12, allocations: [{ id: '12010200', rank: 1 }] }], truncatedSections: [],
    }, [], [], [], [], [], [], [], [{ name: 'Onslaughter', nodes: [{ id: 'onslaughter_c0_r1', column: 0, row: 1 }] }])

    expect(result.build.slots[0]).toEqual({ treeName: 'Onslaughter', nodeStates: { onslaughter_c0_r1: 1 } })
    expect(result.warnings).toContain('1 allocated talent node was matched by inferred grid coordinates; confirm that node in the imported tree.')
  })

  it('does not map unknown talent IDs to coordinates occupied by a different known game ID', () => {
    const result = createUeLogBuild({
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001,
      gear: [], skills: [], talentTrees: [{ careerId: 12, allocations: [{ id: '12010300', rank: 1 }] }], truncatedSections: [],
    }, [], [], [], [], [], [], [], [{ name: 'Onslaughter', nodes: [
      { id: 'onslaughter_c0_r2', game_id: '12010301', column: 0, row: 2 },
   ] }])

    expect(result.build.slots[0]).toBeNull()
    expect(result.warnings).toContain('1 allocated talent node could not be matched to current TLIDB data and was skipped.')
  })

  it('does not use coordinate fallback when the logged career and game ID prefix disagree', () => {
    const result = createUeLogBuild({
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001,
      gear: [], skills: [], talentTrees: [{ careerId: 12, allocations: [{ id: '43010300', rank: 1 }] }], truncatedSections: [],
    }, [], [], [], [], [], [], [], [{ name: 'Onslaughter', nodes: [
      { id: 'onslaughter_c0_r2', column: 0, row: 2 },
    ] }])

    expect(result.build.slots[0]).toBeNull()
    expect(result.warnings).toContain('1 allocated talent node could not be matched to current TLIDB data and was skipped.')
  })

  it('clears an earlier Ethereal Prism when a later capture has the tree but no prism', () => {
    const prism = {
      anchorTalentId: '12060400', baseId: 360620, uniqueItemId: null, rarityValue: 3,
      prefixAffixes: [], baseAffixes: [], baseAttrAffixes: [], effectPositions: [], replacementTalentId: null,
    }
    const capture = (fileNumber: number, modifiedAt: number, talentTrees: NonNullable<UeLogCharacterPreview['talentTrees']>) => ({
      fileNumber, modifiedAt,
      preview: { dumpNumber: fileNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
        gear: [], skills: [], talentTrees, truncatedSections: [] },
    })
    const [group] = groupUeLogCaptures([
      capture(1, 100, [{ careerId: 12, allocations: [], prism }]),
      capture(2, 200, [{ careerId: 12, allocations: [{ id: '12010100', rank: 1 }] }]),
    ])

    expect(group.preview.talentTrees?.[0]?.prism).toBeUndefined()
  })

  it('keeps an earlier Ethereal Prism when a later talent-tree capture is truncated', () => {
    const prism = {
      anchorTalentId: '12060400', baseId: 360620, uniqueItemId: null, rarityValue: 3,
      prefixAffixes: [], baseAffixes: [], baseAttrAffixes: [], effectPositions: [], replacementTalentId: null,
    }
    const capture = (fileNumber: number, modifiedAt: number, talentTrees: NonNullable<UeLogCharacterPreview['talentTrees']>, truncatedSections: string[] = []) => ({
      fileNumber, modifiedAt,
      preview: { dumpNumber: fileNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
        gear: [], skills: [], talentTrees, truncatedSections },
    })
    const [group] = groupUeLogCaptures([
      capture(1, 100, [{ careerId: 12, allocations: [], prism }]),
      capture(2, 200, [{ careerId: 12, allocations: [{ id: '12010100', rank: 1 }] }], ['+geniusInfos+info+1+...']),
    ])

    expect(group.preview.talentTrees?.[0]?.prism).toEqual(prism)
  })

  it('keeps earlier core talent choices when a later talent-tree capture is truncated', () => {
    const capture = (fileNumber: number, modifiedAt: number, coreTalentSelections: string[], truncatedSections: string[] = []) => ({
      fileNumber, modifiedAt,
      preview: { dumpNumber: fileNumber, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
        gear: [], skills: [], talentTrees: [{ careerId: 12, allocations: [], coreTalentSelections }], truncatedSections },
    })
    const [group] = groupUeLogCaptures([
      capture(1, 100, ['12010100', '12020100']),
      capture(2, 200, [], ['+geniusInfos+info+1+...']),
    ])

    expect(group.preview.talentTrees?.[0]?.coreTalentSelections).toEqual(['12010100', '12020100'])
  })

  it('maps logged core talent game IDs to the catalogued Builder slots', () => {
    const result = createUeLogBuild({
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001,
      gear: [], skills: [], talentTrees: [{ careerId: 4, allocations: [], coreTalentSelections: ['40001200', '40002200'] }], truncatedSections: [],
    }, [], [], [], [], [], [], [], [{
      name: 'God of War', nodes: [], core_talent_slots: [
        { options: [{ id: 'god_of_war_blunt', name: 'Blunt', effects: ['+30 % additional Physical Damage', 'Enemies +20 % Injury Buffer (Max Active Divinity: 1)'] }] },
        { options: [{ id: 'god_of_war_gravity', name: 'Gravity', effects: ['+25 % additional Melee Damage', 'Melee Skill has reversed knockback direction (Max Active Divinity: 1)'] }] },
      ],
    }], [], { slatePool: { magic: [], rare: [], legendary: [], core: [
      { key: 'God of War:god_of_war_blunt', game_id: '40001200', treeName: 'God of War', name: 'Blunt', effects: ['+30 % additional Physical Damage', 'Enemies +20 % Injury Buffer (Max Active Divinity: 1)'] },
      { key: 'God of War:god_of_war_gravity', game_id: '40002200', treeName: 'God of War', name: 'Gravity', effects: ['+25 % additional Melee Damage', 'Melee Skill has reversed knockback direction (Max Active Divinity: 1)'] },
    ] } })

    expect(result.build.slots[0]).toEqual({
      treeName: 'God of War', nodeStates: {}, coreTalentSelections: { '0': 'god_of_war_blunt', '1': 'god_of_war_gravity' },
    })
    expect(result.warnings).toEqual([])
  })

  it('imports slate effects and Ethereal Prism item and placement by canonical game IDs', () => {
    const character: UeLogCharacterPreview = {
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [],
      slates: [{ index: 31, pageId: -4, baseId: 260504, uniqueItemId: null, shapeId: 1035, direction: 1,
        rarityValue: 3, baseTalentIds: ['43060400'], enchantTalentIds: [], talentSlots: [] }],
      talentTrees: [{ careerId: 12, allocations: [{ id: '12060300', rank: 2 }], prism: {
        anchorTalentId: '12060400', baseId: 360620, uniqueItemId: null, rarityValue: 3,
        prefixAffixes: [{ id: '12040001', source: null, values: [] }], baseAffixes: [],
        baseAttrAffixes: [],
        effectPositions: [{ x: 3, y: 6 }, { x: 5, y: 7 }], replacementTalentId: '80002000',
      } }],
    }
    const trees = [
      { name: 'Ranger', nodes: [{ id: 'ranger_c3_r4', game_id: '43060400', column: 3, row: 4, node_type: 'Medium Talent', effects: ['+18 % Melee Damage'] }] },
      { name: 'Onslaughter', nodes: [
        { id: 'onslaughter_c5_r3', game_id: '12060400', column: 5, row: 3, node_type: 'Medium Talent', effects: ['+8 % Damage'] },
        { id: 'onslaughter_c5_r2', column: 5, row: 2, node_type: 'Micro Talent', effects: ['+9 % Damage'] },
      ] },
    ]
    const etherealPrisms = {
      season: 'SS14', items: [], base_affixes: [], random_affixes: [],
      base_affix_modifiers: [],
      catalog: {
        items: [{ name: 'Ethereal Prism: Miraculous Touch', game_id: 360620, short_name: 'Miraculous Touch', kind: 'ethereal_prism' as const,
          icon_url: 'test-prism.webp', tags: [], detail: [], rarities: ['rare', 'legendary'] as ('rare' | 'legendary')[],
          default_rarity: 'legendary' as const, tint_when_rare: true,
          implicit: { kind: 'replace' as const, text: 'Replaces the Core Talent with Miraculous Touch' }, replace_description: 'Effect' }],
        area_size: [{ modifier: 'Effect Area expands to 3 x 2', modifier_id: '12040001', cols: 3, rows: 2 }],
        middle: [], advanced: [], do_not_replace: {}, penalties: [],
      },
    }

    const slatePool = { magic: [], rare: [{ nodeId: 'ranger_c3_r4', game_id: '43060400', treeName: 'Ranger', nodeType: 'Medium Talent', effects: ['+18 % Melee Damage'] }], legendary: [], core: [{ key: 'Nether King:Core Option', game_id: '90000061',
      treeName: 'Nether King', name: 'Nether King Core Option', effects: ['+12 % Damage'] }] }
    const { build, warnings } = createUeLogBuild(character, [], [], [], [], [], [], [], trees, [], { etherealPrisms, slatePool } as any)

    expect(build.slates?.[0]).toMatchObject({ kind: 'base', shapeIndex: 1, orientationIndex: 1, anchor: [0, 2],
      cells: [[0, 2], [0, 3], [1, 2], [2, 2]] })
    expect(build.slates?.[0]?.slots).toHaveLength(5)
    expect(build.slates?.[0]?.slots[0]).toMatchObject({ selectedNodeId: 'ranger_c3_r4', effects: ['+18 % Melee Damage'], nodeType: 'Medium Talent' })
    expect(build.prisms?.[0]).toMatchObject({ kind: 'ethereal_prism', name: 'Ethereal Prism: Miraculous Touch',
      treeName: 'Onslaughter', anchorCol: 5, anchorRow: 3,
      ethereal: { shortName: 'Miraculous Touch', rarity: 'rare', areaSize: 'Effect Area expands to 3 x 2', boxCols: 2, boxRows: 3,
        replacementTalentId: '80002000' },
      boxAllocations: {} })
    expect(warnings).toContain('Ethereal Prism: Miraculous Touch: logged area spans 2 columns by 3 rows, but the matched modifier says 3 by 2; imported area follows the logged cells.')
    const withImplicitRoll: UeLogCharacterPreview = { ...character, talentTrees: character.talentTrees?.map(tree => ({
      ...tree, prism: tree.prism ? { ...tree.prism, baseAffixes: [{ id: 'logged-implicit', source: null, values: [12] }] } : undefined,
    })) }
    const rolled = createUeLogBuild(withImplicitRoll, [], [], [], [], [], [], [], trees, [], { etherealPrisms, slatePool } as any)
    expect(rolled.warnings).toContain('Ethereal Prism: Miraculous Touch: logged prism implicit roll values are not stored by the current Builder prism configuration.')

    const withoutPositions: UeLogCharacterPreview = { ...character, talentTrees: character.talentTrees?.map(tree => ({
      ...tree, prism: tree.prism ? { ...tree.prism, effectPositions: [] } : undefined,
    })) }
    const missingAreaCells = createUeLogBuild(withoutPositions, [], [], [], [], [], [], [], trees, [], { etherealPrisms, slatePool } as any)
    expect(missingAreaCells.warnings).toContain('Ethereal Prism: Miraculous Touch: no prism area cells were logged; imported area uses the matched 3 by 2 modifier.')
    expect(missingAreaCells.warnings.some(warning => warning.includes('undefined columns'))).toBe(false)

    const unverifiedRarity = createUeLogBuild({
      ...character,
      talentTrees: character.talentTrees?.map(tree => tree.prism ? { ...tree, prism: { ...tree.prism, rarityValue: 4 } } : tree),
    }, [], [], [], [], [], [], [], trees, [], {
      etherealPrisms: { ...etherealPrisms, catalog: { ...etherealPrisms.catalog,
        items: etherealPrisms.catalog.items.map(prism => ({ ...prism, default_rarity: 'rare' as const })) } },
      slatePool,
    } as any)
    expect(unverifiedRarity.build.prisms?.[0]?.ethereal?.rarity).toBe('rare')
    expect(unverifiedRarity.warnings).toContain('Ethereal Prism: Miraculous Touch: logged prism rarity 4 has no verified mapping; the catalog default was used.')
  })

  it('keeps slate talent IDs in their logged slot when earlier slots are empty', () => {
    const character: UeLogCharacterPreview = {
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [], talentTrees: [],
      slates: [{ index: 22, pageId: -4, baseId: 260504, uniqueItemId: null, shapeId: 1035, direction: 1,
        rarityValue: 3, baseTalentIds: [], enchantTalentIds: [], talentSlots: [
          { color: 'Blue', talentId: null, rarity: null, slotIndex: 0 },
          { color: null, talentId: '42070500', rarity: null, slotIndex: 1 },
        ] }],
    }
    const trees = [{ name: 'Ranger', nodes: [{ id: 'ranger_c3_r4', game_id: '42070500', node_type: 'Medium Talent', effects: ['+18 % Melee Damage'] }] }]
    const slatePool = { magic: [], rare: [{ nodeId: 'ranger_c3_r4', game_id: '42070500', treeName: 'Ranger', nodeType: 'Medium Talent', effects: ['+18 % Melee Damage'] }], legendary: [], core: [] }
    const { build } = createUeLogBuild(character, [], [], [], [], [], [], [], trees, [], { slatePool } as any)

    expect(build.slates?.[0]?.slots[0]?.selectedNodeId).toBeNull()
    expect(build.slates?.[0]?.slots[1]).toMatchObject({ selectedNodeId: 'ranger_c3_r4', effects: ['+18 % Melee Damage'] })
  })

  it('clears the core flag when a regular talent fills a core-eligible slate slot', () => {
    const character: UeLogCharacterPreview = {
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [], talentTrees: [],
      slates: [{ index: 52, pageId: -4, baseId: 394004, uniqueItemId: null, shapeId: 1035, direction: 1,
        rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [
          { color: 'Blue', talentId: '42070500', rarity: null, slotIndex: 0 },
        ] }],
    }
    const trees = [{ name: 'Nether King', nodes: [{ id: 'nether_king_fixed_1', game_id: '42070500', node_type: 'Legendary Medium Nether King Talent Node', effects: ['+18 % Melee Damage'] }] }]
    const slatePool = { magic: [], rare: [], legendary: [], core: [] }
    const { build } = createUeLogBuild(character, [], [], [], [], [], [], [], trees, [], { slatePool } as any)

    expect(build.slates?.[0]?.slots[0]).toMatchObject({ canBeCore: true, isCore: false, selectedNodeId: 'nether_king_fixed_1' })
  })

  it('preserves a branded node when the log does not identify its Nether King variant', () => {
    const character: UeLogCharacterPreview = {
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [], talentTrees: [],
      slates: [{ index: 52, pageId: -4, baseId: 394004, uniqueItemId: 0, shapeId: null, direction: null,
        rarityValue: 4, baseTalentIds: [], enchantTalentIds: [], talentSlots: [
          { color: null, talentId: '90000062', rarity: null, slotIndex: 2 },
        ] }],
    }
    const slatePool = { magic: [], rare: [], legendary: [], core: [{ key: 'Nether King:Contamination Brand', game_id: '90000062',
      treeName: 'Nether King', nodeType: 'Ultimate Nether King Talent Node', name: 'Contamination Brand',
      effects: ['When Contamination is active, +12% Projection Effect'] }] }
    const { build, warnings } = createUeLogBuild(character, [], [], [], [], [], [], [], [], [], { slatePool } as any)

    expect(build.slates?.[0]?.slots[2]).toMatchObject({ selectedCoreKey: 'Nether King:Contamination Brand', isCore: true,
      effects: ['When Contamination is active, +12% Projection Effect'] })
    expect(build.slates?.[0]?.netherKingVariant).toBe('contamination')
    expect(build.slates?.[0]?.cells).toEqual([[1, 4], [2, 4], [3, 4]])
    expect(warnings).not.toContain("Nether King's Divinity at board index 52: the log does not identify its variant; imported as Judgment. Confirm the variant and board placement.")
  })

  it('imports Banishment with its diagonal footprint when a branded node identifies the variant', () => {
    const character: UeLogCharacterPreview = {
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [], talentTrees: [],
      slates: [{ index: 52, pageId: -4, baseId: 394004, uniqueItemId: 0, shapeId: null, direction: null,
        rarityValue: 4, baseTalentIds: [], enchantTalentIds: [], talentSlots: [
          { color: null, talentId: '90000117', rarity: null, slotIndex: 2 },
        ] }],
    }
    const slatePool = { magic: [], rare: [], legendary: [], core: [{ key: 'Nether King:Banishment Brand', game_id: '90000117',
      treeName: 'Nether King', nodeType: 'Ultimate Nether King Talent Node', name: 'Banishment Brand',
      effects: ['When Banishment is active, +12% damage'] }] }
    const { build } = createUeLogBuild(character, [], [], [], [], [], [], [], [], [], { slatePool } as any)

    expect(build.slates?.[0]).toMatchObject({
      netherKingVariant: 'banishment', anchor: [1, 2], orientationIndex: 0,
      cells: [[1, 4], [2, 3], [3, 2]],
    })
  })

  it('maps known unique slate IDs to the Builder slate kinds', () => {
    for (const [uniqueItemId, kind] of [[1003, 'fallen_starlight'], [1005, 'corner_of_divinity']] as const) {
      const { build, warnings } = createUeLogBuild({
        dumpNumber: 1, characterName: 'Slate', level: 1, heroId: null, heroPurchaseId: null,
        gear: [], skills: [], truncatedSections: [],
        slates: [{ index: 13, pageId: -4, baseId: 261003, uniqueItemId, shapeId: 2020, direction: 1,
          rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }],
      }, [], [])
      expect(build.slates?.[0]?.kind).toBe(kind)
      if (kind === 'corner_of_divinity') {
        expect(warnings).toContain('A Corner of Divinity at board index 13: its direction mapping is inferred from other unique slates; confirm its orientation.')
      } else expect(warnings).toEqual([])
    }
  })

  it('leaves out unique slates when logged directions exceed verified rotations', () => {
    for (const [uniqueItemId, direction] of [[1003, 3], [1010, 3]] as const) {
      const { build, warnings } = createUeLogBuild({
        dumpNumber: 1, characterName: 'Slate', level: 1, heroId: null, heroPurchaseId: null,
        gear: [], skills: [], truncatedSections: [],
        slates: [{ index: 13, pageId: -4, baseId: 261003, uniqueItemId, shapeId: 2020, direction,
          rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }],
      }, [], [])
      expect(build.slates ?? []).toEqual([])
      expect(warnings).toContain(`Slate ${uniqueItemId}: logged direction ${direction} is outside the verified range and was left out.`)
    }
  })

  it('warns when an empty base slate has no tree association', () => {
    const result = createUeLogBuild({
      dumpNumber: 1, characterName: 'Slate', level: 98, heroId: null, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [],
      slates: [{ index: 31, pageId: -4, baseId: 260599, uniqueItemId: null, shapeId: 1035, direction: 1,
        rarityValue: 3, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }],
    }, [], [])

    expect(result.build.slates?.[0]?.treeType).toBeUndefined()
    expect(result.warnings).toContain('Slate at board index 31: its talent tree could not be identified from the base item or selected talent IDs; choose the tree manually.')
  })

  it('places the owner log slate at index 13 on the left edge', () => {
    const { build } = createUeLogBuild({
      dumpNumber: 1, characterName: 'Slate', level: 98, heroId: null, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [],
      slates: [{ index: 13, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 2,
        rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }],
    }, [], [])

    expect(build.slates).toMatchObject([{
      kind: 'fallen_starlight', orientationIndex: 1, anchor: [2, 0], cells: [[2, 0], [3, 0]],
    }])
  })

  it('keeps individually placeable slates when another logged index cannot fit the board', () => {
    const { build, warnings } = createUeLogBuild({
      dumpNumber: 1, characterName: 'Slate', level: 98, heroId: null, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [],
      slates: [
        { index: 13, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 2,
          rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
        { index: 99, pageId: -4, baseId: 260504, uniqueItemId: null, shapeId: 1035, direction: 1,
          rarityValue: 3, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
      ],
    }, [], [])

    expect(build.slates).toMatchObject([{ kind: 'fallen_starlight', anchor: [2, 0], cells: [[2, 0], [3, 0]] }])
    expect(warnings).toContain('Slate at board index 99: it could not fit with the other logged slates and was left out.')
  })

  it('fits the shape-less Nether King slate from its logged origin cell', () => {
    const { build, warnings } = createUeLogBuild({
      dumpNumber: 1, characterName: 'Slate', level: 98, heroId: null, heroPurchaseId: null,
      gear: [], skills: [], truncatedSections: [],
      slates: [
        { index: 13, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 2, rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
        { index: 32, pageId: -4, baseId: 261010, uniqueItemId: 1010, shapeId: 2090, direction: 1, rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
        { index: 34, pageId: -4, baseId: 260504, uniqueItemId: null, shapeId: 1045, direction: 3, rarityValue: 3, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
        { index: 43, pageId: -4, baseId: 261005, uniqueItemId: 1005, shapeId: 2030, direction: 1, rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
        { index: 45, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 2, rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
        { index: 52, pageId: -4, baseId: 394004, uniqueItemId: 0, shapeId: null, direction: null, rarityValue: 4, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
        { index: 64, pageId: -4, baseId: 261003, uniqueItemId: 1003, shapeId: 2020, direction: 1, rarityValue: 100, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] },
      ],
    }, [], [])

    expect(build.slates?.map(slate => [slate.anchor, slate.cells])).toEqual([
      [[2, 0], [[2, 0], [3, 0]]],
      [[0, 1], [[0, 2], [0, 3], [1, 1], [1, 2], [1, 3], [2, 1], [2, 2]]],
      [[2, 3], [[2, 3], [2, 4], [3, 3]]],
      [[4, 3], [[4, 3], [5, 3]]],
      [[1, 1], [[1, 4], [4, 1], [4, 4]]],
      [[3, 4], [[3, 4], [3, 5]]],
    ])
    expect(build.slates?.find(slate => slate.kind === 'nether_kings_divinity')).toMatchObject({ orientationIndex: 0, treeType: 'Nether King' })
    expect(warnings).not.toContain("Nether King's Divinity: the game log does not include its branded board shape, so it could not be placed.")
    expect(warnings).toContain('Slate 1045: kind or ShapeId is not mapped from observed log data and was left out.')
    expect(warnings).toContain("Nether King's Divinity at board index 52: the log does not identify its variant; imported as Judgment. Confirm the variant and board placement.")
    expect(build.slates?.find(slate => slate.kind === 'nether_kings_divinity')?.netherKingVariant).toBe('judgment')
  })

  it('maps each logged Judgment origin to the same orientation as editor placement', () => {
    const cases = [
      { index: 22, orientationIndex: 1, cells: [[1, 1], [4, 1], [4, 4]] },
      { index: 52, orientationIndex: 0, cells: [[1, 4], [4, 1], [4, 4]] },
      { index: 25, orientationIndex: 2, cells: [[1, 1], [1, 4], [4, 1]] },
      { index: 55, orientationIndex: 3, cells: [[1, 1], [1, 4], [4, 4]] },
    ] as const
    for (const expected of cases) {
      const { build, warnings } = createUeLogBuild({
        dumpNumber: 1, characterName: 'Slate', level: 98, heroId: null, heroPurchaseId: null,
        gear: [], skills: [], truncatedSections: [],
        slates: [{ index: expected.index, pageId: -4, baseId: 394004, uniqueItemId: 0, shapeId: null,
          direction: null, rarityValue: 4, baseTalentIds: [], enchantTalentIds: [], talentSlots: [] }],
      }, [], [])
      expect(build.slates?.[0]).toMatchObject({ orientationIndex: expected.orientationIndex, anchor: [1, 1], cells: expected.cells })
      if (expected.orientationIndex !== 0) {
        expect(warnings).toContain(`Nether King's Divinity at board index ${expected.index}: its Judgment placement is inferred from the occupied cell; review its board position.`)
      }
    }
  })

  it('maps known logged pact game IDs into the three battle slots and warns when rank is missing', () => {
    const character: UeLogCharacterPreview = {
      dumpNumber: 1,
      characterName: 'Sage',
      level: 98,
      heroId: 1800,
      heroPurchaseId: 18001,
      gear: [],
      skills: [],
      pactContracts: [
        { areaId: 1, servantId: 5330, rank: null },
        { areaId: 2, servantId: 18230, rank: 6 },
        { areaId: 3, servantId: 19230, rank: 1 },
        { areaId: 4, servantId: 6330, rank: 2 },
      ],
      truncatedSections: [],
    }
    const catalog = [
      { item_id: 'preserver_of_eternity', game_id: 5330, name: 'Preserver of Eternity' },
      { item_id: 'kitty_express', game_id: 18230, name: 'Kitty Express' },
      { item_id: 'elixir_fairies', game_id: 19230, name: 'Elixir Fairies' },
    ] as PactSpirit[]

    const result = createUeLogBuild(character, [], [], [], [], [], [], [], [], catalog)

    expect(result.build.pactSpirits).toEqual([
      { itemId: 'preserver_of_eternity', rank: 1 },
      { itemId: 'kitty_express', rank: 6 },
      { itemId: 'elixir_fairies', rank: 1 },
    ])
    expect(result.warnings).toEqual(['Preserver of Eternity: the login captures do not include its rank; rank 1 was used.'])
  })

  it('prefers a pact-spirit catalog game ID over the owner-confirmed fallback alias', () => {
    const result = createUeLogBuild({
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001,
      gear: [], skills: [], pactContracts: [{ areaId: 2, servantId: 18230, rank: 6 }], truncatedSections: [],
    }, [], [], [], [], [], [], [], [], [
      { item_id: 'catalog_game_id_entry', game_id: 18230, name: 'Catalog match' },
      { item_id: 'kitty_express', game_id: 18231, name: 'Kitty Express' },
    ] as PactSpirit[])

    expect(result.build.pactSpirits?.[1]).toEqual({ itemId: 'catalog_game_id_entry', rank: 6 })
  })

  it('does not report the cosmetic pet as a missing combat follower', () => {
    const result = createUeLogBuild({
      dumpNumber: 1,
      characterName: null,
      level: 98,
      heroId: 1800,
      heroPurchaseId: null,
      gear: [],
      skills: [],
      followServantId: 11230,
      servantIds: [16130],
      truncatedSections: [],
    }, [], [])

    expect(result.warnings).toEqual([])
  })

  it('warns when the selected login dump contains truncated data', () => {
    const result = createUeLogBuild({
      dumpNumber: 1,
      characterName: null,
      level: 98,
      heroId: 1800,
      heroPurchaseId: null,
      gear: [],
      skills: [],
      truncatedSections: ['TalentTree'],
    }, [], [])

    expect(result.warnings).toEqual([
      'The game log omitted some player data, so slate placement, equipped skill details, or pact spirit ranks may be incomplete.',
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

  it('keeps a spirit rank found in an earlier login when a later capture omits it', () => {
    const capture = (dumpNumber: number, modifiedAt: number, rank: number | null) => ({
      fileNumber: 1,
      modifiedAt,
      preview: {
        dumpNumber,
        characterName: 'Sage',
        level: 98,
        heroId: 1800,
        heroPurchaseId: 18001,
        gear: [],
        skills: [],
        pactContracts: [{ areaId: 1, servantId: 5330, rank }],
        truncatedSections: [],
      },
    })

    const [group] = groupUeLogCaptures([capture(1, 100, 3), capture(2, 200, null)])

    expect(group.preview.pactContracts).toEqual([{ areaId: 1, servantId: 5330, rank: 3 }])
  })

  it('merges gear, talent, and follower data across the same character’s login captures', () => {
    const gear = (equippedSlot: number, baseId: number) => ({
      baseId,
      itemLevel: 89,
      equippedSlot,
      uniqueItemId: 0,
      baseAttrAffixIds: [],
      baseAffixIds: [],
      prefixes: [],
      suffixes: [],
      chipAffixes: [],
      enchantAffixes: [],
      corroded: false,
    })
    const capture = (dumpNumber: number, modifiedAt: number, preview: Partial<UeLogCharacterPreview>) => ({
      fileNumber: 1,
      modifiedAt,
      preview: {
        dumpNumber,
        characterName: 'Sage',
        level: 98,
        heroId: 1800,
        heroPurchaseId: 18001,
        gear: [],
        skills: [],
        truncatedSections: [],
        ...preview,
      },
    })
    const groups = groupUeLogCaptures([
      capture(1, 100, {
        gear: [gear(1, 3611)],
        followServantId: 11230,
        servantIds: [16130],
        truncatedSections: ['TalentTree'],
      }),
      capture(2, 200, {
        gear: [gear(2, 4725)],
        followServantId: 11330,
        servantIds: [18120],
      }),
    ])

    expect(groups[0].preview.gear.map(item => [item.equippedSlot, item.baseId])).toEqual([
      [1, 3611],
      [2, 4725],
    ])
    expect(groups[0].preview.followServantId).toBe(11330)
    expect(groups[0].preview.servantIds).toEqual([16130, 18120])
    expect(groups[0].preview.truncatedSections).toEqual(['TalentTree'])
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
    expect(result.warnings).toContain('Whirlwind: Whirling Blade (Noble): one or more logged support rolls could not be matched; Builder defaults were used.')
  })

  it('compacts passive skill slots and starts their supports at slot one', () => {
    const character = {
      dumpNumber: 1, characterName: null, level: 98, heroId: 1800, heroPurchaseId: null,
      truncatedSections: [], gear: [], skills: [
        { baseId: 7018, logIndex: 1007, level: 20, skillItemLevel: 16, prefixes: [] },
        { baseId: 7746, logIndex: 1008, level: 1, skillItemLevel: 89, prefixes: [] },
      ],
    }
    const catalog = [
      { item_id: 'focus', name: 'Focus', game_id: 7018, skill_type: 'passive_skill', skill_tags: ['Passive'], description_lines: [], raw_text: '', max_level: 20 },
      { item_id: 'restrain', name: 'Restrain', game_id: 7746, skill_type: 'support_skill', skill_tags: ['Support'], description_lines: [], raw_text: '', max_level: 5 },
    ] as SkillItem[]

    const result = createUeLogBuild(character, [], [], [], [], [], catalog)

    expect(result.build.skills).toEqual([{
      slot: 6, item_id: 'focus', name: 'Focus', level: 20,
      skill_tags: ['Passive'], description_lines: [],
      supports: [{
        support_index: 1, item_id: 'restrain', name: 'Restrain', skill_type: 'support_skill', level: 1,
        skill_tags: ['Support'], description_lines: [],
      }],
    }])
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
    expect(warnings).not.toContain('Vorax Limb: Digits: a base affix is missing from the current Builder data and was left out.')
    expect(build.characterLevel).toBe(98)
    expect(build.conditionState).toEqual({ level: 98 })
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
      { affix: '+20 % additional damage on Critical Strike Intermediate Sequence 1|2|5', source: 'Two-Handed Axe', modifier_id: '160419009', log_modifier_ids: ['160419013'] },
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
    const loggedSequence = createUeLogBuild({ ...character, gear: [{ ...character.gear[0], chipAffixes: [{ id: '160419013', source: null, values: [20] }] }] }, [], [], baseItems, craftTypes, [
      { affix: '+20 % additional damage on Critical Strike Intermediate Sequence 1|2|5', source: 'Two-Handed Axe', modifier_id: '160419009', log_modifier_ids: ['160419013'] },
    ])
    expect(loggedSequence.build.gear?.[0].towerSequence).toBe('+20 % additional damage on Critical Strike Intermediate Sequence 1|2|5')
    expect(loggedSequence.warnings).not.toContain("Brute's Helm (Crafted): its Tower Sequence chip is missing from the current Builder data and was left out.")
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
    expect(result.warnings).toEqual([
      "Death's Touch: the log marks this item as corroded, but no corroded catalog affix was identified.",
    ])
  })

  it("imports Death's Touch with its logged corroded explicit and random affix IDs", () => {
    const unique = {
      item_id: 'death_s_touch', name: "Death's Touch", game_id: 112346, base_type: "Ranger's Rusted Gauntlets",
      required_level: 58, drop_level: 58, flavor_text: null, drop_sources: [], glossary: {},
      random_affixes: {
        base: [{ placeholder: '<A Random Critical Strike or Weapon Damage Affix>', options: [
          { raw_text: '+(70-90) % Critical Strike Damage', modifier_id: '51434661', expression: '+(#) % Critical Strike Damage', condition: null, affix_kind: 'numeric', numeric_values: [] },
        ] }],
        corroded: [{ placeholder: '<A Random Critical Strike or Weapon Damage Affix>Corroded', options: [
          { raw_text: '+(120-150) % Critical Strike Damage', modifier_id: '51434660', expression: '+(#) % Critical Strike Damage', condition: null, affix_kind: 'numeric', numeric_values: [] },
        ] }],
      },
      variants: {
        base: { implicits: [], explicits: [
          { raw_text: '+(90-100) % Critical Strike Rating', modifier_id: '51434611', expression: '+(#) % Critical Strike Rating', condition: null, affix_kind: 'numeric', numeric_values: [] },
          { raw_text: '+(80-100) % Weapon Damage', modifier_id: '51434621', expression: '+(#) % Weapon Damage', condition: null, affix_kind: 'numeric', numeric_values: [] },
          { raw_text: '<A Random Critical Strike or Weapon Damage Affix>', modifier_id: null, expression: '<A Random Critical Strike or Weapon Damage Affix>', condition: null, affix_kind: 'placeholder', numeric_values: [] },
        ] },
        corroded: { implicits: [], explicits: [
          { raw_text: '+(190-210) % Critical Strike Rating', modifier_id: '51434610', expression: '+(#) % Critical Strike Rating', condition: null, affix_kind: 'numeric', numeric_values: [] },
          { raw_text: '+(80-100) % Weapon Damage', modifier_id: '51434621', expression: '+(#) % Weapon Damage', condition: null, affix_kind: 'numeric', numeric_values: [] },
          { raw_text: '<A Random Critical Strike or Weapon Damage Affix>Corroded', modifier_id: null, expression: '<A Random Critical Strike or Weapon Damage Affix>Corroded', condition: null, affix_kind: 'placeholder', numeric_values: [] },
        ] },
      },
    } as unknown as LegendaryGearItem
    const character = {
      dumpNumber: 1, characterName: 'Sage', level: 98, heroId: 1800, heroPurchaseId: 18001,
      truncatedSections: [], skills: [], gear: [{
        baseId: 3311, itemLevel: 58, equippedSlot: 9, uniqueItemId: 112346,
        baseAttrAffixIds: [], baseAffixIds: [], prefixes: [{ id: '51434610', source: null, values: [200] }],
        suffixes: [{ id: '51434660', source: null, values: [140] }], chipAffixes: [], enchantAffixes: [], corroded: true,
      }],
    }

    const result = createUeLogBuild(character, [], [unique])
    const imported = result.build.gear![0]

    expect(imported).toMatchObject({
      corrosion_type: 'desecration', corroded_explicit_indices: [0, 2], selected_random_affixes: { 2: '51434660' },
      customizations: [
        { affix_index: 0, chosen_values: { 0: 200 }, chosen_placeholder_key: null },
        { affix_index: 2, chosen_values: { 0: 140 }, chosen_placeholder_key: null },
      ],
    })
    expect(result.warnings.filter(warning => warning.includes('Death'))).toEqual([])
    expect(migrateLegendaryItem(imported, unique)).toMatchObject({
      corrosion_type: 'desecration', corroded_explicit_indices: [0, 2], selected_random_affixes: { 2: '51434660' },
    })
  })

  it('preserves unique corrosion and random-affix selections through build normalization', () => {
    const unique = {
      item_id: 'broken_sun_ring', name: 'Broken Sun Ring', game_id: 113251, base_type: 'Ripple Pendant',
      required_level: 58, drop_level: 58, flavor_text: null, drop_sources: [], glossary: {},
      random_affixes: {
        base: [{ placeholder: '<A Random Affix>', options: [{
          raw_text: '+10 % Critical Strike Rating', modifier_id: 'base-random', expression: '+10 % Critical Strike Rating',
          condition: null, affix_kind: 'numeric', numeric_values: [{ kind: 'range', sign: '+', min: 8, max: 10, raw: '+(8-10)' }],
        }] }],
        corroded: [{ placeholder: '<A Random Affix>Corroded', options: [{
          raw_text: '+20 % Critical Strike Rating', modifier_id: 'corroded-random', expression: '+20 % Critical Strike Rating',
          condition: null, affix_kind: 'numeric', numeric_values: [{ kind: 'range', sign: '+', min: 18, max: 20, raw: '+(18-20)' }],
        }] }],
      },
      variants: {
        base: { implicits: [], explicits: [{ raw_text: '<A Random Affix>', modifier_id: null, expression: '<A Random Affix>', condition: null, affix_kind: 'placeholder', numeric_values: [] }] },
        corroded: { implicits: [], explicits: [{ raw_text: '<A Random Affix>Corroded', modifier_id: null, expression: '<A Random Affix>Corroded', condition: null, affix_kind: 'placeholder', numeric_values: [] }] },
      },
    } as unknown as LegendaryGearItem
    const character = {
      dumpNumber: 1, characterName: null, level: 98, heroId: 1800, heroPurchaseId: null,
      truncatedSections: [], skills: [], gear: [{
        baseId: 4725, itemLevel: 58, equippedSlot: 6, uniqueItemId: 113251,
        baseAttrAffixIds: [], baseAffixIds: [], prefixes: [{ id: 'corroded-random', source: null, values: [20] }],
        suffixes: [], chipAffixes: [], enchantAffixes: [], corroded: true,
      }],
    }

    const result = createUeLogBuild(character, [], [unique])

    const imported = result.build.gear![0]
    expect(imported).toMatchObject({
      affixes: unique.variants.base.explicits,
      corrosion_type: 'desecration',
      corroded_explicit_indices: [0],
      selected_random_affixes: { 0: 'corroded-random' },
      customizations: [{ affix_index: 0, chosen_values: { 0: 20 }, chosen_placeholder_key: null }],
    })
    const reopened = migrateLegendaryItem(imported, unique)
    expect(reopened.affixes).toEqual([unique.random_affixes.corroded[0].options[0]])
    expect(reopened).toMatchObject({ corrosion_type: 'desecration', corroded_explicit_indices: [0], selected_random_affixes: { 0: 'corroded-random' } })
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
    expect(result.warnings).toEqual([])
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
    expect(result.warnings).toEqual([])
  })
})
