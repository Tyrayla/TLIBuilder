export interface StartupMetric {
  name: string
  durationMs: number
  details?: Record<string, string | number | boolean | null>
}

type StartupDiagnosticWindow = Window & { __tliStartupMetrics?: StartupMetric[] }

/** In-memory timing buffer for repeatable browser and Electron startup profiling. */
export function recordStartupMetric(name: string, durationMs: number, details?: StartupMetric['details']): void {
  if (typeof window === 'undefined') return
  const host = window as StartupDiagnosticWindow
  const metrics = host.__tliStartupMetrics ?? (host.__tliStartupMetrics = [])
  const metric = { name, durationMs: Math.round(durationMs * 10) / 10, ...(details ? { details } : {}) }
  metrics.push(metric)
  if (typeof host.dispatchEvent === 'function' && typeof CustomEvent !== 'undefined') {
    host.dispatchEvent(new CustomEvent('tli-startup-metric', { detail: metric }))
  }
}
