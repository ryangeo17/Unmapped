import { NoRouteError } from '../../api/endpoints'
import { useCompareRoutes } from '../../hooks/useCompareRoutes'
import { useTripStore } from '../../store/tripStore'
import { formatDistance, formatDuration, safetyLevel } from './format'

const firstSentence = (text: string) => text.match(/^.*?[.!?](\s|$)/)?.[0].trim() ?? text

// Compare mode sidebar: one card per mode. Clicking a card opens that mode's full route.
export default function CompareCards() {
  const routes = useCompareRoutes()
  const setMode = useTripStore((s) => s.setMode)
  const setCompareMode = useTripStore((s) => s.setCompareMode)
  const hasRequest = useTripStore((s) => s.submittedRequest !== null)
  if (!hasRequest) return null

  const loaded = routes.flatMap((r) => (r.query.data ? [r.query.data.route] : []))
  const fastest = loaded.length > 1 ? Math.min(...loaded.map((r) => r.durationS)) : null
  const safest = loaded.length > 1 ? Math.max(...loaded.map((r) => r.safety?.score ?? -1)) : null
  const done = routes.filter((r) => !r.query.isFetching).length

  return (
    <section aria-labelledby="compare-heading" className="flex flex-col gap-2 border-t border-gray-200 pt-4">
      <h2 id="compare-heading" className="flex items-baseline justify-between font-semibold text-gray-900">
        Every way to get there
        <span className="text-sm font-normal text-gray-500" aria-live="polite">
          {done < routes.length ? `Loading ${done}/${routes.length}…` : 'Tap one for details'}
        </span>
      </h2>
      <ul className="flex flex-col gap-2">
        {routes.map(({ mode, query }) => {
          const result = query.data
          const route = result?.route
          const safety = route?.safety && safetyLevel(route.safety.score)
          return (
            <li key={mode.id}>
              <button
                type="button"
                disabled={!route}
                onClick={() => {
                  setMode(mode.id)
                  setCompareMode(false)
                }}
                className="w-full rounded-lg border-2 bg-white p-3 text-left hover:bg-gray-50 disabled:cursor-default disabled:hover:bg-white"
                style={{ borderColor: route ? mode.color : '#e5e7eb' }}
              >
                <span className="flex items-center gap-2">
                  <span aria-hidden="true" className="text-xl">
                    {mode.icon}
                  </span>
                  <span className="font-semibold text-gray-900">{mode.label}</span>
                  {/* Same colour + dash as the map line, so cards and lines match up. */}
                  <svg width="28" height="8" aria-hidden="true">
                    <line x1="2" y1="4" x2="26" y2="4" stroke={mode.color} strokeWidth="4" strokeDasharray={mode.dash?.map((d) => d * 4).join(' ')} />
                  </svg>
                  {route && (
                    <span className="ml-auto text-right">
                      <span className="font-bold text-gray-900">{formatDuration(route.durationS)}</span>
                      <span className="text-sm text-gray-600"> · {formatDistance(route.distanceM)}</span>
                    </span>
                  )}
                </span>

                {query.isFetching && (
                  <span className="mt-2 flex items-center gap-2 text-sm text-gray-500">
                    <span aria-hidden="true" className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
                    Finding a route…
                  </span>
                )}
                {query.isError && !query.isFetching && (
                  <span className="mt-2 block text-sm text-red-800">
                    {query.error instanceof NoRouteError ? query.error.message : "Couldn't load this route."}
                  </span>
                )}

                {route && result && !query.isFetching && (
                  <>
                    <span className="mt-1.5 flex flex-wrap gap-1.5">
                      {route.durationS === fastest && <Tag>⚡ Fastest</Tag>}
                      {route.safety && route.safety.score === safest && <Tag>🛡️ Safest</Tag>}
                      {route.safety && safety && (
                        <span className={`rounded-full border px-2 py-0.5 text-xs ${safety.className}`}>
                          Safety {safety.label} · {route.safety.score}
                        </span>
                      )}
                    </span>
                    <span className="mt-1.5 block text-sm text-gray-700">{firstSentence(result.explanation)}</span>
                  </>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="rounded-full bg-gray-900 px-2 py-0.5 text-xs font-medium text-white">{children}</span>
}
