/* eslint-disable @typescript-eslint/no-require-imports */
const { app, shell, BrowserWindow, ipcMain } =
  require('electron') as typeof import('electron')
import { join } from 'path'
import { spawn, execFileSync, ChildProcess } from 'child_process'
import { Socket } from 'net'

const isDev = process.env.NODE_ENV === 'development'
let PYTHON_PORT = 8765
let pythonProcess: ChildProcess | null = null

const log = (...args: unknown[]) => console.log('[main]', ...args)
const err = (...args: unknown[]) => console.error('[main]', ...args)

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

function startPython(): Promise<void> {
  return new Promise((resolve) => {
    log('startPython — begin')
    killPortProcess(8765)

    const script = join(__dirname, '../../server.py')
    const cwd = join(__dirname, '../..')
    log(`startPython — spawning: python ${script} --port ${PYTHON_PORT}`)
    log(`startPython — cwd: ${cwd}`)

    pythonProcess = spawn('python', [script, '--port', String(PYTHON_PORT)], { cwd })

    pythonProcess.stdout?.on('data', (data: Buffer) => {
      const msg = data.toString().trim()
      log(`[python stdout] ${msg}`)
      const match = msg.match(/running on port (\d+)/)
      if (match) {
        const port = parseInt(match[1], 10)
        log(`startPython — port confirmed from stdout: ${port}`)
        resolvePort(port)
        resolve()
      }
    })

    pythonProcess.stderr?.on('data', (data: Buffer) => {
      const msg = data.toString().trim()
      if (msg) err(`[python stderr] ${msg}`)
    })

    pythonProcess.on('error', (e) => {
      err('startPython — spawn error:', e)
      resolvePort(PYTHON_PORT)
      resolve()
    })

    pythonProcess.on('exit', (code) => {
      err(`startPython — process exited with code ${code}, isPortReady=${isPortReady}`)
      if (!isPortReady) {
        resolvePort(PYTHON_PORT)
        resolve()
      }
    })

    setTimeout(() => {
      if (!isPortReady) {
        err('startPython — 5s safety timeout fired, isPortReady still false')
        resolvePort(PYTHON_PORT)
        resolve()
      }
    }, 5000)
  })
}

function createWindow(): void {
  log('createWindow — creating BrowserWindow')
  const mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1100,
    minHeight: 680,
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      webSecurity: false, // allow renderer to connect to 127.0.0.1:8765 (local backend)
    },
  })

  mainWindow.on('ready-to-show', () => {
    log('createWindow — ready-to-show, displaying window')
    mainWindow.show()
    if (isDev) mainWindow.webContents.openDevTools({ mode: 'detach' })
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
  app.setAppUserModelId('com.tliplanner')

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

  log('app.whenReady — calling startPython')
  await startPython()
  log(`app.whenReady — startPython done, PYTHON_PORT=${PYTHON_PORT}`)

  log('app.whenReady — calling waitForPort')
  await waitForPort(PYTHON_PORT)
  log('app.whenReady — waitForPort done, calling createWindow')

  createWindow()

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
