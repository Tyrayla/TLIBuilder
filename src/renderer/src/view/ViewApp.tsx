// ViewApp.tsx — the share-link overview page. Boots standalone (its own Vite entry, see
// src/renderer/view.html) with NO Pyodide/compute engine and NO referenceStore/initApi — it only
// decodes the build code and looks up the two catalogs it actually needs (see
// utils/staticCatalogLean.ts), then renders gear/skills/hero-trait using the same real tooltip
// components the full app uses. Headline stats come from the `preview` snapshot the share service
// stores (computed once, client-side, at share time — see api/share.ts) rather than any
// recomputation here.
import React, { useEffect, useState } from 'react'
import { FloatingPortal } from '@floating-ui/react'
import type { EquippedGearItem, EquippedSkill, HeroTrait } from '../api/client'
// Imported from the small share module directly, not api/client.ts — this page must not pull in
// the full client (Pyodide/IPC wiring etc.) just for one URL-builder function and a type.
import { fetchSharedBuildCode, fetchSharePreview, type SharePreview } from '../api/share'
import { GearTooltipBody } from '../components/tooltip/bodies/GearTooltipBody'
import { SkillTooltipBody } from '../components/tooltip/bodies/SkillTooltipBody'
import { useFloatingTooltip } from '../components/tooltip/useFloatingTooltip'
import { decodeBuildCodeLean, LeanBuildCodeError } from '../utils/decodeBuildCodeLean'
import { rehydrateGearItemLean } from '../utils/rehydrateGearLean'
import { getHeroTraitsLean, getLegendaryGearLean, cdnIconUrl } from '../utils/staticCatalogLean'
import '../index.css'

function idFromPath(): string | null {
  const m = window.location.pathname.match(/\/b\/([A-Za-z0-9_-]+)\/?$/)
  return m ? m[1] : null
}

function HoverTip({ cls, body, children }: { cls: string; body: React.ReactNode; children: (triggerProps: Record<string, unknown>) => React.ReactNode }) {
  const tip = useFloatingTooltip({ anchor: 'cursor', side: 'right' })
  return (
    <>
      {children(tip.triggerProps)}
      {tip.open && (
        <FloatingPortal>
          <div className={cls} {...tip.floatingProps}>{body}</div>
        </FloatingPortal>
      )}
    </>
  )
}

const RES_ORDER: [string, keyof SharePreview][] = [
  ['Fire', 'fire_resist'], ['Cold', 'cold_resist'], ['Lightning', 'lightning_resist'], ['Erosion', 'erosion_resist'],
]

function fmt(n: number): string { return Math.round(n).toLocaleString() }

function StatsHeader({ preview }: { preview: SharePreview }) {
  return (
    <div className="view-header">
      {preview.icon_url && <img src={preview.icon_url} alt="" className="view-hero-icon" />}
      <div>
        <h1>{preview.hero} — {preview.trait}</h1>
        <div className="view-subtitle">Level {preview.level} · Main skill: {preview.main_skill}</div>
        <div className="view-stat-row">
          <span>Life {fmt(preview.max_life)}</span>
          <span>Mana {fmt(preview.max_mana)}</span>
          <span>ES {fmt(preview.max_energy_shield)}</span>
          <span>DPS {fmt(preview.total_dps)}</span>
          <span>Move Speed {preview.movement_speed >= 0 ? '+' : ''}{Math.round(preview.movement_speed)}%</span>
        </div>
        <div className="view-stat-row">
          {RES_ORDER.map(([label, key]) => (
            <span key={key}>{label} {Math.round(preview[key] as number)}%</span>
          ))}
        </div>
      </div>
    </div>
  )
}

// Mirrors GearScreen.tsx's SLOT_ORDER (module-private there, so duplicated rather than imported) —
// same canonical equipment order, so this reads as a real equipment sheet at a glance instead of
// whatever order the build code happened to list items in.
const SLOT_LABELS: Record<string, string> = {
  helmet: 'Helmet', amulet: 'Amulet', chest: 'Chest', gloves: 'Gloves', belt: 'Belt',
  boots: 'Boots', ring1: 'Ring 1', ring2: 'Ring 2', weapon1: 'Weapon 1', weapon2: 'Weapon 2',
}
const SLOT_ORDER = Object.keys(SLOT_LABELS)

