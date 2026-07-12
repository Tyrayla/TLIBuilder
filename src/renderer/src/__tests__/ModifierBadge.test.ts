import { describe, it, expect } from 'vitest'
import { gearModifierStatus } from '../components/ModifierBadge'

// `gearModifierStatus` (2026-07-12: exercises the `resolved_keys` catalog-hover fallback added to
// `/api/legendary-gear`'s affixes — see `backend/server.py::_affix_resolved_keys` and
// `backend/engine/coverage.py::_affix_is_modeled`, the SAME resolution). A gear affix with no LOCAL
// stat key (`stat_key`/`stat_keys`/`min_stat_keys`/`max_stat_keys`/`dual_stat_groups` all empty — the
// shape of a catalog hover, where nothing has gone through the build-scoped `/api/engine-stats` compute
// yet) falls back to the affix's own build-independent `resolved_keys` rather than going straight to
// 'unrecognized'.
describe('gearModifierStatus / resolved_keys fallback', () => {
  const consumed = new Set(['working_key'])
  const universe = new Set(['working_key', 'inactive_key'])

  it('empty local keys + non-empty resolved_keys classifies via consumed/universe, not null', () => {
    const workingAffix = { raw_text: 'some catalog line', resolved_keys: ['working_key'] }
    expect(gearModifierStatus(workingAffix, consumed, universe)).toBe('working')

    const inactiveAffix = { raw_text: 'some other catalog line', resolved_keys: ['inactive_key'] }
    expect(gearModifierStatus(inactiveAffix, consumed, universe)).toBe('inactive')

    const unusedAffix = { raw_text: 'a recognized but never-consumed line', resolved_keys: ['nowhere_key'] }
    expect(gearModifierStatus(unusedAffix, consumed, universe)).toBe('unused')
  })

  it('resolved_keys: [] classifies as unrecognized', () => {
    const affix = { raw_text: 'a genuinely NYI catalog line', resolved_keys: [] }
    expect(gearModifierStatus(affix, consumed, universe)).toBe('unrecognized')
  })

  it('resolved_keys: undefined fails open to null (older backend / not sent)', () => {
    const affix = { raw_text: 'a line from a backend that predates resolved_keys' }
    expect(gearModifierStatus(affix, consumed, universe)).toBeNull()
  })

  it('a build-scoped unresolved hit still wins over an absent resolved_keys check', () => {
    // Mirrors the equipped-build path: no local keys, no resolved_keys sent, but the backend's build-scoped
    // compute already flagged this exact raw_text as unresolved -> 'unrecognized' without ever consulting
    // resolved_keys (the 4th `unresolved` param is checked first).
    const affix = { raw_text: 'an equipped, backend-checked, unresolved line' }
    const unresolved = new Set(['an equipped, backend-checked, unresolved line'])
    expect(gearModifierStatus(affix, consumed, universe, unresolved)).toBe('unrecognized')
  })

  it('a placeholder affix is never flagged, regardless of resolved_keys', () => {
    const affix = { raw_text: 'unfilled random affix slot', affix_kind: 'placeholder', resolved_keys: [] }
    expect(gearModifierStatus(affix, consumed, universe)).toBeNull()
  })

  it('non-empty LOCAL keys take priority over resolved_keys (local keys already drive classification)', () => {
    const affix = { stat_key: 'working_key', resolved_keys: [] }
    expect(gearModifierStatus(affix, consumed, universe)).toBe('working')
  })
})
