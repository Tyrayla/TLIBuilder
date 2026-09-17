export type TliErrorContext = Record<string, string | number | boolean | null>

export interface TliErrorPayload {
  code: string
  title: string
  message: string
  remediation?: string
  operation: string
  retryable: boolean
  requestId?: string
  fingerprint?: string
  context?: TliErrorContext
}

export const ERROR_REGISTRY = {
  'TLI-BOOT-001': { title: 'The local backend did not start', remediation: 'Restart TLI Builder and try again.', retryable: true },
  'TLI-NET-001': { title: 'A required service cannot be reached', remediation: 'Check your connection, then retry.', retryable: true },
  'TLI-DATA-001': { title: 'Required game data is unavailable', remediation: 'Select or import a season, then try again.', retryable: false },
  'TLI-BUILD-001': { title: 'This build code cannot be imported', remediation: 'Check the code and make sure it was copied completely.', retryable: false },
  'TLI-CALC-001': { title: 'Calculation cannot model this build', remediation: 'Adjust the affected setting, or use a different configuration.', retryable: false },
  'TLI-SHARE-001': { title: 'The shared build could not be loaded', remediation: 'Check the link and your connection, then try again.', retryable: true },
  'TLI-UI-001': { title: 'The app encountered an unexpected screen error', remediation: 'Save a recovery code, then reload the app.', retryable: true },
  'TLI-UNEXPECTED-001': { title: 'Something unexpected went wrong', remediation: 'Try again. If this continues, copy the details for a bug report.', retryable: true },
} as const

export type TliErrorCode = keyof typeof ERROR_REGISTRY

function isTliErrorCode(value: unknown): value is TliErrorCode {
  return typeof value === 'string' && value in ERROR_REGISTRY
}

export class TliError extends Error {
  readonly payload: TliErrorPayload

  constructor(payload: TliErrorPayload) {
    super(payload.message)
    this.name = 'TliError'
    this.payload = payload
  }

  get code(): string { return this.payload.code }
}

function registryPayload(code: TliErrorCode, operation: string, message?: string, overrides: Partial<TliErrorPayload> = {}): TliErrorPayload {
  const entry = ERROR_REGISTRY[code]
  const safeMessage = message || entry.title
  return {
    code,
    title: entry.title,
    message: safeMessage,
    remediation: entry.remediation,
    operation,
    retryable: entry.retryable,
    fingerprint: normalizedFingerprint(code, operation, safeMessage),
    ...overrides,
  }
}

// Deliberately group normalized client-side failures only; raw stacks are never put in diagnostics.
function normalizedFingerprint(code: string, operation: string, message: string): string {
  const normalized = `${code}|${operation}|${message}`.toLowerCase()
    .replace(/\b[0-9a-f]{8,}\b|\d+/g, '#')
  let hash = 0x811c9dc5
  for (let index = 0; index < normalized.length; index++) {
    hash ^= normalized.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return `fnv1a-${(hash >>> 0).toString(16).padStart(8, '0')}`
}

export function isTliErrorPayload(value: unknown): value is TliErrorPayload {
  if (!value || typeof value !== 'object') return false
  const v = value as Record<string, unknown>
  return isTliErrorCode(v.code) && typeof v.title === 'string' && typeof v.message === 'string'
    && typeof v.operation === 'string' && typeof v.retryable === 'boolean'
}

export function errorFromResponse(body: unknown, fallbackCode: TliErrorCode, operation: string, message?: string, trusted = false): TliError {
  const candidate = body && typeof body === 'object' && 'error' in body
    ? (body as { error: unknown }).error
    : body
  if (isTliErrorPayload(candidate)) {
    const source = candidate as TliErrorPayload
    const safeOperation = /^[a-z][a-z0-9_.-]{0,80}$/i.test(source.operation) ? source.operation : operation
    const safeMessage = trusted && source.message.length <= 500 && !/[\r\n\0]/.test(source.message)
      ? source.message
      : undefined
    const payload = registryPayload(source.code as TliErrorCode, safeOperation, safeMessage)
    if (/^[a-f0-9]{16,64}$/i.test(source.requestId ?? '')) payload.requestId = source.requestId
    if (/^(?:fnv1a-)?[a-f0-9]{8,64}$/i.test(source.fingerprint ?? '')) payload.fingerprint = source.fingerprint
    return new TliError(payload)
  }
  return new TliError(registryPayload(fallbackCode, operation, message))
}

export function normalizeError(error: unknown, fallbackCode: TliErrorCode, operation: string): TliError {
  if (error instanceof TliError) return error
  // Native Error messages may contain user input, local paths, or pasted codes. Only a validated
  // service envelope may cross into player-visible diagnostics or the later report pipeline.
  return new TliError(registryPayload(fallbackCode, operation))
}

export function copyableErrorDetails(error: TliErrorPayload): string {
  return [
    `Code: ${error.code}`,
    `Operation: ${error.operation}`,
    `Message: ${error.message}`,
    error.remediation ? `Suggested action: ${error.remediation}` : '',
    error.requestId ? `Request ID: ${error.requestId}` : '',
    error.fingerprint ? `Fingerprint: ${error.fingerprint}` : '',
  ].filter(Boolean).join('\n')
}

const reportableDiagnostics: TliErrorPayload[] = []
const MAX_DIAGNOSTICS = 20

export function recordReportableDiagnostic(error: TliErrorPayload): void {
  reportableDiagnostics.unshift(error)
  reportableDiagnostics.splice(MAX_DIAGNOSTICS)
}

export function prepareReport(error: TliErrorPayload): void {
  recordReportableDiagnostic(error)
  window.dispatchEvent(new CustomEvent('tli-report-prepared', { detail: error }))
}

export function getReportableDiagnostics(): readonly TliErrorPayload[] {
  return reportableDiagnostics
}

export function installGlobalErrorCapture(): () => void {
  const onError = (event: ErrorEvent) => recordReportableDiagnostic(normalizeError(
    event.error ?? new Error(event.message), 'TLI-UI-001', 'ui.window-error',
  ).payload)
  const onRejection = (event: PromiseRejectionEvent) => recordReportableDiagnostic(normalizeError(
    event.reason, 'TLI-UI-001', 'ui.unhandled-rejection',
  ).payload)
  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)
  return () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
  }
}
