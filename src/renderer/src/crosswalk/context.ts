// Assembles the pure converter's ConvertContext from (a) the crosswalk bridge tables fetched from the backend
// (/api/crosswalk-tables) and (b) the Builder catalogs the renderer already holds in referenceStore. Then runs
// the pure core (convertBuild) — no fs, no tli1_ encode; the returned Build goes straight to loadBuild.
import { convertBuild, type ConvertContext, type ConvertResult, type Named } from './core'
import { heroMemoryBaseStatText } from '../api/client'
import type { LegendaryGearItem, CraftBaseType, Graft, SkillItem, HeroMemoryBaseStatScaling, MemoryRarity, CreatedHeroMemory } from '../api/client'

export type { ConvertResult }

/** The Builder catalogs the ConvertContext needs — all already present in referenceStore. */
export interface ConvertRefs {
  legendaryCatalog: LegendaryGearItem[] | null
  skills: SkillItem[] | null
  craftBaseTypes: CraftBaseType[] | null
  grafts: Graft[] | null
  // Season-stable base-stat scaling table (referenceStore.heroMemories.base_stat_scaling) — used to recompute
  // imported memory base-stat values from OUR ground truth. Optional; import keeps Compendium's value if absent.
  heroMemoryScaling?: HeroMemoryBaseStatScaling | null
}

export interface CrosswalkPayload {
  season: string | null
  tables: Record<string, any>
  treeNames: Record<string, string>
}

const namedMap = (rows: any[] | undefined): Map<string, Named> =>
  new Map((rows ?? []).filter((r) => r.compendium?.uuid).map((r) => [r.compendium.uuid, { slug: r.builder?.slug ?? null, name: r.name, uuid: r.builder?.uuid ?? null }]))

/** Build the injected context. Throws if the crosswalk tables for this season are missing (caller surfaces it). */
export function buildConvertContext(payload: CrosswalkPayload, refs: ConvertRefs): ConvertContext {
  const t = payload.tables ?? {}
  if (!t['skills'] || !t['tree-nodes']) {
    throw new Error(`No Compendium crosswalk data available for season "${payload.season ?? '?'}".`)
  }
  const craftPoolByBaseItem = new Map<string, any[]>()
  for (const bt of (refs.craftBaseTypes ?? [])) {
    for (const bi of ((bt as any).base_items ?? [])) if (bi?.name) craftPoolByBaseItem.set(bi.name, (bt as any).affixes ?? [])
  }
  return {
    season: payload.season ?? '',
    // crosswalk bridge tables (from the backend)
    skills: namedMap(t['skills']?.rows),
    spirits: namedMap(t['pactspirits']?.rows),
    traits: namedMap(t['hero-traits']?.rows),
    legendaries: namedMap(t['legendaries']?.rows),
    slateMods: new Map((t['slate-mods']?.rows ?? []).filter((r: any) => r.builder).map((r: any) => [r.compendiumId, r.builder])),
    memAffix: new Map((t['memory-affixes']?.rows ?? []).filter((r: any) => r.compendium?.uuid).map((r: any) => [r.compendium.uuid, r.name])),
    legAffixTable: t['legendary-affixes']?.items ?? {},
    traitNodes: t['hero-trait-nodes']?.nodes ?? {},
    coreTalents: t['core-talents']?.notables ?? {},
    kismetTable: t['kismets']?.kismets ?? {},
    ingredientTable: t['ingredients']?.ingredients ?? {},
    prismTable: { prisms: t['prisms']?.prisms ?? {}, affixes: t['prisms']?.affixes ?? {}, dnr: t['prisms']?.dnr ?? {} },
    treeXw: t['tree-nodes'] ?? { trees: {} },
    // Builder catalogs (from referenceStore)
    gearById: new Map((refs.legendaryCatalog ?? []).map((it) => [it.item_id, it])),
    gearByName: new Map((refs.legendaryCatalog ?? []).map((it) => [(it as any).name, it])),
    skillTagsById: new Map((refs.skills ?? []).map((s) => [s.item_id, (s as any).skill_tags ?? []])),
    craftPoolByBaseItem,
    graftById: new Map((refs.grafts ?? []).map((g) => [g.item_id, g])),
    treeNames: payload.treeNames ?? {},
    // Recompute imported base-stat values from our ground-truth table (source: MinMaxedARPG).
    computeBaseStatText: (memoryType, modifierText, rarity, level) =>
      heroMemoryBaseStatText(refs.heroMemoryScaling, memoryType as CreatedHeroMemory['memoryType'], modifierText, rarity as MemoryRarity, level),
  }
}

/** Resolve the build's patch to a data season via the alias map (mirrors the CLI's resolveSeason). */
export function resolveCompendiumSeason(patch: string | undefined, tables: Record<string, any>, fallback: string): string {
  const aliases = tables?.['season-aliases']?.aliases ?? {}
  return (patch && aliases[patch]) || patch || fallback
}

/** Convert a Compendium build JSON → a Builder Build (+ warnings), using the injected tables + catalogs. */
export function convertCompendiumBuild(src: any, payload: CrosswalkPayload, refs: ConvertRefs): ConvertResult {
  return convertBuild(src, buildConvertContext(payload, refs))
}
