// Client for the planner service (planner/server.py).
// Routes are solved live, so the backend has to be running:
//     uvicorn planner.server:app --reload

import type { LineString } from 'geojson'

// 127.0.0.1 rather than localhost: on macOS localhost resolves to ::1 first,
// and uvicorn binds IPv4 by default, so "localhost" can reach a different
// process entirely.
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export type Place = {
  name: string
  kind: string
  use?: string | null
  alias?: string | null
}

export type RouteLeg = {
  kind: 'paved' | 'shortcut' | 'steps' | 'indoor'
  name: string | null
  metres: number
  minutes: number
}

export type Saved = {
  plainMetres: number
  plainMinutes: number
  savedMetres: number
  savedMinutes: number
  plainArrival: string
}

export type RouteOk = {
  status: 'ok'
  smarter: boolean
  origin: { resolved: string; arrival: string; kind: string }
  destination: { resolved: string; arrival: string; kind: string }
  summary: {
    minutes: number
    metres: number
    feet: number
    steps: number
    stepsBesideShortcut: number
    shortcutMetres: number
    shortcutSpaces: string[]
  }
  geometry: LineString
  legs: RouteLeg[]
  savedBySmarter: Saved | null
  warnings: string[]
}

export type RouteAmbiguous = {
  status: 'ambiguous'
  field: 'origin' | 'destination'
  query: string
  candidates: string[]
  error: string
}

export type RouteFailed = {
  status: 'error' | 'no_route'
  field?: string
  error: string
}

export type RouteResult = RouteOk | RouteAmbiguous | RouteFailed

/** The backend not running is the most likely failure in development, so it
 *  gets its own message rather than a bare TypeError. */
export class PlannerUnreachable extends Error {
  constructor() {
    super(`Cannot reach the planner at ${BASE}. Start it with: uvicorn planner.server:app`)
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new PlannerUnreachable()
  }
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

export async function fetchPlaces(): Promise<Place[]> {
  let res: Response
  try {
    res = await fetch(`${BASE}/places`)
  } catch {
    throw new PlannerUnreachable()
  }
  if (!res.ok) throw new Error(`/places -> ${res.status}`)
  return (await res.json()).places
}

export function planRoute(origin: string, destination: string, smarter: boolean) {
  return post<RouteResult>('/route', { origin, destination, smarter })
}
