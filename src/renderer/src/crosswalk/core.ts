/* eslint-disable @typescript-eslint/no-explicit-any */
// ⚠ SYNCED FROM the private tli-build-crosswalk repo (src/core.ts + slateGeometry.ts). Do NOT edit here — change
// it in the crosswalk repo and re-copy, so the CLI and the in-Builder importer stay in lockstep.
/**
 * Pure Compendium → TLI Builder conversion CORE.
 *
 * Turns a Compendium build + INJECTED crosswalk tables/catalogs (ConvertContext) into ONE schema-correct
 * Builder `Build` object (each Compendium loadout → a Builder loadout; flat top-level fields mirror the active
 * loadout). It does NOT touch the filesystem and does NOT encode — so it drops straight into tlibuilder's
 * renderer to power an in-app "Import from Compendium" (inject the tables, hand the returned Build to loadBuild).
 * The CLI shell (emit.ts) does the file I/O + the frozen `tli1_` encode.
 *
 * Fidelity notes: legendary/craft/vorax rolls ride in customizations; prisms + memories + kismets + scent + base
 * slot are all mapped (see the per-subsystem comments below). traitSlotLevels stays [1,1,1,1] (Compendium has no
 * per-slot tier level; Builder derives it from the socketed memories).
 */
import { resolveGeometry, resolveLegendaryGeometry, initSlateSlots } from './slateGeometry'

export interface Named { slug: string | null; name: string; uuid: string | null }

/** Everything the pure converter needs, injected by the caller (crosswalk tables + Builder catalogs). */
export interface ConvertContext {
  season: string
  skills: Map<string, Named>
  spirits: Map<string, Named>
  traits: Map<string, Named>
  legendaries: Map<string, Named>
  slateMods: Map<string, { kind: string; builderId: string }>
  memAffix: Map<string, string>
  legAffixTable: Record<string, { explicits: { key: string; valueCount: number }[] }>
  traitNodes: Record<string, { builderNodeId: string; traitId: string; treeMode: boolean }>
  coreTalents: Record<string, { builderTalentId: string; slotIndex: number }>
  kismetTable: Record<string, { name: string; shortName: string; kind: string; nodeTier: string; effectText: string }>
  ingredientTable: Record<string, string>
  prismTable: { prisms: Record<string, any>; affixes: Record<string, any>; dnr: Record<string, any> }
  gearById: Map<string, any>
  gearByName: Map<string, any>
  skillTagsById: Map<string, string[]>
  craftPoolByBaseItem: Map<string, any[]>
  graftById: Map<string, any>
  treeXw: any
  treeNames: Record<string, string>
  // Optional: recompute a memory base-stat's modifier TEXT from OUR ground-truth scaling table (source:
  // MinMaxedARPG), given (memoryType, the affix's current text, rarity, level). Injected by the tlibuilder
  // adapter; when absent (or it returns null) the importer keeps Compendium's exported value. Kept as an
  // injected fn so the pure core stays free of tlibuilder imports and portable.
  computeBaseStatText?: (memoryType: string, modifierText: string, rarity: string, level: number) => string | null
}

export interface ConvertResult {
  build: Record<string, unknown>
  loadoutName: string
  srcName: string
  patch: string
  warnings: string[]
  stats: { loadouts: number; skills: number; gear: number; trees: number; spirits: number; slates: number; memories: number; customizations: { mapped: number; total: number } }
}

/** Normalize an affix text (rendered or templated) so Compendium mod descriptions match our
 * catalog explicit expressions. Mirrors loaders.normExpr. */
