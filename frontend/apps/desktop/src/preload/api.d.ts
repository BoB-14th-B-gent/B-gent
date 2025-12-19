export {}
declare global {
  interface Window {
    api: {
      getPublicConfig: () => Promise<{ appName: string }>
      openFileDialog: () => Promise<string | null>
      request: (init: RequestInit & { path: string }) => Promise<{ status: number; json: any }>
      saveFile: (opts: {
        data: string | Uint8Array
        defaultPath?: string
        filters?: { name: string; extensions: string[] }[]
      }) => Promise<string | undefined>
      openReportWindow?: (payload: { reportId?: string; stageId?: number }) => Promise<any> | void

      onTotalReportLoaded?: (
        cb: (payload: { stageId?: number; reportId?: string }) => void
      ) => () => void

      openCaseWindow?: (payload: {
        caseId?: string
        conversationId?: string
      }) => Promise<any> | void

      notifyTotalReportLoaded?: (payload: { stageId?: number; reportId?: string }) => void

      quitApp?: () => void
    }
  }
}
