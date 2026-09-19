import { useRouteSummary } from '../../hooks/useRoutes'
import { ROUTE_COLOR, type RouteSummary } from '../../lib/routes'
import { useLayerStore } from '../../store/useLayerStore'

function Detail({ route }: { route: RouteSummary }) {
  return (
    <div className="space-y-2 px-3 pb-3">
      <div className="flex items-baseline gap-3 text-sm">
        <span className="font-medium text-gray-900">{route.minutes?.toFixed(1)} min</span>
        <span className="text-gray-600">{route.metres?.toFixed(0)} m</span>
        {!!route.steps && <span className="text-gray-500">{route.steps} steps</span>}
      </div>

      <dl className="space-y-1 text-xs text-gray-600">
        {!!route.shortcutMetres && (
          <div className="flex gap-2">
            <dt className="w-16 shrink-0 text-gray-400">Shortcut</dt>
            <dd>
              <span className="font-medium text-gray-900">
                {route.shortcutMetres.toFixed(0)} m
              </span>{' '}
              across {route.shortcutSpaces?.join(', ')}
            </dd>
          </div>
        )}
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-gray-400">Arrives</dt>
          <dd>
            <span className="font-medium text-gray-900">{route.to}</span>
            {route.toKind === 'lift' && (
              <span className="ml-1 rounded bg-gray-200 px-1 text-[10px] uppercase tracking-wide">
                lift
              </span>
            )}
          </dd>
        </div>
      </dl>

      {route.warnings?.map((w) => (
        <p key={w} className="text-xs text-amber-700">
          {w}
        </p>
      ))}
    </div>
  )
}

export default function RoutePicker() {
  const { data, isLoading } = useRouteSummary()
  const selected = useLayerStore((s) => s.selectedTrip)
  const selectTrip = useLayerStore((s) => s.selectTrip)

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium text-gray-900">Walking routes</h2>
      <p className="text-xs text-gray-500">
        Each route already cuts across lawn where that is faster and finishes at
        the nearest usable door or lift.
      </p>
      {isLoading && <p className="text-xs text-gray-500">Loading…</p>}

      {(data ?? []).map((route) => {
        const active = selected === route.trip
        const ok = route.status === 'ok'
        return (
          <div
            key={route.trip}
            className={`overflow-hidden rounded-md border ${
              active ? 'border-blue-500 bg-gray-50' : 'border-gray-200'
            }`}
          >
            <button
              type="button"
              disabled={!ok}
              onClick={() => selectTrip(active ? null : route.trip)}
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left disabled:opacity-40"
            >
              <span className="flex items-center gap-2 text-sm font-medium text-gray-900">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: active ? ROUTE_COLOR : '#cbd5e1' }}
                />
                {route.label ?? route.trip}
              </span>
              <span className="shrink-0 text-xs text-gray-500">
                {ok ? (active ? 'hide' : 'show') : route.status}
              </span>
            </button>
            {active && ok && <Detail route={route} />}
          </div>
        )
      })}

      {selected && (
        <p className="text-xs text-gray-500">
          Filled dot is the start, hollow dot the destination. Shortcut edges
          are inferred, not surveyed.
        </p>
      )}
    </section>
  )
}
