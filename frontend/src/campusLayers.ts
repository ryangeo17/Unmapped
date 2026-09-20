/**
 * JHU's published campus data, drawn under the route.
 *
 * The backend routes over this same survey; these layers are what it looks
 * like. Building footprints, the pathway network coloured by the university's
 * own accessibility grade, every entrance coloured by whether it is step-free,
 * the construction closures, and — around Decker Quad, the only area exported
 * so far — the paving, stairs, ramps and planting decoded from the campus
 * basemap tiles.
 *
 * Colours for the surface layers are lifted from JHU's own basemap style, so
 * the result reads like the official map rather than an arbitrary recolour.
 */
import type mapboxgl from 'mapbox-gl'

export const CAMPUS_FILES = {
  facilities: '/data/Facilities.geojson',
  exterior: '/data/Exterior_Spaces.geojson',
  pathways: '/data/Pathways.geojson',
  entryways: '/data/Entryways-All.geojson',
  barriers: '/data/Polygon_Barriers.geojson',
  sidewalk: '/data/surfaces/Sidewalk.geojson',
  vegetation: '/data/surfaces/Vegetation.geojson',
  stairs: '/data/surfaces/Stairs.geojson',
  ramp: '/data/surfaces/Sidewalk_Ramp.geojson',
  road: '/data/surfaces/Road_Area.geojson',
} as const

export type CampusLayerId = keyof typeof CAMPUS_FILES

// The four values of ihcd2021routesurveycode, JHU's 2021 accessibility survey.
export const GRADE_COLORS = {
  FullyCompliant: '#16a34a',
  PartiallyCompliant: '#eab308',
  NonCompliant: '#dc2626',
  Other: '#94a3b8',
} as const

const SURFACE = {
  hedgerows: '#89CD66',
  landscapeBeds: '#D3FFBE',
  woodland: '#B4D79E',
  vegetation: '#C6E2B2',
  road: '#828282',
  sidewalkBrick: '#D7B09E',
  sidewalkOther: '#FFEBBE',
  stairs: '#D7C29E',
  ramp: '#FFDBBE',
}

const EMPTY = { type: 'FeatureCollection' as const, features: [] }

type LayerSpec = mapboxgl.AnyLayer & { slot?: string }

/**
 * Surfaces only cover the Decker Quad neighbourhood. Below this zoom the edge
 * of the exported area is on screen and reads as a rendering fault rather than
 * as scope.
 */
const SURFACE_MINZOOM = 17

