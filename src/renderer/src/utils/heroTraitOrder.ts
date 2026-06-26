// Community "slang" names for hero traits (e.g. "Thea 1"), which the community uses to refer to traits by their
// per-hero release order. Keyed by trait_id. Used to label + sort the Hero Trait dropdown so players can identify
// traits by their shorthand. `order` is the global release order (heroes fall into release order, ascending within
// a hero). Single-trait heroes show just the hero name. See _hero_traits.json for the trait_id slugs.
export interface HeroTraitSlang {
  slang: string
  order: number
}

export const HERO_TRAIT_ORDER: Record<string, HeroTraitSlang> = {
  anger: { slang: 'Rehan 1', order: 1 },
  seething_silhouette: { slang: 'Rehan 2', order: 2 },
  wisdom_of_the_gods: { slang: 'Thea 1', order: 3 },
  incarnation_of_the_gods: { slang: 'Thea 2', order: 4 },
  blasphemer: { slang: 'Thea 3', order: 5 },
  blast_nova: { slang: 'Bing 1', order: 6 },
  creative_genius: { slang: 'Bing 2', order: 7 },
  order_calling: { slang: 'Moto 1', order: 8 },
  charge_calling: { slang: 'Moto 2', order: 9 },
  ice_fire_fusion: { slang: 'Gemma 1', order: 10 },
  frostbitten_heart: { slang: 'Gemma 2', order: 11 },
  flame_of_pleasure: { slang: 'Gemma 3', order: 12 },
  growing_breeze: { slang: 'Iris 1', order: 13 },
  vigilant_breeze: { slang: 'Iris 2', order: 14 },
  high_court_chariot: { slang: 'Rosa 1', order: 15 },
  unsullied_blade: { slang: 'Rosa 2', order: 16 },
  ranger_of_glory: { slang: 'Carino 1', order: 17 },
  lethal_flash: { slang: 'Carino 2', order: 18 },
  zealot_of_war: { slang: 'Carino 3', order: 19 },
  licorice_note: { slang: 'Sage', order: 20 },
  wind_stalker: { slang: 'Erika 1', order: 21 },
  lightning_shadow: { slang: 'Erika 2', order: 22 },
  vendetta_s_sting: { slang: 'Erika 3', order: 23 },
  sing_with_the_tide: { slang: 'Selena', order: 24 },
  spacetime_illusion: { slang: 'Youga 1', order: 25 },
  spacetime_elapse: { slang: 'Youga 2', order: 26 },
}

/** Community slang for a trait (e.g. "Thea 1"), or null if unmapped (new trait not yet listed). */
export function traitSlang(traitId: string | null | undefined): string | null {
  return (traitId && HERO_TRAIT_ORDER[traitId]?.slang) || null
}

/** Global release-order index for sorting; unmapped traits sort last. */
export function traitOrder(traitId: string | null | undefined): number {
  return (traitId && HERO_TRAIT_ORDER[traitId]?.order) || 999
}
