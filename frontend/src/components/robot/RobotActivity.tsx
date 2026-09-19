import { useState } from 'react'
import { useMap } from 'react-map-gl/maplibre'
import { useNow } from '../../hooks/useNow'
import { usePlaces } from '../../hooks/usePlaces'
import { useCoverage, useObservations } from '../../hooks/useRobot'
import type { LngLat, Place } from '../../types/domain'

const SHOWN = 2

// Floating map card: robot coverage + its latest sightings. Hides itself if the
// backend exposes neither (they're optional capabilities).
export default function RobotActivity() {
  const [open, setOpen] = useState(true)
  const { main: map } = useMap()
  const observations = useObservations()
  const coverage = useCoverage()
  const { data: places = [] } = usePlaces('', true) // for "near Gilman Hall"
  const now = useNow(1000)

  if (observations.isError && coverage.isError) return null
  const latest = (observations.data ?? []).slice(0, SHOWN)
  const pct = coverage.data?.verifiedPct

  return (
    <section aria-label="Robot activity" className="absolute top-3 left-3 z-10 w-68 rounded-xl bg-white/95 shadow-md">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex min-h-11 w-full items-center gap-2 px-3 text-left font-semibold text-gray-900"
      >
        <span aria-hidden="true">🤖</span>
        Robot activity
        <span className="relative ml-1 flex h-2 w-2" aria-hidden="true">
          <span className="absolute h-full w-full animate-ping rounded-full bg-green-500 opacity-75" />
          <span className="relative h-2 w-2 rounded-full bg-green-500" />
        </span>
        <span className="sr-only">(live)</span>
        <span aria-hidden="true" className={`ml-auto text-gray-500 transition-transform ${open ? 'rotate-90' : ''}`}>
          ▸
        </span>
      </button>

      {open && (
        <div className="border-t border-gray-100 px-3 pt-2 pb-3">
          {pct !== undefined && (
            <div>
              <p className="flex items-baseline justify-between text-sm">
                <span className="text-gray-700">Demo zone verified</span>
                <span className="font-bold text-gray-900">{pct.toFixed(0)}%</span>
              </p>
              <div
                role="progressbar"
                aria-label="Demo zone verified by robot"
                aria-valuenow={Math.round(pct)}
                aria-valuemin={0}
                aria-valuemax={100}
                className="mt-1 h-2 overflow-hidden rounded-full bg-gray-200"
              >
                <div className="h-full rounded-full bg-green-600 transition-all duration-700" style={{ width: `${pct}%` }} />
              </div>
            </div>
          )}

          {latest.length > 0 && (
            <ul className="mt-2.5 space-y-1.5">
              {latest.map((o) => {
                const near = nearestPlace(o.location, places)
                return (
                  <li key={o.id} className="animate-[fadeIn_0.4s_ease-out] rounded-lg bg-gray-50 px-2 py-1.5 text-sm">
                    <p className="flex items-center gap-1.5 text-xs text-gray-500">
                      <span className="truncate">
                        {timeAgo(o.capturedAt, now)}
                        {near && <> · near {near.name}</>}
                      </span>
                      <button
                        type="button"
                        onClick={() => map?.flyTo({ center: o.location, zoom: 18, duration: 1000 })}
                        className="ml-auto min-h-7 shrink-0 font-medium text-blue-700 hover:underline"
                      >
                        Show on map
                      </button>
                    </p>
                    <p className="mt-0.5 flex flex-wrap gap-1">
                      {o.labels.map((label) => (
                        <span key={label} className="rounded-full bg-white px-2 py-0.5 text-xs text-gray-800 ring-1 ring-gray-200">
                          {label}
                        </span>
                      ))}
                    </p>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

function timeAgo(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  return m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`
}

// Closest known place within ~150 m, for a human-friendly location.
function nearestPlace([lng, lat]: LngLat, places: Place[]): Place | undefined {
  let best: Place | undefined
  let bestD = Infinity
  for (const p of places) {
    const d = Math.hypot((p.location[0] - lng) * 0.77, p.location[1] - lat) * 111_000
    if (d < bestD) [best, bestD] = [p, d]
  }
  return bestD < 150 ? best : undefined
}
