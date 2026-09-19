import { useMemo } from 'react'
import { Layer, Source } from 'react-map-gl/maplibre'
import type { FeatureCollection } from 'geojson'
import { useTripRoutes } from '../../hooks/useRoutes'
import { CASING, MODE_STYLE } from '../../lib/routes'
import { useLayerStore } from '../../store/useLayerStore'

function endpointsOf(line: FeatureCollection | undefined): FeatureCollection | null {
  const geom = line?.features?.[0]?.geometry
  if (!geom || geom.type !== 'LineString') return null
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { role: 'start' },
        geometry: { type: 'Point', coordinates: geom.coordinates[0] },
      },
      {
        type: 'Feature',
        properties: { role: 'end' },
        geometry: {
          type: 'Point',
          coordinates: geom.coordinates[geom.coordinates.length - 1],
        },
      },
    ],
  }
}

/** One route at a time: the selected trip in the selected mode. */
export default function RouteLayers() {
  const trip = useLayerStore((s) => s.selectedTrip)
  const mode = useLayerStore((s) => s.selectedMode)
  const byMode = useTripRoutes(trip)
  const data = byMode[mode]
  const endpoints = useMemo(() => endpointsOf(data), [data])

  if (!trip || !data) return null
  const { color, width } = MODE_STYLE[mode]

  return (
    <>
      <Source id="route-line" type="geojson" data={data}>
        {/* White casing so the line reads as a route over the pathway network,
            which is itself drawn in green/amber/red. */}
        <Layer
          id="route-casing"
          type="line"
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': CASING, 'line-width': width + 6, 'line-opacity': 0.95 }}
        />
        <Layer
          id="route-line"
          type="line"
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': color, 'line-width': width }}
        />
      </Source>

      {endpoints && (
        <Source id="route-endpoints" type="geojson" data={endpoints}>
          <Layer
            id="route-endpoints"
            type="circle"
            paint={{
              'circle-radius': 7,
              'circle-color': ['match', ['get', 'role'], 'start', '#111827', '#ffffff'],
              'circle-stroke-color': '#111827',
              'circle-stroke-width': 3,
            }}
          />
        </Source>
      )}
    </>
  )
}
