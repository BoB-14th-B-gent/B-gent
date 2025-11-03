// ESM에서 __dirname/__filename 폴리필
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

import { app, BrowserWindow, ipcMain, dialog, shell } from 'electron'
import fs from 'node:fs'
import dotenv from 'dotenv'

// dev/prod 모두에서 .env 탐색 로드
const tryEnvPaths = [
  path.resolve(app.getAppPath(), '..', '.env'),
  path.resolve(__dirname, '../../.env'),
]
for (const p of tryEnvPaths) {
  if (fs.existsSync(p)) {
    dotenv.config({ path: p })
    break
  }
}

let win: BrowserWindow | null = null

async function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: '#111827',
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // ⚠️ desktop의 Vite가 주입하는 VITE_DEV_SERVER_URL(5175)은 무시한다.
  //    항상 renderer(React) dev 서버(5173)를 보도록 고정.
  const rendererUrl = process.env.RENDERER_URL || 'http://localhost:5173'

  if (app.isPackaged) {
    // 배포 모드: renderer의 빌드 산출물을 로드
    await win.loadFile(path.join(__dirname, '../../renderer/index.html'))
  } else {
    console.log('[main] loading renderer from:', rendererUrl)
    await win.loadURL(rendererUrl)
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
}

/* ───────────── IPC 예시들 ───────────── */

ipcMain.handle('app:getPublicConfig', () => ({
  appName: process.env.APP_NAME ?? 'B-Gent',
}))

ipcMain.handle('fs:openDialog', async () => {
  const res = await dialog.showOpenDialog(win!, { properties: ['openFile'] })
  return res.canceled ? null : res.filePaths[0]
})

ipcMain.handle(
  'backend:request',
  async (_e, init: RequestInit & { path: string }) => {
    const base = process.env.BACKEND_URL ?? 'http://localhost:8000'
    const res = await fetch(base + init.path, init)
    const json = await res.json().catch(() => ({}))
    return { status: res.status, json }
  }
)

/* ───────────── 앱 수명주기 ───────────── */

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})