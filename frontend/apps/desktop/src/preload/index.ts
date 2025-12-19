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

  notifyTotalReportLoaded: (payload: { stageId?: number; reportId?: string }) => {
    ipcRenderer.send('report:totalLoaded', payload)
  },

  onTotalReportLoaded: (cb: (payload: { stageId?: number; reportId?: string }) => void) => {
    const handler = (_evt: unknown, payload: { stageId?: number; reportId?: string }) => cb(payload)
    ipcRenderer.on('report:totalLoaded', handler)
    return () => ipcRenderer.removeListener('report:totalLoaded', handler)
  },

  openCaseWindow: (payload: { caseId?: string; conversationId?: string } = {}) =>
    ipcRenderer.invoke('case:open', payload),
})
