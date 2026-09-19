// Fake route results built from real path geometry (rawRoutes.json, made by
// scripts/gen-mock-routes.mjs). Each trip has three real paths; each mode
// picks a different one so the modes visibly disagree on the map. Walking
// cuts straight across grass; at night it switches to the lit path instead.
// Route geometry and distances are rebuilt from the segments.
import type { LngLat, Mode, Route, RouteResult, Safety, Segment, TimeOfDay } from '../../types/domain'
import raw from './rawRoutes.json'
import { placeById } from './places'

type Variant = 'direct' | 'viaA' | 'viaB'
type TripId = keyof typeof raw

interface Trip {
  id: TripId
  from: string // place ids
  to: string
  stairs: string // landmark names used in the explanations
  ramp: string
  hill: string
  shortcut: string // the unlit shortcut on the direct path
  grassCut: [number, number] // point indices on the direct path where walking cuts a corner across grass
}

export const trips: Trip[] = [
  { id: 'gilman-malone', from: 'gilman', to: 'malone', stairs: 'the steps behind Gilman Hall', ramp: 'the ramp by Hodson Hall', hill: 'the slope down to Malone', shortcut: 'the grass shortcut behind Gilman Hall', grassCut: [36, 40] },
  { id: 'brody-rec', from: 'brody', to: 'rec', stairs: 'the steps up past Gilman', ramp: 'the library ramp', hill: 'the hill on San Martin Drive', shortcut: 'the lawn by Mudd Hall', grassCut: [55, 66] },
  { id: 'mudd-charles', from: 'mudd', to: 'charles-commons', stairs: 'the Keyser Quad steps', ramp: 'the library ramp', hill: 'the incline up to Charles Street', shortcut: 'the lawn behind the library', grassCut: [29, 53] },
]

// --- Segment conditions ---

type Condition = 'plain' | 'stairs' | 'brick' | 'offroad' | 'unverified' | 'ramp' | 'slope' | 'gentle'

// The made-up "story" along each path: [condition, relative length].
// `offroad` segments are drawn as a straight line across the grass.
function storyFor(tripId: TripId, variant: Variant): [Condition, number][] {
  if (variant === 'direct') {
    // Shortest: stairs, then a corner cut across grass (unlit at night), then brick.
    const [a, b] = trips.find((t) => t.id === tripId)!.grassCut
    const rest = geometryOf(tripId, 'direct').length - 1 - b
    return [['plain', a / 2], ['stairs', a / 2], ['offroad', b - a], ['brick', rest / 2], ['unverified', rest / 2]]
  }
  if (variant === 'viaA') return [['plain', 1], ['ramp', 1], ['plain', 1], ['slope', 1], ['plain', 1], ['plain', 1]] // step-free, lit, one hill
  return [['plain', 1], ['plain', 1], ['unverified', 1], ['plain', 1], ['gentle', 1], ['plain', 1]] // flat and smooth, one dim stretch
}

const conditionData: Record<Condition, Omit<Segment, 'geometry'>> = {
  plain: { tags: { surface: 'concrete', lit: true }, gradePct: 1, confidence: 0.95 },
  stairs: { tags: { stairs: true, surface: 'concrete', lit: true }, gradePct: 0, confidence: 0.97 },
  brick: { tags: { surface: 'brick', roughness: 0.6, lit: true }, gradePct: 1, confidence: 0.85 },
  offroad: { tags: { offroad: true, surface: 'grass', roughness: 0.5, lit: false }, gradePct: 3, confidence: 0.7 },
  unverified: { tags: { surface: 'asphalt', lit: false }, gradePct: 2, confidence: 0.35 },
  ramp: { tags: { ramp: true, surface: 'concrete', lit: true }, gradePct: 6, confidence: 0.9 },
  slope: { tags: { surface: 'asphalt', lit: true }, gradePct: 5, confidence: 0.88 },
  gentle: { tags: { surface: 'asphalt', roughness: 0.1, lit: true }, gradePct: 2, confidence: 0.9 },
}

// Splits a line into consecutive pieces sized by `spans` (sharing their end points).
function splitLine(line: LngLat[], spans: number[]): LngLat[][] {
  const total = spans.reduce((a, b) => a + b, 0)
  const cuts = [0]
  for (const span of spans) cuts.push(cuts[cuts.length - 1] + span)
  const idx = cuts.map((c) => Math.round((c * (line.length - 1)) / total))
  return spans.map((_, k) => line.slice(idx[k], idx[k + 1] + 1))
}

export function midpoint(line: LngLat[]): LngLat {
  if (line.length === 2) return [(line[0][0] + line[1][0]) / 2, (line[0][1] + line[1][1]) / 2]
  return line[Math.floor(line.length / 2)]
}

