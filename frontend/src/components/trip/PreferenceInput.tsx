import { useId } from 'react'
import { useTripStore } from '../../store/tripStore'

export default function PreferenceInput() {
  const id = useId()
  const preferences = useTripStore((s) => s.preferences)
  const setPreferences = useTripStore((s) => s.setPreferences)

  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-gray-700">
        Anything we should know? <span className="font-normal text-gray-500">(optional)</span>
      </label>
      <textarea
        id={id}
        rows={2}
        value={preferences}
        onChange={(e) => setPreferences(e.target.value)}
        placeholder="e.g. on crutches today, avoid hills"
        className="w-full resize-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-base placeholder:text-gray-400"
      />
    </div>
  )
}
