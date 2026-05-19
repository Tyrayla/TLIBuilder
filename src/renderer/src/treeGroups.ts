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

type SlotLike = { treeName: string } | null

export function autoAssignSlot(treeName: string, slots: SlotLike[]): number {
  // Step 1: slot 0 must be a primary, nothing else selectable until it's filled
  if (!slots[0]) {
    return isPrimary(treeName) ? 0 : -1
  }
  // Only one primary allowed total
  if (isPrimary(treeName)) return -1

  // Step 2: slot 1 must be a subtree of slot 0's primary; nothing else until it's filled
  if (!slots[1]) {
    return getSubtrees(slots[0].treeName).includes(treeName) ? 1 : -1
  }

  // Step 3+: slots 2/3 open for anything
  if (!slots[2]) return 2
  if (!slots[3]) return 3
  return -1
}

export function canAddTree(treeName: string, slots: SlotLike[]): boolean {
  if (slots.some(s => s?.treeName === treeName)) return false
  return autoAssignSlot(treeName, slots) !== -1
}

const SLOT_NAMES = ['Slot 1', 'Slot 2', 'Slot 3', 'Slot 4']

export function validateSlotDrop(
  treeName: string,
  targetSlot: number,
  slots: SlotLike[]
): string | null {
  if (slots[targetSlot]) return `${SLOT_NAMES[targetSlot]} is already filled — remove it first`

  const alreadyAt = slots.findIndex(s => s?.treeName === treeName)
  if (alreadyAt !== -1) return `${treeName} is already in ${SLOT_NAMES[alreadyAt]}`

  if (targetSlot === 0) {
    if (!isPrimary(treeName)) return 'Only a God or Goddess can go in Slot 1'
    return null
  }
  if (targetSlot === 1) {
    if (!slots[0]) return 'Add a God or Goddess to Slot 1 first'
    if (isPrimary(treeName)) return 'Slot 2 must be a Subtree, not a Primary'
    if (!getSubtrees(slots[0].treeName).includes(treeName))
      return `${treeName} is not a Subtree of ${slots[0].treeName}`
    return null
  }
  if (!slots[0]) return 'Add a God or Goddess to Slot 1 first'
  if (!slots[1]) return 'Add a Subtree to Slot 2 first'
  if (isPrimary(treeName)) return 'Slots 3 and 4 are for Subtrees only'
  if (targetSlot === 3 && !slots[2]) return 'Fill Slot 3 before Slot 4'
  return null
}

export function isValidBuildState(slots: SlotLike[]): boolean {
  for (let i = 0; i < slots.length; i++) {
    const slot = slots[i]
    if (!slot) continue
    const { treeName } = slot
    if (i === 0 && !isPrimary(treeName)) return false
    if (i === 1) {
      if (!slots[0] || isPrimary(treeName)) return false
      if (!getSubtrees(slots[0].treeName).includes(treeName)) return false
    }
    if (i >= 2) {
      if (!slots[0] || !slots[1] || isPrimary(treeName)) return false
    }
    if (i === 3 && !slots[2]) return false
  }
  return true
}

export function findShiftCandidate(slots: SlotLike[]): { treeName: string; fromSlot: number } | null {
  const primary = slots[0]?.treeName
  if (!primary || slots[1]) return null
  const subtrees = getSubtrees(primary)
  for (const i of [2, 3] as const) {
    const candidate = slots[i]?.treeName
    if (candidate && subtrees.includes(candidate)) {
      return { treeName: candidate, fromSlot: i }
    }
  }
  return null
}
