// MSW handlers: a fake backend in the browser. Paths match api/endpoints.ts.
// `*/path` matches any origin, so mocks work whatever VITE_API_BASE_URL is.
import { delay, http, HttpResponse } from 'msw'
import type { LngLat, Mode, Observation, TimeOfDay } from '../types/domain'
import { annotations } from './data/annotations'
import { INITIAL_COVERAGE_PCT, observations } from './data/observations'
import { placeById, places } from './data/places'
import { buildRouteResult, nearestTrip, trips } from './data/routes'

const MODES: Mode[] = ['walk', 'wheelchair', 'skateboard', 'bike', 'scooter']

// Live-feed state: a new robot sighting every ~5s (looping through the mock
// observations forever, so the demo never runs dry), and coverage creeping up.
const SIGHTING_EVERY_MS = 5000
let revealed: Observation[] = observations.slice(0, 3).map((o, i) => ({
  ...o,
  capturedAt: new Date(Date.now() - (3 - i) * 60_000).toISOString(),
}))
let sightings = revealed.length
let lastSightingAt = 0
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
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    // Test triggers: put #error, #noroute, #fallback, #slow or #timeout in "Anything we should know?".
    const prefs = typeof body.preferences === 'string' ? body.preferences.toLowerCase() : ''
    const trigger = (tag: string) => prefs.includes(`#${tag}`)

    if (trigger('timeout')) await delay(25_000) // longer than the client's 20s timeout
    else if (trigger('slow')) await delay(8000)
    else await delay(1500 + Math.random() * 1500) // fake Gemini thinking time

    if (trigger('error')) return HttpResponse.json({ detail: 'The routing service hit an unexpected error.' }, { status: 500 })
    const mode = MODES.includes(body.mode as Mode) ? (body.mode as Mode) : 'walk'
    const first = trips[0]
    const start = isLngLat(body.start) ? body.start : placeById(first.from).location
    const end = isLngLat(body.end) ? body.end : placeById(first.to).location
    const time: TimeOfDay = body.timeOfDay === 'night' ? 'night' : 'day'
    if (trigger('noroute')) {
      const what = mode === 'wheelchair' ? 'step-free route' : 'route for this travel mode'
      return HttpResponse.json({ detail: `No ${what} found between these places.` }, { status: 404 })
    }
    const { tripId, reversed } = nearestTrip(start, end)
    const result = buildRouteResult(tripId, mode, time, reversed)
    if (trigger('fallback')) {
      // What the backend returns when Gemini is down: a plain shortest-cost route, no reasoning.
      return HttpResponse.json({
        ...result,
        explanation: 'Showing the lowest-cost route for your travel mode, based on the accessibility data we have.',
        tradeoffs: undefined,
        alternatives: [],
        fallbackUsed: true,
      })
    }
    return HttpResponse.json(result)
  }),

  http.get('*/annotations', async () => {
    await delay(300)
    return HttpResponse.json(annotations)
  }),

  http.get('*/observations/recent', async () => {
    await delay(200)
    if (Date.now() - lastSightingAt >= SIGHTING_EVERY_MS) {
      const next = observations[sightings % observations.length]
      revealed = [...revealed, { ...next, id: `${next.id}-${sightings}`, capturedAt: new Date().toISOString() }].slice(-20)
      sightings++
      lastSightingAt = Date.now()
    }
    return HttpResponse.json([...revealed].reverse()) // newest first
  }),

  http.get('*/coverage', async () => {
    await delay(200)
    coveragePct = Math.min(95, coveragePct + 0.3)
    return HttpResponse.json({ verifiedPct: Math.round(coveragePct * 10) / 10 })
  }),
]
