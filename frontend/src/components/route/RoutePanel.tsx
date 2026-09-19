import { NoRouteError } from '../../api/endpoints'
import { useRoute } from '../../hooks/useRoute'
import { useTripStore } from '../../store/tripStore'
import { arrivalTime, formatClock } from '../../utils/time'
import ErrorState from '../common/ErrorState'
import LoadingStages from '../common/LoadingStages'
import { MODES } from '../trip/modes'
import Alternatives from './Alternatives'
import Explanation from './Explanation'
import RouteSummary from './RouteSummary'
import SafetyBadge from './SafetyBadge'
import { formatDistance, formatDuration } from './format'

// The route result under the trip panel: loading stages, errors, or the route.
export default function RoutePanel() {
  const { data: result, isFetching, isError, error, refetch, fetchStatus, status } = useRoute()
  const request = useTripStore((s) => s.submittedRequest)
  const setMode = useTripStore((s) => s.setMode)

  if (status === 'pending' && fetchStatus === 'idle') return null // nothing requested yet

  const route = result?.route
  const departAt = request?.departAt
  const otherModes = MODES.filter((m) => m.id !== request?.mode)

  return (
    <div className="flex flex-col gap-3 border-t border-gray-200 pt-4">
      {/* Screen readers hear when a new route arrives. */}
      <p aria-live="polite" className="sr-only">
        {route && !isFetching
          ? `Route found: ${formatDuration(route.durationS)}, ${formatDistance(route.distanceM)}${departAt ? `, arriving ${formatClock(arrivalTime(new Date(departAt), route.durationS))}` : ''}.`
          : ''}
      </p>

      {isFetching && <LoadingStages night={request?.timeOfDay === 'night'} />}

      {isError && !isFetching &&
        (error instanceof NoRouteError ? (
          <ErrorState title="No route found" message={error.message}>
            <p className="mt-3 text-sm font-medium">Try a different way of getting there:</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {otherModes.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setMode(m.id)}
                  className="flex min-h-10 items-center gap-1.5 rounded-lg border border-red-200 bg-white px-3 text-sm font-medium text-gray-800 hover:bg-red-100"
                >
                  <span aria-hidden="true">{m.icon}</span>
                  {m.label}
                </button>
              ))}
            </div>
          </ErrorState>
        ) : (
          <ErrorState title="Couldn't get a route" message={error.message} onRetry={() => refetch()} />
        ))}

      {result && route && !isFetching && (
        <>
          <RouteSummary route={route} departAt={departAt} />
          {route.safety && <SafetyBadge safety={route.safety} />}
          <Explanation result={result} />
          <Alternatives route={route} alternatives={result.alternatives} />
        </>
      )}
    </div>
  )
}
