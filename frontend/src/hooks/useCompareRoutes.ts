import { useQueries } from '@tanstack/react-query'
import { getRoute } from '../api/endpoints'
import { MODES } from '../components/trip/modes'
import { useTripStore } from '../store/tripStore'

// The submitted trip, fetched for every mode at once (Compare mode). Uses the
// same query keys as useRoute, so opening one mode afterwards is instant.
export function useCompareRoutes() {
  const request = useTripStore((s) => s.submittedRequest)
  const submitCount = useTripStore((s) => s.submitCount)
  const compareMode = useTripStore((s) => s.compareMode)
  const queries = useQueries({
    queries: MODES.map((m) => {
      const req = request && { ...request, mode: m.id }
      return {
        queryKey: ['route', req, submitCount],
        queryFn: ({ signal }: { signal: AbortSignal }) => getRoute(req!, signal),
        enabled: compareMode && req !== null,
        staleTime: Infinity,
        retry: 0,
      }
    }),
  })
  return MODES.map((mode, i) => ({ mode, query: queries[i] }))
}
