import { useEffect, useRef } from 'react'
import { Layer, Marker, Source, useMap } from 'react-map-gl/maplibre'
import { useCompareRoutes } from '../../hooks/useCompareRoutes'
import { useTripStore } from '../../store/tripStore'
import { bounds, pointAlong } from '../../utils/geo'

const LINE_WIDTH = 5

// Compare mode: every mode's route at once, each with its own colour, dash and offset.
export default function CompareLayer() {
  const compareMode = useTripStore((s) => s.compareMode)
  const routes = useCompareRoutes()
  const { current: map } = useMap()

  const loaded = routes.filter((r) => r.query.data).map((r) => ({ mode: r.mode, route: r.query.data!.route }))
  const allSettled = routes.every((r) => !r.query.isFetching)
  const fitKey = allSettled ? loaded.map((l) => l.route.id).join() : ''
  const linesRef = useRef(loaded.map((l) => l.route.geometry))
  useEffect(() => {
    linesRef.current = loaded.map((l) => l.route.geometry)
  })

  // Frame all routes once they have all arrived (re-fits only when the set of routes changes).
  useEffect(() => {
    if (!map || !compareMode || !fitKey) return
    const lines = linesRef.current
    if (lines.length) map.fitBounds(bounds(lines), { padding: 90, duration: 800 })
  }, [map, compareMode, fitKey])

  if (!compareMode) return null

  return (
    <>
      {loaded.map(({ mode, route }) => (
        <Source key={mode.id} id={`compare-${mode.id}`} type="geojson" data={{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: route.geometry } }}>
          <Layer
            id={`compare-${mode.id}-casing`}
            type="line"
            layout={{ 'line-cap': 'round', 'line-join': 'round' }}
            paint={{ 'line-color': '#ffffff', 'line-width': LINE_WIDTH + 3, 'line-offset': mode.offset }}
          />
          <Layer
            id={`compare-${mode.id}-line`}
            type="line"
            layout={{ 'line-cap': mode.dash ? 'butt' : 'round', 'line-join': 'round' }}
            paint={{
              'line-color': mode.color,
              'line-width': LINE_WIDTH,
              'line-offset': mode.offset,
              ...(mode.dash && { 'line-dasharray': mode.dash }),
            }}
          />
        </Source>
      ))}
      {loaded.map(({ mode, route }) => {
        const [lng, lat] = pointAlong(route.geometry, mode.markerAt)
        return (
          <Marker key={mode.id} longitude={lng} latitude={lat} anchor="center">
            <div
              role="img"
              aria-label={`${mode.label} route`}
              className="flex h-8 w-8 items-center justify-center rounded-full border-[3px] bg-white text-base shadow-md"
              style={{ borderColor: mode.color }}
            >
              {mode.icon}
            </div>
          </Marker>
        )
      })}
    </>
  )
}
