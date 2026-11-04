import { describe, expect, it } from 'vitest'
import zlib from 'node:zlib'
import type { LegendaryGearItem } from '../api/client'
import { decodeSharedBuildCode } from '../utils/decodeSharedBuild'
import { LeanBuildCodeError } from '../utils/decodeBuildCodeLean'

function encodeFixture(value: Record<string, unknown>): string {
  const compressed = zlib.deflateSync(Buffer.from(JSON.stringify(value), 'utf8'), { level: 9 })
  const payload = compressed.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `tli1_${payload}`
}

const catalog = [{
  item_id: 'itm_blade', name: 'Catalog Blade',
  variants: { base: { implicits: [], explicits: [] } }, random_affixes: {},
}] as unknown as LegendaryGearItem[]

describe('decodeSharedBuildCode', () => {
  it('decodes and rehydrates a current share code without Python', async () => {
    const code = encodeFixture({
      v: 2, id: 'must-not-overwrite-a-save', name: 'Shared Blade', gear: [
        { item_id: 'itm_blade', slot: 'weapon1' },
        { item_id: 'itm_crafted', is_crafted: true, affixes: [{ raw_text: 'crafted line' }] },
      ], skills: [],
    })

    const decoded = await decodeSharedBuildCode(code, catalog)
    expect(decoded).toEqual({
      name: 'Shared Blade',
      gear: [
        {
          ...catalog[0], slot: 'weapon1', customizations: [], affixes: [], implicit_count: 0,
        },
        { item_id: 'itm_crafted', is_crafted: true, affixes: [{ raw_text: 'crafted line' }] },
      ],
      skills: [],
    })
  })

  it('migrates v1 conditions to the v2 conditionState field', async () => {
    const code = encodeFixture({
      v: 1, conditions: ['enemy_frozen'], conditionValues: { distance: 3 }, gear: [], skills: [],
    })

    const decoded = await decodeSharedBuildCode(code, [])
    expect(decoded).toEqual({ gear: [], skills: [], conditionState: { enemy_frozen: true, distance: 3 } })
  })

  it('rejects malformed gear entries before they reach the editor', async () => {
    const code = encodeFixture({ v: 2, gear: [null], skills: [] })
    await expect(decodeSharedBuildCode(code, [])).rejects.toBeInstanceOf(LeanBuildCodeError)
  })
})
