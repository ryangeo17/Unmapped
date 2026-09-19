import { useEffect, useState } from 'react'

const STAGE_MS = 1000

// Staged progress while a route request runs (Gemini makes it slow), so the
// wait looks intentional. Advances every second and stays on the last stage.
export default function LoadingStages({ night }: { night: boolean }) {
  const stages = [
    'Finding paths',
    'Checking accessibility',
    ...(night ? ['Checking lighting and safety'] : []),
    'Choosing the best route',
  ]
  const [current, setCurrent] = useState(0)

  useEffect(() => {
    if (current >= stages.length - 1) return
    const timer = setTimeout(() => setCurrent((c) => c + 1), STAGE_MS)
    return () => clearTimeout(timer)
  }, [current, stages.length])

  return (
    <div role="status" className="rounded-lg border border-blue-100 bg-blue-50/60 p-4">
      <p className="sr-only">{stages[current]}…</p>
      <ol aria-hidden="true" className="space-y-2">
        {stages.map((label, i) => (
          <li key={label} className={`flex items-center gap-2.5 text-sm ${i > current ? 'text-gray-400' : 'text-gray-800'}`}>
            {i < current ? (
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-xs text-white">✓</span>
            ) : i === current ? (
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
            ) : (
              <span className="h-5 w-5 rounded-full border-2 border-gray-300" />
            )}
            <span className={i === current ? 'font-medium' : ''}>
              {label}
              {i === current && '…'}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
