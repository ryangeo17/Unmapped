// Example routes solved by scripts/route_examples.py. See
// public/data/routes/README.md for the cost model behind each mode.

export type RouteMode = 'walking' | 'smart' | 'partial' | 'accessible'

export type RouteSummary = {
  trip: string
  mode: RouteMode
  modeLabel: string
  from: string
  to: string
  status: string
  minutes?: number
  metres?: number
  feet?: number
  stairSegments?: number
  risers?: number
  fullyCompliantShare?: number | null
  shortcutMetres?: number
  shortcutSpaces?: string[]
  grades?: Record<string, number>
}

export const TRIPS = [
  { id: 'malone-to-clark', label: 'Malone Hall → Clark Hall' },
  { id: 'malone-to-san-martin-garage', label: 'Malone Hall → San Martin Garage' },
] as const

export const MODE_ORDER: RouteMode[] = ['walking', 'smart', 'partial', 'accessible']

// Deliberately outside the green/amber/red the Pathways layer uses for its
// accessibility grading. A route drawn in those colours vanishes into the
// network as soon as the campus data is switched on. Each line also gets a
// white casing underneath so it reads as a route over any background.
export const MODE_STYLE: Record<RouteMode, { color: string; width: number; label: string }> = {
  walking: { color: '#111827', width: 5, label: 'Walking' },
  smart: { color: '#db2777', width: 5, label: 'Walking (shortcuts)' },
  partial: { color: '#a855f7', width: 5, label: 'Partially accessible' },
  accessible: { color: '#2563eb', width: 5, label: 'Fully accessible' },
}

export const CASING = '#ffffff'

export const routeUrl = (trip: string, mode: RouteMode) =>
  `/data/routes/${trip}.${mode}.geojson`

export const SUMMARY_URL = '/data/routes/_summary.json'
