import React from 'react'
import { describe, expect, it } from 'vitest'
import TestRenderer from 'react-test-renderer'
import { TraitTooltipBody } from '../components/HeroTraitShared'
import { resolveTreeNodeTooltip } from '../screens/HeroTraitTree'
import type { HeroTrait, HeroTraitTreeNode } from '../api/client'

const trait = {
  trait_id: 'the_ultimate_one',
  hero: 'Youga',
  variant_name: 'The Ultimate One',
  description: '',
  levels: [
    { level: 1, unlock_level: 1, effects: ['100% CDR bonus applies to Clockwork Core, up to 36%'] },
    { level: 2, unlock_level: 1, effects: ['120% CDR bonus applies to Clockwork Core, up to 39%'] },
    { level: 3, unlock_level: 1, effects: ['140% CDR bonus applies to Clockwork Core, up to 42%'] },
    { level: 4, unlock_level: 1, effects: ['160% CDR bonus applies to Clockwork Core, up to 45%'] },
    { level: 5, unlock_level: 1, effects: ['180% CDR bonus applies to Clockwork Core, up to 48%'] },
  ],
  artificial_moon: { description: '', effects: ['+1 Max Tangle Quantity', '+20% Clockwork Core Damage'] },
  advanced_traits: [],
  tree_root_id: 'the_ultimate_one',
} as HeroTrait

const root = {
  node_id: 'the_ultimate_one',
  name: 'I Am the Ultimate One',
  column: 4,
  row: 3,
  x: 0.514,
  y: 0.53,
  effects: ['stale authored rank text: 0% / 120% / 140% / 160% / 180%'],
} as HeroTraitTreeNode

describe('HeroTraitTree root tooltip', () => {
  it('renders the selected imported rank and only shows Artificial Moon at rank 5', () => {
    const renderAt = (level: number) => {
      const content = resolveTreeNodeTooltip(trait, root, level)
      return TestRenderer.create(
        <TraitTooltipBody name={root.name} slotLevel={level} effects={content.effects} moonEffects={content.moonEffects} />,
      )
    }

    const levelOne = renderAt(1).root
    expect(levelOne.findAllByType('li').map(node => node.children.join(''))).toEqual([
      '100% CDR bonus applies to Clockwork Core, up to 36%',
    ])
    expect(levelOne.findAllByType('div').map(node => node.children.join('')).join(' ')).not.toContain('Artificial Moon')

    const levelFive = renderAt(5).root
    expect(levelFive.findAllByType('li').map(node => node.children.join(''))).toEqual([
      '180% CDR bonus applies to Clockwork Core, up to 48%',
      '+1 Max Tangle Quantity',
      '+20% Clockwork Core Damage',
    ])
    expect(levelFive.findAllByType('div').map(node => node.children.join('')).join(' ')).toContain('Artificial Moon')
  })
})
