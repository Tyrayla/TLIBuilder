import React, { useEffect, useMemo, useState } from 'react'
import { useBuildStore } from '../store/buildStore'
import { useReferenceStore } from '../store/referenceStore'
import { api, type TreeSlot } from '../api/client'
import NotesEditor from '../components/notes/NotesEditor'
import type { NoteResolveCtx, NodeIndexEntry } from '../utils/noteEntities'

export default function NotesScreen() {
  const notes = useBuildStore(s => s.notes)
  const setNotes = useBuildStore(s => s.setNotes)
  const gear = useBuildStore(s => s.gear)
  const skills = useBuildStore(s => s.skills)
  const pactSpirits = useBuildStore(s => s.pactSpirits)
  const heroMemories = useBuildStore(s => s.heroMemories)
  const traitId = useBuildStore(s => s.traitId)
  const allSpirits = useBuildStore(s => s.allSpirits)
  const slots = useBuildStore(s => s.slots)
  const activeLoadoutId = useBuildStore(s => s.activeLoadoutId)

  const skillsById = useReferenceStore(s => s.skillsById)
  const skillsByName = useReferenceStore(s => s.skillsByName)
  const legendaryIndex = useReferenceStore(s => s.legendaryIndex)
  const legendaryCatalog = useReferenceStore(s => s.legendaryCatalog)
  const conditions = useReferenceStore(s => s.conditions)
  const heroTraits = useReferenceStore(s => s.heroTraits)

  const [nodes, setNodes] = useState<NodeIndexEntry[]>([])
  const [showHelp, setShowHelp] = useState(false)

  // No global node catalog — fetch the build's trees and index their nodes (label by primary effect).
  const treeNames = useMemo(
    () => [...new Set(slots.filter((s): s is TreeSlot => !!s).map(s => s.treeName))],
    [slots],
  )
  useEffect(() => {
    let cancelled = false
    Promise.all(treeNames.map(n => api.getTree(n).catch(() => null))).then(trees => {
      if (cancelled) return
      const out: NodeIndexEntry[] = []
      for (const t of trees) {
        if (!t) continue
        for (const node of t.nodes) {
          const primary = (node.effects[0] || node.id).trim()
          out.push({ key: node.id, name: primary.length > 48 ? primary.slice(0, 46) + '…' : primary, lines: node.effects })
        }
      }
      setNodes(out)
    })
    return () => { cancelled = true }
  }, [treeNames.join('|')])  // eslint-disable-line react-hooks/exhaustive-deps

  const ctx: NoteResolveCtx = useMemo(() => ({
    gear, skills, pactSpirits, heroMemories, traitId, allSpirits, nodes,
    reference: { skillsById, skillsByName, legendaryIndex, legendaryCatalog, conditions, heroTraits },
  }), [gear, skills, pactSpirits, heroMemories, traitId, allSpirits, nodes,
      skillsById, skillsByName, legendaryIndex, legendaryCatalog, conditions, heroTraits])

  return (
    <div className="notes-screen">
      <div className="notes-header">
        <h2 className="title-accent" style={{ fontSize: 20 }}>Build Notes</h2>
        <button className="notes-help-btn" onClick={() => setShowHelp(v => !v)} title="How linking works">?</button>
        {showHelp && (
          <div className="notes-help-pop">
            <div className="notes-help-title">Linking entities</div>
            <div>Type <b>@</b> then a name to insert a link to an item, talent node, skill, hero trait, pact spirit, memory, or condition.</div>
            <div>Links prefer this build's own entities, then the general catalog. Hover a link to see its tooltip.</div>
            <div>A red link means the reference no longer resolves (e.g. that item was removed).</div>
          </div>
        )}
      </div>
      {/* Re-mount on loadout switch so the editor re-initializes from that loadout's notes. */}
      <NotesEditor key={activeLoadoutId} initialNotes={notes} onChange={setNotes} ctx={ctx} />
    </div>
  )
}
