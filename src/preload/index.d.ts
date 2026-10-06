declare global {
  interface Window {
    api?: {
      getPythonPort: () => Promise<number>
      apiRequest: (method: string, path: string, body?: unknown) => Promise<{ ok: boolean; status: number; data: unknown }>
      reportRequest: (body: unknown) => Promise<{ ok: boolean; status: number; data: unknown }>
      // Hosted-account bridge. The main process owns the session token (Electron safeStorage); the
      // renderer only ever sees request results.
      accountRequest: (method: string, path: string, body?: unknown) => Promise<{ ok: boolean; status: number; data: unknown }>
      syncRecordsRead: () => Promise<{ localBuildId: string; accountUserId: string; cloudBuildId: string; baseRevisionId: string; baseSemanticHash: string }[]>
      syncRecordsPut: (record: { localBuildId: string; accountUserId: string; cloudBuildId: string; baseRevisionId: string; baseSemanticHash: string }) => Promise<void>
      syncRecordsRemove: (localBuildId: string) => Promise<void>
      accountSignIn: () => Promise<{ ok: boolean; error?: string }>
      accountSignOut: () => Promise<void>
      accountReauth: (authorizeUrl: string) => Promise<{ ok: boolean; error?: string }>
      getIsDev: () => Promise<boolean>
      isVerbose: boolean
      notifyDirty: (dirty: boolean) => void
      onRequestSave: (callback: () => void) => void
      notifySaveDone: () => void
      onUpdateAvailable: (cb: (info: { version: string; releaseNotes: string; releaseDate: string }) => void) => void
      onUpdateProgress: (cb: (pct: number) => void) => void
      onUpdateDownloaded: (cb: () => void) => void
      downloadUpdate: () => Promise<void>
      installUpdate: () => Promise<void>
      getAppVersion: () => Promise<string>
      checkForUpdate: () => Promise<void>
      openExternal: (url: string) => Promise<void>
      onUpdateNotAvailable: (cb: () => void) => void
      onUpdateCheckError: (cb: (msg: string) => void) => void
      getSettings: () => Promise<AppSettings>
      setSetting: (key: keyof AppSettings, value: unknown) => Promise<AppSettings>
      onDeepLinkShare: (cb: (shareId: string) => void) => void
    }
  }
}

export interface AppSettings {
  updateChannel: 'stable' | 'nightly'
  numberSeparator?: 'commas' | 'decimals'
  decimalPrecision?: number
}

export {}
