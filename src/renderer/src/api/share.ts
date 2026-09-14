// Build-code share service. This public host is intentionally separate from the local backend.
import { errorFromResponse, normalizeError } from '../errors/tliError'

const _shareEnv = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
const SHARE_BASE = (_shareEnv?.VITE_SHARE_BASE_URL ?? 'https://api.tlibuilder.com').replace(/\/+$/, '')
const MAX_SHARE_CODE_BYTES = 512 * 1024
const MAX_SHARE_ERROR_BYTES = 16 * 1024

export function getShareBase(): string {
  return SHARE_BASE
}

async function readErrorBody(res: Response): Promise<unknown> {
  const declaredLength = Number(res.headers.get('content-length') ?? 0)
  if (declaredLength > MAX_SHARE_ERROR_BYTES || !res.body) return null
  const reader = res.body.getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  while (true) {
    const next = await reader.read()
    if (next.done) break
    size += next.value.byteLength
    if (size > MAX_SHARE_ERROR_BYTES) {
      await reader.cancel()
      return null
    }
    chunks.push(next.value)
  }
  const bytes = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
  try { return JSON.parse(new TextDecoder().decode(bytes)) } catch { return null }
}

async function postToShareService<T>(path: string, body: unknown): Promise<T> {
  const operation = `share.post.${path.replace(/^\//, '')}`
  try {
    if (path === '/v1/reports' && window.api?.reportRequest) {
      const result = await window.api.reportRequest(body)
      if (!result.ok) {
        throw errorFromResponse(result.data, 'TLI-NET-001', 'report.submit')
      }
      return result.data as T
    }
    const res = await fetch(`${SHARE_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    })
    if (!res.ok) {
      throw errorFromResponse(
        await readErrorBody(res),
        'TLI-SHARE-001',
        operation,
        `Share service request failed (${res.status}).`,
      )
    }
    return res.json() as Promise<T>
  } catch (error) {
    throw normalizeError(error, 'TLI-SHARE-001', operation)
  }
}

async function getFromShareService(path: string): Promise<string> {
  const operation = `share.get.${path.replace(/^\//, '')}`
  try {
    const res = await fetch(`${SHARE_BASE}${path}`, { signal: AbortSignal.timeout(15000) })
    if (!res.ok) {
      throw errorFromResponse(
        await readErrorBody(res),
        'TLI-SHARE-001',
        operation,
        `Shared build could not be loaded (${res.status}).`,
      )
    }
    const len = Number(res.headers.get('content-length') ?? 0)
    if (len > MAX_SHARE_CODE_BYTES) throw new Error('Shared build code exceeds size limit')
    const text = await res.text()
    if (text.length > MAX_SHARE_CODE_BYTES) throw new Error('Shared build code exceeds size limit')
    return text
  } catch (error) {
    throw normalizeError(error, 'TLI-SHARE-001', operation)
  }
}

export function shareBuildCode(code: string): Promise<{ id: string; url: string }> {
  return postToShareService<{ id: string; url: string }>('/b', { code })
}

export function fetchSharedBuildCode(id: string): Promise<string> {
  return getFromShareService(`/b/${id}`)
}

export interface BugReportRequest {
  category: string
  runtime: string
  form_factor: string
  transport: string
  app_version: string
  season?: string
  error_code?: string
  operation?: string
  fingerprint?: string
  description: string
  reproduction_steps?: string
  discord_username?: string
  diagnostics: Record<string, unknown>
  build_snapshot?: Record<string, unknown>
}

export async function submitBugReport(report: BugReportRequest): Promise<{ reportId: string }> {
  const result = await postToShareService<{ reportId?: string, report_id?: string }>('/v1/reports', report)
  const reportId = result.reportId ?? result.report_id
  if (!reportId || !/^TLI-RPT-[A-Z0-9]{8}$/.test(reportId)) {
    throw new Error('Report service returned an invalid receipt.')
  }
  return { reportId }
}
