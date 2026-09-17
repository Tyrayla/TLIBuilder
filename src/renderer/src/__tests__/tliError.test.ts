import { describe, expect, it } from 'vitest'
import { copyableErrorDetails, errorFromResponse, normalizeError } from '../errors/tliError'

describe('TliError', () => {
  it('preserves a server envelope without flattening it into a string', () => {
    const error = errorFromResponse({ error: {
      code: 'TLI-CALC-001',
      title: 'Calculation cannot model this build',
      message: 'Known guardrail reached.',
      operation: 'engine.stats',
      retryable: false,
      requestId: '0123456789abcdef',
    } }, 'TLI-UNEXPECTED-001', 'ignored')

    expect(error.code).toBe('TLI-CALC-001')
    expect(error.payload.requestId).toBe('0123456789abcdef')
    expect(copyableErrorDetails(error.payload)).toContain('Code: TLI-CALC-001')
  })

  it('gives an untyped transport failure a stable, sanitized fallback category', () => {
    expect(normalizeError(new Error('connection refused'), 'TLI-NET-001', 'electron.ipc.api-request').payload)
      .toMatchObject({ code: 'TLI-NET-001', operation: 'electron.ipc.api-request', retryable: true })
  })

  it('groups client fallback errors after normalizing volatile numbers', () => {
    const first = normalizeError(new Error('connection refused at port 8765'), 'TLI-NET-001', 'electron.ipc.api-request')
    const second = normalizeError(new Error('connection refused at port 8766'), 'TLI-NET-001', 'electron.ipc.api-request')
    expect(first.payload.fingerprint).toBe(second.payload.fingerprint)
  })

  it('does not trust a public envelope message without an explicit trusted boundary', () => {
    const error = errorFromResponse({ error: {
      code: 'TLI-SHARE-001', title: 'forged', message: 'forged remote text',
      operation: 'share.get.b', retryable: false,
    } }, 'TLI-SHARE-001', 'share.get.b')
    expect(error.payload.title).toBe('The shared build could not be loaded')
    expect(error.payload.message).toBe('The shared build could not be loaded')
  })
})
