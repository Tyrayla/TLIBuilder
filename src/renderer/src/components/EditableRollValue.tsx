import { useState } from 'react'

// The roll-value number on an affix row (e.g. "52"), click-to-edit into an exact number. Shared by the
// gear/hero-memory editors. Clamps to the modifier's overall achievable range and rounds to `dp` decimals;
// the parent's onCommit does the tier-match + desecration wiring.
interface Props {
  value: number            // signed display value
  dp: number               // decimals to show/round to
  range: [number, number]  // [min, max] (signed) to clamp typed input to
  disabled?: boolean       // e.g. corroded-slot budget full
  title?: string           // override the hover tooltip (defaults to the gear-desecration wording)
  color?: string           // optional value color (e.g. a memory affix's category color); default gear styling
  onCommit: (v: number) => void
}

export default function EditableRollValue({ value, dp, range, disabled, title, color, onCommit }: Props) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const display = dp > 0 ? value.toFixed(dp) : String(value)

  if (!editing) {
    return (
      <span
        className={`gear-affix-value${disabled ? '' : ' gear-affix-value--editable'}`}
        style={color ? { color } : undefined}
        title={title ?? (disabled ? 'Max 2 desecrated mods' : 'Click to set an exact roll (desecrates the mod)')}
        onClick={() => { if (!disabled) { setText(display); setEditing(true) } }}
      >{display}</span>
    )
  }

  const commit = () => {
    setEditing(false)
    const n = parseFloat(text)
    if (!isFinite(n)) return
    const [lo, hi] = range
    const clamped = Math.min(hi, Math.max(lo, n))
    onCommit(dp > 0 ? parseFloat(clamped.toFixed(dp)) : Math.round(clamped))
  }

  return (
    <input
      className="gear-affix-value-input"
      autoFocus
      value={text}
      onChange={e => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.preventDefault(); commit() }
        else if (e.key === 'Escape') { e.preventDefault(); setEditing(false) }
      }}
    />
  )
}
