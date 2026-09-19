import { useRoute } from '../../hooks/useRoute'
import { useTripStore } from '../../store/tripStore'
import { ALTERNATIVE_STYLE, CONDITIONS, CONDITION_STYLE, segmentCondition } from './segmentStyles'

const SWATCH_WIDTH = 4

// Bottom-left map key: one entry per condition that appears on the current route.
export default function Legend() {
  const { data: result } = useRoute()
  const night = useTripStore((s) => s.submittedRequest?.timeOfDay === 'night')
  const segments = result?.route.segments ?? []
  const hasAlternatives = (result?.alternatives.length ?? 0) > 0
  if (segments.length === 0 && !hasAlternatives) return null

  const present = new Set(segments.map((s) => segmentCondition(s, night)))
  const shown = CONDITIONS.filter((c) => present.has(c))

  return (
    <section aria-label="Map legend" className="absolute bottom-8 left-3 z-10 rounded-lg bg-white/95 p-3 text-sm shadow-md">
      <h2 className="mb-1.5 text-xs font-semibold tracking-wide text-gray-500 uppercase">Along this route</h2>
      <ul className="space-y-1">
        {shown.map((c) => {
          const style = CONDITION_STYLE[c]
          return (
            <li key={c} className="flex items-center gap-2">
              <svg width="36" height="10" aria-hidden="true" className="shrink-0">
                <line
                  x1={SWATCH_WIDTH / 2}
                  y1="5"
                  x2={36 - SWATCH_WIDTH / 2}
                  y2="5"
                  stroke={style.color}
                  strokeWidth={SWATCH_WIDTH}
                  strokeLinecap={style.round || !style.dash ? 'round' : 'butt'}
                  strokeDasharray={style.dash?.map((d) => d * SWATCH_WIDTH).join(' ')}
                />
              </svg>
              <span aria-hidden="true" className="w-5 text-center">
                {style.icon}
              </span>
              <span className="text-gray-800">{style.label}</span>
            </li>
          )
        })}
        {hasAlternatives && (
          <li className="flex items-center gap-2">
            <svg width="36" height="10" aria-hidden="true" className="shrink-0">
              <line x1="2" y1="5" x2="34" y2="5" stroke={ALTERNATIVE_STYLE.color} strokeOpacity={ALTERNATIVE_STYLE.opacity} strokeWidth={ALTERNATIVE_STYLE.width} strokeLinecap="round" />
            </svg>
            <span className="w-5" aria-hidden="true" />
            <span className="text-gray-800">{ALTERNATIVE_STYLE.label}</span>
          </li>
        )}
      </ul>
    </section>
  )
}
