import type { Route } from '../../types/domain'
import { arrivalTime, formatClock } from '../../utils/time'
import { formatDistance, formatDuration, routeFacts } from './format'

const toneClass = {
  good: 'border-green-200 bg-green-50 text-green-800',
  warn: 'border-amber-200 bg-amber-50 text-amber-900',
  neutral: 'border-gray-200 bg-gray-50 text-gray-800',
}

export default function RouteSummary({ route, departAt }: { route: Route; departAt?: string }) {
  const facts = routeFacts(route)
  const leave = departAt ? new Date(departAt) : null
  const arrive = leave ? arrivalTime(leave, route.durationS) : null
  return (
    <section aria-label="Route summary">
      <p className="flex items-baseline gap-2">
        <span className="text-3xl font-bold text-gray-900">{formatDuration(route.durationS)}</span>
        <span className="text-lg text-gray-600">· {formatDistance(route.distanceM)}</span>
      </p>
      {leave && arrive && (
        <p className="mt-0.5 text-gray-700">
          Leave {formatClock(leave)} → <span className="font-semibold text-gray-900">Arrive {formatClock(arrive)}</span>
        </p>
      )}
      {facts.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {facts.map((f) => (
            <li key={f.text} className={`flex items-center gap-1 rounded-full border px-2.5 py-1 text-sm ${toneClass[f.tone]}`}>
              <span aria-hidden="true">{f.icon}</span>
              {f.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
