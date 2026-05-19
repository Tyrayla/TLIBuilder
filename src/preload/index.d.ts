declare global {
  interface Window {
    api: {
      getPythonPort: () => Promise<number>
      isVerbose: boolean
    }
  }
}

export {}
