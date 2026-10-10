import React from 'react'
import { describe, it, expect } from 'vitest'
import TestRenderer, { act } from 'react-test-renderer'
import { TraitTooltipBody, findTraitGlossaryTerm } from '../components/HeroTraitShared'

const GLOSSARY = {
  ss14_youga_spacetime_conqueror: {
    name: 'Spacetime Conqueror',
    description: 'Trait Mechanic: example description text',
  },
}

const text = (node: TestRenderer.ReactTestInstance): string =>
  node.children.map(c => (typeof c === 'string' ? c : text(c))).join('')

describe('TraitTooltipBody header term', () => {
  it('finds a glossary entry by its name', () => {
    expect(findTraitGlossaryTerm(GLOSSARY, 'Spacetime Conqueror')?.description).toBe('Trait Mechanic: example description text')
    expect(findTraitGlossaryTerm(GLOSSARY, 'Spacetime Overlord')).toBeNull()
    expect(findTraitGlossaryTerm(undefined, 'Spacetime Conqueror')).toBeNull()
  })

  it('shows the subtitle under the title as a clickable term that opens its glossary text', () => {
    let r!: TestRenderer.ReactTestRenderer
    act(() => {
      r = TestRenderer.create(
        <TraitTooltipBody name="I Arrive Alongside Destiny" slotLevel={5} effects={['+28% Cooldown Recovery Speed']}
          subtitle="Spacetime Conqueror" glossary={GLOSSARY} />)
    })
    const term = r.root.findByProps({ 'data-testid': 'trait-info-term' })
    expect(text(term)).toBe('Spacetime Conqueror')
    expect(r.root.findAllByProps({ 'data-testid': 'trait-info-term-def' })).toHaveLength(0)
    act(() => { term.props.onClick({ stopPropagation() {} }) })
    expect(text(r.root.findByProps({ 'data-testid': 'trait-info-term-def' }))).toBe('Trait Mechanic: example description text')
    act(() => { term.props.onClick({ stopPropagation() {} }) })
    expect(r.root.findAllByProps({ 'data-testid': 'trait-info-term-def' })).toHaveLength(0)
  })

  it('renders a subtitle without a glossary entry as plain text, not a button', () => {
    let r!: TestRenderer.ReactTestRenderer
    act(() => {
      r = TestRenderer.create(
        <TraitTooltipBody name="X" slotLevel={1} effects={[]} subtitle="Spacetime Overlord" glossary={GLOSSARY} />)
    })
    expect(r.root.findAllByType('button')).toHaveLength(0)
    expect(JSON.stringify(r.toJSON())).toContain('Spacetime Overlord')
  })
})
