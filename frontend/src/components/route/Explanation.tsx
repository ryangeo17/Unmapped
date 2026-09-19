import type { RouteResult } from '../../types/domain'

export default function Explanation({ result }: { result: RouteResult }) {
  return (
    <section aria-labelledby="why-heading" className="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50 to-blue-50 p-4">
      <h2 id="why-heading" className="flex items-center gap-2 text-base font-semibold text-violet-900">
        <span aria-hidden="true">✨</span> Why this route
      </h2>
      <p className="mt-2 leading-relaxed text-gray-800">{result.explanation}</p>
      {result.tradeoffs && result.tradeoffs.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-gray-700">
          {result.tradeoffs.map((t) => (
            <li key={t} className="flex gap-2">
              <span aria-hidden="true" className="text-violet-500">•</span>
              {t}
            </li>
          ))}
        </ul>
      )}
      {result.fallbackUsed ? (
        <p className="mt-3 flex items-center gap-1.5 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
          <span aria-hidden="true">ⓘ</span> Basic route (AI reasoning unavailable right now)
        </p>
      ) : (
        <p className="mt-3 text-xs text-violet-700">Reasoning by Gemini, from data mapped by our robot.</p>
      )}
    </section>
  )
}
