declare global {
  interface Window {
    api?: {
      getPythonPort: () => Promise<number>
      apiRequest: (method: string, path: string, body?: unknown) => Promise<{ ok: boolean; status: number; data: unknown }>
      apiFormUpload: (path: string, fileBytes: Uint8Array, fileName: string) => Promise<{ ok: boolean; status: number; data: unknown }>
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
    }
  }
}

export {}
