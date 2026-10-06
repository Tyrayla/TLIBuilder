// The cloud-sync controller wired to the running app's stores and local library.
import { api } from '../api/client'
import { getAccountsApi } from '../api/accounts'
import { getAccountStore } from '../store/accountStore'
import { useReferenceStore } from '../store/referenceStore'
import { createCloudSync, type CloudSync } from './cloudSync'
import { createLocalBuildAccess } from './localBuildAccess'
import { defaultSyncRecordStore } from './syncRecords'
import { semanticBuildHash } from './sync'

declare const __APP_VERSION__: string | undefined

let instance: CloudSync | null = null

export function getCloudSync(): CloudSync {
  if (!instance) {
    instance = createCloudSync({
      accounts: getAccountsApi(),
      records: defaultSyncRecordStore(),
      activeUserId: () => getAccountStore().getState().account?.userId ?? null,
      dataVersion: () => useReferenceStore.getState().season ?? '',
      appVersion: () => (typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : ''),
      local: createLocalBuildAccess({
        getBuilds: () => api.getBuilds(),
        postBuild: (build) => api.postBuild(build),
        encodeBuildCode: (build) => api.encodeBuildCode(build),
        decodeBuildCode: (code) => api.decodeBuildCode(code),
      }),
      hashOf: semanticBuildHash,
    })
  }
  return instance
}
