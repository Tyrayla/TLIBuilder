import { describe, it, expect } from 'vitest'
import { consumeAuthReturn, AUTH_ERROR_MESSAGE } from '../../utils/authReturn'
import { AccountApiError, friendlyAccountError } from '../../api/accounts'

describe('consumeAuthReturn', () => {
  it('reads a failed web sign-in and returns a clean URL without the parameter', () => {
    const r = consumeAuthReturn('https://app.example.test/?auth_error=cancelled&keep=1#x')
    expect(r.authError).toBe('cancelled')
    expect(r.cleanedHref).toBe('https://app.example.test/?keep=1#x')
  })

  it('reads a completed reauthentication', () => {
    const r = consumeAuthReturn('https://app.example.test/index.html?reauth=ok')
    expect(r.reauthOk).toBe(true)
    expect(r.cleanedHref).toBe('https://app.example.test/index.html')
  })

  it('ignores unknown reasons and values so a crafted link cannot inject text', () => {
    const r = consumeAuthReturn('https://app.example.test/?auth_error=<script>alert(1)</script>&reauth=nope')
    expect(r.authError).toBe('unknown')
    expect(r.reauthOk).toBe(false)
    expect(r.cleanedHref).toBe('https://app.example.test/')
  })

  it('treats inherited object properties as unknown auth errors', () => {
    const r = consumeAuthReturn('https://app.example.test/?auth_error=constructor')
    expect(r.authError).toBe('unknown')
    expect(AUTH_ERROR_MESSAGE[r.authError!]).toBe('Sign-in did not complete. Try again.')
  })

  it('leaves an unrelated URL alone', () => {
    const r = consumeAuthReturn('https://app.example.test/?share=abc')
    expect(r).toEqual({ authError: null, reauthOk: false, cleanedHref: null })
  })

  it('has a plain message for every reason the service can send', () => {
    for (const reason of ['cancelled', 'discord_failed', 'signup_closed', 'reauth_failed', 'unknown']) {
      expect(AUTH_ERROR_MESSAGE[reason]).toBeTruthy()
    }
  })
})

describe('friendlyAccountError', () => {
  const e = (code: string, status = 409) => new AccountApiError(status, code, 'raw developer text')
  it('explains the account-service codes in plain words', () => {
    expect(friendlyAccountError(e('signup_closed', 403))).toContain('not open')
    expect(friendlyAccountError(e('name_unavailable'))).toContain('taken')
    expect(friendlyAccountError(e('invalid_name', 422))).toContain('2–24')
    expect(friendlyAccountError(e('handle_limit_reached'))).toContain('name')
    expect(friendlyAccountError(e('already_registered'))).toContain('already')
    expect(friendlyAccountError(e('busy', 503))).toContain('busy')
    expect(friendlyAccountError(e('rate_limited', 429))).toContain('too many')
  })

  it('falls back to the error text for anything else, and to a generic line for non-errors', () => {
    expect(friendlyAccountError(e('something_else'))).toBe('raw developer text')
    expect(friendlyAccountError('x')).toBe('Something went wrong.')
  })
})
