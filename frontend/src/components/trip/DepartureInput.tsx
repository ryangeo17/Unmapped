import { useId } from 'react'
import { useTripStore } from '../../store/tripStore'
import { resolveLeaveAt, timeOfDayAt, toHHMM } from '../../utils/time'

// "Leaving at": Now (default) or a clock time. After dark, routes favour lit paths.
export default function DepartureInput() {
  const id = useId()
  const leaveAt = useTripStore((s) => s.leaveAt)
  const setLeaveAt = useTripStore((s) => s.setLeaveAt)
  const isNow = leaveAt === null
  const night = timeOfDayAt(resolveLeaveAt(leaveAt)) === 'night'

  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-gray-700">
        Leaving at
      </label>
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-pressed={isNow}
          onClick={() => setLeaveAt(null)}
          className={`min-h-11 rounded-lg border-2 px-4 text-sm font-medium ${
            isNow ? 'border-blue-600 bg-blue-50 text-blue-800' : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
          }`}
        >
          Now
        </button>
        <input
          id={id}
          type="time"
          value={leaveAt ?? toHHMM(new Date())}
          onChange={(e) => setLeaveAt(e.target.value || null)}
          className={`min-h-11 flex-1 rounded-lg border-2 bg-white px-3 text-base ${isNow ? 'border-gray-200 text-gray-500' : 'border-blue-600 text-gray-900'}`}
        />
      </div>
      {night && (
        <p className="mt-1 flex items-center gap-1.5 text-sm text-gray-600">
          <span aria-hidden="true">🌙</span> After dark: we'll favour lit paths and emergency phones.
        </p>
      )}
    </div>
  )
}
