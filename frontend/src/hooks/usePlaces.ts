import { useQuery } from '@tanstack/react-query'
import { fetchPlaces } from '../api/planner'

/** Names for the input datalists. 116 of them, so one fetch and keep it. */
export function usePlaces() {
  return useQuery({
    queryKey: ['places'],
    queryFn: fetchPlaces,
    staleTime: Infinity,
    retry: false,
  })
}
