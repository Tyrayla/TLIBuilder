/* eslint-disable @typescript-eslint/no-require-imports */
const { app, shell, BrowserWindow, ipcMain, dialog } =
  require('electron') as typeof import('electron')
import { join } from 'path'
import { spawn, execFileSync, ChildProcess } from 'child_process'
import { Socket } from 'net'
import { existsSync, cpSync } from 'fs'
import { autoUpdater } from 'electron-updater'

// Prevent Chromium GPU shader cache conflicts when multiple instances run
app.commandLine.appendSwitch('disable-gpu-shader-disk-cache')

const isDev = process.env.NODE_ENV === 'development'
const isVerbose = process.env.VERBOSE === 'true'
let PYTHON_PORT = 8765
let pythonProcess: ChildProcess | null = null
let isDirtyMain = false

ipcMain.on('dirty-change', (_event, dirty: boolean) => { isDirtyMain = dirty })

const log = (...args: unknown[]) => { if (isVerbose) console.log('[main]', ...args) }
const err = (...args: unknown[]) => { if (isVerbose) console.error('[main]', ...args) }

// Port readiness tracking — IPC callers wait until Python confirms its port
let isPortReady = false
const portWaiters: ((port: number) => void)[] = []

function resolvePort(port: number): void {
  if (isPortReady) return
  log(`resolvePort(${port}) — marking ready`)
  isPortReady = true
  PYTHON_PORT = port
  for (const fn of portWaiters) fn(port)
  portWaiters.length = 0
}

// Probe the TCP port until Python is actually accepting connections.
function waitForPort(port: number, maxMs = 10000): Promise<void> {
  log(`waitForPort(${port}) — probing every 150ms up to ${maxMs}ms`)
  return new Promise(resolve => {
    const start = Date.now()
    const deadline = start + maxMs
    let probeCount = 0
    const attempt = () => {
      probeCount++
      const sock = new Socket()
      sock.setTimeout(400)
      sock.on('connect', () => {
        sock.destroy()
        log(`waitForPort — connected on probe #${probeCount} after ${Date.now() - start}ms`)
        resolve()
      })
      sock.on('error', () => { sock.destroy(); reschedule() })
      sock.on('timeout', () => { sock.destroy(); reschedule() })
      sock.connect(port, '127.0.0.1')
    }
    const reschedule = () => {
      if (Date.now() < deadline) setTimeout(attempt, 150)
      else {
        err(`waitForPort — timed out after ${probeCount} probes, proceeding anyway`)
        resolve()
      }
    }
    attempt()
  })
}

// Kill whatever is running on the target port before we start (Windows)
function killPortProcess(port: number): void {
  log(`killPortProcess(${port}) — scanning netstat`)
  try {
    const output = execFileSync('netstat', ['-ano'], { encoding: 'utf8' })
    let killed = 0
    for (const line of output.split('\n')) {
      if (line.includes(`:${port}`) && line.includes('LISTENING')) {
        const parts = line.trim().split(/\s+/)
        const pid = parts[parts.length - 1]
        if (pid && /^\d+$/.test(pid)) {
          try {
            execFileSync('taskkill', ['/F', '/PID', pid])
            log(`killPortProcess — killed PID ${pid} on port ${port}`)
            killed++
          } catch (e) {
            err(`killPortProcess — failed to kill PID ${pid}:`, e)
          }
        }
      }
    }
    if (killed === 0) log(`killPortProcess — no process found on port ${port}`)
  } catch (e) {
    err('killPortProcess — netstat failed:', e)
  }
}

function bootstrapDataDir(): string {
  if (!app.isPackaged) {
    return join(__dirname, '../../data')
  }
  const userDataPath = join(app.getPath('userData'), 'data')
  if (!existsSync(userDataPath)) {
    log(`bootstrapDataDir — first launch, copying bundled data to ${userDataPath}`)
    cpSync(join(process.resourcesPath, 'data'), userDataPath, { recursive: true })
  }
  return userDataPath
}

