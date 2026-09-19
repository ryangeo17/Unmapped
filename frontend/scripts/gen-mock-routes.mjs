// Generates real campus path geometry for the mock routes.
// Run once from frontend/: node scripts/gen-mock-routes.mjs
// Writes src/mocks/data/rawRoutes.json. Coordinates are [lng, lat].
import { writeFileSync } from 'node:fs'

const OSRM = 'https://routing.openstreetmap.de/routed-foot/route/v1/foot'

// Keep in sync with src/mocks/data/places.ts (approximate coordinates).
const P = {
  gilman: [-76.6216, 39.329],
  brody: [-76.6194, 39.3284],
  library: [-76.6194, 39.3291],
  malone: [-76.6208, 39.3262],
  hodson: [-76.6223, 39.3276],
  mudd: [-76.6206, 39.3308],
  beach: [-76.6185, 39.3291],
  rec: [-76.6213, 39.3321],
  charlesCommons: [-76.6167, 39.3282],
  krieger: [-76.62, 39.3284],
}

// Each trip gets a direct path plus two detours through other buildings,
// so each travel mode can take a visibly different real path.
const TRIPS = [
  { id: 'gilman-malone', from: P.gilman, to: P.malone, viaA: P.hodson, viaB: P.krieger },
  { id: 'brody-rec', from: P.brody, to: P.rec, viaA: P.library, viaB: P.gilman },
  { id: 'mudd-charles', from: P.mudd, to: P.charlesCommons, viaA: P.library, viaB: P.beach },
]

async function route(points) {
  const coords = points.map((p) => p.join(',')).join(';')
  const res = await fetch(`${OSRM}/${coords}?overview=full&geometries=geojson`)
  if (!res.ok) throw new Error(`OSRM ${res.status} for ${coords}`)
  const data = await res.json()
  const r = data.routes[0]
  return { geometry: r.geometry.coordinates, distanceM: Math.round(r.distance), durationS: Math.round(r.duration) }
}

const out = {}
for (const t of TRIPS) {
  out[t.id] = {
    direct: await route([t.from, t.to]),
    viaA: await route([t.from, t.viaA, t.to]),
    viaB: await route([t.from, t.viaB, t.to]),
  }
  console.log(t.id, Object.values(out[t.id]).map((r) => `${r.geometry.length} pts / ${r.distanceM} m`).join(', '))
}

writeFileSync(new URL('../src/mocks/data/rawRoutes.json', import.meta.url), JSON.stringify(out))
console.log('Wrote src/mocks/data/rawRoutes.json')
