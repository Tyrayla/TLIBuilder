import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  getPythonPort: (): Promise<number> => ipcRenderer.invoke('get-python-port'),
})
