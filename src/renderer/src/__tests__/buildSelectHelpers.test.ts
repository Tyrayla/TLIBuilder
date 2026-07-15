import { describe, it, expect } from 'vitest'
import {
  containerKey,
  sortBuilds,
  sortFolders,
  folderPath,
  isSelfOrDescendant,
  httpErrorStatus
} from '../screens/BuildSelectScreen'
import type { Build, BuildFolder } from '../api/client'

function build(id: string, updatedAt?: number): Build {
  return { id, name: id, slots: [], updatedAt }
}

function folder(id: string, name: string, parentId: string | null): BuildFolder {
  return { id, name, parentId }
}

describe('containerKey', () => {
  it('maps null (root) to the literal "root" key', () => {
    expect(containerKey(null)).toBe('root')
  })

  it('maps a folder id to itself', () => {
    expect(containerKey('f1')).toBe('f1')
  })
})

describe('sortBuilds', () => {
  it('defaults to updatedAt-descending when no order list is given', () => {
    const items = [build('a', 100), build('b', 300), build('c', 200)]
    const sorted = sortBuilds(items, undefined)
    expect(sorted.map(b => b.id)).toEqual(['b', 'c', 'a'])
  })

  it('treats a missing updatedAt as 0 (sorts to the bottom of the unlisted group)', () => {
    const items = [build('a', 100), build('b', undefined), build('c', 200)]
    const sorted = sortBuilds(items, undefined)
    expect(sorted.map(b => b.id)).toEqual(['c', 'a', 'b'])
  })

  it('places unlisted builds above listed ones, newest-first among themselves', () => {
    const items = [build('a', 100), build('b', 300), build('c', 200), build('d', 400)]
    // "a" and "c" are manually ordered (listed); "b" and "d" are unlisted and should float to the
    // top, newest-first, ahead of the listed group which stays in the given order.
    const sorted = sortBuilds(items, ['c', 'a'])
    expect(sorted.map(b => b.id)).toEqual(['d', 'b', 'c', 'a'])
  })

  it('ignores order-list ids that do not correspond to a given build', () => {
    const items = [build('a', 100), build('b', 200)]
    const sorted = sortBuilds(items, ['ghost', 'a'])
    expect(sorted.map(b => b.id)).toEqual(['b', 'a'])
  })

  it('an empty order list behaves like undefined (pure updatedAt-desc)', () => {
    const items = [build('a', 100), build('b', 300)]
    expect(sortBuilds(items, [])).toEqual(sortBuilds(items, undefined))
  })

  it('returns an empty array for an empty input list', () => {
    expect(sortBuilds([], ['a', 'b'])).toEqual([])
  })
})

describe('sortFolders', () => {
  it('defaults to alphabetical by name when no order list is given', () => {
    const items = [folder('c', 'Charlie', null), folder('a', 'Alpha', null), folder('b', 'Bravo', null)]
    const sorted = sortFolders(items, undefined)
    expect(sorted.map(f => f.id)).toEqual(['a', 'b', 'c'])
  })

  it('places unlisted folders (alphabetical) above the folderOrder-listed group', () => {
    const items = [folder('a', 'Alpha', null), folder('b', 'Bravo', null), folder('c', 'Charlie', null)]
    // "b" is manually placed via folderOrder; "a" and "c" are unlisted and sort alphabetically above it.
    const sorted = sortFolders(items, ['b'])
    expect(sorted.map(f => f.id)).toEqual(['a', 'c', 'b'])
  })

  it('ignores folderOrder ids that do not correspond to a given folder', () => {
    const items = [folder('a', 'Alpha', null)]
    const sorted = sortFolders(items, ['ghost', 'a'])
    expect(sorted.map(f => f.id)).toEqual(['a'])
  })

  it('returns an empty array for an empty input list', () => {
    expect(sortFolders([], ['a'])).toEqual([])
  })
})

