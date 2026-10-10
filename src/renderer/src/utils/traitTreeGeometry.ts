// Pure connector geometry for a "tree" allocation_mode Hero Trait. The in-game tree draws a faint ring that many
// nodes sit on, and links between two ring nodes follow the ring ARC; every other link (root -> first ring,
// short neighbour links) is a straight line. We derive that from node positions alone — no per-trait data:
// find the circle that the most non-root nodes lie on (within a tolerance), then any connection whose both ends
// sit on it becomes an arc. A tree with no such ring (fewer than MIN_RING_NODES on a common circle) keeps
// straight lines everywhere, so traits laid out differently render exactly as before.

export interface Pt { x: number; y: number }
export interface Circle { cx: number; cy: number; r: number }
export type ConnectorPath = { kind: 'line' | 'arc'; d: string }

const MIN_RING_NODES = 5
const RING_TOL = 0.1   // a node is "on the ring" when |dist - r| <= RING_TOL * r

function circleThrough(a: Pt, b: Pt, c: Pt): Circle | null {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
  if (Math.abs(d) < 1e-9) return null
  const a2 = a.x * a.x + a.y * a.y, b2 = b.x * b.x + b.y * b.y, c2 = c.x * c.x + c.y * c.y
  const cx = (a2 * (b.y - c.y) + b2 * (c.y - a.y) + c2 * (a.y - b.y)) / d
  const cy = (a2 * (c.x - b.x) + b2 * (a.x - c.x) + c2 * (b.x - a.x)) / d
  return { cx, cy, r: Math.hypot(a.x - cx, a.y - cy) }
}

const onCircle = (p: Pt, c: Circle, tol = RING_TOL) => Math.abs(Math.hypot(p.x - c.cx, p.y - c.cy) - c.r) <= tol * c.r

/** Least-squares circle through `pts` (algebraic fit). Falls back to `seed` when the system is degenerate. */
function refit(pts: Pt[], seed: Circle): Circle {
  // Solve x^2 + y^2 = 2*cx*x + 2*cy*y + k in the least-squares sense via the 3x3 normal equations.
  let sxx = 0, sxy = 0, sx = 0, syy = 0, sy = 0, n = 0, bx = 0, by = 0, b1 = 0
  for (const { x, y } of pts) {
    const z = x * x + y * y
    sxx += 4 * x * x; sxy += 4 * x * y; sx += 2 * x; syy += 4 * y * y; sy += 2 * y; n += 1
    bx += 2 * x * z; by += 2 * y * z; b1 += z
  }
  const M = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]]
  const v = [bx, by, b1]
  const det3 = (m: number[][]) =>
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
    - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
    + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
  const D = det3(M)
  if (Math.abs(D) < 1e-9) return seed
  const col = (i: number) => M.map((row, r) => row.map((val, c) => (c === i ? v[r] : val)))
  const cx = det3(col(0)) / D, cy = det3(col(1)) / D, k = det3(col(2)) / D
  const r2 = k + cx * cx + cy * cy
  return r2 > 0 ? { cx, cy, r: Math.sqrt(r2) } : seed
}

/** The ring circle most non-root nodes lie on, or null when fewer than MIN_RING_NODES do. */
export function findRing(nodes: (Pt & { id: string })[], rootId: string): Circle | null {
  const cand = nodes.filter(n => n.id !== rootId)
  // A real ring is centred inside the layout and no larger than it; nearly-collinear triples give huge circles
  // that "contain" almost any straight run of nodes, so reject those.
  const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y)
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const maxR = 0.75 * Math.max(maxX - minX, maxY - minY)
  let best: { circle: Circle; inliers: number } | null = null
  for (let i = 0; i < cand.length; i++) {
    for (let j = i + 1; j < cand.length; j++) {
      for (let k = j + 1; k < cand.length; k++) {
        const c = circleThrough(cand[i], cand[j], cand[k])
        if (!c || c.r > maxR || c.cx < minX || c.cx > maxX || c.cy < minY || c.cy > maxY) continue
        const first = cand.filter(p => onCircle(p, c, 2 * RING_TOL))
        if (first.length < MIN_RING_NODES) continue
        // Refit on the inliers, then score by how many nodes the REFIT circle holds (ties: larger circle).
        const fitted = refit(first, c)
        const held = cand.filter(p => onCircle(p, fitted))
        if (held.length < MIN_RING_NODES) continue
        // The drawn ring encloses the whole tree: no node (root included) may lie outside it.
        if (nodes.some(p => Math.hypot(p.x - fitted.cx, p.y - fitted.cy) > fitted.r * (1 + RING_TOL))) continue
        // Ties go to the LARGER circle: the drawn ring is the outer one; a smaller circle can coincidentally
        // pass through a few inner nodes.
        if (!best || held.length > best.inliers || (held.length === best.inliers && fitted.r > best.circle.r)) {
          best = { circle: fitted, inliers: held.length }
        }
      }
    }
  }
  return best ? best.circle : null
}

const f = (v: number) => Number(v.toFixed(2))

/** SVG path for the link a -> b: an arc along `ring` when both ends are on it, else a straight line. */
export function connectorPath(a: Pt, b: Pt, ring: Circle | null): ConnectorPath {
  const line: ConnectorPath = { kind: 'line', d: `M ${f(a.x)} ${f(a.y)} L ${f(b.x)} ${f(b.y)}` }
  if (!ring || !onCircle(a, ring) || !onCircle(b, ring)) return line
  // Short arc: sweep-flag is 1 (clockwise in SVG's y-down space) when the cross product of the two radii is positive.
  const cross = (a.x - ring.cx) * (b.y - ring.cy) - (a.y - ring.cy) * (b.x - ring.cx)
  const sweep = cross > 0 ? 1 : 0
  return { kind: 'arc', d: `M ${f(a.x)} ${f(a.y)} A ${f(ring.r)} ${f(ring.r)} 0 0 ${sweep} ${f(b.x)} ${f(b.y)}` }
}
