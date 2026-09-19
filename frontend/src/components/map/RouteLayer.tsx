import { useEffect } from 'react'
import { Layer, Source, useMap } from 'react-map-gl/maplibre'
import { useRoute } from '../../hooks/useRoute'
import { useTripStore } from '../../store/tripStore'
import { bounds } from '../../utils/geo'
import { ALTERNATIVE_STYLE, CONDITIONS, CONDITION_STYLE, segmentFeatures } from './segmentStyles'

const LINE_WIDTH = 6

// Draws the chosen route, colour- and pattern-coded by segment condition, and
// zooms the map to fit it when a new one arrives.
export default function RouteLayer() {
  const { data: result } = useRoute()
  const night = useTripStore((s) => s.submittedRequest?.timeOfDay === 'night')
  const { current: map } = useMap()
  const route = result?.route
  const geometry = route?.geometry

  useEffect(() => {
    if (!map || !geometry || geometry.length < 2) return
    map.fitBounds(bounds([geometry]), { padding: 80, duration: 800 })
  }, [map, geometry])

  if (!route || !geometry) return null

  const line = { type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: geometry } }
  const alternatives = {
    type: 'FeatureCollection' as const,
    features: (result?.alternatives ?? []).map((alt) => ({
      type: 'Feature' as const,
      properties: { id: alt.id },
      geometry: { type: 'LineString' as const, coordinates: alt.geometry },
    })),
  }

  return (
    <>
      <Source id="route" type="geojson" data={line}>
        <Layer id="route-casing" type="line" layout={{ 'line-cap': 'round', 'line-join': 'round' }} paint={{ 'line-color': '#ffffff', 'line-width': LINE_WIDTH + 5 }} />
        {/* No segment data from the backend: fall back to a plain line. */}
        {!route.segments?.length && (
          <Layer id="route-line" type="line" layout={{ 'line-cap': 'round', 'line-join': 'round' }} paint={{ 'line-color': CONDITION_STYLE.smooth.color, 'line-width': LINE_WIDTH }} />
        )}
      </Source>
      {!!route.segments?.length && (
        <Source id="route-segments" type="geojson" data={segmentFeatures(route, night)}>
          {CONDITIONS.map((c) => {
            const style = CONDITION_STYLE[c]
            return (
              <Layer
                key={c}
                id={`route-seg-${c}`}
                type="line"
                filter={['==', ['get', 'condition'], c]}
                layout={{ 'line-cap': style.round || !style.dash ? 'round' : 'butt', 'line-join': 'round' }}
                paint={{
                  'line-color': style.color,
                  'line-width': LINE_WIDTH,
                  ...(style.dash && { 'line-dasharray': style.dash }),
                }}
              />
            )
          })}
        </Source>
      )}
      {/* Rendered after the route but inserted below it (beforeId), so it always sits underneath. */}
      <Source id="route-alternatives" type="geojson" data={alternatives}>
        <Layer
          id="route-alternatives"
          type="line"
          beforeId="route-casing"
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': ALTERNATIVE_STYLE.color, 'line-width': ALTERNATIVE_STYLE.width, 'line-opacity': ALTERNATIVE_STYLE.opacity }}
        />
      </Source>
    </>
  )
}
