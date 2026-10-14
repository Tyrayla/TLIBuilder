import React, { useRef } from 'react'

type OutsideDismissBackdropProps = Omit<React.HTMLAttributes<HTMLDivElement>, 'onClick'> & {
  onDismiss: () => void
}

/** Dismisses only when the pointer press and click both originate on the backdrop. */
export function createOutsideDismissHandlers(onDismiss: () => void, pressStartedInside: { current: boolean }) {
  return {
    onPointerDownCapture: (event: Pick<React.PointerEvent<HTMLDivElement>, 'target' | 'currentTarget'>) => {
      pressStartedInside.current = event.target !== event.currentTarget
    },
    onPointerCancel: () => { pressStartedInside.current = false },
    onClick: (event: Pick<React.MouseEvent<HTMLDivElement>, 'target' | 'currentTarget'>) => {
      const startedInside = pressStartedInside.current
      pressStartedInside.current = false
      if (event.target === event.currentTarget && !startedInside) onDismiss()
    },
  }
}

export default function OutsideDismissBackdrop({ onDismiss, children, ...props }: OutsideDismissBackdropProps) {
  const pressStartedInside = useRef(false)
  const handlers = createOutsideDismissHandlers(onDismiss, pressStartedInside)

  return (
    <div
      {...props}
      {...handlers}
    >
      {children}
    </div>
  )
}
