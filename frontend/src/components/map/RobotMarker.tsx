import { Marker } from 'react-map-gl/maplibre'
import { useObservations } from '../../hooks/useRobot'

// The robot's latest known position (its newest observation).
export default function RobotMarker() {
  const { data } = useObservations()
  const latest = data?.[0]
  if (!latest) return null
  return (
    <Marker longitude={latest.location[0]} latitude={latest.location[1]} anchor="center">
      <div
        role="img"
        aria-label="Robot's latest position"
        title="Robot's latest position"
        className="flex h-9 w-9 items-center justify-center rounded-full border-[3px] border-green-600 bg-white text-lg shadow-md transition-all"
      >
        🤖
      </div>
    </Marker>
  )
}
