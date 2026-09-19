// Frontend domain types. Components only use these, never raw backend
// responses; api/adapters.ts converts backend JSON into these shapes.

export type Mode = 'walk' | 'wheelchair' | 'skateboard' | 'bike' | 'scooter' // scooter = e-scooter

// Internal convention: [lng, lat] (GeoJSON order).
export type LngLat = [number, number]

export interface Place {
  id: string
  name: string
  location: LngLat
  category?: string
}

// Safety (lighting, security) mostly matters after dark.
export type TimeOfDay = 'day' | 'night'

export interface RouteRequest {
  start: Place | LngLat
  end: Place | LngLat
  mode: Mode
  preferences?: string
  timeOfDay?: TimeOfDay // derived from departAt; lets the backend route for lighting
  departAt?: string // ISO 8601; when the user is leaving
}

export interface SegmentTags {
  stairs?: boolean
  ramp?: boolean
  surface?: string
  roughness?: number
  offroad?: boolean
  lit?: boolean // has street lighting
}

export interface Segment {
  geometry: LngLat[]
  tags: SegmentTags
  gradePct?: number
  confidence?: number // 0–1
  imageUrl?: string
}

export interface Route {
  id: string
  geometry: LngLat[]
  distanceM: number
  durationS: number
  segments?: Segment[]
  safety?: Safety
  rejectedBecause?: string // set on alternatives
}

// Personal safety: lighting, visibility, security nearby. Not crime data.
export interface Safety {
  score: number // 0–100, higher is safer
  factors: string[] // plain-language reasons, e.g. "2 blue-light phones along the route"
}

export interface RouteResult {
  route: Route
  alternatives: Route[]
  explanation: string
  tradeoffs?: string[]
  fallbackUsed?: boolean // true when the backend answered without Gemini
}

export type AnnotationKind =
  | 'stairs'
  | 'ramp'
  | 'slope'
  | 'rough'
  | 'obstacle'
  | 'offroad'
  // safety
  | 'light' // street light
  | 'dark' // unlit stretch
  | 'emergency_phone' // blue-light emergency phone
  | 'security' // security post / desk

export interface Annotation {
  id: string
  kind: AnnotationKind
  geometry: LngLat | LngLat[] // a point, or a line
  confidence?: number // 0–1
}

export interface Observation {
  id: string
  imageUrl?: string // may be missing; the UI hides the photo
  location: LngLat
  labels: string[]
  capturedAt: string // ISO 8601
}

export interface Coverage {
  verifiedPct: number // 0–100
}
