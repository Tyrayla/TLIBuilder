// A cloud build, named link, or imported build may have been saved under a different game data
// version. The first release opens it with the current data and says so; it does not load old datasets.
export function dataVersionWarning(saved: string | null | undefined, current: string | null): string | null {
  if (!saved) return null
  if (current && saved === current) return null
  const have = current ? `This app has ${current}. ` : ''
  return `This build was saved under game data version ${saved}. ${have}Some items, talents, or effects may have changed, and anything that no longer exists is handled as an unknown item.`
}
