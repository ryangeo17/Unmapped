import { useEffect } from 'react'
import { Layer, Source, useMap } from 'react-map-gl/maplibre'
import { useRoute } from '../../hooks/useRoute'
import type { LngLat } from '../../types/domain'

// Draws the chosen route and zooms the map to fit it when a new one arrives.
export default function RouteLayer() {
  const { data: result } = useRoute()
  const { current: map } = useMap()
  const geometry = result?.route.geometry

  useEffect(() => {
    if (!map || !geometry || geometry.length < 2) return
    map.fitBounds(bounds(geometry), { padding: 80, duration: 800 })
  }, [map, geometry])

  if (!geometry) return null

  return (
    <Source id="route" type="geojson" data={{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: geometry } }}>
      <Layer id="route-casing" type="line" layout={{ 'line-cap': 'round', 'line-join': 'round' }} paint={{ 'line-color': '#ffffff', 'line-width': 10 }} />
      <Layer id="route-line" type="line" layout={{ 'line-cap': 'round', 'line-join': 'round' }} paint={{ 'line-color': '#2563eb', 'line-width': 6 }} />
    </Source>
  )
}

function bounds(line: LngLat[]): [LngLat, LngLat] {
  const lngs = line.map((p) => p[0])
  const lats = line.map((p) => p[1])
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ]
}
