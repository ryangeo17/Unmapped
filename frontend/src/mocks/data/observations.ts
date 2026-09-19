// Robot observations along the demo trips. No photos in the mock;
// capturedAt is filled in by the handler when each one is "revealed".
import type { Observation } from '../../types/domain'
import { midpoint, segmentsWithConditions, trips } from './routes'

const sightings = [
  { variant: 'direct', index: 1, labels: ['stairs', 'concrete', 'handrail'] },
  { variant: 'direct', index: 3, labels: ['brick', 'uneven surface'] },
  { variant: 'viaA', index: 1, labels: ['ramp', 'concrete', 'handrail'] },
  { variant: 'viaB', index: 2, labels: ['asphalt', 'curb cut'] },
  { variant: 'direct', index: 2, labels: ['open lawn', 'no street light', 'worn footpath'] },
  { variant: 'viaA', index: 4, labels: ['well lit', 'blue-light phone'] },
] as const

// Ordered trip by trip, so consecutive sightings show different things.
export const observations: Omit<Observation, 'capturedAt'>[] = trips.flatMap((trip) =>
  sightings.map((s) => ({
    id: `obs-${trip.id}-${s.variant}-${s.index}`,
    location: midpoint(segmentsWithConditions(trip.id, s.variant)[s.index].segment.geometry),
    labels: [...s.labels],
  })),
)

export const INITIAL_COVERAGE_PCT = 60
