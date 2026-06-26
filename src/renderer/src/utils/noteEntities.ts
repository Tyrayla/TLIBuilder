// Note hyperlink entities: the `{{type:key}}` token grammar, build-first resolution, and the autocomplete index.
// Approach-agnostic (used by the Lexical editor's mention node + typeahead). Resolution prefers the CURRENT build's
// own entities, falling back to the generic catalogs. Returns a uniform shape so one EntityChip/tooltip renders all.
import type {
  EquippedGearItem, EquippedSkill, SelectedPactSpirit, CreatedHeroMemory, PactSpirit,
  SkillItem, LegendaryGearIndexItem, LegendaryGearItem, ConditionDef, HeroTrait,
} from '../api/client'
import { gearQualityColor } from './gearItem'
import { sourceKindColor } from './sourceKind'

export type NoteEntityType = 'item' | 'node' | 'skill' | 'cond' | 'trait' | 'spirit' | 'memory'

export interface NoteEntity {
  type: NoteEntityType
  key: string
  name: string
  color: string
  kindLabel: string      // "Item" / "Skill" / "Talent" / …
  lines: string[]        // tooltip body lines (best-effort)
  source: 'build' | 'catalog'
}

// A talent-node index entry (the build's trees are loaded by the editor and passed in — there's no global
// node catalog).
export interface NodeIndexEntry { key: string; name: string; lines: string[] }

export interface NoteResolveCtx {
  gear: EquippedGearItem[]
  skills: EquippedSkill[]
  pactSpirits: (SelectedPactSpirit | null)[]
  heroMemories: (CreatedHeroMemory | null)[]
  traitId: string | null
  allSpirits: PactSpirit[]
  nodes: NodeIndexEntry[]
  reference: {
    skillsById: Record<string, SkillItem> | null
    skillsByName: Record<string, SkillItem> | null
    legendaryIndex: LegendaryGearIndexItem[] | null
    legendaryCatalog: LegendaryGearItem[] | null
    conditions: Record<string, ConditionDef[]> | null
    heroTraits: HeroTrait[] | null
  }
}

const KIND: Record<NoteEntityType, string> = {
  item: 'Item', node: 'Talent', skill: 'Skill', cond: 'Condition', trait: 'Hero Trait', spirit: 'Pact Spirit', memory: 'Hero Memory',
}
const typeColor = (t: NoteEntityType): string => ({
  item: sourceKindColor('gear'), node: sourceKindColor('talent'), skill: sourceKindColor('skill'),
  cond: sourceKindColor('condition'), trait: sourceKindColor('hero_trait'),
  spirit: sourceKindColor('pact_spirit'), memory: sourceKindColor('hero_memory'),
}[t])

const MEMORY_LABEL: Record<string, string> = { origin: 'Origin', discipline: 'Discipline', progress: 'Progress' }

// ── Token grammar: {{type:key}} (key may contain anything but `}`) ───────────────
const TOKEN_RE = /\{\{(item|node|skill|cond|trait|spirit|memory):([^}]+)\}\}/g
export const tokenFor = (type: NoteEntityType, key: string): string => `{{${type}:${key}}}`

export type NoteSegment = { kind: 'text'; text: string } | { kind: 'token'; type: NoteEntityType; key: string }

// Split a notes string into prose + token segments (preserves all prose verbatim).
export function parseNoteSegments(text: string): NoteSegment[] {
  const out: NoteSegment[] = []
  let last = 0
  for (const m of text.matchAll(TOKEN_RE)) {
    const i = m.index ?? 0
    if (i > last) out.push({ kind: 'text', text: text.slice(last, i) })
    out.push({ kind: 'token', type: m[1] as NoteEntityType, key: m[2] })
    last = i + m[0].length
  }
  if (last < text.length) out.push({ kind: 'text', text: text.slice(last) })
  return out
}

