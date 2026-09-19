import { useQuery } from '@tanstack/react-query'
import { getRoute } from '../api/endpoints'
import { useTripStore } from '../store/tripStore'

// The route for the last submitted trip. Any component can call this; they
// all share one request and one cached result.
export function useRoute() {
  const request = useTripStore((s) => s.submittedRequest)
  return useQuery({
    queryKey: ['route', request],
    queryFn: ({ signal }) => getRoute(request!, signal),
    enabled: request !== null,
    staleTime: Infinity, // a route for the same trip doesn't change while you look at it
    retry: 0, // requests are slow (Gemini); let the user retry instead
  })
}