// Spawns Python and resolves with the detected port once Python prints its ready message.
// Does NOT call resolvePort() — caller does that after TCP confirmation.
function startPython(): Promise<number> {
  return new Promise<number>((resolve) => {
    log('startPython — begin')
    killPortProcess(8765)

    const dataDir = bootstrapDataDir()
    const pythonArgs = ['--port', String(PYTHON_PORT)]
    if (isVerbose) pythonArgs.push('--verbose')

    let spawnCmd: string
    let spawnArgs: string[]
    let spawnOpts: { cwd?: string; env?: NodeJS.ProcessEnv }

    if (app.isPackaged) {
      spawnCmd = join(process.resourcesPath, 'backend.exe')
      spawnArgs = pythonArgs
      spawnOpts = { env: { ...process.env, TLI_DATA_DIR: dataDir } }
      log(`startPython — packaged mode, spawning: ${spawnCmd}`)
      log(`startPython — TLI_DATA_DIR: ${dataDir}`)
    } else {
      const script = join(__dirname, '../../backend/server.py')
      const cwd = join(__dirname, '../../backend')
      spawnCmd = 'python'
      spawnArgs = [script, ...pythonArgs]
      spawnOpts = { cwd }
      log(`startPython — dev mode, spawning: python ${script} --port ${PYTHON_PORT}`)
      log(`startPython — cwd: ${cwd}`)
    }

    pythonProcess = spawn(spawnCmd, spawnArgs, spawnOpts)
    let resolved = false
    const done = (port: number) => { if (!resolved) { resolved = true; PYTHON_PORT = port; resolve(port) } }

    pythonProcess.stdout?.on('data', (data: Buffer) => {
      const msg = data.toString().trim()
      log(`[python stdout] ${msg}`)
      const match = msg.match(/running on port (\d+)/)
      if (match) {
        const port = parseInt(match[1], 10)
        log(`startPython — port confirmed from stdout: ${port}`)
        done(port)
      }
    })

    pythonProcess.stderr?.on('data', (data: Buffer) => {
      const msg = data.toString().trim()
      if (msg) err(`[python stderr] ${msg}`)
    })

    pythonProcess.on('error', (e) => {
      err('startPython — spawn error:', e)
      done(PYTHON_PORT)
    })

    pythonProcess.on('exit', (code) => {
      err(`startPython — process exited with code ${code}`)
      done(PYTHON_PORT)
    })

    setTimeout(() => {
      err('startPython — 5s safety timeout fired')
      done(PYTHON_PORT)
    }, 5000)
  })
}

function initUpdater(win: typeof BrowserWindow.prototype): void {
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = false

  autoUpdater.on('update-available', (info) => {
    win.webContents.send('update-available', {
      version: info.version,
      releaseNotes: info.releaseNotes ?? '',
      releaseDate: info.releaseDate,
    })
  })
  autoUpdater.on('download-progress', (p) => {
    win.webContents.send('update-download-progress', Math.round(p.percent))
  })
  autoUpdater.on('update-downloaded', () => {
    win.webContents.send('update-downloaded')
  })
  autoUpdater.on('update-not-available', () => {
    win.webContents.send('update-not-available')
  })
  autoUpdater.on('error', (e) => {
    err('autoUpdater error:', e)
    win.webContents.send('update-check-error', String(e?.message ?? e))
  })

  if (app.isPackaged) {
    win.once('ready-to-show', () => {
      setTimeout(() => autoUpdater.checkForUpdates(), 3000)
    })
  }
}

