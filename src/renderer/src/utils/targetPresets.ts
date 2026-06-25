// Training-dummy presets for the Config "Enemy / Target" editor. All levels are bosses (enemy-count weight 5).
// Values are PERCENTAGES. Armor-vs-Non-Phys is derived (armor × 0.6) and Armor-vs-DoT is fixed 0 — neither is
// stored/editable. The Lv85 row == the engine's historical hardcoded dummy, so it's the default everywhere.
import type { TargetConfig } from '../api/client'

export const TARGET_LEVELS = [40, 60, 75, 85] as const
export type TargetLevel = (typeof TARGET_LEVELS)[number]

// level → { armor %, resist % (applied to fire/cold/lightning/erosion equally) }
export const TARGET_PRESETS: Record<TargetLevel, { armor: number; res: number }> = {
  40: { armor: 20, res: 10 },
  60: { armor: 30, res: 15 },
  75: { armor: 40, res: 20 },
  85: { armor: 50, res: 30 },
}

export const NONPHYS_ARMOR_FACTOR = 0.6   // armor fraction that applies to non-physical damage (display hint)

export function presetTargetConfig(level: TargetLevel): TargetConfig {
  const p = TARGET_PRESETS[level]
  return { level, armor: p.armor, fireRes: p.res, coldRes: p.res, lightningRes: p.res, erosionRes: p.res }
}

export const DEFAULT_TARGET_CONFIG: TargetConfig = presetTargetConfig(85)

// Normalize a possibly-partial/legacy value into a full TargetConfig (defaults to Lv85).
export function sanitizeTargetConfig(t: unknown): TargetConfig {
  const d = DEFAULT_TARGET_CONFIG
  if (!t || typeof t !== 'object') return { ...d }
  const o = t as Record<string, unknown>
  const num = (v: unknown, fb: number) => (typeof v === 'number' && isFinite(v) ? v : fb)
  return {
    level: num(o.level, d.level),
    armor: num(o.armor, d.armor),
    fireRes: num(o.fireRes, d.fireRes),
    coldRes: num(o.coldRes, d.coldRes),
    lightningRes: num(o.lightningRes, d.lightningRes),
    erosionRes: num(o.erosionRes, d.erosionRes),
  }
}
