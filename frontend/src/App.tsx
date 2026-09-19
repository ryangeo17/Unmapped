import { MapProvider } from 'react-map-gl/maplibre'
import MapView from './components/map/MapView'
import RoutePanel from './components/route/RoutePanel'
import TripPanel from './components/trip/TripPanel'

function App() {
  return (
    <MapProvider>
      <div className="flex h-screen overflow-hidden">
        <aside className="flex w-[380px] shrink-0 flex-col gap-4 overflow-y-auto border-r border-gray-200 bg-white p-4">
          <h1 className="text-2xl font-bold text-blue-600">Unmapped</h1>
          <TripPanel />
          <RoutePanel />
        </aside>
        <main className="relative flex-1">
          <MapView />
        </main>
      </div>
    </MapProvider>
  )
}

export default App