function createWindow(): void {
  log('createWindow — creating BrowserWindow')
  const mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1100,
    minHeight: 680,
    title: 'TLI Builder',
    icon: join(__dirname, '../../resources/icon.png'),
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
    },
  })

  mainWindow.removeMenu()

  mainWindow.on('close', async (e) => {
    e.preventDefault()
    if (!isDirtyMain) {
      mainWindow.destroy()
      return
    }
    const { response } = await dialog.showMessageBox(mainWindow, {
      type: 'question',
      buttons: ['Save', "Don't Save", 'Cancel'],
      defaultId: 0,
      cancelId: 2,
      title: 'Unsaved Changes',
      message: 'Your build has unsaved changes.',
      detail: 'Do you want to save before closing?',
      noLink: true,
    })
    if (response === 0) {
      mainWindow.webContents.send('request-save')
      ipcMain.once('save-done', () => mainWindow.destroy())
    } else if (response === 1) {
      mainWindow.destroy()
    }
    // response === 2 (Cancel): do nothing, window stays open
  })

  mainWindow.on('ready-to-show', () => {
    log('createWindow — ready-to-show, displaying window')
    mainWindow.show()
    if (isDev && isVerbose) mainWindow.webContents.openDevTools({ mode: 'detach' })
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (isDev && process.env['ELECTRON_RENDERER_URL']) {
    const url = process.env['ELECTRON_RENDERER_URL']
    log(`createWindow — dev mode, loading URL: ${url}`)
    mainWindow.loadURL(url)
  } else {
    const file = join(__dirname, '../renderer/index.html')
    log(`createWindow — prod mode, loading file: ${file}`)
    mainWindow.loadFile(file)
  }
}

app.whenReady().then(async () => {
  log('app.whenReady — start')
  app.setAppUserModelId('com.tlibuilder')

  ipcMain.handle('get-python-port', (): Promise<number> | number => {
    if (isPortReady) {
      log(`IPC get-python-port — immediate return: ${PYTHON_PORT}`)
      return PYTHON_PORT
    }
    log('IPC get-python-port — queueing, waiting for port...')
    return new Promise<number>(resolve => {
      portWaiters.push((port) => {
        log(`IPC get-python-port — resolved from queue: ${port}`)
        resolve(port)
      })
      setTimeout(() => {
        err(`IPC get-python-port — 12s safety timeout, returning ${PYTHON_PORT}`)
        resolve(PYTHON_PORT)
      }, 12000)
    })
  })

  ipcMain.handle('get-is-dev', () => !app.isPackaged)

  ipcMain.handle('api-request', async (_event, { method, path, body }: { method: string; path: string; body?: unknown }) => {
    const url = `http://127.0.0.1:${PYTHON_PORT}/api${path}`
    try {
      const res = await fetch(url, {
        method,
        headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(30000),
      })
      const data = await res.json().catch(() => null)
      return { ok: res.ok, status: res.status, data }
    } catch (e) {
      return { ok: false, status: 0, data: null, error: String(e) }
    }
  })

  ipcMain.handle('api-form-upload', async (_event, path: string, fileBytes: Uint8Array, fileName: string) => {
    const url = `http://127.0.0.1:${PYTHON_PORT}/api${path}`
    try {
      const form = new FormData()
      form.append('file', new Blob([Buffer.from(fileBytes)]), fileName)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const res = await fetch(url, { method: 'POST', body: form as any })
      const data = await res.json().catch(() => null)
      return { ok: res.ok, status: res.status, data }
    } catch (e) {
      return { ok: false, status: 0, data: null, error: String(e) }
    }
  })

  ipcMain.handle('download-update', () => autoUpdater.downloadUpdate())
  ipcMain.handle('install-update', () => autoUpdater.quitAndInstall(false, true))
  ipcMain.handle('get-app-version', () => app.getVersion())
  ipcMain.handle('check-for-update', async () => {
    try { await autoUpdater.checkForUpdates() } catch { /* error event fires */ }
  })
  ipcMain.handle('open-external', (_event, url: string) => shell.openExternal(url))

  // Open the window immediately so users see the "Starting backend…" state
  // instead of a blank taskbar entry. getPythonPort() IPC calls queue until
  // resolvePort() fires below.
  createWindow()
  const mainWin = BrowserWindow.getAllWindows()[0]
  if (mainWin) initUpdater(mainWin)

  log('app.whenReady — calling startPython')
  const detectedPort = await startPython()
  log(`app.whenReady — startPython done, detectedPort=${detectedPort}`)

  log('app.whenReady — calling waitForPort')
  await waitForPort(detectedPort)
  log('app.whenReady — waitForPort done, resolving port for renderer')

  resolvePort(detectedPort)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('before-quit', () => {
  log('before-quit — killing python process')
  pythonProcess?.kill()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
