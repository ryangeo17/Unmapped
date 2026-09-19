// The ONLY file that knows backend response shapes. Each function takes
// raw JSON and returns a domain type. For now they assume the backend
// returns our shapes exactly; Task 13 rewrites them for the real API.
import type {
  Annotation,
  Coverage,
  LngLat,
  Observation,
  Place,
  RouteRequest,
  RouteResult,
} from '../types/domain'

// --- Requests (domain → backend) ---

export function fromRouteRequest(req: RouteRequest) {
  return {
    start: toCoords(req.start),
    end: toCoords(req.end),
    mode: req.mode,
    preferences: req.preferences || undefined,
    timeOfDay: req.timeOfDay ?? 'day',
    departAt: req.departAt,
  }
}

function toCoords(p: RouteRequest['start']): LngLat {
  return Array.isArray(p) ? p : p.location
}

// --- Responses (backend → domain) ---

export function toPlace(raw: unknown): Place {
  return raw as Place
}

export function toRouteResult(raw: unknown): RouteResult {
  const r = raw as RouteResult
  return { ...r, alternatives: r.alternatives ?? [] }
}

export function toAnnotation(raw: unknown): Annotation {
  return raw as Annotation
}

export function toObservation(raw: unknown): Observation {
  return raw as Observation
}

export function toCoverage(raw: unknown): Coverage {
  return raw as Coverage
}

export function toList<T>(raw: unknown, convert: (item: unknown) => T): T[] {
  return Array.isArray(raw) ? raw.map(convert) : []
}