function primarySlot(item: EquippedGearItem): string | null {
  const s = item.slot
  return (Array.isArray(s) ? s[0] : s) ?? null
}

function GearList({ items }: { items: EquippedGearItem[] }) {
  if (items.length === 0) return null
  const sorted = [...items].sort((a, b) => {
    const ai = SLOT_ORDER.indexOf(primarySlot(a) ?? '')
    const bi = SLOT_ORDER.indexOf(primarySlot(b) ?? '')
    return (ai === -1 ? SLOT_ORDER.length : ai) - (bi === -1 ? SLOT_ORDER.length : bi)
  })
  return (
    <section className="view-section">
      <h2>Gear</h2>
      <div className="view-gear-grid">
        {sorted.map((item, i) => {
          const slot = primarySlot(item)
          return (
            <HoverTip key={i} cls="tooltip tooltip--gear" body={<GearTooltipBody item={item} hideBadges />}>
              {trigger => (
                <div className="view-gear-row" {...trigger}>
                  {slot && <span className="view-gear-slot-label">{SLOT_LABELS[slot] ?? slot}</span>}
                  <span className="view-gear-item-name">{item.displayName || item.name}</span>
                </div>
              )}
            </HoverTip>
          )
        })}
      </div>
    </section>
  )
}

function SkillList({ items }: { items: EquippedSkill[] }) {
  if (items.length === 0) return null
  return (
    <section className="view-section">
      <h2>Skills</h2>
      <div className="view-chip-row">
        {items.map((item, i) => (
          <HoverTip key={i} cls="tooltip tooltip--skill" body={<SkillTooltipBody lines={item.description_lines ?? []} />}>
            {trigger => <span className="view-chip" {...trigger}>{item.name}</span>}
          </HoverTip>
        ))}
      </div>
    </section>
  )
}

// Deliberately self-sufficient (icon + name + description) rather than relying on StatsHeader for
// the name — StatsHeader only renders when a preview snapshot exists (an older client, or one that
// hit the buildSharePreview() fail-soft path, means no preview), so this must stand on its own.
function TraitCard({ trait }: { trait: HeroTrait }) {
  const icon = cdnIconUrl('hero_trait', trait.icon_url)
  return (
    <section className="view-section">
      <h2>Hero Trait</h2>
      <div className="view-trait-card">
        {icon && <img src={icon} alt="" className="view-trait-icon" />}
        <div>
          <div className="view-trait-name">{trait.hero} — {trait.variant_name}</div>
          {trait.description && <p className="view-trait-description">{trait.description}</p>}
        </div>
      </div>
    </section>
  )
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'not-found' }
  | { kind: 'ready'; preview: SharePreview | null; gear: EquippedGearItem[]; skills: EquippedSkill[]; trait: HeroTrait | null }