export const CAMPUS_LAYERS: LayerSpec[] = [
  // --- surfaces, Decker Quad area only -------------------------------------
  {
    id: 'campus-road', type: 'fill', source: 'campus-road', slot: 'bottom',
    minzoom: SURFACE_MINZOOM,
    paint: { 'fill-color': SURFACE.road, 'fill-opacity': 0.3 },
  },
  {
    id: 'campus-vegetation', type: 'fill', source: 'campus-vegetation', slot: 'bottom',
    minzoom: SURFACE_MINZOOM,
    paint: {
      'fill-color': [
        'match', ['get', 'class'],
        'Hedgerows', SURFACE.hedgerows,
        'Landscape Beds', SURFACE.landscapeBeds,
        'Woodland', SURFACE.woodland,
        SURFACE.vegetation,
      ],
      'fill-opacity': 0.8,
    },
  },
  {
    id: 'campus-sidewalk', type: 'fill', source: 'campus-sidewalk', slot: 'bottom',
    minzoom: SURFACE_MINZOOM,
    paint: {
      'fill-color': [
        'match', ['get', 'class'],
        'Brick Paver', SURFACE.sidewalkBrick,
        SURFACE.sidewalkOther,
      ],
      'fill-opacity': 0.9,
    },
  },
  {
    id: 'campus-ramp', type: 'fill', source: 'campus-ramp', slot: 'bottom',
    minzoom: SURFACE_MINZOOM,
    paint: { 'fill-color': SURFACE.ramp, 'fill-outline-color': '#b45309' },
  },
  // Stairs get a hard outline: they are the thing that decides a route.
  {
    id: 'campus-stairs-fill', type: 'fill', source: 'campus-stairs', slot: 'bottom',
    minzoom: SURFACE_MINZOOM,
    paint: { 'fill-color': SURFACE.stairs, 'fill-opacity': 0.95 },
  },
  {
    id: 'campus-stairs-line', type: 'line', source: 'campus-stairs', slot: 'bottom',
    minzoom: SURFACE_MINZOOM,
    paint: { 'line-color': '#b91c1c', 'line-width': 1.2 },
  },

  // --- named outdoor spaces -------------------------------------------------
  {
    id: 'campus-exterior', type: 'fill', source: 'campus-exterior', slot: 'bottom',
    paint: { 'fill-color': '#84cc16', 'fill-opacity': 0.12 },
  },
  {
    id: 'campus-exterior-line', type: 'line', source: 'campus-exterior', slot: 'bottom',
    paint: { 'line-color': '#4d7c0f', 'line-width': 1, 'line-dasharray': [3, 2] },
  },

  // --- buildings ------------------------------------------------------------
  {
    id: 'campus-facilities', type: 'fill', source: 'campus-facilities', slot: 'bottom',
    paint: { 'fill-color': '#94a3b8', 'fill-opacity': 0.35 },
  },
  {
    id: 'campus-facilities-line', type: 'line', source: 'campus-facilities', slot: 'bottom',
    paint: { 'line-color': '#475569', 'line-width': 1 },
  },

  // --- the routing network, coloured by the official grade ------------------
  {
    id: 'campus-pathways', type: 'line', source: 'campus-pathways', slot: 'middle',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': [
        'match', ['get', 'ihcd2021routesurveycode'],
        'FullyCompliant', GRADE_COLORS.FullyCompliant,
        'PartiallyCompliant', GRADE_COLORS.PartiallyCompliant,
        'NonCompliant', GRADE_COLORS.NonCompliant,
        GRADE_COLORS.Other,
      ],
      'line-width': ['interpolate', ['linear'], ['zoom'], 14, 0.8, 18, 3],
      'line-opacity': 0.85,
    },
  },
  // Stair segments carry riser counts; mark them apart from the grading.
  {
    id: 'campus-pathways-stairs', type: 'line', source: 'campus-pathways', slot: 'middle',
    filter: ['==', ['get', 'pathway_type'], 2],
    paint: {
      'line-color': '#7f1d1d',
      'line-width': ['interpolate', ['linear'], ['zoom'], 14, 1.5, 18, 5],
      'line-dasharray': [1, 1],
    },
  },

  // --- construction closures -----------------------------------------------
  {
    id: 'campus-barriers', type: 'fill', source: 'campus-barriers', slot: 'middle',
    paint: { 'fill-color': '#ef4444', 'fill-opacity': 0.2 },
  },
  {
    id: 'campus-barriers-line', type: 'line', source: 'campus-barriers', slot: 'middle',
    paint: { 'line-color': '#b91c1c', 'line-width': 1.5, 'line-dasharray': [2, 1] },
  },

  // --- entrances, last: step-free or not is the headline of this data -------
  {
    id: 'campus-entryways', type: 'circle', source: 'campus-entryways', slot: 'middle',
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 14, 2.5, 18, 5.5],
      'circle-color': ['match', ['get', 'accessible_entrance'], 'Y', '#2563eb', '#64748b'],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.2,
    },
  },
]

export function addCampusLayers(map: mapboxgl.Map) {
  for (const id of Object.keys(CAMPUS_FILES) as CampusLayerId[]) {
    if (!map.getSource(`campus-${id}`)) {
      map.addSource(`campus-${id}`, { type: 'geojson', data: EMPTY })
    }
  }
  for (const layer of CAMPUS_LAYERS) {
    if (!map.getLayer(layer.id)) {
      map.addLayer({ ...layer, layout: { ...layer.layout, visibility: 'none' } } as never)
    }
  }
}

export function setCampusVisibility(map: mapboxgl.Map, visible: boolean) {
  for (const layer of CAMPUS_LAYERS) {
    if (map.getLayer(layer.id)) {
      map.setLayoutProperty(layer.id, 'visibility', visible ? 'visible' : 'none')
    }
  }
}

/** Fetched once and kept; ~4 MB of GeoJSON, ~450 KB over the wire. */
const cache = new Map<CampusLayerId, unknown>()

export async function loadCampusData(map: mapboxgl.Map) {
  await Promise.all(
    (Object.keys(CAMPUS_FILES) as CampusLayerId[]).map(async (id) => {
      try {
        if (!cache.has(id)) {
          const response = await fetch(CAMPUS_FILES[id])
          if (!response.ok) throw new Error(`${CAMPUS_FILES[id]} -> ${response.status}`)
          cache.set(id, await response.json())
        }
        const source = map.getSource(`campus-${id}`) as mapboxgl.GeoJSONSource | undefined
        source?.setData(cache.get(id) as never)
      } catch (error) {
        // One missing layer should not blank the rest of the overlay.
        console.warn('campus layer failed', id, error)
      }
    }),
  )
}
