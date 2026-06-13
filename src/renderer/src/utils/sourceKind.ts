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
  condition: 'Condition',
}

const COLORS: Record<string, string> = {
  Item: '#d99a4e',      // orange (item-name color)
  Base: '#8a8aa0',      // grey
  Tree: '#6fb86f',      // green
  Slate: '#5fa8c0',     // cyan
  Core: '#c08fe0',      // purple
  Custom: '#d06a9a',    // pink
  Support: '#7a9af0',   // blue
  Skill: '#e0c060',     // gold
  Spirit: '#b06fd0',    // violet
  Memory: '#6fc0b0',    // teal
  Condition: '#c08060', // brown
}

export function sourceKindLabel(sourceType: string | undefined | null): string {
  if (!sourceType) return 'Other'
  return LABELS[sourceType] ?? (sourceType.charAt(0).toUpperCase() + sourceType.slice(1))
}

export function sourceKindColor(sourceType: string | undefined | null): string {
  return COLORS[sourceKindLabel(sourceType)] ?? '#bbbbcc'
}
