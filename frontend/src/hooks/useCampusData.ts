import { useQueries } from '@tanstack/react-query'
import type { FeatureCollection } from 'geojson'
import { CAMPUS_DATA, type CampusLayerId } from '../lib/campusData'

async function fetchGeoJson(url: string): Promise<FeatureCollection> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} -> ${res.status}`)
  return res.json()
}

const LAYER_IDS = Object.keys(CAMPUS_DATA) as CampusLayerId[]

/**
 * Loads every local campus GeoJSON. `enabled` gates the fetch so nothing is
 * pulled until the local-data view is switched on; results stay cached after
 * that, so toggling back and forth doesn't refetch.
 */
export function useCampusData(enabled: boolean) {
  const results = useQueries({
    queries: LAYER_IDS.map((id) => ({
      queryKey: ['campus', id],
      queryFn: () => fetchGeoJson(CAMPUS_DATA[id]),
      enabled,
      staleTime: Infinity,
      gcTime: Infinity,
      retry: 1,
    })),
  })

  const data = {} as Record<CampusLayerId, FeatureCollection | undefined>
  LAYER_IDS.forEach((id, i) => {
    data[id] = results[i].data
  })

  return {
    data,
    isLoading: enabled && results.some((r) => r.isLoading),
    loaded: results.filter((r) => r.isSuccess).length,
    total: LAYER_IDS.length,
    failed: LAYER_IDS.filter((_, i) => results[i].isError),
  }
}
