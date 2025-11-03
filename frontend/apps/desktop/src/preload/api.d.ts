export {}
declare global {
  interface Window {
    api: {
      getPublicConfig: () => Promise<{ appName: string }>
      openFileDialog: () => Promise<string | null>
      request: (init: RequestInit & { path: string }) =>
        Promise<{ status: number; json: any }>
    }
  }
}