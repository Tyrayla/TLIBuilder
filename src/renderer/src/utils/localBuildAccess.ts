// Bridges cloud sync to the local build library (desktop backend files or the web Pyodide store)
// through the existing api.* calls. The sync record never touches the build itself.
import type { LocalBuildAccess } from './cloudSync'
import { semanticBuildHash } from './sync'

export function createLocalBuildAccess(api: {
  getBuilds: () => Promise<unknown[]>
  postBuild: (build: never) => Promise<unknown>
  encodeBuildCode: (build: never) => Promise<{ code: string }>
  decodeBuildCode: (code: string) => Promise<{ build: Record<string, unknown> }>
}): LocalBuildAccess {
  async function find(localBuildId: string): Promise<Record<string, unknown>> {
    const builds = (await api.getBuilds()) as Record<string, unknown>[]
    const found = builds.find((b) => b.id === localBuildId)
    if (!found) throw new Error(`Local build not found: ${localBuildId}`)
    return found
  }
  const post = (build: Record<string, unknown>) => api.postBuild(build as never) as Promise<Record<string, unknown>>

  return {
    async read(localBuildId) {
      const build = await find(localBuildId)
      const { code } = await api.encodeBuildCode(build as never)
      return { name: String(build.name ?? ''), code, hash: await semanticBuildHash(code) }
    },

    async rename(localBuildId, name) {
      await post({ ...(await find(localBuildId)), name })
    },

    async createFromCloud(code, name) {
      const { build } = await api.decodeBuildCode(code)
      const saved = await post({ ...build, id: undefined, name })
      if (typeof saved.id !== 'string') throw new Error('The local save did not return a build id.')
      return saved.id
    },

    async replaceFromCloud(localBuildId, code, name) {
      const { build } = await api.decodeBuildCode(code)
      await post({ ...build, id: localBuildId, name })
    },
  }
}
