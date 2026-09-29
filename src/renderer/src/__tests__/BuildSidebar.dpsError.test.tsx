import React from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import BuildSidebar from '../components/BuildSidebar'
import { useBuildStore } from '../store/buildStore'
import type { TliErrorPayload } from '../errors/tliError'

// bug-289 (sidebar half): a failed engine-stats compute left the Full DPS box showing a bare "—"
// forever — visually identical to "nothing equipped yet", with no way to tell a real failure happened.
// When statsError is set and there's no total to show, the box must say so instead.

const initialState = useBuildStore.getState()

const ERROR: TliErrorPayload = {
  code: 'TLI-NET-001',
  title: 'A required service cannot be reached',
  message: 'Check your connection, then retry.',
  remediation: 'Check your connection, then retry.',
  operation: 'engine.stats',
  retryable: true,
}

function noop() {}

describe('BuildSidebar — Full DPS box surfaces a stats error (bug-289)', () => {
  beforeEach(() => {
    useBuildStore.setState(initialState, true)
  })

  it('shows "Error" (not a bare "—") with the error message as the element\'s title, when statsError is set and there is no total', () => {
    useBuildStore.setState({ statsError: ERROR, statsLoading: false })

    let renderer!: TestRenderer.ReactTestRenderer
    act(() => {
      renderer = TestRenderer.create(
        <BuildSidebar
          screen="build-overview" buildName="Test Build" isDirty={false}
          onNav={noop} onSave={noop} onSaveAs={noop} onGoBack={noop}
        />,
      )
    })

    // Found by its text content, not a className — the bug report describes the observable text/title,
    // not which element carries it.
    const errorNodes = renderer.root.findAll(
      (n) => typeof n.type === 'string' && n.children.length === 1 && n.children[0] === 'Error',
    )
    expect(errorNodes).toHaveLength(1)
    expect(errorNodes[0].props.title).toBe(ERROR.message)
    renderer.unmount()
  })
})
