import React from 'react'

interface Props {
  left?: React.ReactNode
  center?: React.ReactNode
  right?: React.ReactNode
}

// Shared header shell for TreeSelectorScreen and TreeViewerScreen's non-preview headers — one
// component and one CSS rule (.app-header) so the two screens can't independently drift in height
// or padding the way .screen-header/.viewer-header did before this existed.
export default function ScreenHeader({ left, center, right }: Props) {
  return (
    <div className="app-header">
      <div className="app-header-left">{left}</div>
      {center && <div className="app-header-center">{center}</div>}
      {right && <div className="app-header-right">{right}</div>}
    </div>
  )
}
