import type { GraphJob, Hazard, Landmark, LatLng, RouteResult, Submission, SuggestionPayload, TravelMode } from './types'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const API_ORIGIN = API_BASE_URL.endsWith('/api') ? API_BASE_URL.slice(0, -4) : ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const raw = await response.text().catch(() => '')
    let message = raw
    try {
      message = JSON.parse(raw).detail || raw
    } catch {
      // FastAPI errors are usually JSON, but proxy errors may be plain text.
    }
    throw new Error(message || `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

function distanceMeters(a: LatLng, b: LatLng) {
  const toRadians = (value: number) => (value * Math.PI) / 180
  const dLat = toRadians(b[0] - a[0])
  const dLng = toRadians(b[1] - a[1])
  const value = Math.sin(dLat / 2) ** 2
    + Math.cos(toRadians(a[0])) * Math.cos(toRadians(b[0])) * Math.sin(dLng / 2) ** 2
  return 6371000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value))
}

async function nearestNode(point: LatLng) {
  const snapped = await request<{ id: string }>(
    `/nodes/nearest?lat=${point[0]}&lng=${point[1]}`,
  )
  return snapped.id
}

function mapSubmission(item: Record<string, unknown>): Submission {
  const rawStatus = String(item.status)
  const status: Submission['status'] =
    rawStatus === 'pending' ? 'pending'
      : rawStatus === 'rejected' ? 'rejected'
        : rawStatus === 'published' ? 'published' : 'approved'
  return {
    id: String(item.id),
    reference: String(item.tracking_code),
    description: String(item.name || item.description),
    reason: String(item.description || ''),
    createdAt: String(item.created_at),
    status,
    coordinates: Array.isArray(item.geometry) ? item.geometry as LatLng[] : [],
  }
}

interface BackendJob {
  id: number
  submission_id: number
  status: string
  result?: unknown
}

function mapJob(job: BackendJob): GraphJob {
  const progress = { queued: 10, dispatched: 35, inspecting: 65, succeeded: 100, failed: 100 }[job.status] ?? 0
  return {
    id: String(job.id),
    label: `Robot verification job ${job.id}`,
    progress,
    status: job.status === 'succeeded' ? 'complete' : job.status === 'published' ? 'published'
      : job.status === 'queued' ? 'queued' : 'running',
  }
}

export const api = {
  async searchLandmarks(query: string, signal?: AbortSignal) {
    const items = await request<Array<{
      id: string
      name: string
      description: string
      node_id: string
      latitude: number
      longitude: number
    }>>(`/landmarks?query=${encodeURIComponent(query)}`, { signal })
    return items
      .filter((item) => `${item.name} ${item.description}`.toLowerCase().includes(query.toLowerCase()))
      .map<Landmark>((item) => ({
        id: item.node_id,
        name: item.name,
        subtitle: item.description,
        coordinates: [item.latitude, item.longitude],
      }))
  },

  async calculateRoute(input: {
    start: Landmark
    destination: Landmark
    mode: TravelMode
    time: 'day' | 'night'
    smarter?: boolean
    avoidEdgeIds?: string[]
  }): Promise<RouteResult> {
    // Places go to the backend by name. It knows every door of each one and
    // picks whichever is actually nearest, which snapping a single coordinate
    // here cannot do — and it saves pulling the 2.2 MB graph overlay three
    // times per route just to find one node.
    const avoidEdges = input.avoidEdgeIds ?? []
    const result = await request<{
      start_node: string
      end_node: string
      geometry: [number, number][]
      edge_ids: string[]
      steps: { instruction: string; distance_m: number }[]
      scores: { safety: number | null; accessibility: number }
      smarter: boolean
      start_door: { label: string; kind: string; step_free: boolean } | null
      end_door: { label: string; kind: string; step_free: boolean } | null
      verified_stats: {
        distance_m: number
        estimated_seconds: number
        verified_percent?: number
        riser_count?: number
        shortcut_m?: number
        shortcut_spaces?: string[]
        unknown_attribute_m?: number
        fully_compliant_percent?: number | null
      }
      hazards: Array<{
        id: string
        title: string
        description?: string
        severity: number
        edge_id?: string
        latitude?: number
        longitude?: number
        verified?: boolean
        evidence?: string[]
      }>
      explanation: string[]
    }>('/routes/compute', {
      method: 'POST',
      body: JSON.stringify({
        start: input.start.name,
        end: input.destination.name,
        mode: input.mode,
        nighttime: input.time === 'night',
        smarter: input.smarter ?? true,
        avoid_edges: avoidEdges,
      }),
    })
    const coordinates = result.geometry.map<LatLng>((point) => [point[1], point[0]])
    const routeHazards = result.hazards.map<Hazard>((hazard) => ({
      id: hazard.id,
      edgeId: hazard.edge_id,
      title: hazard.title,
      description: hazard.description || 'Robot-observed caution on this path segment.',
      severity: hazard.severity >= 3 ? 'high' : hazard.severity === 2 ? 'medium' : 'low',
      coordinates: [
        hazard.latitude ?? coordinates[0][0],
        hazard.longitude ?? coordinates[0][1],
      ],
      verified: hazard.verified ?? false,
      evidence: hazard.evidence?.map((path) => path.startsWith('http') ? path : `${API_ORIGIN}${path}`),
    }))
    const stats = result.verified_stats
    return {
      id: `${result.start_node}-${result.end_node}-${input.mode}`,
      coordinates,
      distanceMeters: result.verified_stats.distance_m,
      durationMinutes: Math.max(1, Math.round(result.verified_stats.estimated_seconds / 60)),
      accessibilityScore: Math.round(result.scores.accessibility),
      // Null once the synthetic safety readings are gone: nobody has surveyed
      // security coverage here yet, and a score of 0 would read as dangerous.
      safetyScore: result.scores.safety === null ? null : Math.round(result.scores.safety),
      verifiedPercent: Math.round(stats.verified_percent ?? 0),
      riserCount: stats.riser_count ?? 0,
      shortcutMeters: stats.shortcut_m ?? 0,
      shortcutSpaces: stats.shortcut_spaces ?? [],
      unknownMeters: stats.unknown_attribute_m ?? 0,
      compliantPercent: stats.fully_compliant_percent ?? null,
      smarter: result.smarter,
      startDoor: result.start_door,
      endDoor: result.end_door,
      explanation: result.explanation.join(' '),
      steps: result.steps.map((step, index) => ({
        instruction: step.instruction,
        distance: `${Math.round(step.distance_m)} m`,
        coordinates: coordinates[Math.min(index, coordinates.length - 1)],
      })),
      hazards: routeHazards,
      alternatives: [],
    }
  },

  async submitSuggestion(payload: SuggestionPayload) {
    const [fromNode, toNode] = await Promise.all([
      nearestNode(payload.coordinates[0]),
      nearestNode(payload.coordinates[payload.coordinates.length - 1]),
    ])
    const length = payload.coordinates.slice(1).reduce(
      (sum, point, index) => sum + distanceMeters(payload.coordinates[index], point),
      0,
    )
    const data = new FormData()
    data.append('name', payload.description)
    data.append('description', `${payload.reason}: ${payload.description}`)
    data.append('reason', payload.reason)
    data.append('geometry', JSON.stringify(payload.coordinates))
    data.append('from_node', fromNode)
    data.append('to_node', toNode)
    data.append('distance_m', String(Math.max(1, length)))
    if (payload.photo) data.append('image', payload.photo)
    const result = await request<{ tracking_code: string }>('/submissions', { method: 'POST', body: data })
    return { reference: result.tracking_code }
  },

  adminLogin(password: string) {
    return request<{ token: string }>('/admin/login', { method: 'POST', body: JSON.stringify({ password }) })
  },

  async getSubmissions(token: string) {
    const items = await request<Record<string, unknown>[]>('/admin/submissions', {
      headers: { Authorization: `Bearer ${token}` },
    })
    return items.map(mapSubmission)
  },

  async updateSubmission(id: string, status: Submission['status'], token: string) {
    const path = status === 'approved' ? 'approve' : 'reject'
    const result = await request<Record<string, unknown>>(`/admin/submissions/${id}/${path}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ note: status === 'rejected' ? 'Rejected during admin review' : 'Approved for robot verification' }),
    })
    return mapSubmission((result.submission || result) as Record<string, unknown>)
  },

  async createGraphJob(token: string) {
    const jobs = await request<BackendJob[]>('/admin/robot-jobs', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!jobs.length) throw new Error('Approve a submission before creating a robot job.')
    return mapJob(jobs[0])
  },

  async getGraphJob(id: string, token: string) {
    const jobs = await request<BackendJob[]>('/admin/robot-jobs', {
      headers: { Authorization: `Bearer ${token}` },
    })
    const job = jobs.find((item) => String(item.id) === id)
    if (!job) throw new Error('Robot job not found.')
    return mapJob(job)
  },

  async simulateGraphJob(id: string, token: string) {
    const headers = { Authorization: `Bearer ${token}` }
    const jobs = await request<BackendJob[]>('/admin/robot-jobs', { headers })
    let job = jobs.find((item) => String(item.id) === id)
    if (!job) throw new Error('Robot job not found.')
    if (job.status === 'queued') {
      job = await request<BackendJob>(`/admin/robot-jobs/${id}/transition`, {
        method: 'POST', headers, body: JSON.stringify({ status: 'dispatched' }),
      })
    }
    if (job.status === 'dispatched') {
      job = await request<BackendJob>(`/admin/robot-jobs/${id}/transition`, {
        method: 'POST', headers, body: JSON.stringify({ status: 'inspecting' }),
      })
    }
    const completed = await request<BackendJob>(`/admin/robot-jobs/${id}/simulate-result`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        success: true,
        surface: 'paved',
        roughness: 0.04,
        slope: 0.01,
        note: 'Automated demo robot pipeline completed successfully.',
      }),
    })
    return mapJob(completed)
  },

  async publishGraphJob(id: string, token: string) {
    const headers = { Authorization: `Bearer ${token}` }
    const jobs = await request<BackendJob[]>('/admin/robot-jobs', { headers })
    const job = jobs.find((item) => String(item.id) === id)
    if (!job) throw new Error('Robot job not found.')
    await request(`/admin/submissions/${job.submission_id}/publish`, { method: 'POST', headers })
    return { ...mapJob(job), status: 'published' as const, progress: 100 }
  },

  setDemoClosure(closed: boolean, token: string) {
    return request<{ id: string; closed: boolean }>('/admin/edges/e-rec-mse', {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ closed }),
    })
  },
}
