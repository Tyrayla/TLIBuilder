// Single source of truth for build-import compatibility checks. Previously duplicated in
// ImportExportOverlay and BuildSelectScreen, which let the two KNOWN_BUILD_KEYS sets drift out of sync
// (each was missing different current fields, so valid builds were flagged as "older format"). Keep this
// list current whenever a new top-level build field is added (see CLAUDE.md: Build interface + KNOWN_BUILD_KEYS).

export const KNOWN_BUILD_KEYS = new Set<string>([
  'name', 'id', 'slots', 'slates', 'slateInventory', 'prisms', 'prismInventory', 'conditionState',
  // Legacy keys — present on builds saved before the conditionState unification.
  'conditions', 'conditionValues', 'hasPrism', 'traitLevel',
  'gear', 'skills', 'characterLevel', 'traitId', 'traitSlotLevels', 'advancedTraitSelections',
  'heroMemories', 'pactSpirits', 'notes', 'customMods',
  // Current fields (loadouts, pact fates/kismets, per-loadout target config, trait skill supports).
  'loadouts', 'activeLoadoutId', 'fates', 'undetermined', 'targetConfig', 'traitSkillSupports',
  'licoricePreparedSkill', 'elixirIngredients',
])

/** Surface any problems with a pasted/imported build (missing tree, unmatched gear, unknown fields). */
export function checkBuildCompatibility(build: Record<string, unknown>): string[] {
  const issues: string[] = []
  if (!Array.isArray(build.slots)) issues.push('Slots data is missing or unreadable.')
  else if ((build.slots as unknown[]).every(s => !s)) issues.push('Build has no tree slots selected.')
  if (Array.isArray(build.gear)) {
    const unmatched = (build.gear as Record<string, unknown>[]).filter(g => !Array.isArray(g.affixes))
    if (unmatched.length) {
      const names = unmatched.map(g => (g.name ?? g.item_id ?? 'Unknown') as string).join(', ')
      issues.push(`${unmatched.length} gear item(s) not found in current season data and will contribute no stats: ${names}`)
    }
  }
  const unknown = Object.keys(build).filter(k => !KNOWN_BUILD_KEYS.has(k))
  if (unknown.length) issues.push(`Unrecognized fields (older format): ${unknown.join(', ')}`)
  return issues
}
