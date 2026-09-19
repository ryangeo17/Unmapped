import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { searchPlaces } from '../api/endpoints'

export function usePlaces(query: string, enabled: boolean) {
  return useQuery({
    queryKey: ['places', query],
    queryFn: ({ signal }) => searchPlaces(query, signal),
    enabled,
    placeholderData: keepPreviousData, // keep old results visible while typing
    staleTime: 60_000,
  })
}
