// MSW handlers: a fake backend in the browser. Paths match api/endpoints.ts.
// `*/path` matches any origin, so mocks work whatever VITE_API_BASE_URL is.
import { delay, http, HttpResponse } from 'msw'
import type { LngLat, Mode, Observation, TimeOfDay } from '../types/domain'
import { annotations } from './data/annotations'
import { INITIAL_COVERAGE_PCT, observations } from './data/observations'
import { placeById, places } from './data/places'
import { buildRouteResult, nearestTrip, trips } from './data/routes'

const MODES: Mode[] = ['walk', 'wheelchair', 'skateboard', 'bike', 'scooter']

// Live-feed state: each poll "reveals" one more observation and nudges coverage up.
let revealed: Observation[] = observations.slice(0, 3).map((o, i) => ({
  ...o,
  capturedAt: new Date(Date.now() - (3 - i) * 60_000).toISOString(),
}))
let coveragePct = INITIAL_COVERAGE_PCT

function isLngLat(v: unknown): v is LngLat {
  return Array.isArray(v) && v.length === 2 && v.every((n) => typeof n === 'number')
}

export const handlers = [
  http.get('*/places', async ({ request }) => {
    await delay(150)
    const q = (new URL(request.url).searchParams.get('q') ?? '').trim().toLowerCase()
    return HttpResponse.json(places.filter((p) => p.name.toLowerCase().includes(q)))
  }),

  http.post('*/route', async ({ request }) => {
    await delay(1500 + Math.random() * 1500) // fake Gemini thinking time
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const mode = MODES.includes(body.mode as Mode) ? (body.mode as Mode) : 'walk'
    const first = trips[0]
    const start = isLngLat(body.start) ? body.start : placeById(first.from).location
    const end = isLngLat(body.end) ? body.end : placeById(first.to).location
    const time: TimeOfDay = body.timeOfDay === 'night' ? 'night' : 'day'
    const { tripId, reversed } = nearestTrip(start, end)
    return HttpResponse.json(buildRouteResult(tripId, mode, time, reversed))
  }),

  http.get('*/annotations', async () => {
    await delay(300)
    return HttpResponse.json(annotations)
  }),

  http.get('*/observations/recent', async () => {
    await delay(200)
    const next = observations[revealed.length]
    if (next) revealed = [...revealed, { ...next, capturedAt: new Date().toISOString() }]
    return HttpResponse.json([...revealed].reverse()) // newest first
  }),

  http.get('*/coverage', async () => {
    await delay(200)
    coveragePct = Math.min(95, coveragePct + 0.4)
    return HttpResponse.json({ verifiedPct: Math.round(coveragePct * 10) / 10 })
  }),
]
