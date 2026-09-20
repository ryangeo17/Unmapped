import { useMemo } from 'react'
import { Layer, Source } from 'react-map-gl/maplibre'
import type { FeatureCollection } from 'geojson'
import { useLayerStore } from '../../store/useLayerStore'

// Outside the green/amber/red the Pathways layer uses for accessibility
// grading, so the route still reads as a route over the campus data.
export const ROUTE_COLOR = '#db2777'
const WIDTH = 5

export default function RouteLayers() {
  const route = useLayerStore((s) => s.route)

  const line = useMemo<FeatureCollection | null>(
    () =>
      route && {
        type: 'FeatureCollection',
        features: [{ type: 'Feature', properties: {}, geometry: route.geometry }],
      },
    [route],
  )

  const endpoints = useMemo<FeatureCollection | null>(() => {
    if (!route) return null
    const coords = route.geometry.coordinates
    return {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: { role: 'start' },
          geometry: { type: 'Point', coordinates: coords[0] },
        },
        {
          type: 'Feature',
          properties: { role: 'end' },
          geometry: { type: 'Point', coordinates: coords[coords.length - 1] },
        },
      ],
    }
  }, [route])

  if (!line || !endpoints) return null

  return (
    <>
      <Source id="route-line" type="geojson" data={line}>
        {/* White casing so the line reads as a route over the pathway network,
            which is itself drawn in green/amber/red. */}
        <Layer
          id="route-casing"
          type="line"
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': '#ffffff', 'line-width': WIDTH + 6, 'line-opacity': 0.95 }}
        />
        <Layer
          id="route-line"
          type="line"
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': ROUTE_COLOR, 'line-width': WIDTH }}
        />
      </Source>

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
    </>
  )
}
