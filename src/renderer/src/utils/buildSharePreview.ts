import { SharePreview } from '../api/client'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'

// The share service's icon_url allowlist is deliberately kept strict to ONLY this CDN (see that
// service's config.py) — never widened to trust a third-party origin, even one the app itself
// already loads images from elsewhere. A record whose icon hasn't been rehosted here yet just
// gets no icon in the preview rather than the field being sent and rejected — see buildSharePreview.
const PREVIEW_ICON_ALLOWED_PREFIX = 'https://tlibuilder-data.pages.dev/icons/'

// Snapshots the already-computed values the Stats screen is currently showing into a small
// display-only summary, sent once alongside the code at share time (never recomputed server-side
// — see share.ts's SharePreview docstring). `skipReason` set (and `preview` absent) means the
// snapshot couldn't be built — the caller surfaces that in the UI (not just the console, which is
// often impractical to check) but never treats it as a reason to block the share itself.
export function buildSharePreview(): { preview?: SharePreview; skipReason?: string } {
  try {
    const build = useBuildStore.getState()
    const { defense, offense, stats } = build.computedStats
    if (!defense || !offense) {
      return { skipReason: "Stats hadn't finished computing yet — try again in a moment." }
    }

    const heroTraits = useReferenceStore.getState().heroTraits
    const trait = heroTraits?.find(t => t.trait_id === build.traitId)
    if (!trait) {
      return { skipReason: `The selected hero trait ("${build.traitId}") wasn't found in the loaded catalog.` }
    }

    // Records carry a full CDN icon_url (see api/client.ts's iconUrl() comment) — used as-is here,
    // deliberately NOT run through iconUrl(), which rewrites it to the desktop app's local backend
    // host for offline asset serving. But not every record has actually been rehosted to OUR CDN
    // yet — some still carry their original third-party source URL (e.g. cdn.tlidb.com) directly.
    // Omit the icon rather than sending (and having the whole preview rejected for) a URL the share
    // service's allowlist will never accept — the stats are still worth sharing without an image.
    const icon_url = trait.icon_url?.startsWith(PREVIEW_ICON_ALLOWED_PREFIX) ? trait.icon_url : undefined

    return {
      preview: {
        hero: trait.hero,
        trait: trait.variant_name,
        level: build.characterLevel,
        main_skill: offense.skill_name,
        icon_url,
        max_life: defense.max_life,
        max_mana: defense.max_mana,
        max_energy_shield: defense.max_energy_shield,
        total_dps: offense.total_dps_vs_target,
        fire_resist: defense.fire_resist,
        cold_resist: defense.cold_resist,
        lightning_resist: defense.lightning_resist,
        erosion_resist: defense.erosion_resist,
        movement_speed: stats['movement_speed']?.total ?? 0,
      },
    }
  } catch (e) {
    // Fail-soft — see handleShare's comment. A snapshot problem must never block a share.
    return { skipReason: `Unexpected error building the preview: ${e instanceof Error ? e.message : String(e)}` }
  }
}
