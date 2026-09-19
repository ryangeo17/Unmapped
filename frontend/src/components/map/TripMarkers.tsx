import { Marker } from 'react-map-gl/maplibre'
import { useTripStore } from '../../store/tripStore'
import type { Place } from '../../types/domain'

// Start and end markers for the chosen places (shown as soon as they're picked).
export default function TripMarkers() {
  const start = useTripStore((s) => s.start)
  const end = useTripStore((s) => s.end)
  return (
    <>
      {start && <TripMarker place={start} letter="A" label="Start" className="bg-green-600" />}
      {end && <TripMarker place={end} letter="B" label="Destination" className="bg-red-600" />}
    </>
  )
}

function TripMarker({ place, letter, label, className }: { place: Place; letter: string; label: string; className: string }) {
  return (
    <Marker longitude={place.location[0]} latitude={place.location[1]} anchor="center">
      <div
        role="img"
        aria-label={`${label}: ${place.name}`}
        title={`${label}: ${place.name}`}
        className={`flex h-8 w-8 items-center justify-center rounded-full border-[3px] border-white text-sm font-bold text-white shadow-md ${className}`}
      >
        {letter}
      </div>
    </Marker>
  )
}
