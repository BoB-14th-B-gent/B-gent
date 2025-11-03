import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

import { app, BrowserWindow, ipcMain, dialog, shell, nativeImage } from 'electron'
import dotenv from 'dotenv'

app.setName('B-Gent')

const tryEnvPaths = [
  path.resolve(app.getAppPath(), '..', '.env'),
  path.resolve(__dirname, '../../.env'),
]
for (const p of tryEnvPaths) {
  if (fs.existsSync(p)) { dotenv.config({ path: p }); break }
}

function getAssetPath(...p: string[]) {
  return app.isPackaged
    ? path.join(process.resourcesPath, ...p)
    : path.join(__dirname, '..', '..', ...p)
}

let win: BrowserWindow | null = null

async function createWindow() {
  const iconPath = getAssetPath('assets', 'icon.png')
  const appIcon = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath) : undefined

  win = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: '#111827',
    icon: appIcon,
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (process.platform === 'darwin' && appIcon) {
    app.dock?.setIcon(appIcon)
  }

  if (app.isPackaged) {
    const html = getAssetPath('renderer', 'index.html')
    await win.loadFile(html)
  } else {
    const rendererUrl = process.env.RENDERER_URL || 'http://localhost:5173'
    console.log('[main] loading renderer from:', rendererUrl)
    await win.loadURL(rendererUrl)
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
}

ipcMain.handle('app:getPublicConfig', () => ({
  appName: process.env.APP_NAME ?? 'B-Gent',
}))

ipcMain.handle('fs:openDialog', async () => {
  if (!win) return null
  const res = await dialog.showOpenDialog(win, { properties: ['openFile'] })
  return res.canceled ? null : res.filePaths[0]
})

ipcMain.handle('backend:request', async (_e, init: RequestInit & { path: string }) => {
  const base = process.env.BACKEND_URL ?? 'http://localhost:8080'
  const res = await fetch(base + init.path, init)
  const json = await res.json().catch(() => ({}))
  return { status: res.status, json }
})

app.whenReady().then(createWindow)
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })