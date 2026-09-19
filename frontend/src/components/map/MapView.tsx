import Map, { NavigationControl } from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useLayerStore } from '../../store/useLayerStore'
import CampusOverlay from './CampusOverlay'

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

export default function MapView() {
  const showLocalData = useLayerStore((s) => s.showLocalData)

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
    >
      <NavigationControl position="top-right" />
      {showLocalData && <CampusOverlay />}
    </Map>
  )
}
