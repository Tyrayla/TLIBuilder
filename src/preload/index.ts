import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  getPythonPort: (): Promise<number> => ipcRenderer.invoke('get-python-port'),
  apiRequest: (method: string, path: string, body?: unknown): Promise<{ ok: boolean; status: number; data: unknown }> =>
    ipcRenderer.invoke('api-request', { method, path, body }),
  apiFormUpload: (path: string, fileBytes: Uint8Array, fileName: string): Promise<{ ok: boolean; status: number; data: unknown }> =>
    ipcRenderer.invoke('api-form-upload', path, fileBytes, fileName),
  isVerbose: process.env.VERBOSE === 'true',
  notifyDirty: (dirty: boolean) => ipcRenderer.send('dirty-change', dirty),
  onRequestSave: (callback: () => void) => ipcRenderer.on('request-save', callback),
  notifySaveDone: () => ipcRenderer.send('save-done'),
})
