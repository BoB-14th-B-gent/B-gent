import { contextBridge, ipcRenderer } from 'electron' 

contextBridge.exposeInMainWorld('api', {
  getPublicConfig: () => ipcRenderer.invoke('app:getPublicConfig'),
  openFileDialog: () => ipcRenderer.invoke('fs:openDialog'),
  request: (init: RequestInit & { path: string }) =>
    ipcRenderer.invoke('backend:request', init),
})