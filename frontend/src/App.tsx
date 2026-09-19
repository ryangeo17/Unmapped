import { MapProvider } from 'react-map-gl/maplibre'
import Legend from './components/map/Legend'
import MapView from './components/map/MapView'
import CompareCards from './components/route/CompareCards'
import RoutePanel from './components/route/RoutePanel'
import RobotActivity from './components/robot/RobotActivity'
import TripPanel from './components/trip/TripPanel'
import { useTripStore } from './store/tripStore'

function App() {
  const compareMode = useTripStore((s) => s.compareMode)
  return (
    <MapProvider>
      <div className="flex h-screen overflow-hidden">
        <aside className="flex w-[380px] shrink-0 flex-col gap-4 overflow-y-auto border-r border-gray-200 bg-white p-4">
          <h1 className="text-2xl font-bold text-blue-600">Unmapped</h1>
          <TripPanel />
          {compareMode ? <CompareCards /> : <RoutePanel />}
        </aside>
        <main className="relative flex-1">
          <MapView />
          <RobotActivity />
          {!compareMode && <Legend />}
        </main>
      </div>
    </MapProvider>
  )
}

export default App
