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

export interface RouteResult {
  id: string
  coordinates: LatLng[]
  distanceMeters: number
  durationMinutes: number
  accessibilityScore: number
  safetyScore: number
  verifiedPercent: number
  explanation: string
  steps: RouteStep[]
  hazards: Hazard[]
  graphEdges?: LatLng[][]
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
