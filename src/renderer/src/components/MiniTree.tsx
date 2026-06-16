// A small, read-only render of a talent tree with one node highlighted — used as a hover tooltip in the
// stats source breakdown so a talent contribution shows WHERE on the tree it comes from. Mirrors the
// deterministic 7×5 SVG grid that TreeViewerScreen draws (same nodeX/nodeY math), but with no interaction,
// search, or core-talent chrome. Tree data is fetched once per tree name and cached for the session.
import React, { useEffect, useState } from 'react'
import { api, TreeData } from '../api/client'

const COLS = 7
const ROWS = 5
const VW = 700
const VH = 500
const HEADER = 42
const CELL_W = VW / COLS
const CELL_H = (VH - HEADER) / ROWS
const NODE_R = 28

const nodeX = (col: number) => col * CELL_W + CELL_W / 2
const nodeY = (row: number) => HEADER + row * CELL_H + CELL_H / 2

// One in-flight/resolved promise per tree name — trees aren't in the reference store, so cache here.
const _treeCache = new Map<string, Promise<TreeData>>()
function getTreeCached(name: string): Promise<TreeData> {
  let p = _treeCache.get(name)
  if (!p) { p = api.getTree(name); _treeCache.set(name, p) }
  return p
}

export function MiniTree({ treeName, nodeId }: { treeName: string; nodeId: string }) {
  const [tree, setTree] = useState<TreeData | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    let live = true
    getTreeCached(treeName).then(t => { if (live) setTree(t) }).catch(() => { if (live) setErr(true) })
    return () => { live = false }
  }, [treeName])

  if (err) return <div style={{ padding: 6, fontSize: 11, color: '#cfcfe6', fontWeight: 700 }}>{treeName}</div>
  if (!tree) return <div style={{ padding: 6, fontSize: 11, color: '#888' }}>Loading {treeName}…</div>

  const nodeMap = Object.fromEntries(tree.nodes.map(n => [n.id, n]))
  const target = nodeMap[nodeId]
  const W = 240

  return (
    <div style={{ width: W }}>
      <div style={{ fontWeight: 700, color: '#cfcfe6', fontSize: 11, marginBottom: 4 }}>
        {treeName}{target ? ` · ${target.node_type}` : ''}
      </div>
      <svg viewBox={`0 0 ${VW} ${VH}`} width={W} height={Math.round(W * VH / VW)} style={{ display: 'block' }}>
        {tree.connections.map(({ from, to }, i) => {
          const n1 = nodeMap[from]; const n2 = nodeMap[to]
          if (!n1 || !n2) return null
          return (
            <line key={i}
              x1={nodeX(n1.column)} y1={nodeY(n1.row)} x2={nodeX(n2.column)} y2={nodeY(n2.row)}
              stroke="#3a3a5a" strokeWidth={2} />
          )
        })}
        {tree.nodes.map(n => {
          const hl = n.id === nodeId
          return (
            <circle key={n.id}
              cx={nodeX(n.column)} cy={nodeY(n.row)} r={hl ? NODE_R * 1.2 : NODE_R}
              fill={hl ? '#e9c046' : 'rgba(120,120,160,0.16)'}
              stroke={hl ? '#fff7d0' : '#454566'} strokeWidth={hl ? 5 : 1.5} />
          )
        })}
      </svg>
      {target && target.effects.length > 0 && (
        <div style={{ marginTop: 5, fontSize: 10, color: '#b8b8c8', lineHeight: 1.4 }}>
          {target.effects.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
    </div>
  )
}
