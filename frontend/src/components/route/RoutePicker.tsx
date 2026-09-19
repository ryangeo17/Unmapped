import { useRouteSummary } from '../../hooks/useRoutes'
import {
  MODE_ORDER,
  MODE_STYLE,
  TRIPS,
  type RouteMode,
  type RouteSummary,
} from '../../lib/routes'
import { useLayerStore } from '../../store/useLayerStore'

function ModeRow({
  row,
  active,
  onSelect,
}: {
  row: RouteSummary
  active: boolean
  onSelect: () => void
}) {
  const style = MODE_STYLE[row.mode]
  const unavailable = row.status !== 'ok'
  return (
    <button
      type="button"
      disabled={unavailable}
      onClick={onSelect}
      className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs ${
        active ? 'bg-white ring-1 ring-gray-300' : 'hover:bg-white/60'
      } ${unavailable ? 'cursor-not-allowed opacity-40' : ''}`}
    >
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-full"
        style={{ backgroundColor: style.color }}
      />
      <span className={`flex-1 ${active ? 'font-medium text-gray-900' : 'text-gray-600'}`}>
        {style.label}
      </span>
      {unavailable ? (
        <span className="text-gray-400">no route</span>
      ) : (
        <>
          <span className="tabular-nums text-gray-600">{row.minutes?.toFixed(1)} min</span>
          <span className="w-12 text-right tabular-nums text-gray-600">
            {row.metres?.toFixed(0)} m
          </span>
          <span className="w-16 text-right">
            {row.risers ? (
              <span className="text-red-600">{row.risers} steps</span>
            ) : (
              <span className="text-green-700">step-free</span>
            )}
          </span>
        </>
      )}
    </button>
  )
}

export default function RoutePicker() {
  const { data, isLoading } = useRouteSummary()
  const selectedTrip = useLayerStore((s) => s.selectedTrip)
  const selectTrip = useLayerStore((s) => s.selectTrip)
  const selectedMode = useLayerStore((s) => s.selectedMode)
  const selectMode = useLayerStore((s) => s.selectMode)

  const activeRow = (data ?? []).find(
    (r) => r.trip === selectedTrip && r.mode === selectedMode && r.status === 'ok',
  )

  const pick = (tripId: string, mode?: RouteMode) => {
    selectTrip(tripId)
    if (mode) selectMode(mode)
  }

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium text-gray-900">Example routes</h2>
      {isLoading && <p className="text-xs text-gray-500">Loading…</p>}

      {TRIPS.map((trip) => {
        const rows = (data ?? []).filter((r) => r.trip === trip.id)
        const active = selectedTrip === trip.id
        return (
          <div
            key={trip.id}
            className={`overflow-hidden rounded-md border ${
              active ? 'border-blue-500 bg-gray-50' : 'border-gray-200'
            }`}
          >
            <button
              type="button"
              onClick={() => selectTrip(active ? null : trip.id)}
              className="flex w-full items-center justify-between px-3 py-2 text-left"
            >
              <span className="text-sm font-medium text-gray-900">{trip.label}</span>
              <span className="text-xs text-gray-500">{active ? 'hide' : 'show'}</span>
            </button>

            {active && rows.length > 0 && (
              <div className="space-y-0.5 px-2 pb-2">
                {MODE_ORDER.map((mode) => {
                  const row = rows.find((r) => r.mode === mode)
                  if (!row) return null
                  return (
                    <ModeRow
                      key={mode}
                      row={row}
                      active={selectedMode === mode}
                      onSelect={() => pick(trip.id, mode)}
                    />
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      {activeRow && (activeRow.shortcutMetres || activeRow.to) && (
        <div className="space-y-1 rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-600">
          {!!activeRow.shortcutMetres && (
            <p>
              Cuts{' '}
              <span className="font-medium text-gray-900">
                {activeRow.shortcutMetres.toFixed(0)} m
              </span>{' '}
              across {activeRow.shortcutSpaces?.join(', ')}.
            </p>
          )}
          <p>
            Arrives at <span className="font-medium text-gray-900">{activeRow.to}</span>.
          </p>
        </div>
      )}

      {selectedTrip && (
        <p className="text-xs text-gray-500">
          One mode is drawn at a time — pick a row to switch. Filled dot is the
          start, hollow dot the destination. Shortcut edges cross open lawn and
          are not wheelchair-safe; they are only offered to walking.
        </p>
      )}
    </section>
  )
}
