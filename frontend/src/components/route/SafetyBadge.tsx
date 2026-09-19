import type { Safety } from '../../types/domain'
import { safetyLevel } from './format'

// Personal safety (lighting, visibility, security nearby). The word label and
// score carry the meaning; colour is only a hint.
export default function SafetyBadge({ safety }: { safety: Safety }) {
  const level = safetyLevel(safety.score)
  return (
    <section aria-label="Safety" className={`rounded-lg border p-3 ${level.className}`}>
      <p className="flex items-center gap-2 font-semibold">
        <span aria-hidden="true">🛡️</span>
        Safety: {level.label}
        <span className="ml-auto text-sm font-normal">{safety.score}/100</span>
      </p>
      {safety.factors.length > 0 && (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-6 text-sm">
          {safety.factors.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
