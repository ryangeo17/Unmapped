// Accessibility and safety features placed along the demo trips' real paths,
// derived from the same segment "stories" the mock routes use, so they line up.
import type { Annotation, AnnotationKind } from '../../types/domain'
import { placeById } from './places'
import { midpoint, segmentsWithConditions, trips } from './routes'

const kindFor: Partial<Record<string, AnnotationKind>> = {
  stairs: 'stairs',
  ramp: 'ramp',
  slope: 'slope',
  brick: 'rough',
  offroad: 'offroad',
}

const POINT_KINDS: AnnotationKind[] = ['stairs', 'ramp', 'obstacle']

// Blue-light emergency phones: [variant, segment index] on each trip.
const PHONES = [
  ['viaA', 1],
  ['viaA', 4],
  ['viaB', 3],
] as const

const accessibility: Annotation[] = trips.flatMap((trip) => {
  const found: Annotation[] = []
  for (const variant of ['direct', 'viaA', 'viaB'] as const) {
    segmentsWithConditions(trip.id, variant).forEach(({ condition, segment }, i) => {
      const kind = kindFor[condition]
      if (!kind) return
      found.push({
        id: `${trip.id}-${variant}-${i}`,
        kind,
        geometry: POINT_KINDS.includes(kind) ? midpoint(segment.geometry) : segment.geometry,
        confidence: segment.confidence,
      })
    })
  }
  // One temporary obstacle (e.g. a construction barrier) per trip, off the chosen routes.
  const plain = segmentsWithConditions(trip.id, 'direct')[0].segment
  found.push({ id: `${trip.id}-obstacle`, kind: 'obstacle', geometry: midpoint(plain.geometry), confidence: 0.6 })
  return found
})

const safety: Annotation[] = trips.flatMap((trip) => {
  const found: Annotation[] = []
  for (const variant of ['direct', 'viaA', 'viaB'] as const) {
    segmentsWithConditions(trip.id, variant).forEach(({ segment }, i) => {
      if (segment.tags.lit) {
        // A street light at the start of every lit segment.
        found.push({ id: `${trip.id}-${variant}-${i}-light`, kind: 'light', geometry: segment.geometry[0], confidence: 0.9 })
      } else {
        found.push({ id: `${trip.id}-${variant}-${i}-dark`, kind: 'dark', geometry: segment.geometry, confidence: segment.confidence })
      }
    })
  }
  for (const [variant, index] of PHONES) {
    const seg = segmentsWithConditions(trip.id, variant)[index].segment
    found.push({ id: `${trip.id}-${variant}-${index}-phone`, kind: 'emergency_phone', geometry: midpoint(seg.geometry), confidence: 1 })
  }
  return found
})

// Security desks, APPROXIMATE (hand-placed at buildings with staffed entrances).
const security: Annotation[] = ['library', 'levering', 'charles-commons'].map((id) => ({
  id: `security-${id}`,
  kind: 'security',
  geometry: placeById(id).location,
  confidence: 1,
}))

// Paths shared between variants can produce overlapping lights; fine for a mock.
export const annotations: Annotation[] = [...accessibility, ...safety, ...security]
