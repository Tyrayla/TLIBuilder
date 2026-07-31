import React from 'react'

const LINE = Array(5).fill('PREVIEW MODE').join(' · ')
const LINE_COUNT = 14

// Repeating diagonal "PREVIEW MODE" tiling — the sole signal that a screen is in preview mode now
// that both TreeSelectorScreen and TreeViewerScreen render through the normal ScreenHeader with no
// bespoke badge. Sits behind all real content (z-index:0, pointer-events:none); the containing
// screen must give its sidebar/main content an explicit position:relative so they stack above it —
// a plain absolutely-positioned z-index:0 layer otherwise paints ABOVE static in-flow siblings.
export default function PreviewWatermark() {
  return (
    <div className="preview-watermark">
      <div className="preview-watermark-tiles">
        {Array.from({ length: LINE_COUNT }, (_, i) => (
          <div key={i} className="preview-watermark-line">{LINE}</div>
        ))}
      </div>
    </div>
  )
}
