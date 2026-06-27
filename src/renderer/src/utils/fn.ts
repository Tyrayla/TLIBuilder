// Tiny local replacements for the only two lodash-es functions we used (isEqual, debounce), so we can drop the
// dependency. Both are intentionally minimal — deepEqual handles the JSON-shaped build data we compare, and
// debounce returns a callable with a .cancel() method (matching how useBuildCalculation uses it).

/** Structural equality for JSON-shaped values (primitives, arrays, plain objects). */
export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false
  const arrA = Array.isArray(a), arrB = Array.isArray(b)
  if (arrA !== arrB) return false
  const ka = Object.keys(a as object), kb = Object.keys(b as object)
  if (ka.length !== kb.length) return false
  for (const k of ka) {
    if (!Object.prototype.hasOwnProperty.call(b, k)) return false
    if (!deepEqual((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k])) return false
  }
  return true
}

/** Trailing-edge debounce; the returned function carries a .cancel() to drop a pending call. */
export function debounce<A extends unknown[]>(
  fn: (...args: A) => void, ms: number,
): ((...args: A) => void) & { cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null
  const wrapped = (...args: A) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { timer = null; fn(...args) }, ms)
  }
  wrapped.cancel = () => { if (timer) { clearTimeout(timer); timer = null } }
  return wrapped
}