function normExpr(s: string): string {
  return String(s ?? '')
    .toLowerCase()
    .replace(/\(#\)/g, '#')
    .replace(/[0-9]+(?:[.,][0-9]+)?/g, '#')
    .replace(/#[.,]#/g, '#')
    .replace(/\s*%/g, '%')
    .replace(/[.,()]/g, '')
    .replace(/#\s*[–\-]\s*#/g, '#-#')
    .replace(/\s+/g, ' ')
    .trim()
}

// Compendium memory rarity → Builder MemoryRarity, matched by TIER POSITION (the naming schemes
// differ: Compendium labels the 5 tiers Normal/Magic/Epic/Legendary/Ultimate, while Builder uses
// the in-game normal/magic/rare/epic/ultimate). So Epic→rare and Legendary→epic.
const MEMORY_RARITY_MAP: Record<string, string> = {
  normal: 'normal', magic: 'magic', epic: 'rare', legendary: 'epic', ultimate: 'ultimate',
}
// Per-rarity enhancement-level cap (Builder rarity keys). Compendium doesn't export the memory's level, so we
// assume fully built (the rarity's max) on import — matches Builder's create-default and the typical shared state.
const MEMORY_MAX_LEVEL: Record<string, number> = {
  normal: 10, magic: 20, rare: 30, epic: 40, ultimate: 50,
}
// Base-stat tier by rarity — the rarity's max tier, matching the native creator (HeroTraitScreen minTier:
// ultimate→0, epic→1, rare→2, magic→3, normal→4). Used when recomputing an imported memory's base stat.
const BASE_TIER_BY_RARITY: Record<string, number> = {
  ultimate: 0, epic: 1, rare: 2, magic: 3, normal: 4,
}

// Divinity slate treeType is ALWAYS one of the six god base trees (a Goddess-of-Knowledge slate
// pulls from all Knowledge subtrees: arcanist/magister/etc.) — never a subtree. Map Compendium `god`.
const GOD_TREE_MAP: Record<string, string> = {
  knowledge: 'Goddess of Knowledge',
  war: 'God of War',
  might: 'God of Might',
  machines: 'God of Machines',
  hunting: 'Goddess of Hunting',
  deception: 'Goddess of Deception',
}

const SLOT_MAP: Record<string, string> = {
  helmet: 'helmet', chest: 'chest', gloves: 'gloves', boots: 'boots', belt: 'belt',
  ring1: 'ring1', ring2: 'ring2', necklace: 'amulet', mainHand: 'weapon1', offHand: 'weapon2',
}

function numericValues(rolled: any[]): any[] {
  // Shape MUST match client.ts LegendaryNumericValue: { kind, sign, min?, max?, value?, raw }.
  // `raw` is REQUIRED (no `unit` field exists on it — unit lives on the affix). For a fixed roll,
  // raw is the signed value token; for a range with no picked value there is nothing to substitute,
  // so raw is '' (which _materializeAffixText treats as "skip", preserving behavior).
  return rolled.map((v: any) =>
    v.value != null
      ? { kind: 'fixed', sign: v.sign ?? null, value: v.value, raw: `${v.sign ?? ''}${v.value}` }
      : { kind: 'range', sign: v.sign ?? null, min: v.minValue, max: v.maxValue, raw: '' },
  )
}
/** Build a Builder affix from a Compendium mod. Renders the `#` template with the ACTUAL rolled
 * values so raw_text (what the UI shows and the resolver parses) carries real numbers, not `#`. */
function affixFromMod(mod: any): any {
  const template = mod.description ?? mod.modifierDescription ?? ''
  const rolled = mod.rolledValues ?? mod.values ?? []
  let i = 0
  const raw_text = template.replace(/#/g, () => {
    const rv = rolled[i++]
    return rv && rv.value != null ? String(rv.value) : '#'
  })
  return { raw_text, modifier_id: null, expression: template, condition: null, affix_kind: 'numeric', numeric_values: numericValues(rolled), tier: mod.tier }
}

export function convertBuild(src: any, ctx: ConvertContext, loadoutFilter?: string): ConvertResult {
  const {
    skills, spirits, traits, legendaries, slateMods, memAffix, legAffixTable, traitNodes, coreTalents,
    kismetTable, ingredientTable, prismTable, gearById, gearByName, skillTagsById, craftPoolByBaseItem,
    graftById, treeXw, treeNames, computeBaseStatText,
  } = ctx
  // Legendary explicits by normalized text (a Vorax graft can carry a legendary, e.g. "Rock Lizard's Skull") —
  // joined by name → canonical raw_text (Builder does the same join).
  const legendaryExplicitByText = (legName: string): Map<string, any> => {
    const it = gearByName.get(legName)
    const variants = it?.variants ?? {}
    const vkey = variants.base ? 'base' : Object.keys(variants)[0] ?? 'base'
    return new Map<string, any>(((variants[vkey]?.explicits ?? []) as any[]).map((e: any) => [normExpr(e.expression ?? e.raw_text ?? ''), e]))
  }
  const matchCraftAffix = (baseItemName: string, mod: any): any | null => {
    const pool = craftPoolByBaseItem.get(baseItemName) ?? []
    const key = normExpr(mod.modifierDescription ?? mod.description ?? '')
    const cands = pool.filter((a) => normExpr(a.expression ?? a.raw_text ?? '') === key)
    if (!cands.length) return null
    const rv0 = (mod.rolledValues ?? [])[0] ?? {}
    // Prefer the tier whose range matches the Compendium roll's [min,max]; else the first same-text affix.
    return cands.find((a) => (a.numeric_values ?? []).some((v: any) => v.kind === 'range' && v.min === rv0.minValue && v.max === rv0.maxValue)) ?? cands[0]
  }
  // Match a Compendium vorax affix to a graft catalog affix by normalized text (mirrors matchCraftAffix).
  const matchGraftAffix = (pool: any[], mod: any): any | null => {
    const key = normExpr(mod.modifierDescription ?? mod.description ?? mod.descriptionTemplate ?? '')
    const cands = (pool ?? []).filter((a) => normExpr(a.expression ?? a.raw_text ?? '') === key)
    if (!cands.length) return null
    const rv0 = (mod.rolledValues ?? [])[0] ?? {}
    return cands.find((a) => (a.numeric_values ?? []).some((v: any) => v.kind === 'range' && v.min === rv0.minValue && v.max === rv0.maxValue)) ?? cands[0]
  }
  // Mirror backend build_code._rehydrate_gear_item so a legendary item is self-sufficient in any loadout.
  const rehydrateLegendary = (item_id: string | null, name: string, slot: string | null, customizations: any[]) => {
    const full = item_id ? gearById.get(item_id) : null
    if (!full) return { item_id, name, slot, is_crafted: false, customizations, affixes: [], implicit_count: 0 }
    const variants = full.variants ?? {}
    // Prefer the base variant (native getImplicitCount reads variants.base) so the affixes array
    // order — and therefore the customization affix_index — matches what the gear editor computes.
    const vkey = variants.base ? 'base' : Object.keys(variants)[0] ?? 'base'
    const variant = variants[vkey] ?? {}
    const implicits = variant.implicits ?? []
    const explicits = variant.explicits ?? []
    const affixes = [
      ...implicits,
      ...explicits,
      ...((full.random_affixes?.[vkey] ?? []).map((g: any) => ({ raw_text: g.placeholder, modifier_id: null, expression: g.placeholder, condition: null, affix_kind: 'placeholder', numeric_values: [] }))),
    ]
    return { ...full, slot, customizations, affixes, implicit_count: implicits.length }
  }

  const populated = (src.loadouts?.loadouts ?? []).filter((l: any) => l.hero)
  if (populated.length === 0) throw new Error('No populated loadout found.')

  const customCov = { mapped: 0, total: 0 }
  // Conversion warnings — anything that couldn't be mapped and was dropped, or imported with a
  // best-guess value, is recorded here (never silently lost). Surfaced in the build notes so the
  // user sees it after import, and printed by the CLI. (Future: Builder's warnings/issues sidebar.)
  const warnings: string[] = []
  const emitSkill = (s: any, slot: number) => {
    const ref = skills.get(s.skillGuid)
    return {
      slot, item_id: ref?.slug ?? null, name: ref?.name ?? '', level: s.level ?? 20,
      skill_tags: (ref?.slug && skillTagsById.get(ref.slug)) ?? [], description_lines: [], enabled: s.enabled !== false,
      // Slot 1 is the headline DPS skill on import (Builder's deriveMainSkill prefers slot 1).
      countInDps: slot === 1 ? true : undefined,
      supports: (s.supports ?? []).filter(Boolean).map((sup: any, i: number) => {
        const sref = skills.get(sup.supportGuid)
        // Full EquippedSupportSkill shape (client.ts): skill_tags + description_lines are REQUIRED
        // (native makeSupport always sets them). Tags come from _skills.json; description falls back to
        // the catalog on load, so [] is safe there.
        return {
          support_index: i + 1, item_id: sref?.slug ?? null, name: sref?.name ?? '',
          skill_type: sup.type ?? 'support', level: sup.level ?? 20,
          skill_tags: (sref?.slug && skillTagsById.get(sref.slug)) ?? [], description_lines: [],
        }
      }),
    }
  }
  const memSlot = (sel: any) => sel ? { modifier: (sel.guid && memAffix.get(sel.guid)) ?? null, tier: sel.tier ?? 1, rolledValue: sel.value ?? null } : null

  // Convert ONE Compendium loadout → the swappable field values (grouped later into AREA_FIELDS snapshots).
  const loadoutFields = (lo: any) => {
    const emittedSkills = [
      ...(lo.skills?.activeSkills ?? []).map((s: any, i: number) => emitSkill(s, i + 1)),
      ...(lo.skills?.passiveSkills ?? []).filter((s: any) => s?.skillGuid).map((s: any, i: number) => emitSkill(s, i + 6)),
    ]
    const slots = (lo.skillTree?.slots ?? []).filter((s: any) => s.treeId).map((s: any) => {
      const nodeMap = new Map<string, string>((treeXw.trees[s.treeId]?.nodes ?? []).map((n: any) => [n.compendiumUuid, n.builderNodeId]))
      const nodeStates: Record<string, number> = {}
      for (const [uuid, pts] of Object.entries(s.nodePoints ?? {})) { const id = nodeMap.get(uuid); if (id) nodeStates[id] = pts as number }
      // Core talents (notables): selectedNotable12/24 → coreTalentSelections { slotIndex: talentId }.
      const coreTalentSelections: Record<string, string> = {}
      for (const nuid of [s.selectedNotable12, s.selectedNotable24]) {
        const m = nuid ? coreTalents[nuid] : undefined
        if (m) coreTalentSelections[String(m.slotIndex)] = m.builderTalentId
      }
      return { treeName: treeNames[s.treeId] ?? s.treeId, nodeStates, coreTalentSelections }
    })
    while (slots.length < 4) slots.push(null as any)

    const gear = (lo.gear?.inventory ?? []).map((g: any) => {
      const slotKey = Object.entries(lo.gear.equipped ?? {}).find(([, id]) => id === g.id)?.[0]
      const slot = slotKey ? SLOT_MAP[slotKey] ?? null : null
      if (g.rarity === 'Legendary') {
        const ref = legendaries.get(g.legendaryItem?.legendaryId)
        const explicits = ref?.slug ? legAffixTable[ref.slug]?.explicits ?? [] : []
        // customizations.affix_index is 0-based over the FULL affixes array (implicits + explicits),
        // NOT over explicits alone — native keys them on implCount+explicitIndex (GearScreen
        // handleLegendaryValueEdit / handleToggleCorroded). Offset by the base variant's implicit count.
        const implicitOffset = (() => {
          const full = ref?.slug ? gearById.get(ref.slug) : null
          const variants = full?.variants ?? {}
          const vkey = variants.base ? 'base' : Object.keys(variants)[0] ?? 'base'
          return (variants[vkey]?.implicits ?? []).length
        })()
        const used = new Set<number>()
        const customizations: any[] = []
        for (const mod of g.legendaryMods ?? []) {
          const key = normExpr(mod.description ?? '')
          const idx = explicits.findIndex((e, i) => e.key === key && !used.has(i))
          customCov.total++
          if (idx < 0) continue
          used.add(idx); customCov.mapped++
          const chosen_values: Record<number, number> = {}
          ;(mod.rolledValues ?? []).forEach((v: any, i: number) => { if (v.value != null) chosen_values[i] = v.value })
          if (Object.keys(chosen_values).length) customizations.push({ affix_index: implicitOffset + idx, chosen_values, chosen_placeholder_key: null })
        }
        return rehydrateLegendary(ref?.slug ?? null, g.legendaryItem?.name ?? ref?.name ?? '', slot, customizations)
      }
      // Rare / crafted: implicits (base-item, rendered) + base affixes (slots 0-1) + prefixes (2-4) +
      // suffixes (5-7). Explicits use the catalog affix verbatim (so the craft editor matches by
      // raw_text); the rolled value rides in customizations, indexed by explicit position.
      const baseName = String(g.baseItem?.name ?? '')   // String()-coerce: untrusted gear name, non-string would throw at .toLowerCase()/interp
      const implicits = (g.baseItem?.implicits ?? []).map((a: any) => ({ ...affixFromMod(a), affix_kind: 'implicit' }))
      const explicitEntries: { mod: any; slot: number }[] = [
        ...[g.baseAffix, g.baseAffix2].filter(Boolean).map((m: any, i: number) => ({ mod: m, slot: i })),
        ...(g.prefixes ?? []).map((m: any, i: number) => ({ mod: m, slot: 2 + i })),
        ...(g.suffixes ?? []).map((m: any, i: number) => ({ mod: m, slot: 5 + i })),
      ]
      const customizations: any[] = []
      const explicitAffixes = explicitEntries.map(({ mod }, i) => {
        const cat = matchCraftAffix(baseName, mod)
        const chosen: Record<number, number> = {}
        ;(mod.rolledValues ?? []).forEach((v: any, vi: number) => { if (v.value != null) chosen[vi] = v.value })
        if (Object.keys(chosen).length) customizations.push({ affix_index: implicits.length + i, chosen_values: chosen, chosen_placeholder_key: null })
        return cat ? { ...cat } : affixFromMod(mod) // fall back to rendered text if no catalog match
      })
      // Match native makeCraftedItem exactly: item_id = slugified name, name = "<base> (Crafted)",
      // required_level present (interface-required, not backfilled on load). Re-editing keys on base_type.
      return {
        item_id: baseName.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, ''),
        name: `${baseName} (Crafted)`, base_type: baseName, slot, is_crafted: true,
        required_level: g.baseItem?.requiredLevel ?? g.baseItem?.required_level ?? 0,
        implicit_count: implicits.length,
        craft_slot_positions: explicitEntries.map((e) => e.slot),
        customizations,
        affixes: [...implicits, ...explicitAffixes],
      }
    })

    // Vorax grafts: items live in `vorax.inventory` but are EQUIPPED via `gear.equipped[<slot>] = voraxId`, so
    // realize each equipped one as an is_vorax gear item (mirrors Builder's buildVoraxItem): baseAffix = the Base
    // (implicit, slot 0), then the graft's affixes; each affix matched to the _grafts.json pool by text so raw_text
    // is canonical, with the rolled values in customizations. Gear slot comes from where it's equipped.
    const voraxById = new Map<string, any>((lo.vorax?.inventory ?? []).map((v: any) => [v.id, v]))
    for (const [gearSlot, id] of Object.entries(lo.gear?.equipped ?? {})) {
      const v = typeof id === 'string' ? voraxById.get(id) : null
      if (!v) continue
      const graftId = `vorax_limb_${String(v.limbType ?? '').toLowerCase()}`
      const graft = graftById.get(graftId)
      if (!graft) { warnings.push(`${lo.name}: Vorax graft "${graftId}" not in crosswalk — skipped`); continue }
      const pool = [...(graft.base_affixes ?? []), ...(graft.affixes ?? [])]
      // affixType → Builder affix_type. Base affix (v.baseAffix) is the implicit ('Base'); a legendary graft affix
      // ('Rock Lizard's Skull' etc.) → 'Legendary' with canonical text from the legendary catalog; the rest keep
      // their Basic/Advanced/Ultimate Affix type from the graft pool.
      const AFFIX_TYPE: Record<string, string> = { Basic: 'Basic Affix', Advanced: 'Advanced Affix', Ultimate: 'Ultimate Affix' }
      const entries = [v.baseAffix, ...(v.affixes ?? [])].filter(Boolean)
      const voraxCustom: any[] = []
      let legSource: string | null = null
      let legCount = 0
      const voraxAffixes = entries.map((mod: any, i: number) => {
        const chosen: Record<number, number> = {}
        ;(mod.rolledValues ?? []).forEach((rv: any, vi: number) => { if (rv.value != null) chosen[vi] = rv.value })
        if (Object.keys(chosen).length) voraxCustom.push({ affix_index: i, chosen_values: chosen, chosen_placeholder_key: null })
        const isLeg = mod.isLegendary === true || mod.affixType === 'Legendary'
        if (isLeg) {
          legCount++
          if (mod.legendaryName) legSource = mod.legendaryName
          const cat = mod.legendaryName ? legendaryExplicitByText(mod.legendaryName).get(normExpr(mod.descriptionTemplate ?? mod.modifierDescription ?? '')) : null
          return { ...(cat ?? affixFromMod(mod)), affix_type: 'Legendary', affix_kind: cat?.affix_kind ?? 'numeric' }
        }
        const cat = matchGraftAffix(pool, mod)
        const affix_type = i === 0 ? 'Base' : (AFFIX_TYPE[mod.affixType] ?? cat?.affix_type ?? 'Basic Affix')
        return { ...(cat ?? affixFromMod(mod)), affix_type, affix_kind: i === 0 ? 'implicit' : (cat?.affix_kind ?? 'numeric') }
      })
      gear.push({
        item_id: graftId, name: `${v.displayName || graft.name || 'Vorax'} (Vorax)`,
        slot: SLOT_MAP[gearSlot] ?? null, is_crafted: true, is_vorax: true, implicit_count: 1,
        craft_slot_positions: entries.map((_: any, i: number) => i), required_level: v.itemLevel ?? 0,
        ...(legSource ? { legendary_source: legSource, legendary_affix_count: legCount } : {}),
        customizations: voraxCustom, affixes: voraxAffixes,
      })
    }

    const pactSpirits: any[] = (lo.pactspirits ?? []).filter((p: any) => p?.guid).map((p: any) => ({ itemId: spirits.get(p.guid)?.slug ?? null, rank: p.level ?? 1 }))
    while (pactSpirits.length < 3) pactSpirits.push(null)

    // fixedAffixes/randomAffixes are fixed 2-tuples [X|null, X|null] in the interface (native creator
    // produces exactly 2; sanitizeHeroMemory truncates extras on load). Normalize to length 2 here.
    const twoTuple = (arr: any[]) => { const m = (arr ?? []).map(memSlot); return [m[0] ?? null, m[1] ?? null] }
    // A Compendium memory → a Builder CreatedHeroMemory. The id is NAMESPACED BY LOADOUT: the same
    // Compendium memory id can appear in several loadouts with DIFFERENT data (e.g. rare in TM7 but epic in
    // TM8 — Compendium reuses one id across loadout configs). Builder inventories are per-loadout, so each
    // must be a distinct entity; without the namespace, Builder's cross-loadout "All loadouts" dedup-by-id
    // collapses them and shows only whichever loadout is currently loaded.
    const memInv = lo.heroMemories?.inventory ?? []
    const toMemory = (m: any, i: number) => {
      // String()-coerce before toLowerCase: this is untrusted Compendium JSON, and a non-string rarity/
      // memoryType (number/bool/object) would otherwise throw and abort the WHOLE import instead of letting
      // this one memory degrade (rarity → 'normal'; a bad memoryType is warned + dropped downstream).
      const rarity = MEMORY_RARITY_MAP[String(m.rarity ?? '').toLowerCase()] ?? 'normal'
      const memoryType = String(m.memoryType ?? '').toLowerCase()
      const level = MEMORY_MAX_LEVEL[rarity] ?? 10
      // Base stat: recompute the VALUE from OUR ground-truth table at the assumed rarity-max level (owner:
      // Compendium's exported value may be wrong). Keep Compendium's value only if the table lacks the stat.
      // The value lives in the text (rolledValue cleared) and tier is set to the rarity's max tier, matching
      // the native creator's base-stat shape (ultimate→0 … normal→4).
      const baseStat = memSlot(m.baseStat)
      if (baseStat?.modifier && computeBaseStatText) {
        const t = computeBaseStatText(memoryType, baseStat.modifier, rarity, level)
        if (t) { baseStat.modifier = t; baseStat.rolledValue = null; baseStat.tier = BASE_TIER_BY_RARITY[rarity] ?? baseStat.tier }
      }
      return {
        id: `${lo.id}:${(typeof m.id === 'string' && m.id) ? m.id : `import-${i}`}`,
        memoryType,
        rarity,
        // Compendium doesn't export the enhancement level — assume fully built (the rarity's max), matching
        // Builder's create-default and the typical shared-build state. The user can adjust after import.
        level,
        baseStat, fixedAffixes: twoTuple(m.fixedAffixes), randomAffixes: twoTuple(m.randomAffixes),
        // Wax & Wane can only exist on a REVIVALED memory, so a Compendium waxAndWane implies revived.
        // Compendium doesn't expose the revival mod itself in this data, so revivalMod stays null.
        revived: m.waxAndWane === true, revivalMod: null, waxAndWane: m.waxAndWane === true,
      }
    }
    // memoryInventory = every OWNED memory (not just the socketed ones — the whole point of the inventory).
    const memoryInventory: any[] = memInv.map(toMemory)
    // Map the ORIGINAL Compendium id → the loadout-namespaced memory, so `equipped` (which references the
    // original ids) still resolves the socketed memories.
    const byOrigId = new Map<string, any>(memInv.map((m: any, i: number) => [m.id, memoryInventory[i]]))
    // The 3 socketed slots come from `equipped` (slot45→origin, slot60→discipline, slot75→progress).
    const eq = lo.heroMemories?.equipped ?? {}
    const heroMemories: any[] = [eq.slot45, eq.slot60, eq.slot75].map((mid: any) => (typeof mid === 'string' && byOrigId.get(mid)) ? byOrigId.get(mid) : null)

    // Base/Special slot (Compendium `slotLevel1Special` = { memoryId, sourceSlot, modifierPercent }). Builder
    // models the base slot as ENABLED by a revival mod on the sourceSlot memory, with the penalty encoded in that
    // mod's text; Compendium gives the penalty directly (modifierPercent) but not the enabler mod. So reconstruct
    // it: mark the sourceSlot (45/60/75) memory revived + synthesize an enabler mod whose type/rarity-cap match the
    // base memory and whose "by N%" carries the penalty, so Builder's parseBaseSlotEnabler/resolveBaseSlot validate.
    let baseMemory: any = null
    const special = eq.slotLevel1Special
    if (special && typeof special.memoryId === 'string') {
      const SRC_IDX: Record<number, number> = { 45: 0, 60: 1, 75: 2 }
      const srcIdx = SRC_IDX[special.sourceSlot as number]
      const bm = byOrigId.get(special.memoryId)
      const host = srcIdx != null ? heroMemories[srcIdx] : null
      if (bm && host) {
        // Base memory must be NON-revived (Builder gate); its id already differs from the 3 socketed ids.
        bm.revived = false; bm.revivalMod = null; bm.waxAndWane = false
        baseMemory = bm
        const RARITY_LABEL: Record<string, string> = { normal: 'Normal', magic: 'Magic', rare: 'Rare', epic: 'Epic', ultimate: 'Ultimate' }
        const TYPE_LABEL: Record<string, string> = { origin: 'Origin', discipline: 'Discipline', progress: 'Progress' }
        const pct = Math.abs(Number(special.modifierPercent) || 0)
        const cap = RARITY_LABEL[bm.rarity] ?? 'Ultimate'
        const typ = TYPE_LABEL[bm.memoryType] ?? 'Origin'
        host.revived = true
        host.revivalMod = {
          modifier: `Base Traits now have Base Trait slots that can be installed with a ${cap} or lower ${typ} Memory. Reduces the Base Stats and Random Affixes of Memories installed in this slot by ${pct}%`,
          tier: 2, rolledValue: null,
        }
      }
    }

    const placements = new Map<string, [number, number]>((lo.divinity?.placements ?? []).map((p: any) => [p.slateId, [p.row, p.col]]))
    // The whole divinity board belongs to one god; legendary/empty slates carry no `god`, so fall
    // back to the board god (from any slate that has one).
    const boardGod = (lo.divinity?.inventory ?? []).map((s: any) => s.god).find(Boolean) ?? null
    const slates = (lo.divinity?.inventory ?? []).map((s: any) => {
      const anchor = placements.get(s.id) ?? [0, 0]
      // Legendary slates are their own shapes (kind = LegendaryKind); base slates use the tetromino transform.
      const leg = s.type === 'legendary' && s.legendaryTemplate ? resolveLegendaryGeometry(s.legendaryTemplate, s.orientation?.rotation) : null
      const geom = leg
        ? { kind: leg.kind, shapeIndex: 0, orientationIndex: leg.orientationIndex, cells: leg.cells }
        : (() => { const g = resolveGeometry(s.shapeId, s.orientation?.rotation, s.orientation?.flipH, s.orientation?.flipV); return { kind: 'base', shapeIndex: g.shapeIndex, orientationIndex: g.orientationIndex, cells: g.cells } })()
      // Slots come from the slate KIND (fixed count/types, mirrors SlateScreen.initSlots) — NOT from
      // the number of imported affixes. Fill each imported affix into the next slot, preferring the
      // one it was placed in (slotIndex) when that's in range.
      const slots = initSlateSlots(geom.kind)
      const affixes = (s.affixes ?? [])
      const used = new Set<number>()
      for (const a of affixes) {
        const ref = slateMods.get(a.modGuid)
        const t = String(a.nodeType ?? '').toLowerCase()   // String()-coerce: untrusted slate affix, non-string nodeType would throw
        const slotType = t.includes('legendary') ? 'legendary' : t.includes('medium') ? 'rare' : 'magic'
        // Prefer the affix's own slotIndex; else the first free slot.
        let idx = typeof a.slotIndex === 'number' && a.slotIndex < slots.length && !used.has(a.slotIndex) ? a.slotIndex : -1
        if (idx < 0) idx = slots.findIndex((_, i) => !used.has(i))
        if (idx < 0 || !slots[idx]) continue
        used.add(idx)
        slots[idx] = {
          ...slots[idx]!,
          slotType: slotType as any,
          isCore: ref?.kind === 'core',
          selectedNodeId: ref?.kind === 'node' ? ref.builderId : null,
          selectedCoreKey: ref?.kind === 'core' ? ref.builderId : null,
          effects: a.description ? [a.description] : [],
          nodeType: a.nodeType ?? null,
        }
      }
      // Moth/space-rift/spark kinds carry a copy DIRECTION; without it the slate produces NO effect
      // (SlateScreen returns [] when mothDirection is unset). Compendium ships no explicit direction,
      // so seed the native creator defaults per kind (spark→above, space_rift→left) so the slate at
      // least resolves; a build that actually uses these should map direction from its orientation.
      const MOTH_DEFAULT: Record<string, string> = { spark_of_moth_fire: 'above', when_sparks_set_prairie_ablaze: 'above', space_rift: 'left' }
      const mothDirection = MOTH_DEFAULT[geom.kind]
      return {
        id: s.id, templateId: s.id, kind: geom.kind, shapeIndex: geom.shapeIndex, orientationIndex: geom.orientationIndex,
        anchor, cells: geom.cells.map(([r, c]) => [anchor[0] + r, anchor[1] + c]),
        treeType: GOD_TREE_MAP[String(s.god ?? boardGod ?? '').toLowerCase()] ?? null,
        ...(mothDirection ? { mothDirection } : {}),
        slots,
      }
    })

    // Ethereal prisms → prismInventory (CraftedPrism) + prisms (PlacedPrism). The prism's 3 randomAffixes resolve
    // to the areaSize (box cols/rows) / middle (in-area stat) / advanced (do-not-replace) slots; the catalog join
    // gives name/shortName/implicit (the "Replaces the Core Talent … with X" line that drives the replacement).
    // Placement: equippedPrism.nodeId → the Builder node's col/row (anchor); boxAllocations stays {} for ethereal.
    const OFF_ROLLS = { micro: -100, medium: -100, legendary: -100 }
    const prismInvById = new Map<string, any>()
    const prismInventory = (lo.etherealPrisms?.inventory ?? []).map((p: any) => {
      const cat = prismTable.prisms[p.baseId]
      if (!cat) { warnings.push(`${lo.name}: ethereal prism not in crosswalk — dropped (baseId ${p.baseId})`); return null }
      // Inverse Image: no EtherealConfig; its "rolls" are the tempering ranges (inverseModValues → PrismRolls).
      if (p.prismType === 'inverse' || cat.kind === 'inverse_image') {
        const rolls = { micro: -100, medium: -100, legendary: -100 }
        for (const mv of (p.inverseModValues ?? [])) {
          const n = String(mv.name ?? '').toLowerCase()
          if (n.includes('legendary')) rolls.legendary = mv.value          // check legendary before medium ("Legendary Medium…")
          else if (n.includes('micro')) rolls.micro = mv.value
          else if (n.includes('medium')) rolls.medium = mv.value
        }
        const cp = { id: p.id, kind: 'inverse_image', name: cat.name, iconUrl: cat.iconUrl, rolls }
        prismInvById.set(p.id, cp)
        return cp
      }
      let areaSize: string | undefined, boxCols: number | undefined, boxRows: number | undefined, middle: string | undefined, advanced: string | undefined
      for (const uid of (p.randomAffixes ?? [])) {
        const ra = prismTable.affixes[uid]; if (!ra) continue
        if (ra.slot === 'areaSize') { areaSize = ra.text; boxCols = ra.cols; boxRows = ra.rows }
        else if (ra.slot === 'middle') middle = ra.text
        else if (ra.slot === 'advanced') {
          if (ra.dnr) {
            // Pick the do-not-replace variant for THIS prism (by shortName) whose penalty matches extraStats, so
            // the editor selects it. Compare penalties space-insensitively ("-5% …" vs "-5 % …").
            const norm = (s: string) => String(s ?? '').replace(/\s+/g, '').toLowerCase()
            const opts: any[] = prismTable.dnr?.[cat.shortName] ?? []
            advanced = (opts.find((o) => norm(o.penalty) === norm(ra.penalty)) ?? opts[0])?.modifier
            if (!advanced) warnings.push(`${lo.name}: prism "${cat.shortName}" do-not-replace option not found in catalog — advanced slot left empty`)
          } else advanced = ra.text
        }
      }
      const rarity = advanced ? 'legendary' : 'rare'
      const ethereal = {
        shortName: cat.shortName, rarity, implicit: cat.implicit, tintWhenRare: false,
        ...(areaSize ? { areaSize, boxCols, boxRows } : {}), ...(middle ? { middle } : {}),
        ...(rarity === 'legendary' && advanced ? { advanced } : {}),
      }
      const cp = { id: p.id, kind: 'ethereal_prism', name: cat.name, iconUrl: cat.iconUrl, rolls: OFF_ROLLS, ethereal }
      prismInvById.set(p.id, cp)
      return cp
    }).filter(Boolean)
    // Placed prisms: one per tree slot carrying an equippedPrism, anchored at the node's Builder grid position.
    const prisms: any[] = []
    const XT = treeXw.transform ?? { col: { offset: 96, step: 128 }, row: { offset: 80, step: 96 } }
    for (const s of (lo.skillTree?.slots ?? [])) {
      const ep = s.equippedPrism
      const iis = s.inverseImageState
      if (!ep?.prismId) continue
      const cp = prismInvById.get(ep.prismId)
      if (!cp) continue
      const anchorUuid = cp.kind === 'inverse_image' ? (iis?.centerNodeId ?? ep.nodeId) : ep.nodeId
      const node = (treeXw.trees[s.treeId]?.nodes ?? []).find((n: any) => n.compendiumUuid === anchorUuid)
      if (!node) { warnings.push(`${lo.name}: prism placement node not in crosswalk — prism left unplaced (node ${anchorUuid})`); continue }
      // Inverse Image: boxAllocations maps each reflected cell (svgPosition → grid) to the ORIGINAL node's points
      // (the reflected copy carries the mirror-source's allocation). Ethereal: box stays {} (it edits real nodes).
      const boxAllocations: Record<string, number> = {}
      if (cp.kind === 'inverse_image') {
        for (const m of (iis?.mirroredNodes ?? [])) {
          const pts = s.nodePoints?.[m.originalNodeId]
          if (!(pts > 0) || !m.svgPosition) continue
          const col = (m.svgPosition.cx - XT.col.offset) / XT.col.step
          const row = (m.svgPosition.cy - XT.row.offset) / XT.row.step
          boxAllocations[`${col},${row}`] = pts
        }
      }
      prisms.push({
        id: `${cp.id}-placed`, templateId: cp.id, kind: cp.kind, name: cp.name, iconUrl: cp.iconUrl,
        rolls: cp.rolls, ...(cp.ethereal ? { ethereal: cp.ethereal } : {}), treeName: treeNames[s.treeId] ?? s.treeId,
        anchorCol: node.col, anchorRow: node.row, boxAllocations,
      })
    }

    // Kismets → fates (Record "<spiritSlotIdx>:<nodeIdx>" → InstalledFate). nodeId "slot_<s>_<n>" → nodeIdx n,
    // which aligns index-for-index with Builder's spirit slots[] (verified). Only emit when that spirit is present.
    const fates: Record<string, any> = {}
    for (const k of (lo.kismets ?? [])) {
      const si = k.pactspritIndex
      const nm = typeof k.nodeId === 'string' ? /_(\d+)$/.exec(k.nodeId) : null
      if (typeof si !== 'number' || !pactSpirits[si] || !nm) continue
      const info = k.kismetGuid ? kismetTable[k.kismetGuid] : null
      if (!info) { if (k.kismetGuid) warnings.push(`${lo.name}: kismet not in crosswalk — dropped (guid ${k.kismetGuid})`); continue }
      fates[`${si}:${Number(nm[1])}`] = {
        name: info.name, shortName: info.shortName, kind: info.kind, nodeTier: info.nodeTier,
        effectText: info.effectText, rolledValues: k.rollValues ?? [],
      }
    }

    // Scent bottle (Licorice elixir) → licoricePreparedSkill + elixirIngredients (slot 2 = basic, 3 = special;
    // category label → ingredient NAME). The prepared skill comes from the ACTIVE scent's skillGuid.
    const sb = lo.scentBottle ?? {}
    let licoricePreparedSkill: string | null = null
    const elixirIngredients: Record<number, Record<string, string>> = {}
    const scentToSlot = (scent: any, slotNo: number) => {
      if (!scent) return
      const bag: Record<string, string> = {}
      const put = (uuid: any, cat: string) => { const n = typeof uuid === 'string' ? ingredientTable[uuid] : null; if (n) bag[cat] = n }
      put(scent.damageIngredient, 'Damage Ingredient')
      put(scent.defenseIngredient, 'Defense Ingredient')
      put(scent.functionalIngredient, 'Functional Ingredient')
      for (const s of (scent.specialIngredients ?? [])) put(s, 'Special Ingredient')
      if (Object.keys(bag).length) elixirIngredients[slotNo] = bag
    }
    scentToSlot(sb.basic, 2)
    scentToSlot(sb.special, 3)
    // Prepared skill: prefer the ACTIVE scent's skill, else whichever scent defines one (Builder holds a single
    // licoricePreparedSkill; the active bottle may legitimately have none while the other does).
    const scentSkillGuid = [sb.activeScent === 'special' ? sb.special : sb.basic, sb.basic, sb.special]
      .map((s: any) => s?.skillGuid).find((g: any) => typeof g === 'string' && g)
    if (scentSkillGuid) {
      const sk = skills.get(scentSkillGuid)
      if (sk?.slug) licoricePreparedSkill = sk.slug
      else warnings.push(`${lo.name}: scent-bottle prepared skill not in crosswalk (guid ${scentSkillGuid})`)
    }

    const traitId = lo.hero?.heroGuid ? traits.get(lo.hero.heroGuid)?.slug ?? null : null
    // Hero-trait node selections (hero.traits level1/45/60/75 = Compendium node uuids). TREE traits feed
    // traitTreeAllocations (our node_ids); FIXED traits feed advancedTraitSelections (our advanced-trait
    // NAMES). The base node (level1) isn't a pick and simply isn't in the crosswalk, so it maps to neither.
    const traitTreeAllocations: string[] = []
    const advancedTraitSelections: string[] = []
    for (const sel of Object.values(lo.hero?.traits ?? {})) {
      const n = sel ? traitNodes[sel as string] : undefined
      if (!n?.builderNodeId) continue
      if (n.treeMode) traitTreeAllocations.push(n.builderNodeId)
      else advancedTraitSelections.push(n.builderNodeId)
    }

    // Record every source entity that had an id but no crosswalk match (so nothing vanishes silently),
    // plus best-guess imports the user should verify. Tagged by loadout name.
    const warn = (m: string) => warnings.push(`${lo.name}: ${m}`)
    for (const s of (lo.skills?.activeSkills ?? [])) {
      if (s?.skillGuid && !skills.get(s.skillGuid)) warn(`active skill not in crosswalk — dropped (guid ${s.skillGuid})`)
      for (const sup of (s?.supports ?? [])) if (sup?.supportGuid && !skills.get(sup.supportGuid)) warn(`support gem not in crosswalk — dropped (guid ${sup.supportGuid})`)
    }
    for (const s of (lo.skills?.passiveSkills ?? [])) if (s?.skillGuid && !skills.get(s.skillGuid)) warn(`passive skill not in crosswalk — dropped (guid ${s.skillGuid})`)
    for (const p of (lo.pactspirits ?? [])) if (p?.guid && !spirits.get(p.guid)) warn(`pact spirit not in crosswalk — dropped (guid ${p.guid})`)
    for (const g of (lo.gear?.inventory ?? [])) {
      if (g.rarity === 'Legendary' && g.legendaryItem?.legendaryId && !legendaries.get(g.legendaryItem.legendaryId))
        warn(`legendary "${g.legendaryItem?.name ?? g.legendaryItem.legendaryId}" not in crosswalk — imported without affixes`)
    }
    for (const m of (lo.heroMemories?.inventory ?? [])) {
      const chk = (sel: any, label: string) => { if (sel?.guid && !memAffix.get(sel.guid)) warn(`hero-memory ${label} affix not in crosswalk — dropped (guid ${sel.guid})`) }
      chk(m.baseStat, 'base'); (m.fixedAffixes ?? []).forEach((x: any) => chk(x, 'fixed')); (m.randomAffixes ?? []).forEach((x: any) => chk(x, 'random'))
      if (m.memoryType && !['origin', 'discipline', 'progress'].includes(String(m.memoryType).toLowerCase()))
        warn(`hero memory has unexpected type "${m.memoryType}" — will be dropped on import`)
    }
    for (const s of (lo.divinity?.inventory ?? [])) for (const a of (s.affixes ?? []))
      if (a.modGuid && !slateMods.get(a.modGuid)) warn(`slate modifier not in crosswalk — slot left empty (guid ${a.modGuid})`)
    if (lo.hero?.heroGuid && !traits.get(lo.hero.heroGuid)) warn(`hero trait not in crosswalk — dropped (guid ${lo.hero.heroGuid})`)
    // Surface any picked trait node (45/60/75) that had no crosswalk match, so a dropped advanced selection
    // isn't silent. level1 is the always-on base node (not a pick) and legitimately maps to nothing.
    for (const [tier, sel] of Object.entries(lo.hero?.traits ?? {})) {
      if (tier !== 'level1' && typeof sel === 'string' && sel && !traitNodes[sel]) warn(`hero-trait ${tier} selection not in crosswalk — dropped (node ${sel})`)
    }
    // Moth/Space Rift slates: Compendium ships no copy-direction, so ours is a best guess — flag for review.
    for (const sl of slates) if ((sl as any).mothDirection) warn(`"${(sl as any).kind}" slate copy-direction is a best guess (Compendium omits it) — verify/adjust it in Builder`)

    // Base slot present in source but unmappable (memory or host slot missing) — surface, don't drop silently.
    if (special && typeof special.memoryId === 'string' && !baseMemory)
      warn(`base/special memory slot could not be mapped (memory ${special.memoryId} / sourceSlot ${special.sourceSlot}) — skipped`)
    return { traitId, traitTreeAllocations, advancedTraitSelections, slots, gear, skills: emittedSkills, pactSpirits, fates, heroMemories, baseMemory, memoryInventory, slates, prisms, prismInventory, licoricePreparedSkill, elixirIngredients }
  }

  // Convert EVERY populated loadout → one Build with Builder loadouts (each Compendium loadout
  // becomes a loadout in our system, sharing one build code).
  const converted = populated.map((lo: any) => ({ lo, f: loadoutFields(lo) }))
  const defaultTarget = { level: 85, armor: 50, fireRes: 30, coldRes: 30, lightningRes: 30, erosionRes: 30 }
  // Warnings ride in the notes so they're visible in Builder after import (nothing dropped silently);
  // until Builder has a dedicated warnings/issues panel, this is the surface the user sees.
  const warnSuffix = warnings.length
    ? `\n\n⚠ Import warnings (${warnings.length}) — items TLI Compendium had that could not be mapped (dropped), or best-guess imports to verify:\n` + warnings.map((w) => `• ${w}`).join('\n')
    : ''
  const buildNotes = `Converted from TLI Compendium build "${src.name}" (patch ${src.patch}). Loadouts: ${populated.map((l: any) => l.name).join(', ')}.${warnSuffix}`
  // Group a loadout's fields into the per-area snapshots Builder's loadout system expects
  // (keys/shape must match utils/loadoutAreas.ts AREA_FIELDS exactly).
  // Emit ALL 13 areas (loadoutAreas.AREA_FIELDS) so a non-active loadout carries a complete snapshot,
  // exactly like native snapshotAllAreas — not just the 10 that have imported content.
  const areaData = (f: ReturnType<typeof loadoutFields>) => ({
    talents: { slots: f.slots, activeSlot: 0 },
    slates: { slates: f.slates, slateInventory: [] },   // slateInventory is now a per-loadout area field
    prisms: { prisms: f.prisms },   // placed prisms are per-loadout; prismInventory is build-global (top-level only)
    gear: { gear: f.gear },
    skills: { skills: f.skills },
    trait: { traitId: f.traitId, traitSlotLevels: [1, 1, 1, 1], advancedTraitSelections: f.advancedTraitSelections, traitTreeAllocations: f.traitTreeAllocations, traitSkillSupports: [], licoricePreparedSkill: f.licoricePreparedSkill, elixirIngredients: f.elixirIngredients },
    spirits: { pactSpirits: f.pactSpirits, fates: f.fates, undetermined: [null, null, null] },
    memories: { heroMemories: f.heroMemories, baseMemory: f.baseMemory, memoryInventory: f.memoryInventory },
    conditions: { conditionState: {} },
    level: { characterLevel: 100 },
    customMods: { customMods: [] },
    notes: { notes: buildNotes },   // same notes on every loadout (propagates across the build)
    target: { targetConfig: defaultTarget },
  })
  type Conv = { lo: any; f: ReturnType<typeof loadoutFields> }
  const loadouts = converted.map(({ lo, f }: Conv) => ({ id: lo.id, name: lo.name, inherit: {}, data: areaData(f) }))

  // Active loadout: the Compendium's current one if populated; else the requested filter; else most gear-complete.
  const currentId = src.loadouts?.currentLoadoutId
  const byName = loadoutFilter ? converted.find((c: Conv) => c.lo.name === loadoutFilter) : undefined
  const byCurrent = converted.find((c: Conv) => c.lo.id === currentId)
  const mostComplete = converted.slice().sort((a: Conv, b: Conv) => b.f.gear.length - a.f.gear.length)[0]!
  const active = byName ?? byCurrent ?? mostComplete
  const af = active.f

  // Flat top-level fields mirror the ACTIVE loadout (Builder's loadBuild spreads these directly as the live view).
  const build = {
    name: `${src.name} (imported)`,
    slots: af.slots, gear: af.gear, skills: af.skills, slates: af.slates,
    traitId: af.traitId, traitSlotLevels: [1, 1, 1, 1], advancedTraitSelections: af.advancedTraitSelections, traitTreeAllocations: af.traitTreeAllocations, traitSkillSupports: [], licoricePreparedSkill: af.licoricePreparedSkill, elixirIngredients: af.elixirIngredients,
    pactSpirits: af.pactSpirits, fates: af.fates, undetermined: [null, null, null],
    heroMemories: af.heroMemories, baseMemory: af.baseMemory, memoryInventory: af.memoryInventory,
    // prismInventory is build-GLOBAL (not a per-loadout area) — aggregate every loadout's crafted prisms, deduped by id.
    prisms: af.prisms,
    prismInventory: [...new Map(converted.flatMap((c: Conv) => c.f.prismInventory).map((p: any) => [p.id, p])).values()],
    slateInventory: [],
    conditionState: {}, characterLevel: 100, customMods: [],
    targetConfig: defaultTarget,
    notes: buildNotes,
    loadouts,
    activeLoadoutId: active.lo.id,
  }

  return {
    build, loadoutName: converted.map((c: Conv) => c.lo.name).join(', '), srcName: src.name, patch: src.patch,
    warnings,
    stats: {
      loadouts: converted.length,
      skills: af.skills.length, gear: af.gear.length, trees: af.slots.filter(Boolean).length,
      spirits: af.pactSpirits.filter(Boolean).length, slates: af.slates.length, memories: af.heroMemories.filter(Boolean).length,
      customizations: { mapped: customCov.mapped, total: customCov.total },
    },
  }
}
