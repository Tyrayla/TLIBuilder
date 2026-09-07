// Layer 1 of the tooltip system: one positioning + behavior primitive backed by
// @floating-ui/react. Owns anchoring (element or cursor), collision handling
// (flip/shift/size), and open/hover/pin state. The primitive does NOT render — it only
// supplies prop bags. The caller renders the floating element inside <FloatingPortal>,
// conditional on `open`. See docs/TOOLTIP_REVAMP_HANDOFF.md §4.

import React, { useCallback, useState } from 'react'
import {
  useFloating, autoUpdate, offset, flip, shift, size,
  useHover, useClick, useDismiss, useFocus, useInteractions, safePolygon,
  type Placement,
} from '@floating-ui/react'

export interface UseFloatingTooltipOptions {
  anchor: 'element' | 'cursor'   // sit beside the trigger, or follow the pointer
  side?: Placement               // preferred placement; auto-flips. default: 'right' (element) / 'top' (cursor)
  trigger?: 'hover' | 'click'    // open on hover (default) or on click (a dismissible popover)
  pinnable?: boolean             // (hover only) click trigger to keep open after mouse leaves
  interactive?: boolean          // tooltip body receives pointer events (scroll / click inside). default false
  openDelay?: number             // ms hover delay before showing. default 0
  viewportPadding?: number       // px gap from viewport edges. default 8
}

export interface FloatingTooltip {
  open: boolean
  pinned: boolean
  triggerProps: Record<string, unknown>   // spread onto the hovered element
  floatingProps: Record<string, unknown>  // spread onto the floating .tooltip div
}

export function useFloatingTooltip(opts: UseFloatingTooltipOptions): FloatingTooltip {
  const {
    anchor, side, trigger = 'hover', pinnable = false, interactive = false,
    openDelay = 0, viewportPadding = 8,
  } = opts

  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false)

  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: (next) => { setOpen(next); if (!next) setPinned(false) },
    placement: side ?? (anchor === 'cursor' ? 'top' : 'right'),
    whileElementsMounted: autoUpdate,
    middleware: [
      offset(8),
      flip({ padding: viewportPadding }),
      // crossAxis: shift along the CROSS axis too so a side-placed (left/right) tooltip that's taller than the
      // space beside its anchor slides vertically to stay on-screen instead of overflowing the top/bottom edge.
      shift({ padding: viewportPadding, crossAxis: true }),
      // variable size: cap to available height, let the body scroll if genuinely too tall
      size({
        padding: viewportPadding,
        apply({ availableHeight, elements }) {
          Object.assign(elements.floating.style, { maxHeight: `${Math.max(120, availableHeight)}px` })
        },
      }),
    ],
  })

  // Cursor anchoring: feed a zero-size virtual element at the pointer.
  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (anchor !== 'cursor') return
    refs.setPositionReference({
      getBoundingClientRect: () => ({
        width: 0, height: 0,
        x: e.clientX, y: e.clientY,
        left: e.clientX, top: e.clientY, right: e.clientX, bottom: e.clientY,
      }),
    })
  }, [anchor, refs])

  const hover = useHover(context, {
    enabled: trigger === 'hover' && !pinned,           // pinned tooltips ignore mouseleave
    delay: { open: openDelay, close: 0 },
    handleClose: interactive ? safePolygon() : null,   // lets the cursor travel into an interactive body
  })
  const click = useClick(context, { enabled: trigger === 'click' })
  // Guard `window`/`navigator` — floating-ui's useFocus effect touches both unconditionally whenever
  // enabled, and the vitest suite renders this in a DOM-less `node` environment (react-test-renderer,
  // no jsdom). Real app always has a window, so this is a no-op guard outside tests. Mirrors the
  // `typeof window === 'undefined'` guard already used for the mobile tree-toggle effect.
  const focus = useFocus(context, { enabled: typeof window !== 'undefined' && typeof navigator !== 'undefined' })
  // Click popovers dismiss on outside-click/Escape; hover tooltips only when pinned.
  const dismiss = useDismiss(context, { enabled: trigger === 'click' || pinned })

  const { getReferenceProps, getFloatingProps } = useInteractions([hover, click, focus, dismiss])

  // Merge the ref in explicitly rather than relying on getReferenceProps to forward it.
  // Only inject the pin onClick for hover+pinnable; click-triggered popovers let useClick own
  // the click, and plain hover tooltips must not clobber a consumer's own click handler.
  const userRefProps: Record<string, unknown> = { onMouseMove }
  if (trigger === 'hover' && pinnable) userRefProps.onClick = () => { setPinned(p => !p); setOpen(true) }
  const triggerProps: Record<string, unknown> = {
    ...getReferenceProps(userRefProps),
    ref: refs.setReference,
  }

  const floatingProps: Record<string, unknown> = {
    ...getFloatingProps(),
    ref: refs.setFloating,
    style: { ...floatingStyles, pointerEvents: interactive ? 'auto' : 'none' },
  }

  return { open, pinned, triggerProps, floatingProps }
}
