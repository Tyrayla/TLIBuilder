import type { HeroTrait } from '../api/client'
import { characterLevelFrom } from './conditions'

// Character identity readout, like a class/ascendancy line: "Lv 90 Selena · Dance of the Deep".
// Level comes from the `level` condition (the single character-level source); the hero/trait
// names resolve through the season catalog, so an unknown/unloaded traitId degrades to level-only.
// Takes the minimal shape so it works on both saved builds (cards) and live store state (sidebar).
export function characterSummary(
  source: { traitId?: string | null; conditionState?: Record<string, number | boolean | string> },
  heroTraits: HeroTrait[] | null,
): { level: number; identity: string | null } {
  const level = characterLevelFrom(source.conditionState ?? {})
  const trait = source.traitId ? heroTraits?.find(t => t.trait_id === source.traitId) : null
  return { level, identity: trait ? `${trait.hero} · ${trait.variant_name}` : null }
}
