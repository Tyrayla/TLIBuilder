export const GROUPS = [
  { primary: 'God of Might',         trees: ['The Brave', 'Onslaughter', 'Warlord', 'Warrior'] },
  { primary: 'Goddess of Hunting',   trees: ['Marksman', 'Bladerunner', 'Druid', 'Assassin'] },
  { primary: 'Goddess of Knowledge', trees: ['Magister', 'Arcanist', 'Elementalist', 'Prophet'] },
  { primary: 'God of War',           trees: ['Shadowdancer', 'Ronin', 'Ranger', 'Sentinel'] },
  { primary: 'Goddess of Deception', trees: ['Shadowmaster', 'Psychic', 'Warlock', 'Lich'] },
  { primary: 'God of Machines',      trees: ['Machinist', 'Steel Vanguard', 'Alchemist', 'Artisan'] },
]

export function isPrimary(treeName: string): boolean {
  return GROUPS.some(g => g.primary === treeName)
}

export function getSubtrees(primaryName: string): string[] {
  return GROUPS.find(g => g.primary === primaryName)?.trees ?? []
}

export function getPrimaryFor(treeName: string): string | null {
  for (const g of GROUPS) {
    if (g.trees.includes(treeName)) return g.primary
  }
  return null
}
