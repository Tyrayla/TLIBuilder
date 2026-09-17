// Flag-gated React render profiler — a small permanent perf primitive.
//
// When enabled it wraps its children in React's <Profiler> and records each commit's
// `actualDuration` into a ring buffer exposed on `window.__perf`, so the E2E perf harness
// (and ad-hoc console inspection) can read render timings. When DISABLED it renders its
// children unchanged — no <Profiler>, no callback, zero cost — so it is safe to leave wired
// into production.
//
// Enable it by setting `window.__perfEnabled = true` BEFORE the app bundle loads (the Playwright
// perf spec does this via addInitScript), or by loading with `?perf=1`. The flag is read once at
// module load so the tree shape never flips at runtime (which would remount the subtree).
//
// Read results from a page/renderer context:
//   window.__perf.reset()                 // clear before a measured interaction
//   window.__perf.stats('screens')        // { count, mean, median, p95, max } (ms) for that Profiler id
import { Profiler, type ProfilerOnRenderCallback, type ReactNode } from 'react'

export interface PerfSample {
  id: string
  phase: 'mount' | 'update' | 'nested-update'
  actualDuration: number
  baseDuration: number
  startTime: number
  commitTime: number
}

export interface PerfStats {
  count: number
  mean: number
  median: number
  p95: number
  max: number
}

interface PerfApi {
  samples: PerfSample[]
  record: (s: PerfSample) => void
  reset: () => void
  stats: (id?: string) => PerfStats
}

declare global {
  interface Window {
    __perf?: PerfApi
    __perfEnabled?: boolean
    // E2E perf-spec drivers, installed by App only when __perfEnabled is set (absent in a normal run).
    __perfNav?: (screen: string) => void
    __perfEdit?: () => void
    __perfBuildState?: () => { buildVersion: number; computedVersion: number; statsLoading: boolean }
  }
}

// Cap the buffer so a long session can't grow it without bound.
const RING_MAX = 5000

function perfEnabled(): boolean {
  if (typeof window === 'undefined') return false
  if (window.__perfEnabled) return true
  try {
    return new URLSearchParams(window.location.search).has('perf')
  } catch {
    return false
  }
}

// Read once at module load — the enable flag is set before the bundle runs, so the profiled tree
// shape stays stable across renders (no add/remove of the <Profiler> node mid-session).
export const PERF_ENABLED = perfEnabled()

function emptyStats(): PerfStats {
  return { count: 0, mean: 0, median: 0, p95: 0, max: 0 }
}

function ensurePerfApi(): PerfApi {
  if (window.__perf) return window.__perf
  const samples: PerfSample[] = []
  const api: PerfApi = {
    samples,
    record(s) {
      samples.push(s)
      if (samples.length > RING_MAX) samples.shift()
    },
    reset() {
      samples.length = 0
    },
    stats(id) {
      const durs = (id ? samples.filter(s => s.id === id) : samples)
        .map(s => s.actualDuration)
        .sort((a, b) => a - b)
      if (durs.length === 0) return emptyStats()
      const quantile = (p: number) => durs[Math.min(durs.length - 1, Math.floor(p * durs.length))]
      const sum = durs.reduce((a, b) => a + b, 0)
      return {
        count: durs.length,
        mean: sum / durs.length,
        median: quantile(0.5),
        p95: quantile(0.95),
        max: durs[durs.length - 1],
      }
    },
  }
  window.__perf = api
  return api
}

export default function PerfProfiler({ id, children }: { id: string; children: ReactNode }) {
  if (!PERF_ENABLED) return <>{children}</>
  const api = ensurePerfApi()
  const onRender: ProfilerOnRenderCallback = (pid, phase, actualDuration, baseDuration, startTime, commitTime) => {
    api.record({ id: pid, phase, actualDuration, baseDuration, startTime, commitTime })
  }
  return (
    <Profiler id={id} onRender={onRender}>
      {children}
    </Profiler>
  )
}
