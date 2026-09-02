// Maps an engine `source_type` to a short user-facing "Source" label + a color (Item names in orange,
// Base in grey, etc.). One place so the stat breakdown popup and any chips stay consistent.

const LABELS: Record<string, string> = {
  gear: 'Item',
  normal_gear: 'Item',
  legendary_gear: 'Item',
  character: 'Base',
  talent: 'Tree',
  slate: 'Slate',
  core_talent: 'Core',
  custom: 'Custom',
  support: 'Support',
  skill: 'Skill',
  pact_spirit: 'Spirit',
  hero_memory: 'Memory',
  hero_trait: 'Hero Trait',
  condition: 'Condition',
  warcry: 'Warcry',
}

// Gear (rarity/legendary via gearQualityColor) and Tree (per-tree branch color) are resolved per-row at the
// call site; these are the flat fallbacks + the colors for the remaining source types.
const COLORS: Record<string, string> = {
  Item: '#c8a050',      // gear fallback (legendary gold); real color comes from gearQualityColor
  Base: '#8a8aa0',      // grey
  Tree: '#6fb86f',      // fallback; real color is the tree's branch color
  Slate: '#5fc0d0',     // cyan
  Core: '#c08fe0',      // purple
  Custom: '#d06a9a',    // pink
  Support: '#7a9af0',   // blue
  Skill: '#e0c060',     // gold
  Spirit: '#b06fd0',    // violet
  Memory: '#6fc0b0',    // teal
  'Hero Trait': '#d0a860', // amber
  Condition: '#c08060', // brown
  Warcry: '#d88b3d',    // orange
}

export function sourceKindLabel(sourceType: string | undefined | null): string {
  if (!sourceType) return 'Other'
  return LABELS[sourceType] ?? (sourceType.charAt(0).toUpperCase() + sourceType.slice(1))
}

export function sourceKindColor(sourceType: string | undefined | null): string {
  return COLORS[sourceKindLabel(sourceType)] ?? '#bbbbcc'
}
