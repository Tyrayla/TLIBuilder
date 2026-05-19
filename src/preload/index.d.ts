declare global {
  interface Window {
    api: {
      getPythonPort: () => Promise<number>
    }
  }
}

export {}
