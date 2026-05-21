import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  getPythonPort: (): Promise<number> => ipcRenderer.invoke('get-python-port'),
  isVerbose: process.env.VERBOSE === 'true',
  notifyDirty: (dirty: boolean) => ipcRenderer.send('dirty-change', dirty),
  onRequestSave: (callback: () => void) => ipcRenderer.on('request-save', callback),
  notifySaveDone: () => ipcRenderer.send('save-done'),
})
