// A cloud build, named link, or imported build may have been saved under a different game data
// version. The first release opens it with the current data and says so; it does not load old datasets.

/**
 * The form of a version string the hosted service accepts: 1 to 64 characters from A-Z a-z 0-9 . _ + -.
 * Anything else becomes "_" and an empty value becomes "unknown". The same function runs on both sides
 * of every comparison, so a season name with spaces never causes a false warning.
 */
export function toWireVersion(version: string | null | undefined): string {
  const cleaned = (version ?? '').replace(/[^A-Za-z0-9._+-]/g, '_').slice(0, 64)
  return cleaned || 'unknown'
}

export function dataVersionWarning(saved: string | null | undefined, current: string | null): string | null {
  if (!saved) return null
  if (current && toWireVersion(saved) === toWireVersion(current)) return null
  const have = current ? `This app has ${current}. ` : ''
  return `This build was saved under game data version ${saved}. ${have}Some items, talents, or effects may have changed, and anything that no longer exists is handled as an unknown item.`
}
