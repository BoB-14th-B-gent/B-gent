import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'
import { promises as fsp } from 'node:fs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

import { app, BrowserWindow, ipcMain, dialog, shell, nativeImage } from 'electron'
import dotenv from 'dotenv'

app.setName('B-GENT')

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

function getAssetPath(...p: string[]) {
  return app.isPackaged
    ? path.join(process.resourcesPath, ...p)
    : path.join(__dirname, '..', '..', ...p)
}

function getPreloadPath() {
  return path.join(__dirname, '../preload/index.mjs')
}

function getRendererUrl(): string {
  return process.env.RENDERER_URL || 'http://localhost:5173'
}

let win: BrowserWindow | null = null
let splash: BrowserWindow | null = null

function createMainWindow() {
  const iconPath = getAssetPath('assets', 'icon.png')
  const appIcon = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath) : undefined

  const w = new BrowserWindow({
    show: false,
    width: 1280,
    height: 800,
    backgroundColor: '#111827',
    icon: appIcon,
    webPreferences: {
      preload: getPreloadPath(),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (process.platform === 'darwin' && appIcon) {
    app.dock?.setIcon(appIcon)
  }

  if (app.isPackaged) {
    const html = getAssetPath('renderer', 'index.html')
    void w.loadFile(html)
  } else {
    const url = getRendererUrl()
    console.log('[main] loading renderer from:', url)
    void w.loadURL(url)
  }

  w.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  return w
}

function createReportWindow(payload: { reportId?: string } = {}) {
  const w = new BrowserWindow({
    show: false,
    width: 1280,
    height: 900,
    backgroundColor: '#111827',
    title: 'B-GENT Report',
    webPreferences: {
      preload: getPreloadPath(),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  const search = new URLSearchParams()
  if (payload.reportId) search.set('reportId', payload.reportId)

  if (app.isPackaged) {
    const html = getAssetPath('renderer', 'index.html')
    const base = pathToFileURL(html).toString()
    const target = `${base}#/report-window?${search.toString()}`
    void w.loadURL(target)
  } else {
    const base = getRendererUrl()
    const target = `${base}#/report-window?${search.toString()}`
    console.log('[main] loading report window:', target)
    void w.loadURL(target)
  }

  w.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  w.once('ready-to-show', () => w.show())
  return w
}

function createSplashWindow() {
  const splashHtmlDev = getAssetPath('assets', 'splash', 'index.html')
  const splashUrl = pathToFileURL(splashHtmlDev).toString()

  const s = new BrowserWindow({
    show: false,
    width: 520,
    height: 360,
    frame: false,
    transparent: false,
    resizable: false,
    backgroundColor: '#142445ff',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  void s.loadURL(splashUrl)

  s.once('ready-to-show', () => s.show())

  return s
}

function attachSplashAutoTransition() {
  if (!splash || !win) return

  splash.webContents.once('did-finish-load', () => {
    setTimeout(() => {
      try {
        splash?.destroy()
      } catch {}
      splash = null

      win?.show()
      win?.focus()
    }, 1500)
  })
}

async function boot() {
  win = createMainWindow()
  splash = createSplashWindow()
  attachSplashAutoTransition()
}

ipcMain.handle('app:getPublicConfig', () => ({
  appName: process.env.APP_NAME ?? 'B-GENT',
}))

ipcMain.handle('fs:openDialog', async () => {
  if (!win) return null
  const res = await dialog.showOpenDialog(win, { properties: ['openFile'] })
  return res.canceled ? null : res.filePaths[0]
})

ipcMain.handle('backend:request', async (_e, init: RequestInit & { path: string }) => {
  const base = process.env.BACKEND_URL || 'http://localhost:8080'
  const res = await fetch(base + init.path, init)
  const ct = res.headers.get('content-type') || ''
  let body: any = {}
  if (ct.includes('application/json')) {
    body = await res.json().catch(() => ({}))
  } else {
    body = await res.text().catch(() => '')
  }
  return { status: res.status, json: body }
})

ipcMain.handle('report:open', (_e, payload: { reportId?: string }) => {
  createReportWindow(payload)
  return { ok: true }
})

ipcMain.handle(
  'fs:save',
  async (
    _e,
    opts: { data: string | Buffer; defaultPath?: string; filters?: Electron.FileFilter[] }
  ) => {
    const { data, defaultPath, filters } = opts ?? {}
    const res = await dialog.showSaveDialog({
      title: 'Save file',
      defaultPath: defaultPath ?? 'Bgent_Report.md',
      filters: filters ?? [
        { name: 'Markdown', extensions: ['md'] },
        { name: 'Text', extensions: ['txt'] },
      ],
    })
    if (res.canceled || !res.filePath) return undefined

    const buf = typeof data === 'string' ? Buffer.from(data, 'utf8') : Buffer.from(data)
    await fsp.writeFile(res.filePath, buf)
    return res.filePath
  }
)

const gotLock = app.requestSingleInstanceLock()
if (!gotLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore()
      win.show()
      win.focus()
    }
  })

  app.whenReady().then(boot)

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
  })
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) boot()
  })
}
