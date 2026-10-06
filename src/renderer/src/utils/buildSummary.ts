// One-line facts about an encoded build for the conflict screen: hero and main skill.
import type { HeroTrait } from '../api/client'
import { decodeBuildCodeLean } from './decodeBuildCodeLean'
import { characterSummary } from './characterSummary'

export interface CodeSummary {
  hero: string | null
  mainSkill: string | null
}

export async function summarizeCode(code: string, heroTraits: HeroTrait[] | null): Promise<CodeSummary> {
  try {
    const build = await decodeBuildCodeLean(code)
    const hero = characterSummary(
      { traitId: typeof build.traitId === 'string' ? build.traitId : null },
      heroTraits,
    ).identity
    const skills = Array.isArray(build.skills) ? (build.skills as { slot?: unknown; name?: unknown; enabled?: unknown }[]) : []
    const active = skills
      .filter((s) => typeof s?.slot === 'number' && s.slot >= 1 && s.slot <= 5 && s.enabled !== false && typeof s.name === 'string')
      .sort((a, b) => (a.slot as number) - (b.slot as number))
    return { hero, mainSkill: active.length > 0 ? (active[0].name as string) : null }
  } catch {
    return { hero: null, mainSkill: null }
  }
}
