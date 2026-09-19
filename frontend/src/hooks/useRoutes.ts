import { useQueries, useQuery } from '@tanstack/react-query'
import type { FeatureCollection } from 'geojson'
import {
  MODE_ORDER,
  SUMMARY_URL,
  routeUrl,
  type RouteMode,
  type RouteSummary,
} from '../lib/routes'

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} -> ${res.status}`)
  return res.json()
}

export function useRouteSummary() {
  return useQuery({
    queryKey: ['routes', 'summary'],
    queryFn: () => fetchJson<RouteSummary[]>(SUMMARY_URL),
    staleTime: Infinity,
  })
}

/** The three mode lines for one trip. `trip` null means nothing is selected. */
export function useTripRoutes(trip: string | null) {
  const results = useQueries({
    queries: MODE_ORDER.map((mode) => ({
      queryKey: ['routes', trip, mode],
      queryFn: () => fetchJson<FeatureCollection>(routeUrl(trip!, mode)),
      enabled: !!trip,
      staleTime: Infinity,
    })),
  })

  const byMode = {} as Record<RouteMode, FeatureCollection | undefined>
  MODE_ORDER.forEach((mode, i) => {
    byMode[mode] = results[i].data
  })
  return byMode
}
