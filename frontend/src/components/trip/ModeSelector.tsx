import { useTripStore } from '../../store/tripStore'
import { MODES } from './modes'

export default function ModeSelector() {
  const mode = useTripStore((s) => s.mode)
  const setMode = useTripStore((s) => s.setMode)

  return (
    <fieldset>
      <legend className="mb-1 text-sm font-medium text-gray-700">How are you getting there?</legend>
      <div className="grid grid-cols-5 gap-1">
        {MODES.map((m) => {
          const selected = m.id === mode
          return (
            <button
              key={m.id}
              type="button"
              aria-pressed={selected}
              onClick={() => setMode(m.id)}
              className={`flex min-h-16 flex-col items-center justify-center gap-1 rounded-lg border-2 px-0.5 text-[11px] font-medium whitespace-nowrap ${
                selected ? 'border-blue-600 bg-blue-50 text-blue-800' : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
              }`}
            >
              <span aria-hidden="true" className="text-2xl leading-none">
                {m.icon}
              </span>
              {m.label}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}
