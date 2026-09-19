import { useQuery } from '@tanstack/react-query'
import { getCoverage, getObservations } from '../api/endpoints'

// Latest robot observations, polled so the feed looks live.
export function useObservations() {
  return useQuery({
    queryKey: ['observations'],
    queryFn: ({ signal }) => getObservations(signal),
    refetchInterval: 3000,
    retry: 0,
  })
}

// How much of the demo zone the robot has verified.
export function useCoverage() {
  return useQuery({
    queryKey: ['coverage'],
    queryFn: ({ signal }) => getCoverage(signal),
    refetchInterval: 5000,
    retry: 0,
  })
}
