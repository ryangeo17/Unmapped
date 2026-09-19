import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  PlannerUnreachable,
  planRoute,
  type RouteResult,
} from '../../api/planner'
import { usePlaces } from '../../hooks/usePlaces'
import { useLayerStore } from '../../store/useLayerStore'
import RouteResultPanel from './RouteResult'

export default function RouteForm() {
  const [origin, setOrigin] = useState('Malone Hall')
  const [destination, setDestination] = useState('San Martin Garage')
  const [smarter, setSmarter] = useState(true)
  const setRoute = useLayerStore((s) => s.setRoute)
  const places = usePlaces()

  const plan = useMutation<RouteResult, Error, void>({
    mutationFn: () => planRoute(origin.trim(), destination.trim(), smarter),
    onSuccess: (result) => setRoute(result.status === 'ok' ? result : null),
    onError: () => setRoute(null),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (origin.trim() && destination.trim()) plan.mutate()
  }

  // An ambiguous name comes back with candidates; filling the field from one
  // of them is faster than making the user retype.
  const useCandidate = (field: 'origin' | 'destination', name: string) => {
    if (field === 'origin') setOrigin(name)
    else setDestination(name)
    setTimeout(() => plan.mutate(), 0)
  }

  const field = (
    label: string,
    value: string,
    onChange: (v: string) => void,
  ) => (
    <label className="block">
      <span className="text-xs font-medium text-gray-500">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        list="campus-places"
        required
        className="mt-1 w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm
                   focus:border-blue-500 focus:outline-none"
      />
    </label>
  )

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium text-gray-900">Plan a walk</h2>

      <form onSubmit={submit} className="space-y-3">
        {field('From', origin, setOrigin)}
        {field('To', destination, setDestination)}
        <datalist id="campus-places">
          {(places.data ?? []).map((p) => (
            <option key={p.name} value={p.name} />
          ))}
        </datalist>

        <label className="flex cursor-pointer items-start gap-3">
          <button
            type="button"
            role="switch"
            aria-checked={smarter}
            onClick={() => setSmarter((v) => !v)}
            className={`mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors ${
              smarter ? 'bg-blue-600' : 'bg-gray-300'
            }`}
          >
            <span
              className={`block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                smarter ? 'translate-x-5.5' : 'translate-x-0.5'
              }`}
            />
          </button>
          <span>
            <span className="block text-sm font-medium text-gray-900">
              Smarter planner
            </span>
            <span className="block text-xs text-gray-500">
              {smarter
                ? 'May cut across lawns and use any door or lift'
                : 'Official paved network and signed entrances only'}
            </span>
          </span>
        </label>

        <button
          type="submit"
          disabled={plan.isPending}
          className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white
                     hover:bg-blue-700 disabled:opacity-50"
        >
          {plan.isPending ? 'Planning…' : 'Show route'}
        </button>
      </form>

      {places.isError && places.error instanceof PlannerUnreachable && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {places.error.message}
        </p>
      )}

      {plan.isError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
          {plan.error.message}
        </p>
      )}

      {plan.data && (
        <RouteResultPanel result={plan.data} onPickCandidate={useCandidate} />
      )}
    </section>
  )
}
