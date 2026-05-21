declare global {
  interface Window {
    api: {
      getPythonPort: () => Promise<number>
      isVerbose: boolean
      notifyDirty: (dirty: boolean) => void
      onRequestSave: (callback: () => void) => void
      notifySaveDone: () => void
    }
  }
}

export {}
