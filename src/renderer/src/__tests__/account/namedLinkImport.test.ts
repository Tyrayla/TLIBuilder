import { describe, it, expect, vi } from 'vitest'
import { dataVersionWarning } from '../../utils/dataVersion'
import { parseNamedLinkUrl, resolveImportSource } from '../../utils/resolveImportInput'
import { fetchNamedLink, AccountApiError } from '../../api/accounts'

describe('dataVersionWarning', () => {
  it('names the saved version when it differs from the current one', () => {
    const w = dataVersionWarning('SS12', 'SS13')
    expect(w).toContain('SS12')
    expect(w).toContain('SS13')
    expect(w!.toLowerCase()).toContain('may have changed')
  })

  it('is silent when the versions match or the saved version is unknown', () => {
    expect(dataVersionWarning('SS13', 'SS13')).toBeNull()
    expect(dataVersionWarning(null, 'SS13')).toBeNull()
    expect(dataVersionWarning('', 'SS13')).toBeNull()
    expect(dataVersionWarning(undefined, 'SS13')).toBeNull()
  })

  it('still names the saved version when the current one is not loaded yet', () => {
    expect(dataVersionWarning('SS12', null)).toContain('SS12')
  })
})

describe('parseNamedLinkUrl', () => {
  it('reads handle and slug from an api or app URL', () => {
    expect(parseNamedLinkUrl('https://api.tlibuilder.com/u/tyra-4472/fire-mage')).toEqual({ handle: 'tyra-4472', slug: 'fire-mage' })
    expect(parseNamedLinkUrl('https://app.tlibuilder.com/u/tyra.x_1-0918/a1/')).toEqual({ handle: 'tyra.x_1-0918', slug: 'a1' })
  })

  it('rejects anything that is not a named link', () => {
    expect(parseNamedLinkUrl('https://api.tlibuilder.com/b/abc123')).toBeNull()
    expect(parseNamedLinkUrl('https://x.test/u/tyra/fire')).toBeNull() // no -NNNN tag
    expect(parseNamedLinkUrl('https://x.test/u/tyra-4472/Bad_Slug')).toBeNull()
    expect(parseNamedLinkUrl('https://x.test/u/tyra-4472/fire/extra')).toBeNull()
    expect(parseNamedLinkUrl('tli1_abc')).toBeNull()
    expect(parseNamedLinkUrl('ftp://x.test/u/tyra-4472/fire')).toBeNull()
  })
})

describe('fetchNamedLink', () => {
  const okBody = { name: 'Fire', code: 'tli1_abc', data_version: 'SS12', owner: { name: 'Tyra', tag: '4472' } }

  it('sends no credentials and returns the code with its data version', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify(okBody), { status: 200 })) as unknown as typeof fetch
    const out = await fetchNamedLink('tyra-4472', 'fire', { base: 'https://api.example.test', fetchImpl })
    expect(out).toEqual({ name: 'Fire', code: 'tli1_abc', dataVersion: 'SS12' })
    const [url, init] = (fetchImpl as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0]
    expect(url).toBe('https://api.example.test/u/tyra-4472/fire')
    expect(init.credentials).toBe('omit')
  })

  it('says a removed link was removed by its owner', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ error: { code: 'removed_by_owner', message: 'x' } }), { status: 410 })) as unknown as typeof fetch
    const error = await fetchNamedLink('tyra-4472', 'fire', { base: 'https://api.example.test', fetchImpl }).catch((e) => e)
    expect(error).toBeInstanceOf(AccountApiError)
    expect(error.code).toBe('removed_by_owner')
    expect(error.message).toBe('This build was removed by its owner.')
  })

  it('rejects a response that is not a build code', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ ...okBody, code: 'nope' }), { status: 200 })) as unknown as typeof fetch
    await expect(fetchNamedLink('tyra-4472', 'fire', { base: 'https://api.example.test', fetchImpl })).rejects.toThrow()
  })
})

describe('resolveImportSource', () => {
  it('returns a raw code unchanged with no data version', async () => {
    expect(await resolveImportSource('  tli1_abc  ')).toEqual({ code: 'tli1_abc', dataVersion: null })
  })

  it('resolves a named link to its code and saved data version', async () => {
    const fetchNamed = vi.fn(async () => ({ name: 'Fire', code: 'tli1_named', dataVersion: 'SS12' }))
    expect(await resolveImportSource('https://api.tlibuilder.com/u/tyra-4472/fire', { fetchNamed }))
      .toEqual({ code: 'tli1_named', dataVersion: 'SS12' })
    expect(fetchNamed).toHaveBeenCalledWith('tyra-4472', 'fire')
  })
})
