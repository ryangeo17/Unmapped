import type { Route } from '../../types/domain'
import { formatDistance, safetyLevel } from './format'

// "+2 min" / "−70 m" relative to the chosen route.
function diffMinutes(seconds: number) {
  const m = Math.round(seconds / 60)
  return m === 0 ? 'same time' : `${m > 0 ? '+' : '−'}${Math.abs(m)} min`
}
function diffDistance(metres: number) {
  return Math.abs(metres) < 5 ? 'same distance' : `${metres > 0 ? '+' : '−'}${formatDistance(Math.abs(metres))}`
}

// "Why not the other routes?": what Gemini considered and rejected, and why.
export default function Alternatives({ route, alternatives }: { route: Route; alternatives: Route[] }) {
  if (alternatives.length === 0) return null

  return (
    <details className="group rounded-lg border border-gray-200 bg-white">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 font-medium text-gray-900">
        <span aria-hidden="true" className="text-gray-500 transition-transform group-open:rotate-90">
          ▸
        </span>
        Why not the other routes?
        <span className="ml-auto text-sm font-normal text-gray-500">{alternatives.length} considered</span>
      </summary>
      <ul className="divide-y divide-gray-100 border-t border-gray-100">
        {alternatives.map((alt, i) => {
          const safety = alt.safety && safetyLevel(alt.safety.score)
          return (
            <li key={alt.id} className="px-3 py-2.5">
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                <span className="font-semibold text-gray-900">Option {i + 2}</span>
                <span className="text-gray-600">
                  {diffMinutes(alt.durationS - route.durationS)} · {diffDistance(alt.distanceM - route.distanceM)}
                </span>
                {alt.safety && safety && (
                  <span className={`ml-auto rounded-full border px-2 py-0.5 text-xs ${safety.className}`}>
                    🛡️ {safety.label} · {alt.safety.score}
                  </span>
                )}
              </p>
              {alt.rejectedBecause && <p className="mt-1 text-sm text-gray-700">{alt.rejectedBecause}</p>}
            </li>
          )
        })}
      </ul>
    </details>
  )
}
