import { MapProvider } from 'react-map-gl/maplibre'
import MapView from './components/map/MapView'

function App() {
  return (
    <MapProvider>
      <div className="flex h-screen overflow-hidden">
        <aside className="w-[380px] shrink-0 overflow-y-auto border-r border-gray-200 bg-white p-4">
          <h1 className="text-2xl font-bold text-blue-600">Unmapped</h1>
        </aside>
        <main className="relative flex-1">
          <MapView />
        </main>
      </div>
    </MapProvider>
  )
}

export default App
