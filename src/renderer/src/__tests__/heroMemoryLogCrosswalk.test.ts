import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

type MemoryCrosswalk = {
  base_stats: { log_modifier_id: string; source: string; stat_name: string }[]
  affixes: {
    log_modifier_id: string
    source: string
    group: 'fixed_affixes' | 'random_affixes'
    affix_uuid: string
    tier?: number
  }[]
  _meta: {
    unmapped_affix_families: { group: string; uuid: string; sources: string[] }[]
  }
}

type MemoryCatalog = {
  base_stats: { source: string; modifier: string; uuid: string }[]
  fixed_affixes: { source: string; modifier: string; uuid: string; tier: number }[]
  random_affixes: { source: string; modifier: string; uuid: string; tier: number }[]
}

const seasonDir = resolve(process.cwd(), 'data/seasons/SS14')
const crosswalk = JSON.parse(readFileSync(resolve(seasonDir, '_hero_memory_log_crosswalk.json'), 'utf8')) as MemoryCrosswalk
const catalog = JSON.parse(readFileSync(resolve(seasonDir, '_hero_memories.json'), 'utf8')) as MemoryCatalog
const legacyRows = JSON.parse(readFileSync(resolve(process.cwd(), 'data/crosswalk/SS13/memory-affixes.json'), 'utf8')).rows as {
  name: string
  compendium: { gameId: string }
}[]

function normalizedModifier(value: string): string {
  return value.normalize('NFKC').replace(/\s+/g, '').replace(/[−–—]/g, '-').toLowerCase()
}

function normalizedFamily(value: string): string {
  return normalizedModifier(value).replace(/[+-]?\d+(?:\.\d+)?/g, '#')
}

function statName(modifier: string): string {
  return modifier.replace(/^\s*[+-]?\d+(?:\.\d+)?\s*%?\s*/, '').trim()
}

describe('SS14 Hero Memory log crosswalk', () => {
  it('maps every legacy memory ID to a current stat or affix family', () => {
    const mappedIds = new Set([
      ...crosswalk.base_stats.map(row => row.log_modifier_id),
      ...crosswalk.affixes.map(row => row.log_modifier_id),
    ])
    const missingIds = [...new Set(legacyRows.map(row => String(row.compendium.gameId)))].filter(id => !mappedIds.has(id))

    expect(missingIds).toEqual([])
  })

  it('does not contain duplicate or unknown ID mappings', () => {
    const knownIds = new Set(legacyRows.map(row => String(row.compendium.gameId)))
    const mappingKeys = [
      ...crosswalk.base_stats.map(row => `base|${row.log_modifier_id}|${row.source}|${row.stat_name}`),
      ...crosswalk.affixes.map(row => `affix|${row.log_modifier_id}|${row.source}|${row.group}|${row.affix_uuid}|${row.tier ?? ''}`),
    ]
    const additionalCurrentBaseIds = new Set(crosswalk.base_stats
      .map(row => row.log_modifier_id)
      .filter(id => !knownIds.has(id)))

    expect(mappingKeys.filter((key, index) => mappingKeys.indexOf(key) !== index)).toEqual([])
    expect(crosswalk.affixes.filter(row => !knownIds.has(row.log_modifier_id))).toEqual([])
    expect(crosswalk.base_stats.filter(row => !knownIds.has(row.log_modifier_id)
      && !additionalCurrentBaseIds.has(row.log_modifier_id))).toEqual([])
  })

  it('covers every SS14 affix family or documents the families without a known game ID', () => {
    const catalogFamilies = new Set(
      (['fixed_affixes', 'random_affixes'] as const).flatMap(group =>
        catalog[group].map(row => `${group}|${row.source}|${row.uuid}`)),
    )
    const mappedFamilies = new Set(crosswalk.affixes.map(row => `${row.group}|${row.source}|${row.affix_uuid}`))
    const documentedGaps = new Set(crosswalk._meta.unmapped_affix_families.flatMap(row =>
      row.sources.map(source => `${row.group}|${source}|${row.uuid}`)))
    const accountedFamilies = new Set([...mappedFamilies, ...documentedGaps])

    expect([...accountedFamilies].sort()).toEqual([...catalogFamilies].sort())
  })

  it('maps every SS14 base-stat family by source and stat name', () => {
    const catalogFamilies = new Set(catalog.base_stats.map(row => `${row.source}|${statName(row.modifier)}`))
    const mappedFamilies = new Set(crosswalk.base_stats.map(row => `${row.source}|${row.stat_name}`))
    const missingFamilies = [...catalogFamilies].filter(family => !mappedFamilies.has(family))
    const invalidMappings = crosswalk.base_stats.filter(row => !catalogFamilies.has(`${row.source}|${row.stat_name}`))

    expect(missingFamilies).toEqual([])
    expect(invalidMappings).toEqual([])
  })

  it('points each affix mapping at the matching current family and preserves exact legacy tiers', () => {
    for (const mapping of crosswalk.affixes) {
      const legacy = legacyRows.find(row => String(row.compendium.gameId) === mapping.log_modifier_id)
      const candidates = catalog[mapping.group].filter(row =>
        row.source === mapping.source && row.uuid === mapping.affix_uuid)

      expect(legacy).toBeDefined()
      expect(candidates.length).toBeGreaterThan(0)
      expect(candidates.some(row => normalizedFamily(row.modifier) === normalizedFamily(legacy!.name))).toBe(true)
      if (mapping.tier !== undefined) {
        expect(candidates.some(row => row.tier === mapping.tier)).toBe(true)
      }

      const exactTiers = new Set(candidates
        .filter(row => normalizedModifier(row.modifier) === normalizedModifier(legacy?.name ?? ''))
        .map(row => row.tier))
      if (exactTiers.size === 1) {
        expect(mapping.tier).toBe([...exactTiers][0])
      }
    }
  })
})
