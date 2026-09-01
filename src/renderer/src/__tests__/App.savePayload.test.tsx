import fs from 'node:fs'
import path from 'node:path'
import { describe, it, expect } from 'vitest'

// Regression coverage for bug-266/bug-267: baseMemory (the revival-enabled Base/Special hero-memory
// slot) and memoryInventory were silently dropped by TWO of App.tsx's three hand-written
// build-payload literals (saveBuild, saveAsBuild, onRequestSave's quit/close-triggered save) — each
// literal duplicates the full field list independently rather than sharing one, which is exactly how
// a field can be added to the store/backend but missed at one or more of the three call sites. App.tsx
// can't be rendered directly here (see App.previewWiring.test.tsx's note: it touches
// document.documentElement.style.zoom unconditionally on mount, and this suite runs in a DOM-less
// 'node' vitest environment) — so this pins the source text of each literal instead, the same
// technique already used for the preview-wiring call sites.
const APP_TSX = fs.readFileSync(path.resolve(__dirname, '../App.tsx'), 'utf-8')

// Each `const build = { ... }` literal that gets sent to api.postBuild — saveBuild, saveAsBuild, and
// the onRequestSave quit/close handler.
const BUILD_LITERALS = [...APP_TSX.matchAll(/const build = \{[^}]*\}/g)].map(m => m[0])

describe('App.tsx build-save payload literals (source pin)', () => {
  it('found all three save-payload literals (saveBuild, saveAsBuild, onRequestSave)', () => {
    expect(BUILD_LITERALS).toHaveLength(3)
  })

  it('every save-payload literal includes baseMemory and memoryInventory alongside heroMemories', () => {
    for (const literal of BUILD_LITERALS) {
      expect(literal).toContain('heroMemories: s.heroMemories')
      expect(literal).toContain('baseMemory: s.baseMemory')
      expect(literal).toContain('memoryInventory: s.memoryInventory')
    }
  })
})
