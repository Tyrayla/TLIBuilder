declare global {
  interface Window {
    api?: {
      getPythonPort: () => Promise<number>
      apiRequest: (method: string, path: string, body?: unknown) => Promise<{ ok: boolean; status: number; data: unknown }>
      apiFormUpload: (path: string, fileBytes: Uint8Array, fileName: string) => Promise<{ ok: boolean; status: number; data: unknown }>
      isVerbose: boolean
      notifyDirty: (dirty: boolean) => void
      onRequestSave: (callback: () => void) => void
      notifySaveDone: () => void
    }
  }
}

export {}
