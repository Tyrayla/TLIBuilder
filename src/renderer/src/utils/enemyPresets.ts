// Enemy registry for the Config "Incoming Damage" editor — the enemy skills whose damage the defensive
// (Max-Hit / EHP) calc mitigates. STATIC data, owner-authored/owner-tested; the per-loadout EnemyIncomingConfig
// stores only the current selection + the (editable, prefilled) per-type damage. Mirrors utils/targetPresets.ts.
//
// Real enemy incoming-damage magnitudes are not in any dataset (owner measures them live). Until then the sole
// entry is a Test Enemy with a Test Attack + Test Spell prefilling 1000 per hit type, so the panel shows live math.
import type { EnemyIncomingConfig, EnemyDamage, EnemyDamageKind } from '../api/client'

export interface EnemySkillDef {
  id: string
  name: string
  kind: EnemyDamageKind
  damage: EnemyDamage
}
export interface EnemyDef {
  id: string
  name: string
  skills: EnemySkillDef[]
}

export const ZERO_DAMAGE: EnemyDamage = {
  phys_hit: 0, fire_hit: 0, cold_hit: 0, lightning_hit: 0, erosion_hit: 0,
  phys_dot: 0, fire_dot: 0, cold_dot: 0, lightning_dot: 0, erosion_dot: 0,
}

// The 1000-per-type placeholder hit. Editable in the UI; owner swaps in measured values later.
const testHit = (): EnemyDamage => ({
  ...ZERO_DAMAGE,
  phys_hit: 1000, fire_hit: 1000, cold_hit: 1000, lightning_hit: 1000, erosion_hit: 1000,
})

export const ENEMY_REGISTRY: EnemyDef[] = [
  {
    id: 'test_enemy',
    name: 'Test Enemy',
    skills: [
      { id: 'test_attack', name: 'Test Attack', kind: 'attack', damage: testHit() },
      { id: 'test_spell', name: 'Test Spell', kind: 'spell', damage: testHit() },
    ],
  },
]

export function findEnemy(enemyId: string): EnemyDef | undefined {
  return ENEMY_REGISTRY.find(e => e.id === enemyId)
}

export function findEnemySkill(enemyId: string, skillId: string): EnemySkillDef | undefined {
  return findEnemy(enemyId)?.skills.find(s => s.id === skillId)
}

// A full config for a given enemy+skill selection, prefilled from the registry (fresh damage copy so edits
// don't mutate the static registry). Falls back to the first enemy/skill if the ids don't resolve.
export function configForSelection(enemyId: string, skillId: string): EnemyIncomingConfig {
  const enemy = findEnemy(enemyId) ?? ENEMY_REGISTRY[0]
  const skill = enemy.skills.find(s => s.id === skillId) ?? enemy.skills[0]
  return { enemyId: enemy.id, skillId: skill.id, kind: skill.kind, damage: { ...skill.damage } }
}

export const DEFAULT_ENEMY_CONFIG: EnemyIncomingConfig = configForSelection('test_enemy', 'test_attack')

// Normalize a possibly-partial/legacy value into a full EnemyIncomingConfig (defaults to the Test Attack).
export function sanitizeEnemyConfig(t: unknown): EnemyIncomingConfig {
  const d = DEFAULT_ENEMY_CONFIG
  if (!t || typeof t !== 'object') return configForSelection(d.enemyId, d.skillId)
  const o = t as Record<string, unknown>
  const enemyId = typeof o.enemyId === 'string' ? o.enemyId : d.enemyId
  const skillId = typeof o.skillId === 'string' ? o.skillId : d.skillId
  const base = configForSelection(enemyId, skillId)
  // Keep any user-edited per-type damage overrides on top of the registry defaults.
  const num = (v: unknown, fb: number) => (typeof v === 'number' && isFinite(v) ? v : fb)
  const src = (o.damage && typeof o.damage === 'object' ? o.damage : {}) as Record<string, unknown>
  const damage: EnemyDamage = { ...base.damage }
  for (const k of Object.keys(base.damage) as (keyof EnemyDamage)[]) damage[k] = num(src[k], base.damage[k])
  const kind: EnemyDamageKind = o.kind === 'spell' || o.kind === 'attack' ? o.kind : base.kind
  return { enemyId: base.enemyId, skillId: base.skillId, kind, damage }
}
