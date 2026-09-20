export type LatLng = [number, number]
export type TravelMode = 'walking' | 'wheelchair' | 'scooter' | 'bicycle'

export interface Landmark {
  id: string
  name: string
  subtitle: string
  coordinates: LatLng
}

export interface Hazard {
  id: string
  /** The graph edge it sits on, so "avoid this" needs no second lookup. */
  edgeId?: string
  title: string
  description: string
  severity: 'low' | 'medium' | 'high'
  coordinates: LatLng
  verified: boolean
  evidence?: string[]
}

export interface RouteStep {
  instruction: string
  distance: string
  coordinates: LatLng
}

export interface RouteDoor {
  label: string
  kind: string
  step_free: boolean
}

export interface RouteResult {
  id: string
  coordinates: LatLng[]
  distanceMeters: number
  durationMinutes: number
  accessibilityScore: number
  /** Null until something has actually surveyed security coverage. */
  safetyScore: number | null
  verifiedPercent: number
  /** Stair risers the route climbs, from JHU's survey. */
  riserCount: number
  /** Metres of lawn the smarter walk cuts across, and which lawns. */
  shortcutMeters: number
  shortcutSpaces: string[]
  /** Metres with no slope, surface, roughness, lighting or security reading. */
  unknownMeters: number
  /** Share of the route JHU grades as fully accessible, null if ungraded. */
  compliantPercent: number | null
  smarter: boolean
  startDoor: RouteDoor | null
  endDoor: RouteDoor | null
  explanation: string
  steps: RouteStep[]
  hazards: Hazard[]
  alternatives?: LatLng[][]
}

export interface SuggestionPayload {
  coordinates: LatLng[]
  description: string
  reason: string
  photo?: File
}

export type SubmissionStatus = 'pending' | 'approved' | 'rejected' | 'published'

export interface Submission {
  id: string
  reference: string
  description: string
  reason: string
  createdAt: string
  status: SubmissionStatus
  coordinates: LatLng[]
}

export interface GraphJob {
  id: string
  label: string
  progress: number
  status: 'queued' | 'running' | 'complete' | 'published'
}