// ── Resolution (build-first, then catalog) ───────────────────────────────────────
export function resolveNoteEntity(type: NoteEntityType, key: string, ctx: NoteResolveCtx): NoteEntity | null {
  const base = { type, key, kindLabel: KIND[type] }
  switch (type) {
    case 'item': {
      const g = ctx.gear.find(i => i.item_id === key)
      if (g) return { ...base, name: g.name, color: gearQualityColor(g), source: 'build',
        lines: [g.base_type ?? '', ...g.affixes.map(a => a.raw_text).filter(Boolean).slice(0, 10)].filter(Boolean) }
      // Catalog: the FULL legendary catalog carries the affixes (variants); the lightweight index has only base_type.
      const cat = ctx.reference.legendaryCatalog?.find(i => i.item_id === key || i.name === key)
      if (cat) {
        const variant = Object.values(cat.variants)[0]
        const affixes = variant ? [...variant.implicits, ...variant.explicits].map(a => a.raw_text).filter(Boolean) : []
        return { ...base, name: cat.name, color: '#c8a050', source: 'catalog', lines: [cat.base_type, ...affixes].filter(Boolean).slice(0, 12) }
      }
      const li = ctx.reference.legendaryIndex?.find(i => i.item_id === key || i.name === key)
      if (li) return { ...base, name: li.name, color: '#c8a050', source: 'catalog', lines: [li.base_type].filter(Boolean) }
      return null
    }
    case 'skill': {
      const s = ctx.skills.find(sk => sk.item_id === key)
      if (s) return { ...base, name: s.name, color: typeColor('skill'), source: 'build', lines: (s.description_lines ?? []).slice(0, 10) }
      const cat = ctx.reference.skillsById?.[key] ?? ctx.reference.skillsByName?.[key]
      if (cat) return { ...base, name: cat.name, color: typeColor('skill'), source: 'catalog', lines: (cat.description_lines ?? []).slice(0, 10) }
      return null
    }
    case 'node': {
      const n = ctx.nodes.find(x => x.key === key)
      if (n) return { ...base, name: n.name, color: typeColor('node'), source: 'build', lines: n.lines }
      return null
    }
    case 'cond': {
      const all = ctx.reference.conditions ? Object.values(ctx.reference.conditions).flat() : []
      const c = all.find(x => x.key === key)
      if (c) return { ...base, name: c.label, color: typeColor('cond'), source: 'catalog', lines: [c.category ?? ''].filter(Boolean) }
      return null
    }
    case 'trait': {
      const t = ctx.reference.heroTraits?.find(x => x.trait_id === key)
      if (t) return { ...base, name: t.variant_name || t.trait_id, color: typeColor('trait'),
        source: ctx.traitId === key ? 'build' : 'catalog', lines: [t.hero, t.description].filter(Boolean) }
      return null
    }
    case 'spirit': {
      const sp = ctx.allSpirits.find(x => x.item_id === key)
      const equipped = ctx.pactSpirits.some(p => p?.itemId === key)
      if (sp) return { ...base, name: sp.name, color: typeColor('spirit'), source: equipped ? 'build' : 'catalog', lines: [sp.description].filter(Boolean) }
      return null
    }
    case 'memory': {
      const m = ctx.heroMemories.find(x => x?.memoryType === key)
      if (m) return { ...base, name: `${MEMORY_LABEL[key] ?? key} Memory`, color: typeColor('memory'), source: 'build',
        lines: [m.rarity, ...(m.fixedAffixes ?? []).flatMap(a => a ? [a.modifier] : [])].filter(Boolean).slice(0, 10) }
      return null
    }
  }
}

// Unresolvable token → a red "unknown" chip (never silently dropped).
export function unknownEntity(type: NoteEntityType, key: string): NoteEntity {
  return { type, key, name: `${key} (unknown)`, color: '#ff6b6b', kindLabel: KIND[type] ?? 'Link', lines: ['Unresolved reference'], source: 'catalog' }
}

// ── Autocomplete index (build entries first, then catalog; deduped by type:key) ──
export function buildEntityIndex(ctx: NoteResolveCtx): NoteEntity[] {
  const out: NoteEntity[] = []
  const seen = new Set<string>()
  const push = (e: NoteEntity | null) => {
    if (!e) return
    const id = `${e.type}:${e.key}`
    if (seen.has(id)) return
    seen.add(id); out.push(e)
  }
  // Build entities first.
  ctx.gear.forEach(g => push(resolveNoteEntity('item', g.item_id, ctx)))
  ctx.skills.forEach(s => push(resolveNoteEntity('skill', s.item_id, ctx)))
  ctx.nodes.forEach(n => push({ type: 'node', key: n.key, name: n.name, color: typeColor('node'), kindLabel: 'Talent', lines: n.lines, source: 'build' }))
  ctx.pactSpirits.forEach(p => p && push(resolveNoteEntity('spirit', p.itemId, ctx)))
  ctx.heroMemories.forEach(m => m && push(resolveNoteEntity('memory', m.memoryType, ctx)))
  if (ctx.traitId) push(resolveNoteEntity('trait', ctx.traitId, ctx))
  // Catalog.
  ctx.reference.legendaryIndex?.forEach(li => push(resolveNoteEntity('item', li.item_id, ctx)))
  Object.values(ctx.reference.skillsById ?? {}).forEach(s => push(resolveNoteEntity('skill', s.item_id, ctx)))
  ctx.reference.heroTraits?.forEach(t => push(resolveNoteEntity('trait', t.trait_id, ctx)))
  if (ctx.reference.conditions) Object.values(ctx.reference.conditions).flat().forEach(c => {
    if (c.visible !== false) push(resolveNoteEntity('cond', c.key, ctx))
  })
  return out
}
