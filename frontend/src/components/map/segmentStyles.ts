import type { FeatureCollection, LineString } from 'geojson'
import type { Route, Segment } from '../../types/domain'

// One condition per route segment. The order is the priority when a segment
// has several (e.g. stairs that are also unverified show as stairs).
export const CONDITIONS = ['stairs', 'dark', 'offroad', 'rough', 'slope', 'lowConfidence', 'smooth'] as const
export type Condition = (typeof CONDITIONS)[number]

export function segmentCondition(s: Segment, night: boolean): Condition {
  if (s.tags.stairs) return 'stairs'
  if (night && s.tags.lit === false) return 'dark'
  if (s.tags.offroad) return 'offroad'
  if ((s.tags.roughness ?? 0) >= 0.5 || s.tags.surface === 'brick' || s.tags.surface === 'gravel') return 'rough'
  if (Math.abs(s.gradePct ?? 0) >= 5) return 'slope'
  if (s.confidence !== undefined && s.confidence < 0.5) return 'lowConfidence'
  return 'smooth'
}

// Colour AND line pattern differ per condition, so the map never relies on colour
// alone. `dash` is in multiples of the line width; `round` caps turn [0, n] into dots.
export const CONDITION_STYLE: Record<Condition, { label: string; icon: string; color: string; dash?: number[]; round?: boolean }> = {
  smooth: { label: 'Smooth path', icon: '✓', color: '#2563eb' },
  slope: { label: 'Hill (5%+)', icon: '⛰️', color: '#c2410c', dash: [3, 1] },
  rough: { label: 'Rough surface', icon: '〰️', color: '#92400e', dash: [1.2, 0.8] },
  stairs: { label: 'Stairs', icon: '🪜', color: '#dc2626', dash: [0.5, 0.5] },
  offroad: { label: 'Across grass', icon: '🌱', color: '#15803d', dash: [0, 1.6], round: true },
  lowConfidence: { label: 'Not yet verified', icon: '❔', color: '#6b7280', dash: [2, 2] },
  dark: { label: 'Unlit at night', icon: '🌑', color: '#312e81', dash: [4, 1, 0.5, 1] },
}

// Rejected alternatives: thinner, muted, drawn under the chosen route.
export const ALTERNATIVE_STYLE = { label: 'Other routes considered', color: '#6b7280', width: 4, opacity: 0.55 }

// The route's segments as GeoJSON, each tagged with its condition (and index, for clicks later).
export function segmentFeatures(route: Route, night: boolean): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: (route.segments ?? []).map((s, index) => ({
      type: 'Feature',
      properties: { index, condition: segmentCondition(s, night), confidence: s.confidence ?? null },
      geometry: { type: 'LineString', coordinates: s.geometry },
    })),
  }
}
