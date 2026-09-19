import { useTripStore } from '../../store/tripStore'

// "Compare all modes" switch.
export default function CompareToggle() {
  const compareMode = useTripStore((s) => s.compareMode)
  const setCompareMode = useTripStore((s) => s.setCompareMode)
  return (
    <button
      type="button"
      role="switch"
      aria-checked={compareMode}
      onClick={() => setCompareMode(!compareMode)}
      className="flex min-h-11 items-center gap-3 rounded-lg px-1 text-left"
    >
      <span className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${compareMode ? 'bg-blue-600' : 'bg-gray-300'}`}>
        <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${compareMode ? 'translate-x-5' : ''}`} />
      </span>
      <span>
        <span className="block text-sm font-medium text-gray-900">Compare all modes</span>
        <span className="block text-xs text-gray-500">See every way to get there, side by side</span>
      </span>
    </button>
  )
}
