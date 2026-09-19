// Manifest of the local campus data under public/data.
// Everything here is static GeoJSON in WGS84; see public/data/README.md and
// docs/CAMPUS_DATA.md for what the attributes mean.

export type CampusLayerId =
  // Feature layers, campus-wide.
  | 'facilities'
  | 'exteriorSpaces'
  | 'pathways'
  | 'entryways'
  | 'elevators'
  | 'landmarks'
  | 'barriers'
  // Surface polygons, Decker Quad area only.
  | 'campusArea'
  | 'vegetation'
  | 'roadArea'
  | 'sidewalk'
  | 'sidewalkRamp'
  | 'stairs'

export const CAMPUS_DATA: Record<CampusLayerId, string> = {
  facilities: '/data/Facilities.geojson',
  exteriorSpaces: '/data/Exterior_Spaces.geojson',
  pathways: '/data/Pathways.geojson',
  entryways: '/data/Entryways-All.geojson',
  elevators: '/data/Elevators.geojson',
  landmarks: '/data/Landmarks.geojson',
  barriers: '/data/Polygon_Barriers.geojson',
  campusArea: '/data/surfaces/Campus_Area.geojson',
  vegetation: '/data/surfaces/Vegetation.geojson',
  roadArea: '/data/surfaces/Road_Area.geojson',
  sidewalk: '/data/surfaces/Sidewalk.geojson',
  sidewalkRamp: '/data/surfaces/Sidewalk_Ramp.geojson',
  stairs: '/data/surfaces/Stairs.geojson',
}

// Surface layers only cover the Decker Quad neighbourhood, not the whole
// campus. Worth saying in the UI so a blank area doesn't read as a bug.
export const SURFACE_LAYERS: CampusLayerId[] = [
  'campusArea',
  'vegetation',
  'roadArea',
  'sidewalk',
  'sidewalkRamp',
  'stairs',
]

// Palette lifted from the JHU basemap's own style, so the local render looks
// like the official map rather than an arbitrary recolour.
export const SURFACE_COLORS = {
  campusArea: '#C6E2B2',
  vegetationApproximate: '#C6E2B2',
  vegetationHedgerows: '#89CD66',
  vegetationLandscapeBeds: '#D3FFBE',
  vegetationWoodland: '#B4D79E',
  road: '#828282',
  sidewalkBrick: '#D7B09E',
  sidewalkOther: '#FFEBBE',
  stairs: '#D7C29E',
  ramp: '#FFDBBE',
} as const

// Accessibility grading from Pathways.ihcd2021routesurveycode.
export const ACCESS_COLORS = {
  FullyCompliant: '#16a34a',
  PartiallyCompliant: '#eab308',
  NonCompliant: '#dc2626',
  Other: '#94a3b8',
} as const