export default function ViewApp() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const id = idFromPath()

  useEffect(() => {
    if (!id) { setState({ kind: 'not-found' }); return }
    let cancelled = false

    ;(async () => {
      // Preview is best-effort — an id that predates this feature (or whose client couldn't
      // compute one) still gets a gear/skills/trait overview, just no headline stats banner.
      const preview = await fetchSharePreview(id)

      let code: string
      try {
        code = await fetchSharedBuildCode(id)
      } catch {
        if (!cancelled) setState({ kind: 'not-found' })
        return
      }

      let build: Record<string, unknown>
      try {
        build = await decodeBuildCodeLean(code)
      } catch (e) {
        if (!cancelled) setState({ kind: 'not-found' })
        console.error('decodeBuildCodeLean failed:', e instanceof LeanBuildCodeError ? e.message : e)
        return
      }

      // Everything past this point reads fields out of attacker-shapeable JSON (the share service
      // stores whatever any anonymous poster submits, and only checks it's *structurally* a valid
      // tli1 code — see build_code.py's validate_build_code — never that gear/skills entries are
      // well-formed objects). A malformed entry (null, a bare string, etc.) must degrade this one
      // build's overview to "not found," never leave the page stuck on "Loading build…" forever
      // via an unhandled rejection in this un-awaited IIFE — hence the try/catch around all of it,
      // plus filtering non-object entries before they ever reach rehydration/rendering.
      try {
        const isPlainObject = (v: unknown): v is Record<string, unknown> =>
          typeof v === 'object' && v !== null && !Array.isArray(v)
        // Coerce fields the tooltip bodies iterate over (.map/.slice) to real arrays. isPlainObject
        // only guards the entry's own shape — a crafted/Vorax gear item or an unknown legendary
        // (rehydrateGearItemLean's pass-through branches) still reaches the tooltip with whatever
        // `affixes`/`customizations` shape was in the code, and a skill entry's `description_lines`/
        // `skill_tags` are never touched by any rehydration step at all. Wrong-typed here (e.g. a
        // string instead of an array) would otherwise throw inside a tooltip hover — AFTER this
        // try/catch has already resolved — breaking the whole page instead of degrading one item.
        const arrayField = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])

        const rawGear = Array.isArray(build.gear) ? build.gear.filter(isPlainObject).map((g): Record<string, unknown> => ({
          ...g, affixes: arrayField(g.affixes), customizations: arrayField(g.customizations),
        })) : []
        const needsLegendaryCatalog = rawGear.some(g => !g.is_crafted && !g.is_vorax)
        const traitId = typeof build.traitId === 'string' ? build.traitId : null

        const [legendaryItems, heroTraits] = await Promise.all([
          needsLegendaryCatalog ? getLegendaryGearLean().catch(() => []) : Promise.resolve([]),
          traitId ? getHeroTraitsLean().catch(() => []) : Promise.resolve([]),
        ])

        const gear = rawGear.map(g => rehydrateGearItemLean(g, legendaryItems))
        const skills = (Array.isArray(build.skills)
          ? build.skills.filter(isPlainObject).filter(s => typeof s.name === 'string').map(s => ({
              ...s, skill_tags: arrayField(s.skill_tags), description_lines: arrayField(s.description_lines),
            }))
          : []) as unknown as EquippedSkill[]
        const trait = traitId ? (heroTraits.find(t => t.trait_id === traitId) ?? null) : null

        if (!cancelled) setState({ kind: 'ready', preview, gear, skills, trait })
      } catch (e) {
        if (!cancelled) setState({ kind: 'not-found' })
        console.error('Rendering the shared build failed:', e)
      }
    })()

    return () => { cancelled = true }
  }, [id])

  if (state.kind === 'loading') return <div className="view-shell view-status">Loading build…</div>
  if (state.kind === 'not-found') {
    return <div className="view-shell view-status">This build link doesn't exist, or the service is unreachable.</div>
  }

  const { preview, gear, skills, trait } = state
  const webOpenUrl = id ? `${window.location.origin}/?share=${encodeURIComponent(id)}` : '/'
  const desktopOpenUrl = id ? `tlibuilder://import/${encodeURIComponent(id)}` : undefined

  return (
    <div className="view-shell">
      {preview && <StatsHeader preview={preview} />}
      {/* Two-column body — gear alongside skills/trait — so the whole build fits as one
          at-a-glance sheet instead of a long stack of full-width sections. */}
      <div className="view-body">
        <GearList items={gear} />
        <div className="view-body-col">
          <SkillList items={skills} />
          {trait && <TraitCard trait={trait} />}
        </div>
      </div>
      <div className="view-actions">
        <a className="btn btn-primary" href={webOpenUrl}>Open in TLI Builder (Web)</a>
        {desktopOpenUrl && <a className="btn btn-secondary" href={desktopOpenUrl}>Open in Desktop App</a>}
      </div>
    </div>
  )
}
