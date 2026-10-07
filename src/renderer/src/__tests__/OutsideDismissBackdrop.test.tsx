import { describe, expect, it, vi } from 'vitest'
import { createOutsideDismissHandlers } from '../components/OutsideDismissBackdrop'

describe('OutsideDismissBackdrop', () => {
  it('keeps the dialog open when a press starts in an input and releases on the backdrop', () => {
    const onDismiss = vi.fn()
    const backdropNode = {} as HTMLDivElement
    const inputNode = {} as HTMLInputElement
    const handlers = createOutsideDismissHandlers(onDismiss, { current: false })

    // A pointerup outside does not reset the origin; the browser then dispatches click on the backdrop.
    handlers.onPointerDownCapture({ target: inputNode, currentTarget: backdropNode })
    handlers.onClick({ target: backdropNode, currentTarget: backdropNode })

    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('dismisses on a direct backdrop click but leaves inner clicks alone', () => {
    const onDismiss = vi.fn()
    const backdropNode = {} as HTMLDivElement
    const inputNode = {} as HTMLInputElement
    const handlers = createOutsideDismissHandlers(onDismiss, { current: false })

    handlers.onPointerDownCapture({ target: inputNode, currentTarget: backdropNode })
    handlers.onClick({ target: inputNode, currentTarget: backdropNode })
    expect(onDismiss).not.toHaveBeenCalled()

    handlers.onPointerDownCapture({ target: backdropNode, currentTarget: backdropNode })
    handlers.onClick({ target: backdropNode, currentTarget: backdropNode })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
