import { ROUTE_COLOR } from './RouteLayers'
import type { RouteOk, RouteResult } from '../../api/planner'

type Props = {
  routes: RouteResult[]
  selected: RouteOk | null
  onSelect: (route: RouteOk) => void
  onPickCandidate: (field: 'origin' | 'destination', name: string) => void
}

function Row({ route, active, onSelect }: {
  route: RouteOk
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs ${
        active ? 'bg-white ring-1 ring-gray-300' : 'hover:bg-white/60'
      }`}
    >
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-full"
        style={{ backgroundColor: active ? ROUTE_COLOR : '#cbd5e1' }}
      />
      <span className={`flex-1 ${active ? 'font-medium text-gray-900' : 'text-gray-600'}`}>
        {route.profileLabel}
      </span>
      <span className="tabular-nums text-gray-600">
        {route.summary.minutes.toFixed(1)} min
      </span>
      <span className="w-12 text-right tabular-nums text-gray-600">
        {route.summary.metres.toFixed(0)} m
      </span>
      <span className="w-16 text-right text-gray-500">
        {route.summary.steps
          ? `${route.summary.steps} steps`
          : route.summary.stepsBesideShortcut
            ? 'steps possible'
            : 'no steps'}
      </span>
    </button>
  )
}

export default function RouteOptions({
  routes, selected, onSelect, onPickCandidate,
}: Props) {
  const ambiguous = routes.find((r) => r.status === 'ambiguous')
  if (ambiguous && ambiguous.status === 'ambiguous') {
    return (
      <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3">
        <p className="text-xs text-amber-900">
          “{ambiguous.query}” matches {ambiguous.candidates.length} places. Which one?
        </p>
        <div className="flex flex-wrap gap-1.5">
          {ambiguous.candidates.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => onPickCandidate(ambiguous.field, name)}
              className="rounded border border-amber-300 bg-white px-2 py-1 text-xs
                         text-amber-900 hover:bg-amber-100"
            >
              {name}
            </button>
          ))}
        </div>
      </div>
    )
  }

  const ok = routes.filter((r): r is RouteOk => r.status === 'ok')
  if (!ok.length) {
    const failed = routes[0]
    return (
      <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
        {failed && 'error' in failed ? failed.error : 'No route found.'}
      </p>
    )
  }

  const shown = selected ?? ok[0]
  const saved = shown.savedBySmarter

  return (
    <div className="space-y-3 rounded-md border border-gray-200 bg-gray-50 p-3">
      <div className="space-y-0.5">
        {ok.map((route) => (
          <Row
            key={route.profile}
            route={route}
            active={route.profile === shown.profile}
            onSelect={() => onSelect(route)}
          />
        ))}
        {routes.filter((r) => r.status === 'no_route').length > 0 && (
          <p className="px-2 py-1.5 text-xs text-gray-400">
            Some profiles found no route between these places.
          </p>
        )}
      </div>

      {/* Only shown for walking, which is the only profile the switch reaches. */}
      {saved && (saved.savedMetres > 0.5 || saved.savedMinutes > 0.05) && (
        <p className="rounded bg-blue-50 px-2 py-1.5 text-xs text-blue-900">
          <span className="font-semibold">{saved.savedMetres.toFixed(0)} m shorter</span>{' '}
          than the paved route ({saved.plainMetres.toFixed(0)} m
          {saved.plainArrival !== shown.destination.arrival &&
            `, which ends at ${saved.plainArrival}`}
          ).
        </p>
      )}

      <dl className="space-y-1 text-xs text-gray-600">
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-gray-400">Starts</dt>
          <dd className="font-medium text-gray-900">{shown.origin.arrival}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-gray-400">Arrives</dt>
          <dd>
            <span className="font-medium text-gray-900">{shown.destination.arrival}</span>
            {shown.destination.kind === 'lift' && (
              <span className="ml-1 rounded bg-gray-200 px-1 text-[10px] uppercase tracking-wide">
                lift
              </span>
            )}
          </dd>
        </div>
        {!!shown.summary.shortcutMetres && (
          <div className="flex gap-2">
            <dt className="w-16 shrink-0 text-gray-400">Shortcut</dt>
            <dd>
              <span className="font-medium text-gray-900">
                {shown.summary.shortcutMetres.toFixed(0)} m
              </span>{' '}
              across {shown.summary.shortcutSpaces.join(', ')}
            </dd>
          </div>
        )}
      </dl>

      {shown.warnings.map((w) => (
        <p key={w} className="text-xs text-amber-700">{w}</p>
      ))}
    </div>
  )
}
