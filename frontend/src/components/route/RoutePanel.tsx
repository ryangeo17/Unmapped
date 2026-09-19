import { useRoute } from '../../hooks/useRoute'
import { useTripStore } from '../../store/tripStore'
import { arrivalTime, formatClock } from '../../utils/time'
import Explanation from './Explanation'
import RouteSummary from './RouteSummary'
import SafetyBadge from './SafetyBadge'
import { formatDistance, formatDuration } from './format'

// The route result under the trip panel. Task 9 upgrades the loading and error states.
export default function RoutePanel() {
  const { data: result, isFetching, isError, error, refetch, fetchStatus, status } = useRoute()
  const departAt = useTripStore((s) => s.submittedRequest?.departAt)

  if (status === 'pending' && fetchStatus === 'idle') return null // nothing requested yet

  const route = result?.route
  return (
    <div className="flex flex-col gap-3 border-t border-gray-200 pt-4">
      {/* Screen readers hear when a new route arrives. */}
      <p aria-live="polite" className="sr-only">
        {isFetching
          ? 'Finding a route…'
          : route
            ? `Route found: ${formatDuration(route.durationS)}, ${formatDistance(route.distanceM)}${departAt ? `, arriving ${formatClock(arrivalTime(new Date(departAt), route.durationS))}` : ''}.`
            : ''}
      </p>

      {isFetching && (
        <p className="flex items-center gap-2 text-gray-700">
          <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          Finding the best route…
        </p>
      )}

      {isError && !isFetching && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-900">
          <p>{error.message}</p>
          <button type="button" onClick={() => refetch()} className="mt-2 min-h-10 rounded-md bg-red-700 px-3 text-sm font-semibold text-white">
            Try again
          </button>
        </div>
      )}

      {result && route && !isFetching && (
        <>
          <RouteSummary route={route} departAt={departAt} />
          {route.safety && <SafetyBadge safety={route.safety} />}
          <Explanation result={result} />
        </>
      )}
    </div>
  )
}
