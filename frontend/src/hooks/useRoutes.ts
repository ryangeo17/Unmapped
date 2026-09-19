import { useQuery } from '@tanstack/react-query'
import type { FeatureCollection } from 'geojson'
import { SUMMARY_URL, routeUrl, type RouteSummary } from '../lib/routes'

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

/** The line for one trip. `trip` null means nothing is selected. */
export function useTripRoute(trip: string | null) {
  return useQuery({
    queryKey: ['routes', trip],
    queryFn: () => fetchJson<FeatureCollection>(routeUrl(trip!)),
    enabled: !!trip,
    staleTime: Infinity,
  })
}
