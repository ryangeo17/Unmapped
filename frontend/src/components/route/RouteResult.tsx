import type { RouteResult } from '../../api/planner'

type Props = {
  result: RouteResult
  onPickCandidate: (field: 'origin' | 'destination', name: string) => void
}

export default function RouteResultPanel({ result, onPickCandidate }: Props) {
  if (result.status === 'ambiguous') {
    return (
      <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3">
        <p className="text-xs text-amber-900">
          “{result.query}” matches {result.candidates.length} places. Which one?
        </p>
        <div className="flex flex-wrap gap-1.5">
          {result.candidates.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => onPickCandidate(result.field, name)}
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

  if (result.status !== 'ok') {
    return (
      <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
        {result.error}
      </p>
    )
  }

  const { summary, savedBySmarter: saved } = result

  return (
    <div className="space-y-3 rounded-md border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-baseline gap-3">
        <span className="text-lg font-semibold text-gray-900">
          {summary.minutes.toFixed(1)} min
        </span>
        <span className="text-sm text-gray-600">{summary.metres.toFixed(0)} m</span>
        {!!summary.steps && (
          <span className="text-xs text-gray-500">{summary.steps} steps</span>
        )}
        {!summary.steps && !!summary.stepsBesideShortcut && (
          <span className="text-xs text-gray-500">steps possible</span>
        )}
      </div>

      {/* The only thing that makes the toggle mean anything to the user. */}
      {saved && (saved.savedMetres > 0.5 || saved.savedMinutes > 0.05) && (
        <p className="rounded bg-blue-50 px-2 py-1.5 text-xs text-blue-900">
          <span className="font-semibold">
            {saved.savedMetres.toFixed(0)} m shorter
          </span>{' '}
          than the paved route ({saved.plainMetres.toFixed(0)} m
          {saved.plainArrival !== result.destination.arrival &&
            `, which ends at ${saved.plainArrival}`}
          ).
        </p>
      )}
      {saved && saved.savedMetres <= 0.5 && saved.savedMinutes <= 0.05 && (
        <p className="text-xs text-gray-500">
          Same as the paved route here — no shortcut or closer door helps.
        </p>
      )}

      <dl className="space-y-1 text-xs text-gray-600">
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-gray-400">Starts</dt>
          <dd className="font-medium text-gray-900">{result.origin.arrival}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-gray-400">Arrives</dt>
          <dd>
            <span className="font-medium text-gray-900">
              {result.destination.arrival}
            </span>
            {result.destination.kind === 'lift' && (
              <span className="ml-1 rounded bg-gray-200 px-1 text-[10px] uppercase tracking-wide">
                lift
              </span>
            )}
          </dd>
        </div>
        {!!summary.shortcutMetres && (
          <div className="flex gap-2">
            <dt className="w-16 shrink-0 text-gray-400">Shortcut</dt>
            <dd>
              <span className="font-medium text-gray-900">
                {summary.shortcutMetres.toFixed(0)} m
              </span>{' '}
              across {summary.shortcutSpaces.join(', ')}
            </dd>
          </div>
        )}
      </dl>

      {result.warnings.map((w) => (
        <p key={w} className="text-xs text-amber-700">
          {w}
        </p>
      ))}
    </div>
  )
}