function lengthM(line: LngLat[]): number {
  const R = 6_371_000
  const rad = (d: number) => (d * Math.PI) / 180
  let m = 0
  for (let i = 1; i < line.length; i++) {
    const [lng1, lat1] = line[i - 1]
    const [lng2, lat2] = line[i]
    const a =
      Math.sin(rad(lat2 - lat1) / 2) ** 2 +
      Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lng2 - lng1) / 2) ** 2
    m += 2 * R * Math.asin(Math.sqrt(a))
  }
  return m
}

// Joins consecutive segments back into one line (dropping the shared joints).
function joinSegments(segments: Segment[]): LngLat[] {
  return segments.flatMap((s, i) => (i === 0 ? s.geometry : s.geometry.slice(1)))
}

function geometryOf(tripId: TripId, variant: Variant): LngLat[] {
  return raw[tripId][variant].geometry as LngLat[]
}

// Forward-direction segments with their conditions (also used for annotations/observations).
export function segmentsWithConditions(tripId: TripId, variant: Variant) {
  const story = storyFor(tripId, variant)
  const pieces = splitLine(geometryOf(tripId, variant), story.map(([, span]) => span))
  return pieces.map((piece, i) => {
    const condition = story[i][0]
    const geometry = condition === 'offroad' ? [piece[0], piece[piece.length - 1]] : piece
    return { condition, segment: { geometry, ...conditionData[condition] } as Segment }
  })
}

// --- Safety (lighting, visibility, security nearby) ---

function safetyFor(variant: Variant, time: TimeOfDay, trip: Trip): Safety {
  const table: Record<Variant, Record<TimeOfDay, Safety>> = {
    direct: {
      day: { score: 78, factors: ['Busy paths during the day', `Short secluded stretch on ${trip.shortcut}`] },
      night: {
        score: 41,
        factors: [`${capitalize(trip.shortcut)} is unlit`, 'No emergency phone within 150 m of the shortcut', 'Poor sightlines between buildings'],
      },
    },
    viaA: {
      day: { score: 90, factors: ['Open paths with good sightlines', '2 blue-light phones along the route'] },
      night: { score: 88, factors: ['Lit the whole way', '2 blue-light phones along the route', 'Passes the library, open late'] },
    },
    viaB: {
      day: { score: 86, factors: ['Open paths with good sightlines', '1 blue-light phone nearby'] },
      night: { score: 70, factors: ['Mostly lit', "1 dim stretch the robot hasn't checked at night", '1 blue-light phone nearby'] },
    },
  }
  return table[variant][time]
}

