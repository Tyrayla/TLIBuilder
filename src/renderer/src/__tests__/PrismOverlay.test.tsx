import React from 'react'
import { describe, expect, it } from 'vitest'
import TestRenderer from 'react-test-renderer'
import PrismOverlay from '../components/PrismOverlay'
import type { EtherealCatalog, PlacedPrism } from '../api/client'

describe('PrismOverlay', () => {
  it('shows the replacement Core Talent effect while editing a named Prism', () => {
    const effect = '+12% additional Erosion Damage for each type of Crowd Control Effect on the enemy.'
    const item = {
      name: 'Ethereal Prism: Self-Delusion', short_name: 'Self-Delusion', kind: 'ethereal_prism' as const,
      icon_url: '', tags: ['Prism'], detail: [], rarities: ['rare', 'legendary'] as ('rare' | 'legendary')[],
      default_rarity: 'legendary' as const, tint_when_rare: true,
      implicit: { kind: 'replace' as const, text: 'Replaces the Core Talent with Self-Delusion' },
      replace_description: effect,
    }
    const catalog: EtherealCatalog = {
      items: [item], area_size: [], middle: [], advanced: [], do_not_replace: {}, penalties: [],
    }
    const placed: PlacedPrism = {
      id: 'prism-1', templateId: 'prism-1', kind: 'ethereal_prism', name: item.name, iconUrl: '',
      rolls: { micro: -100, medium: -100, legendary: -100 },
      ethereal: { shortName: item.short_name, rarity: 'legendary', implicit: item.implicit.text!, tintWhenRare: true },
      treeName: 'God of Might', anchorCol: 0, anchorRow: 0, boxAllocations: {},
    }
    const renderer = TestRenderer.create(
      <PrismOverlay items={[]} ethereal={catalog} inventory={[]} setInventory={() => {}} onPlace={() => {}}
        onClose={() => {}} editPlaced={placed} onUpdatePlaced={() => {}} />,
    )

    expect(renderer.root.findByProps({ className: 'prism-replacement-effect' }).children).toContain(effect)
  })
})
