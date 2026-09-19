import { useState } from 'react'
import Map, { NavigationControl, Popup, type MapLayerMouseEvent } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useTripStore, type TripField } from '../../store/tripStore'
import type { LngLat, Place } from '../../types/domain'
import CompareLayer from './CompareLayer'
import RobotMarker from './RobotMarker'
import RouteLayer from './RouteLayer'
import TripMarkers from './TripMarkers'

const STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty'

// Homewood campus centre, [lng, lat].
const CAMPUS_CENTER: [number, number] = [-76.6205, 39.329]

// Keep panning near campus: [west, south, east, north].
const CAMPUS_BOUNDS: [number, number, number, number] = [
  CAMPUS_CENTER[0] - 0.01,
  CAMPUS_CENTER[1] - 0.01,
  CAMPUS_CENTER[0] + 0.01,
  CAMPUS_CENTER[1] + 0.01,
]

function droppedPin([lng, lat]: LngLat): Place {
  return { id: `pin-${lng.toFixed(6)},${lat.toFixed(6)}`, name: 'Dropped pin', location: [lng, lat] }
}

export default function MapView() {
  const pinning = useTripStore((s) => s.pinTarget !== null && s[s.pinTarget] === null)
  const compareMode = useTripStore((s) => s.compareMode)
  const [menuAt, setMenuAt] = useState<LngLat | null>(null)

  // Clicking the map: if an empty search box was just focused, fill it directly;
  // otherwise offer "Start here" / "Go here" in a popup.
  function onClick(e: MapLayerMouseEvent) {
    const point: LngLat = [e.lngLat.lng, e.lngLat.lat]
    const state = useTripStore.getState()
    if (state.pinTarget && state[state.pinTarget] === null) {
      state.setPlace(state.pinTarget, droppedPin(point))
      setMenuAt(null)
      return
    }
    setMenuAt(point)
  }

  function choose(field: TripField) {
    if (!menuAt) return
    useTripStore.getState().setPlace(field, droppedPin(menuAt))
    setMenuAt(null)
  }

  return (
    <Map
      id="main"
      initialViewState={{
        longitude: CAMPUS_CENTER[0],
        latitude: CAMPUS_CENTER[1],
        zoom: 16,
      }}
      maxBounds={CAMPUS_BOUNDS}
      mapStyle={STYLE_URL}
      style={{ width: '100%', height: '100%' }}
      cursor={pinning ? 'crosshair' : undefined}
      onClick={onClick}
    >
      <NavigationControl position="top-right" />
      {compareMode ? <CompareLayer /> : <RouteLayer />}
      <TripMarkers />
      <RobotMarker />
      {menuAt && (
        <Popup
          longitude={menuAt[0]}
          latitude={menuAt[1]}
          anchor="bottom"
          offset={8}
          closeOnClick={false}
          onClose={() => setMenuAt(null)}
        >
          <div className="flex flex-col gap-1 pt-3" onKeyDown={(e) => e.key === 'Escape' && setMenuAt(null)}>
            <button
              type="button"
              autoFocus
              onClick={() => choose('start')}
              className="flex min-h-10 items-center gap-2 rounded-md px-3 text-left text-sm font-medium hover:bg-gray-100"
            >
              <span aria-hidden="true" className="flex h-5 w-5 items-center justify-center rounded-full bg-green-600 text-[11px] font-bold text-white">A</span>
              Start here
            </button>
            <button
              type="button"
              onClick={() => choose('end')}
              className="flex min-h-10 items-center gap-2 rounded-md px-3 text-left text-sm font-medium hover:bg-gray-100"
            >
              <span aria-hidden="true" className="flex h-5 w-5 items-center justify-center rounded-full bg-red-600 text-[11px] font-bold text-white">B</span>
              Go here
            </button>
          </div>
        </Popup>
      )}
    </Map>
  )
}