function capitalize(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

// --- Per-mode choices and wording ---

const speedMps: Record<Mode, number> = { walk: 1.4, wheelchair: 1.0, skateboard: 3.0, bike: 4.5, scooter: 5.5 }

function chosenVariant(mode: Mode, time: TimeOfDay): Variant {
  if (mode === 'walk') return time === 'night' ? 'viaA' : 'direct' // skip the dark shortcut at night
  if (mode === 'wheelchair' || mode === 'scooter') return 'viaA' // scooter: the motor handles the hill
  return 'viaB'
}

function rejectionReason(mode: Mode, time: TimeOfDay, variant: Variant, trip: Trip, extraM: number, safety: Safety): string {
  const longer = extraM > 0 ? `${extraM} m longer` : 'no shorter'
  switch (mode) {
    case 'walk':
      if (time === 'night') {
        return variant === 'direct'
          ? `Uses ${trip.shortcut}, which is unlit with no emergency phone nearby (safety ${safety.score}/100).`
          : `${extraM < 0 ? `${-extraM} m shorter, but has` : `${longer}, with`} a dim stretch the robot hasn't checked at night (safety ${safety.score}/100).`
      }
      return variant === 'viaA'
        ? `${longer} to avoid stairs you can easily take on foot.`
        : `${longer} with nothing gained on foot.`
    case 'wheelchair':
      return variant === 'direct'
        ? `Not step-free: uses ${trip.stairs}.`
        : `Includes a stretch the robot hasn't verified recently, so curb cuts aren't confirmed.`
    case 'scooter':
      return variant === 'direct'
        ? `Uses ${trip.stairs} and a rough brick stretch, both bad for small wheels.`
        : `Has a stretch the robot hasn't verified recently; hidden cracks are risky on small wheels.`
    case 'skateboard':
    case 'bike':
      return variant === 'direct'
        ? `Uses ${trip.stairs} and a rough brick stretch.`
        : `Goes over ${trip.hill} (about 5% grade).`
  }
}

function explanationFor(mode: Mode, time: TimeOfDay, trip: Trip, route: Route, shortestM: number) {
  const from = placeById(trip.from).name
  const to = placeById(trip.to).name
  const minutes = Math.max(1, Math.round(route.durationS / 60))
  const extraM = route.distanceM - shortestM
  const night = time === 'night'
  switch (mode) {
    case 'walk':
      if (night) {
        return {
          explanation: `It's dark out, so this skips ${trip.shortcut}, which has no street lights and no emergency phone nearby. Instead it stays on lit paths past two blue-light phones. It's ${extraM} m longer than the daytime shortcut, about a minute more.`,
          tradeoffs: ['Lit the whole way', '2 blue-light phones on the route', `${extraM} m longer than the shortcut`],
        }
      }
      return {
        explanation: `The quickest way from ${from} to ${to} on foot. It takes ${trip.stairs} and cuts straight across ${trip.shortcut}, a shortcut regular map apps don't show. The last stretch hasn't been verified by the robot recently, but it's a paved path, so the risk is low.`,
        tradeoffs: ['Includes stairs', 'Cuts across grass', 'Fastest option'],
      }
    case 'wheelchair':
      return {
        explanation: `This route is fully step-free. It avoids ${trip.stairs} by using ${trip.ramp}, which the robot measured at about 6%, within the ADA limit. It's ${extraM} m longer than the shortest route, but every segment has been checked for curb cuts.${night ? ' It is also lit the whole way, with two blue-light phones along it.' : ''}`,
        tradeoffs: ['Step-free', `${extraM} m longer than the shortest route`, 'One moderate 5% slope'],
      }
    case 'skateboard':
      return {
        explanation: `Stays on smooth asphalt and skips both the brick stretch and ${trip.hill}. The steepest part is a gentle 2% grade, so you can keep rolling the whole way. One segment hasn't been verified recently${night ? " and it's dim after dark" : ''}, so watch for cracks there.`,
        tradeoffs: ['Smooth surface throughout', 'Avoids the hill', night ? 'One dim, unverified stretch' : 'One unverified segment'],
      }
    case 'scooter':
      return {
        explanation: `Takes the paved route past ${trip.ramp}. The motor makes ${trip.hill} easy, so the route can focus on what matters on small wheels: it avoids the brick stretch, ${trip.stairs}, and a stretch the robot hasn't checked recently that could hide cracks.${night ? ' It is also lit the whole way.' : ''}`,
        tradeoffs: ['Smooth pavement', 'Hill is easy with a motor', `About ${minutes} min`],
      }
    case 'bike':
      return {
        explanation: `Best on a bike: smooth pavement, no stairs, and it avoids ${trip.hill}. About ${minutes} min at an easy pace.${night ? ' Use your light on the one dim stretch.' : " Walk your bike through the unverified stretch if it's crowded."}`,
        tradeoffs: ['No stairs', 'Avoids the hill', `About ${minutes} min`],
      }
  }
}

// --- Building a RouteResult ---

function buildRoute(trip: Trip, variant: Variant, mode: Mode, time: TimeOfDay, reversed: boolean): Route {
  let segments = segmentsWithConditions(trip.id, variant).map((s) => s.segment)
  if (reversed) segments = segments.map((s) => ({ ...s, geometry: [...s.geometry].reverse() })).reverse()
  const geometry = joinSegments(segments)
  const distanceM = Math.round(lengthM(geometry))
  return {
    id: `${trip.id}-${variant}`,
    geometry,
    distanceM,
    durationS: Math.round(distanceM / speedMps[mode]),
    segments,
    safety: safetyFor(variant, time, trip),
  }
}

export function buildRouteResult(tripId: TripId, mode: Mode, time: TimeOfDay = 'day', reversed = false): RouteResult {
  const trip = trips.find((t) => t.id === tripId)!
  const chosen = chosenVariant(mode, time)
  const route = buildRoute(trip, chosen, mode, time, reversed)
  const alternatives = (['direct', 'viaA', 'viaB'] as Variant[])
    .filter((v) => v !== chosen)
    .map((v) => {
      const alt = buildRoute(trip, v, mode, time, reversed)
      const reason = rejectionReason(mode, time, v, trip, alt.distanceM - route.distanceM, alt.safety!)
      return { ...alt, rejectedBecause: reason }
    })
  const shortestM = Math.round(lengthM(joinSegments(segmentsWithConditions(trip.id, 'direct').map((s) => s.segment))))
  return { route, alternatives, ...explanationFor(mode, time, trip, route, shortestM), fallbackUsed: false }
}

// Picks the demo trip closest to the requested start/end (either direction).
export function nearestTrip(start: LngLat, end: LngLat): { tripId: TripId; reversed: boolean } {
  const d2 = (a: LngLat, b: LngLat) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
  let best = { tripId: trips[0].id, reversed: false, cost: Infinity }
  for (const t of trips) {
    const from = placeById(t.from).location
    const to = placeById(t.to).location
    const forward = d2(start, from) + d2(end, to)
    const backward = d2(start, to) + d2(end, from)
    if (forward < best.cost) best = { tripId: t.id, reversed: false, cost: forward }
    if (backward < best.cost) best = { tripId: t.id, reversed: true, cost: backward }
  }
  return { tripId: best.tripId, reversed: best.reversed }
}
