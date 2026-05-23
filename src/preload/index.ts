import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  getPythonPort: (): Promise<number> => ipcRenderer.invoke('get-python-port'),
  apiRequest: (method: string, path: string, body?: unknown): Promise<{ ok: boolean; status: number; data: unknown }> =>
    ipcRenderer.invoke('api-request', { method, path, body }),
  apiFormUpload: (path: string, fileBytes: Uint8Array, fileName: string): Promise<{ ok: boolean; status: number; data: unknown }> =>
    ipcRenderer.invoke('api-form-upload', path, fileBytes, fileName),
  getIsDev: (): Promise<boolean> => ipcRenderer.invoke('get-is-dev'),
  isVerbose: process.env.VERBOSE === 'true',
  notifyDirty: (dirty: boolean) => ipcRenderer.send('dirty-change', dirty),
  onRequestSave: (callback: () => void) => ipcRenderer.on('request-save', callback),
  notifySaveDone: () => ipcRenderer.send('save-done'),
  onUpdateAvailable: (cb: (info: { version: string; releaseNotes: string; releaseDate: string }) => void) =>
    ipcRenderer.on('update-available', (_e, info) => cb(info)),
  onUpdateProgress: (cb: (pct: number) => void) =>
    ipcRenderer.on('update-download-progress', (_e, pct) => cb(pct)),
  onUpdateDownloaded: (cb: () => void) =>
    ipcRenderer.on('update-downloaded', () => cb()),
  downloadUpdate: () => ipcRenderer.invoke('download-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
})
