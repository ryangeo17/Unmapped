import { Layer, Source } from 'react-map-gl/maplibre'
import type { FeatureCollection } from 'geojson'
import { useCampusData } from '../../hooks/useCampusData'
import { ACCESS_COLORS, SURFACE_COLORS } from '../../lib/campusData'

// Below this the exported surface area shows its rectangular edge.
const SURFACE_MINZOOM = 17

type SourceBlockProps = {
  id: string
  data: FeatureCollection | undefined
  children: React.ReactNode
}

function SourceBlock({ id, data, children }: SourceBlockProps) {
  if (!data) return null
  return (
    <Source id={id} type="geojson" data={data}>
      {children}
    </Source>
  )
}

/**
 * The local campus data drawn over the online basemap.
 *
 * Order matters: surfaces at the bottom, then buildings, then the routing
 * network, then point features. A white scrim sits underneath so the online
 * basemap reads as background rather than competing with the local data.
 *
 * Surface layers only cover the Decker Quad area; the rest of campus shows
 * buildings, pathways and entryways only.
 */
export default function CampusOverlay() {
  const { data } = useCampusData(true)

  return (
    <>
      <Layer
        id="local-scrim"
        type="background"
        paint={{ 'background-color': '#ffffff', 'background-opacity': 0.6 }}
      />

      {/* ---- Surfaces (Decker Quad area) ----
          These only cover one neighbourhood, so below SURFACE_MINZOOM the
          edge of the exported area is visible as a rectangle. Hold them back
          until the viewport is inside it. */}
      <SourceBlock id="src-campus-area" data={data.campusArea}>
        <Layer
          id="campus-area"
          minzoom={SURFACE_MINZOOM}
          type="fill"
          paint={{ 'fill-color': SURFACE_COLORS.campusArea, 'fill-opacity': 0.9 }}
        />
      </SourceBlock>

      <SourceBlock id="src-vegetation" data={data.vegetation}>
        <Layer
          id="vegetation"
          minzoom={SURFACE_MINZOOM}
          type="fill"
          paint={{
            'fill-color': [
              'match',
              ['get', 'class'],
              'Hedgerows', SURFACE_COLORS.vegetationHedgerows,
              'Landscape Beds', SURFACE_COLORS.vegetationLandscapeBeds,
              'Woodland', SURFACE_COLORS.vegetationWoodland,
              SURFACE_COLORS.vegetationApproximate,
            ],
            'fill-opacity': 0.85,
          }}
        />
      </SourceBlock>

      <SourceBlock id="src-road" data={data.roadArea}>
        <Layer
          id="road-area"
          minzoom={SURFACE_MINZOOM}
          type="fill"
          paint={{ 'fill-color': SURFACE_COLORS.road, 'fill-opacity': 0.35 }}
        />
      </SourceBlock>

      <SourceBlock id="src-sidewalk" data={data.sidewalk}>
        <Layer
          id="sidewalk"
          minzoom={SURFACE_MINZOOM}
          type="fill"
          paint={{
            'fill-color': [
              'match',
              ['get', 'class'],
              'Brick Paver', SURFACE_COLORS.sidewalkBrick,
              SURFACE_COLORS.sidewalkOther,
            ],
            'fill-opacity': 0.95,
          }}
        />
      </SourceBlock>

      <SourceBlock id="src-ramp" data={data.sidewalkRamp}>
        <Layer
          id="sidewalk-ramp"
          minzoom={SURFACE_MINZOOM}
          type="fill"
          paint={{ 'fill-color': SURFACE_COLORS.ramp, 'fill-outline-color': '#b45309' }}
        />
      </SourceBlock>

      {/* Stairs get a hard outline: they are the thing that decides a route. */}
      <SourceBlock id="src-stairs" data={data.stairs}>
        <Layer
          id="stairs-fill"
          minzoom={SURFACE_MINZOOM}
          type="fill"
          paint={{ 'fill-color': SURFACE_COLORS.stairs, 'fill-opacity': 0.95 }}
        />
        <Layer
          id="stairs-outline"
          minzoom={SURFACE_MINZOOM}
          type="line"
          paint={{ 'line-color': '#b91c1c', 'line-width': 1.2 }}
        />
      </SourceBlock>

      {/* ---- Named outdoor spaces ---- */}
      <SourceBlock id="src-exterior" data={data.exteriorSpaces}>
        <Layer
          id="exterior-fill"
          type="fill"
          paint={{ 'fill-color': '#84cc16', 'fill-opacity': 0.12 }}
        />
        <Layer
          id="exterior-line"
          type="line"
          paint={{ 'line-color': '#4d7c0f', 'line-width': 1, 'line-dasharray': [3, 2] }}
        />
        <Layer
          id="exterior-label"
          type="symbol"
          layout={{
            'text-field': ['get', 'name'],
            'text-font': ['Noto Sans Regular'],
            'text-size': 11,
            'text-transform': 'uppercase',
            'text-letter-spacing': 0.08,
          }}
          paint={{ 'text-color': '#3f6212', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 }}
        />
      </SourceBlock>

      {/* ---- Buildings ---- */}
      <SourceBlock id="src-facilities" data={data.facilities}>
        <Layer
          id="facilities-fill"
          type="fill"
          paint={{ 'fill-color': '#94a3b8', 'fill-opacity': 0.55 }}
        />
        <Layer
          id="facilities-line"
          type="line"
          paint={{ 'line-color': '#475569', 'line-width': 1 }}
        />
        {/* minScale 2000 on the source layer, which is about z17 here. */}
        <Layer
          id="facilities-label"
          type="symbol"
          minzoom={16}
          layout={{
            'text-field': ['get', 'name'],
            'text-font': ['Noto Sans Regular'],
            'text-size': 11,
            'text-max-width': 8,
          }}
          paint={{ 'text-color': '#1e293b', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 }}
        />
      </SourceBlock>

      {/* ---- Routing network, coloured by official accessibility grade ---- */}
      <SourceBlock id="src-pathways" data={data.pathways}>
        <Layer
          id="pathways"
          type="line"
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{
            'line-color': [
              'match',
              ['get', 'ihcd2021routesurveycode'],
              'FullyCompliant', ACCESS_COLORS.FullyCompliant,
              'PartiallyCompliant', ACCESS_COLORS.PartiallyCompliant,
              'NonCompliant', ACCESS_COLORS.NonCompliant,
              ACCESS_COLORS.Other,
            ],
            'line-width': ['interpolate', ['linear'], ['zoom'], 14, 0.8, 18, 3],
            'line-opacity': 0.9,
          }}
        />
        {/* Stair segments carry riser counts; mark them separately. */}
        <Layer
          id="pathways-stairs"
          type="line"
          filter={['==', ['get', 'pathway_type'], 2]}
          layout={{ 'line-cap': 'butt' }}
          paint={{
            'line-color': '#7f1d1d',
            'line-width': ['interpolate', ['linear'], ['zoom'], 14, 1.5, 18, 5],
            'line-dasharray': [1, 1],
          }}
        />
      </SourceBlock>

      {/* ---- Construction closures ---- */}
      <SourceBlock id="src-barriers" data={data.barriers}>
        <Layer
          id="barriers-fill"
          type="fill"
          paint={{ 'fill-color': '#ef4444', 'fill-opacity': 0.22 }}
        />
        <Layer
          id="barriers-line"
          type="line"
          paint={{ 'line-color': '#b91c1c', 'line-width': 1.5, 'line-dasharray': [2, 1] }}
        />
      </SourceBlock>

      {/* ---- Points ---- */}
      <SourceBlock id="src-elevators" data={data.elevators}>
        <Layer
          id="elevators"
          type="circle"
          paint={{
            'circle-radius': 4,
            'circle-color': '#7c3aed',
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.5,
          }}
        />
      </SourceBlock>

      <SourceBlock id="src-landmarks" data={data.landmarks}>
        <Layer
          id="landmarks"
          type="circle"
          paint={{
            'circle-radius': 4,
            'circle-color': '#0ea5e9',
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.5,
          }}
        />
      </SourceBlock>

      {/* Entryways last: accessible vs not is the headline of this data. */}
      <SourceBlock id="src-entryways" data={data.entryways}>
        <Layer
          id="entryways"
          type="circle"
          paint={{
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 14, 3, 18, 6],
            'circle-color': [
              'match',
              ['get', 'accessible_entrance'],
              'Y', '#2563eb',
              '#64748b',
            ],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 1.5,
          }}
        />
      </SourceBlock>
    </>
  )
}
