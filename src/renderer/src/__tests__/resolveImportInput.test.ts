import { describe, it, expect, vi, beforeEach } from 'vitest'

// Module mock — resolveImportInput only imports `api` from client.ts, so a minimal
// stub covering fetchSharedBuildCode is enough.
vi.mock('../api/client', () => ({
  api: { fetchSharedBuildCode: vi.fn() },
}))

import { api } from '../api/client'
import { resolveImportInput, ShareFetchError } from '../utils/resolveImportInput'

const mockFetchShared = api.fetchSharedBuildCode as unknown as ReturnType<typeof vi.fn>

describe('resolveImportInput', () => {
  beforeEach(() => {
    mockFetchShared.mockReset()
  })

  it('share URL with a trailing slash matches and fetches the raw code', async () => {
    mockFetchShared.mockResolvedValue('tli1_abc')
    const result = await resolveImportInput('https://tlibuilder.com/b/xyz789/')
    expect(result).toBe('tli1_abc')
    expect(mockFetchShared).toHaveBeenCalledWith('xyz789')
  })

  it('share URL with extra path segments after the id does NOT match — treated as a raw code', async () => {
    const input = 'https://tlibuilder.com/b/xyz789/extra'
    const result = await resolveImportInput(input)
    expect(result).toBe(input)
    expect(mockFetchShared).not.toHaveBeenCalled()
  })

  it('non-http(s) scheme containing /b/ is treated as a raw code (scheme gate fails first)', async () => {
    const input = 'ftp://tlibuilder.com/b/xyz789'
    const result = await resolveImportInput(input)
    expect(result).toBe(input)
    expect(mockFetchShared).not.toHaveBeenCalled()
  })

  it('empty string input resolves to an empty (trimmed) string, no fetch', async () => {
    const result = await resolveImportInput('   ')
    expect(result).toBe('')
    expect(mockFetchShared).not.toHaveBeenCalled()
  })

  it('wraps a non-Error rejection via String(e)', async () => {
    mockFetchShared.mockRejectedValue('boom')
    await expect(resolveImportInput('https://tlibuilder.com/b/xyz789')).rejects.toThrow(ShareFetchError)
    try {
      await resolveImportInput('https://tlibuilder.com/b/xyz789')
      throw new Error('should have thrown')
    } catch (e) {
      expect(e).toBeInstanceOf(ShareFetchError)
      expect((e as Error).message).toBe('boom')
    }
  })

  it('share body not starting with tli1_ throws ShareFetchError', async () => {
    mockFetchShared.mockResolvedValue('<html>not a code</html>')
    await expect(resolveImportInput('https://tlibuilder.com/b/xyz789')).rejects.toThrow(ShareFetchError)
    await expect(resolveImportInput('https://tlibuilder.com/b/xyz789')).rejects.toThrow(
      'Share service returned an invalid build code.',
    )
  })
})
