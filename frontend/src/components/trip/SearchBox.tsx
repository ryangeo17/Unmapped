import { useId, useState } from 'react'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { usePlaces } from '../../hooks/usePlaces'
import { useTripStore, type TripField } from '../../store/tripStore'
import type { Place } from '../../types/domain'

type Option = { kind: 'my-location' } | { kind: 'place'; place: Place }

interface Props {
  field: TripField
  label: string
  placeholder: string
}

// An accessible combobox: type to search campus places, pick with mouse or
// arrow keys + Enter. The From box also offers "Use my location".
export default function SearchBox({ field, label, placeholder }: Props) {
  const id = useId()
  const listId = `${id}-list`
  const place = useTripStore((s) => s[field])
  const setPlace = useTripStore((s) => s.setPlace)
  const setPinTarget = useTripStore((s) => s.setPinTarget)
  const showPinHint = useTripStore((s) => s.pinTarget === field && s[field] === null)

  // `draft` is what the user is typing; null means "show the chosen place's name".
  const [draft, setDraft] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [geoStatus, setGeoStatus] = useState<'idle' | 'locating' | 'error'>('idle')

  const query = useDebouncedValue((draft ?? '').trim(), 250)
  const { data: results = [], isFetching, isError } = usePlaces(query, open)

  const options: Option[] = [
    ...(field === 'start' && 'geolocation' in navigator ? [{ kind: 'my-location' } as const] : []),
    ...results.map((p) => ({ kind: 'place', place: p }) as const),
  ]

  function choose(option: Option) {
    setOpen(false)
    setActiveIndex(-1)
    setDraft(null)
    if (option.kind === 'place') {
      setPlace(field, option.place)
      return
    }
    setGeoStatus('locating')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeoStatus('idle')
        setPlace(field, { id: 'my-location', name: 'My location', location: [pos.coords.longitude, pos.coords.latitude] })
      },
      () => setGeoStatus('error'),
      { timeout: 10_000 },
    )
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActiveIndex((i) => Math.min(i + 1, options.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && open && options[activeIndex]) {
      e.preventDefault()
      choose(options[activeIndex])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const optionId = (i: number) => `${id}-opt-${i}`
  const value = draft ?? place?.name ?? ''

  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-gray-700">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && activeIndex >= 0 ? optionId(activeIndex) : undefined}
          autoComplete="off"
          placeholder={placeholder}
          value={value}
          onChange={(e) => {
            setDraft(e.target.value)
            setOpen(true)
            setActiveIndex(-1)
            if (place) setPlace(field, null)
          }}
          onFocus={() => {
            setOpen(true)
            setPinTarget(field)
          }}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
          className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 pr-10 text-base placeholder:text-gray-400"
        />
        {value && (
          <button
            type="button"
            aria-label={`Clear ${label}`}
            onClick={() => {
              setDraft(null)
              setPlace(field, null)
            }}
            className="absolute top-1/2 right-1 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100"
          >
            ✕
          </button>
        )}
      </div>

      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label={`${label} suggestions`}
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
        >
          {options.map((option, i) => (
            <li
              key={option.kind === 'place' ? option.place.id : 'my-location'}
              id={optionId(i)}
              role="option"
              aria-selected={i === activeIndex}
              // mousedown (not click) so the input doesn't blur and close the list first
              onMouseDown={(e) => {
                e.preventDefault()
                choose(option)
              }}
              onMouseEnter={() => setActiveIndex(i)}
              className={`flex min-h-11 cursor-pointer items-center gap-2 px-3 ${i === activeIndex ? 'bg-blue-50' : ''}`}
            >
              {option.kind === 'my-location' ? (
                <span className="font-medium text-blue-700">📍 Use my location</span>
              ) : (
                <>
                  <span>{option.place.name}</span>
                  {option.place.category && <span className="ml-auto text-xs text-gray-500">{option.place.category}</span>}
                </>
              )}
            </li>
          ))}
          {results.length === 0 && (
            <li className="px-3 py-2 text-sm text-gray-500">
              {isError ? "Couldn't load places." : isFetching ? 'Searching…' : 'No matching places.'}
            </li>
          )}
        </ul>
      )}

      {geoStatus === 'locating' && <p className="mt-1 text-sm text-gray-600">Finding your location…</p>}
      {geoStatus === 'error' && <p className="mt-1 text-sm text-red-700">Couldn't get your location. Search for a place instead.</p>}
      {showPinHint && !open && <p className="mt-1 text-sm text-gray-500">Or click the map to drop a pin here.</p>}
    </div>
  )
}