describe('folderPath', () => {
  it('returns an empty path for the root container (null folderId)', () => {
    const folders = [folder('a', 'Alpha', null)]
    expect(folderPath(folders, null)).toEqual([])
  })

  it('returns a single-entry path for a top-level folder', () => {
    const folders = [folder('a', 'Alpha', null)]
    expect(folderPath(folders, 'a')).toEqual([folder('a', 'Alpha', null)])
  })

  it('builds the full root-to-nested breadcrumb chain in order', () => {
    const folders = [
      folder('grandparent', 'Grandparent', null),
      folder('parent', 'Parent', 'grandparent'),
      folder('child', 'Child', 'parent')
    ]
    const path = folderPath(folders, 'child')
    expect(path.map(f => f.id)).toEqual(['grandparent', 'parent', 'child'])
  })

  it('is robust against a dangling parentId (stops the walk instead of throwing)', () => {
    const folders = [folder('child', 'Child', 'ghost-parent')]
    const path = folderPath(folders, 'child')
    expect(path.map(f => f.id)).toEqual(['child'])
  })

  it('is robust against a folderId that does not exist at all', () => {
    const folders = [folder('a', 'Alpha', null)]
    expect(folderPath(folders, 'nonexistent')).toEqual([])
  })

  it('terminates on a corrupted parent cycle (a<->b) instead of hanging, returning a finite path', () => {
    const folders = [folder('a', 'A', 'b'), folder('b', 'B', 'a')]
    const path = folderPath(folders, 'a')
    expect(Array.isArray(path)).toBe(true)
    expect(path.length).toBeLessThanOrEqual(folders.length)
    expect(path.map(f => f.id).sort()).toEqual(['a', 'b'])
  })
})

describe('isSelfOrDescendant', () => {
  const folders = [
    folder('root-f', 'Root Folder', null),
    folder('child', 'Child', 'root-f'),
    folder('grandchild', 'Grandchild', 'child'),
    folder('unrelated', 'Unrelated', null)
  ]

  it('is true when the candidate IS the ancestor (self)', () => {
    expect(isSelfOrDescendant(folders, 'root-f', 'root-f')).toBe(true)
  })

  it('is true for a direct child', () => {
    expect(isSelfOrDescendant(folders, 'child', 'root-f')).toBe(true)
  })

  it('is true for a deep (multi-level) descendant', () => {
    expect(isSelfOrDescendant(folders, 'grandchild', 'root-f')).toBe(true)
  })

  it('is false for an unrelated folder', () => {
    expect(isSelfOrDescendant(folders, 'unrelated', 'root-f')).toBe(false)
  })

  it('is false for an ancestor checked against its own descendant (direction matters)', () => {
    expect(isSelfOrDescendant(folders, 'root-f', 'grandchild')).toBe(false)
  })

  it('is false when the candidate id does not exist', () => {
    expect(isSelfOrDescendant(folders, 'ghost', 'root-f')).toBe(false)
  })

  it('terminates on a corrupted parent cycle (a<->b) instead of hanging, when the ancestor is unrelated', () => {
    const cyclic = [folder('a', 'A', 'b'), folder('b', 'B', 'a')]
    const result = isSelfOrDescendant(cyclic, 'a', 'unrelated')
    expect(typeof result).toBe('boolean')
    expect(result).toBe(false)
  })

  it('terminates on a corrupted parent cycle (a<->b) and still finds the direct-cycle ancestor', () => {
    const cyclic = [folder('a', 'A', 'b'), folder('b', 'B', 'a')]
    const result = isSelfOrDescendant(cyclic, 'a', 'b')
    expect(typeof result).toBe('boolean')
    expect(result).toBe(true)
  })
})

describe('httpErrorStatus', () => {
  it('anchors on the trailing status, not a status-shaped substring earlier in the message (regression)', () => {
    // The build id "abc404xy" contains "404" mid-string; the real trailing status is 500 and must win.
    const err = new Error('DELETE /builds/abc404xy → 500')
    expect(httpErrorStatus(err)).toBe(500)
  })

  it('parses the trailing "→ <status>" out of a client.ts-shaped error message', () => {
    const err = new Error('DELETE /builds/x → 404')
    expect(httpErrorStatus(err)).toBe(404)
  })

  it('returns null for a network-level error with no status suffix', () => {
    const err = new TypeError('Failed to fetch')
    expect(httpErrorStatus(err)).toBeNull()
  })

  it('returns null for non-Error input (string)', () => {
    expect(httpErrorStatus('not an error')).toBeNull()
  })

  it('returns null for non-Error input (undefined)', () => {
    expect(httpErrorStatus(undefined)).toBeNull()
  })
})
