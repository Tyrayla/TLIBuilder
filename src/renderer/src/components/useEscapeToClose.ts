import { useEffect, useRef } from 'react'

// Escape closes the top-most open modal only. Modals register in mount order, which is also their
// stacking order (a modal opened from inside another one mounts after it), so the last entry is the one
// on top. One shared window listener serves the whole stack.
// Assumes stacked modals mount in separate commits, as today (e.g. ReportModal opened from Settings is a
// sibling rendered later). Two modals mounting in the same commit with one nested inside the other would
// register child-first, since React runs a child's effects before its parent's.
type CloseRef = { current: () => void }
const stack: CloseRef[] = []

function onKeyDown(e: KeyboardEvent) {
  if (e.key !== 'Escape' || stack.length === 0) return
  stack[stack.length - 1].current()
}

export function useEscapeToClose(onClose: () => void): void {
  // A ref, so a new onClose each render (callers pass inline arrows) never re-registers the modal.
  const ref = useRef(onClose)
  ref.current = onClose

  useEffect(() => {
    if (typeof window === 'undefined') return  // no DOM (some unit tests); nothing to listen to
    stack.push(ref)
    if (stack.length === 1) window.addEventListener('keydown', onKeyDown)
    return () => {
      const i = stack.lastIndexOf(ref)
      if (i !== -1) stack.splice(i, 1)
      if (stack.length === 0) window.removeEventListener('keydown', onKeyDown)
    }
  }, [])
}
