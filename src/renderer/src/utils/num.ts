// Format a number with UP TO 2 decimal places, trimming trailing zeros (and a bare trailing dot):
//   14.5 → "14.5", 14 → "14", 7.25 → "7.25", 100 → "100", 0.5 → "0.5".
// Owner rule: only show decimals when present — never force trailing zeros, never show just 1 when 2 differ.
export function dec(v: number): string {
  return v.toFixed(2).replace(/\.?0+$/, '')
}
