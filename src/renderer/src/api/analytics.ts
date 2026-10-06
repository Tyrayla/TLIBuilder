// Anonymous build-composition reporting transport. Deliberately separate from the account client:
// it sends no cookies, no Authorization header, and no referrer, so a report can never carry an
// account, session, or installation identifier. See docs/HOSTED_ACCOUNT_API_CONTRACT.md.
import { getShareBase } from './share'
import type { Composition } from '../utils/buildComposition'

const REQUEST_TIMEOUT_MS = 10_000

export function createAnalyticsClient(opts: { base?: string; fetchImpl?: typeof fetch } = {}) {
  const base = (opts.base ?? getShareBase()).replace(/\/+$/, '')
  const doFetch = opts.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args))

  return {
    async sendComposition(composition: Composition): Promise<void> {
      const res = await doFetch(`${base}/v1/stats/composition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
        referrerPolicy: 'no-referrer',
        body: JSON.stringify({
          data_version: composition.dataVersion,
          entities: composition.entities,
          relations: composition.relations.map((r) => ({ skill_id: r.skillId, support_id: r.supportId })),
          mechanics: composition.mechanics,
        }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      })
      if (!res.ok) throw new Error(`Composition report rejected (${res.status}).`)
    },
  }
}
