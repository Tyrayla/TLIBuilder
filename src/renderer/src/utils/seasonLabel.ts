import type { SeasonSummary } from '../api/client'

/** Display label for a season: its `_season.json` label, else the folder name. */
export function seasonLabel(s: Pick<SeasonSummary, 'name' | 'label'>): string {
  return s.label?.trim() || s.name
}

/** True when the season is flagged as a pre-season dataset. */
export function isPreSeason(s: Pick<SeasonSummary, 'status'>): boolean {
  return (s.status ?? '').toLowerCase() === 'pre-season'
}
