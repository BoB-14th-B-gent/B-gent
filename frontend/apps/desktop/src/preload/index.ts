import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('api', {
  getPublicConfig: () => ipcRenderer.invoke('app:getPublicConfig'),
  openFileDialog: () => ipcRenderer.invoke('fs:openDialog'),
  request: (init: RequestInit & { path: string }) => ipcRenderer.invoke('backend:request', init),

  openReportWindow: (payload: { reportId?: string } = {}) =>
    ipcRenderer.invoke('report:open', payload),

  saveFile: (opts: {
    data: string | Uint8Array
    defaultPath?: string
    filters?: { name: string; extensions: string[] }[]
  }) => ipcRenderer.invoke('fs:save', opts),

  quitApp: () => ipcRenderer.invoke('app:quit'),

  openCaseWindow: (payload: { caseId?: string; conversationId?: string } = {}) =>
    ipcRenderer.invoke('case:open', payload),
})
