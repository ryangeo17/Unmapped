// Example walking routes solved by the planner package; see planner/SKILL.md.
// One route per trip: lawn shortcuts and the nearest usable entrance are
// priced into the search, not offered as options.
// Accessibility routing is a separate feature and is not represented here.

export type RouteSummary = {
  trip: string
  label: string
  from: string
  to: string
  toKind: 'entrance' | 'lift' | 'centre'
  status: string
  minutes?: number
  metres?: number
  feet?: number
  steps?: number
  stepsBesideShortcut?: number
  shortcutMetres?: number
  shortcutSpaces?: string[]
  warnings?: string[]
}

// Outside the green/amber/red the Pathways layer uses for accessibility
// grading, so the route still reads as a route over the campus data.
export const ROUTE_COLOR = '#db2777'
export const ROUTE_WIDTH = 5
export const ROUTE_CASING = '#ffffff'

export const routeUrl = (trip: string) => `/data/routes/${trip}.geojson`
export const SUMMARY_URL = '/data/routes/_summary.json'
