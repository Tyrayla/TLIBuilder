import React from 'react'
import { describe, expect, it } from 'vitest'
import TestRenderer from 'react-test-renderer'
import AlternateSpacetimeEffects from '../components/AlternateSpacetimeEffects'

describe('AlternateSpacetimeEffects', () => {
  it('renders every skill choice and each source effect line in the expandable section', () => {
    const renderer = TestRenderer.create(
      <AlternateSpacetimeEffects
        header="Alternate Spacetime Youga Effects (19 Skill Effects)"
        effects={[
          { skill: 'Chromatic Shot', lines: [
            'While Selves of All Realms is active, +1% additional Cold Damage and -1% additional Lightning and Fire Damage for this skill for every 3 Intelligence you have. Stacks up to 110 time(s)',
            'While Selves of All Realms is active, +1% additional Lightning Damage and -1% additional Cold and Fire Damage for this skill for every 4 Dexterity you have. Stacks up to 116 time(s)',
            'While Selves of All Realms is active, +1% additional Fire Damage and -1% additional Cold and Lightning Damage for this skill for every 5 Strength you have. Stacks up to 122 time(s)',
          ] },
          { skill: 'Shadow Shot', lines: [
            'While Selves of All Realms is active, +30% additional Erosion Damage dealt by this skill to enemies for each type of Crowd Control Effect they are under, up to +120%',
          ] },
        ]}
      />,
    )

    const details = renderer.root.findByType('details')
    expect(details.findByType('summary').children.join('')).toBe('Alternate Spacetime Youga Effects (19 Skill Effects)')
    expect(details.findAllByType('h3').map(node => node.children.join(''))).toEqual(['Chromatic Shot', 'Shadow Shot'])
    expect(details.findAllByType('p').map(node => node.children.join(''))).toEqual([
      'While Selves of All Realms is active, +1% additional Cold Damage and -1% additional Lightning and Fire Damage for this skill for every 3 Intelligence you have. Stacks up to 110 time(s)',
      'While Selves of All Realms is active, +1% additional Lightning Damage and -1% additional Cold and Fire Damage for this skill for every 4 Dexterity you have. Stacks up to 116 time(s)',
      'While Selves of All Realms is active, +1% additional Fire Damage and -1% additional Cold and Lightning Damage for this skill for every 5 Strength you have. Stacks up to 122 time(s)',
      'While Selves of All Realms is active, +30% additional Erosion Damage dealt by this skill to enemies for each type of Crowd Control Effect they are under, up to +120%',
    ])
  })
})
