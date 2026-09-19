import { useIsFetching } from '@tanstack/react-query'
import { useTripStore } from '../../store/tripStore'
import CompareToggle from './CompareToggle'
import ModeSelector from './ModeSelector'
import PreferenceInput from './PreferenceInput'
import SearchBox from './SearchBox'
import DepartureInput from './DepartureInput'

export default function TripPanel() {
  const start = useTripStore((s) => s.start)
  const end = useTripStore((s) => s.end)
  const swapPlaces = useTripStore((s) => s.swapPlaces)
  const submitRoute = useTripStore((s) => s.submitRoute)
  const ready = start !== null && end !== null
  const compareMode = useTripStore((s) => s.compareMode)
  const isFetching = useIsFetching({ queryKey: ['route'] }) > 0

  return (
    <form
      aria-label="Plan a trip"
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (ready && !isFetching) submitRoute()
      }}
    >
      <div className="flex flex-col gap-2">
        <SearchBox field="start" label="From" placeholder="Search campus or use my location" />
        <div className="-my-1 flex justify-end">
          <button
            type="button"
            onClick={swapPlaces}
            aria-label="Swap From and To"
            className="flex min-h-9 items-center gap-1 rounded-md px-2 text-sm text-gray-600 hover:bg-gray-100"
          >
            <span aria-hidden="true">⇅</span> Swap
          </button>
        </div>
        <SearchBox field="end" label="To" placeholder="Where are you headed?" />
      </div>

      {compareMode ? (
        <p className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-900">Comparing all 5 ways of getting there.</p>
      ) : (
        <ModeSelector />
      )}
      <CompareToggle />
      <DepartureInput />
      <PreferenceInput />

      <button
        type="submit"
        disabled={!ready || isFetching}
        className="min-h-12 rounded-lg bg-blue-600 text-base font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-gray-600"
      >
        {isFetching ? 'Finding route…' : compareMode ? 'Compare routes' : 'Find route'}
      </button>
      {!ready && <p className="-mt-2 text-center text-sm text-gray-500">Choose where you're starting and where you're going.</p>}
    </form>
  )
}
