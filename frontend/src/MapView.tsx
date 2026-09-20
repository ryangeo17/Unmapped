import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { addCampusLayers, applyOverlayVisibility, loadCampusData } from './campusLayers'
import type { Hazard, LatLng, RouteResult } from './types'

const HOMEWOOD: [number, number] = [-76.6205, 39.3299]
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || ''
const NAVIGATION_ZOOM = 18.2
const NAVIGATION_LOOKAHEAD_M = 22
// Top inset moves the camera centre down the screen, leaving the road ahead visible
// and parking the puck in the lower third the way turn-by-turn apps do.
const NAVIGATION_TOP_PADDING = 230

const lineFeature = (coordinates: LatLng[]) => ({
  type: 'Feature' as const,
  properties: {},
  geometry: {
    type: 'LineString' as const,
    coordinates: coordinates.map(([latitude, longitude]) => [longitude, latitude]),
  },
})

function setLineData(map: mapboxgl.Map, sourceId: string, lines: LatLng[][]) {
  const source = map.getSource(sourceId) as mapboxgl.GeoJSONSource | undefined
  source?.setData({
    type: 'FeatureCollection',
    features: lines.filter((line) => line.length > 1).map(lineFeature),
  })
}

function markerElement(kind: 'start' | 'end' | 'person') {
  const element = document.createElement('span')
  element.className = `map-pin map-pin--${kind}`
  element.setAttribute('aria-label', kind === 'person' ? 'Current position' : `${kind} of route`)
  element.textContent = kind === 'person' ? '▲' : kind === 'start' ? 'A' : 'B'
  return element
}

function metersBetween(a: LatLng, b: LatLng) {
  const latitude = (b[0] - a[0]) * 111320
  const longitude = (b[1] - a[1]) * 111320 * Math.cos((a[0] * Math.PI) / 180)
  return Math.sqrt(latitude * latitude + longitude * longitude)
}

function bearingBetween(from: LatLng, to: LatLng) {
  const latitude1 = (from[0] * Math.PI) / 180
  const latitude2 = (to[0] * Math.PI) / 180
  const longitudeDelta = ((to[1] - from[1]) * Math.PI) / 180
  const y = Math.sin(longitudeDelta) * Math.cos(latitude2)
  const x = Math.cos(latitude1) * Math.sin(latitude2)
    - Math.sin(latitude1) * Math.cos(latitude2) * Math.cos(longitudeDelta)
  return (Math.atan2(y, x) * 180) / Math.PI
}

const interpolate = (a: LatLng, b: LatLng, fraction: number): LatLng => [
  a[0] + (b[0] - a[0]) * fraction,
  a[1] + (b[1] - a[1]) * fraction,
]

/** Position in metres east/north of an origin, so segment maths can stay planar. */
function toLocal(origin: LatLng, point: LatLng): [number, number] {
  return [
    (point[1] - origin[1]) * 111320 * Math.cos((origin[0] * Math.PI) / 180),
    (point[0] - origin[0]) * 111320,
  ]
}

/**
 * Direction of travel toward a point a fixed distance further along the route.
 * Snapping to the closest vertex instead would aim the camera at the next corner,
 * which swings the view sideways whenever the geometry is sparse.
 */
function routeHeading(position: LatLng, coordinates: LatLng[]) {
  if (coordinates.length < 2) return undefined
  let closest = { index: 0, fraction: 0, distance: Number.POSITIVE_INFINITY }
  for (let index = 0; index < coordinates.length - 1; index += 1) {
    const [ax, ay] = toLocal(position, coordinates[index])
    const [bx, by] = toLocal(position, coordinates[index + 1])
    const dx = bx - ax
    const dy = by - ay
    const lengthSquared = dx * dx + dy * dy
    const fraction = lengthSquared
      ? Math.min(1, Math.max(0, -(ax * dx + ay * dy) / lengthSquared))
      : 0
    const distance = Math.hypot(ax + dx * fraction, ay + dy * fraction)
    if (distance < closest.distance) closest = { index, fraction, distance }
  }

  let cursor = interpolate(coordinates[closest.index], coordinates[closest.index + 1], closest.fraction)
  let remaining = NAVIGATION_LOOKAHEAD_M
  for (let index = closest.index; index < coordinates.length - 1; index += 1) {
    const next = coordinates[index + 1]
    const span = metersBetween(cursor, next)
    if (span >= remaining) {
      return bearingBetween(position, interpolate(cursor, next, span ? remaining / span : 1))
    }
    remaining -= span
    cursor = next
  }
  return metersBetween(position, cursor) < 0.5 ? undefined : bearingBetween(position, cursor)
}

/** Shortest signed turn from one compass bearing to another, in the range (-180, 180]. */
function bearingDelta(from: number, to: number) {
  return ((to - from + 540) % 360) - 180
}

interface MapViewProps {
  route?: RouteResult
  currentPosition?: LatLng
  suggestionPoints?: LatLng[]
  suggestionMode?: boolean
  showGraph?: boolean
  showCampus?: boolean
  recenterToken?: number
  nighttime?: boolean
  navigationActive?: boolean
  avoidedHazards?: string[]
  onAvoidHazard?: (hazard: Hazard) => void
  onSuggestionPoint?: (point: LatLng) => void
  onMapClick?: (point: LatLng) => void
  verifiedPath?: LatLng[]
  editableHazards?: Hazard[]
  selectedHazardId?: string
  onHazardClick?: (hazard: Hazard) => void
}

export default function MapView({
  route,
  currentPosition,
  suggestionPoints = [],
  suggestionMode = false,
  showGraph = false,
  showCampus = false,
  recenterToken = 0,
  nighttime = false,
  navigationActive = false,
  avoidedHazards = [],
  onAvoidHazard,
  onSuggestionPoint,
  onMapClick,
  verifiedPath = [],
  editableHazards = [],
  selectedHazardId,
  onHazardClick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map>()
  const markersRef = useRef<mapboxgl.Marker[]>([])
  const cameraTargetRef = useRef<{ center: [number, number]; bearing: number }>()
  const frameRef = useRef<number>()
  const wasNavigatingRef = useRef(false)
  const [threeDimensional, setThreeDimensional] = useState(true)
  const clickState = useRef({ suggestionMode, onSuggestionPoint, onMapClick })
  clickState.current = { suggestionMode, onSuggestionPoint, onMapClick }
  const overlayRef = useRef({ showGraph, showCampus })
  overlayRef.current = { showGraph, showCampus }

  useEffect(() => {
    if (!containerRef.current || !MAPBOX_TOKEN || mapRef.current) return
    mapboxgl.accessToken = MAPBOX_TOKEN
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/standard',
      center: HOMEWOOD,
      zoom: 16,
      pitch: 62,
      bearing: -18,
      antialias: true,
      // Turn-by-turn rotation is the point of the view, not decoration.
      respectPrefersReducedMotion: false,
      config: {
        basemap: {
          lightPreset: 'day',
          show3dObjects: true,
          showPedestrianRoads: true,
        },
      },
    })
    map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), 'bottom-right')
    map.on('click', (event) => {
      const point: LatLng = [event.lngLat.lat, event.lngLat.lng]
      if (clickState.current.suggestionMode) {
        clickState.current.onSuggestionPoint?.(point)
      } else {
        clickState.current.onMapClick?.(point)
      }
    })
    map.on('style.load', () => {
      map.addSource('unmapped-route', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addSource('unmapped-suggestion', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addSource('unmapped-verified', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addLayer({
        id: 'unmapped-route-shadow',
        type: 'line',
        source: 'unmapped-route',
        slot: 'top',
        paint: { 'line-color': '#ffffff', 'line-width': 10, 'line-opacity': 0.9 },
      })
      map.addLayer({
        id: 'unmapped-route',
        type: 'line',
        source: 'unmapped-route',
        slot: 'top',
        paint: { 'line-color': '#1369d0', 'line-width': 7, 'line-opacity': 0.96 },
      })
      map.addLayer({
        id: 'unmapped-suggestion',
        type: 'line',
        source: 'unmapped-suggestion',
        slot: 'top',
        paint: { 'line-color': '#7c3aed', 'line-width': 5, 'line-dasharray': [1, 1.5] },
      })
      map.addLayer({
        id: 'unmapped-verified',
        type: 'line',
        source: 'unmapped-verified',
        slot: 'top',
        paint: { 'line-color': '#0f9d58', 'line-width': 7, 'line-opacity': 0.92 },
      })
      // Added at style load so they sit below the route, which is added above
      // them here and stays above them: Mapbox draws in the order layers were
      // added within a slot, and the route is in 'top'.
      addCampusLayers(map)
    })
    mapRef.current = map
    return () => {
      markersRef.current.forEach((marker) => marker.remove())
      markersRef.current = []
      map.remove()
      mapRef.current = undefined
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const update = () => {
      setLineData(map, 'unmapped-route', route?.coordinates ? [route.coordinates] : [])
      setLineData(map, 'unmapped-suggestion', suggestionPoints.length > 1 ? [suggestionPoints] : [])
      setLineData(map, 'unmapped-verified', verifiedPath.length > 1 ? [verifiedPath] : [])
    }
    if (map.isStyleLoaded()) update()
    else map.once('style.load', update)
  }, [route, suggestionPoints, verifiedPath])

  useEffect(() => {
    if (!navigationActive || !currentPosition || !route?.coordinates.length) {
      cameraTargetRef.current = undefined
      return
    }
    const heading = routeHeading(currentPosition, route.coordinates)
    cameraTargetRef.current = {
      center: [currentPosition[1], currentPosition[0]],
      bearing: heading ?? cameraTargetRef.current?.bearing ?? mapRef.current?.getBearing() ?? 0,
    }
  }, [currentPosition, navigationActive, route])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (!navigationActive) {
      map.setPadding({ top: 0, right: 0, bottom: 0, left: 0 })
      if (wasNavigatingRef.current) {
        wasNavigatingRef.current = false
        map.easeTo({ bearing: threeDimensional ? -18 : 0, zoom: 16.4, duration: 700 })
      }
      return
    }
    wasNavigatingRef.current = true
    map.setPadding({ top: NAVIGATION_TOP_PADDING, right: 0, bottom: 0, left: 0 })
    // A single rAF loop eases the camera every frame. Firing easeTo per GPS tick
    // cancels the previous animation before it makes progress, so the map never turns.
    const followRoute = () => {
      frameRef.current = requestAnimationFrame(followRoute)
      const target = cameraTargetRef.current
      if (!target) return
      const center = map.getCenter()
      const bearing = map.getBearing()
      const zoom = map.getZoom()
      map.jumpTo({
        center: [
          center.lng + (target.center[0] - center.lng) * 0.2,
          center.lat + (target.center[1] - center.lat) * 0.2,
        ],
        bearing: bearing + bearingDelta(bearing, target.bearing) * 0.1,
        zoom: zoom + (NAVIGATION_ZOOM - zoom) * 0.06,
        pitch: threeDimensional ? 62 : 0,
      })
    }
    frameRef.current = requestAnimationFrame(followRoute)
    return () => {
      if (frameRef.current !== undefined) cancelAnimationFrame(frameRef.current)
      frameRef.current = undefined
    }
  }, [navigationActive, threeDimensional])

  // Apply Graph/Campus after the style exists. Calling addSource/addLayer
  // before that throws and whites out the whole page.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    let cancelled = false
    let retry: number | undefined
    const update = () => {
      if (cancelled) return
      try {
        addCampusLayers(map)
        const { showGraph: graphOn, showCampus: campusOn } = overlayRef.current
        const reveal = () => {
          if (cancelled) return
          applyOverlayVisibility(map, overlayRef.current.showGraph, overlayRef.current.showCampus)
        }
        if (graphOn || campusOn) void loadCampusData(map).then(reveal)
        else reveal()
      } catch {
        retry = window.setTimeout(update, 200)
      }
    }
    map.on('style.load', update)
    map.once('idle', update)
    retry = window.setTimeout(update, 0)
    return () => {
      cancelled = true
      if (retry !== undefined) window.clearTimeout(retry)
      map.off('style.load', update)
      map.off('idle', update)
    }
  }, [showGraph, showCampus])

  // Campus 是一个动作而不是图层：把相机带回 Homewood，不往图上加任何东西。
  // 令牌初值为 0，所以首次挂载不会抢走地图自己的开场镜头。
  useEffect(() => {
    if (!recenterToken) return
    const map = mapRef.current
    if (!map) return
    try {
      map.easeTo({ center: HOMEWOOD, zoom: Math.max(map.getZoom(), 16), duration: 700 })
    } catch {
      // 地图还在启动；它本来就以 Homewood 为中心打开。
    }
  }, [recenterToken])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const updateLighting = () => map.setConfigProperty('basemap', 'lightPreset', nighttime ? 'night' : 'day')
    if (map.isStyleLoaded()) updateLighting()
    else map.once('style.load', updateLighting)
  }, [nighttime])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = []
    if (route?.coordinates.length) {
      const start = route.coordinates[0]
      const end = route.coordinates[route.coordinates.length - 1]
      markersRef.current.push(
        new mapboxgl.Marker({ element: markerElement('start') }).setLngLat([start[1], start[0]]).addTo(map),
        new mapboxgl.Marker({ element: markerElement('end') }).setLngLat([end[1], end[0]]).addTo(map),
      )
      const bounds = route.coordinates.reduce(
        (value, [latitude, longitude]) => value.extend([longitude, latitude]),
        new mapboxgl.LngLatBounds([start[1], start[0]], [start[1], start[0]]),
      )
      if (!navigationActive) {
        map.fitBounds(bounds, { padding: 70, maxZoom: 17.5, pitch: threeDimensional ? 62 : 0, duration: 700 })
      }
    }
    route?.hazards.forEach((hazard) => {
      const element = document.createElement('button')
      element.type = 'button'
      element.className = `mapbox-hazard mapbox-hazard--${hazard.severity}`
      element.setAttribute('aria-label', `Open caution: ${hazard.title}`)
      element.textContent = '!'
      const popupContent = document.createElement('div')
      popupContent.className = 'hazard-popup'
      const title = document.createElement('strong')
      title.textContent = hazard.title
      const description = document.createElement('p')
      description.textContent = hazard.description
      popupContent.append(title, description)
      hazard.evidence?.forEach((source) => {
        const image = document.createElement('img')
        image.src = source
        image.alt = `Demo robot evidence for ${hazard.title}`
        image.className = 'mapbox-popup-evidence'
        popupContent.append(image)
      })
      const status = document.createElement('span')
      status.className = `verification ${hazard.verified ? 'verified' : ''}`
      status.textContent = hazard.verified ? '✓ Robot verified demo observation' : 'Unverified report'
      const avoid = document.createElement('button')
      avoid.type = 'button'
      avoid.className = 'text-button'
      avoid.disabled = avoidedHazards.includes(hazard.id)
      avoid.textContent = avoid.disabled ? 'Already avoiding' : 'Avoid this obstacle'
      avoid.addEventListener('click', () => onAvoidHazard?.(hazard))
      popupContent.append(status)
      if (onAvoidHazard) popupContent.append(avoid)
      if (hazard.robotNote) {
        const note = document.createElement('p')
        note.className = 'hazard-popup-note'
        note.textContent = hazard.robotNote
        popupContent.insertBefore(note, status)
      }
      if (hazard.activeWhen && hazard.activeWhen !== 'always') {
        const when = document.createElement('small')
        when.textContent = hazard.activeWhen === 'night' ? 'Applies at night' : 'Applies during the day'
        popupContent.insertBefore(when, status)
      }
      const popup = new mapboxgl.Popup({ offset: 18, maxWidth: '270px' }).setDOMContent(popupContent)
      markersRef.current.push(
        new mapboxgl.Marker({ element }).setLngLat([hazard.coordinates[1], hazard.coordinates[0]]).setPopup(popup).addTo(map),
      )
    })
    editableHazards.forEach((hazard) => {
      const element = document.createElement('button')
      element.type = 'button'
      element.className = `mapbox-hazard mapbox-hazard--${hazard.severity}${selectedHazardId === hazard.id ? ' is-selected' : ''}`
      element.setAttribute('aria-label', `Edit caution: ${hazard.title}`)
      element.textContent = '!'
      element.addEventListener('click', (event) => {
        event.stopPropagation()
        onHazardClick?.(hazard)
      })
      markersRef.current.push(
        new mapboxgl.Marker({ element }).setLngLat([hazard.coordinates[1], hazard.coordinates[0]]).addTo(map),
      )
    })
    suggestionPoints.forEach((point, index) => {
      const element = document.createElement('span')
      element.className = 'map-pin map-pin--vertex'
      element.textContent = String(index + 1)
      markersRef.current.push(
        new mapboxgl.Marker({ element }).setLngLat([point[1], point[0]]).addTo(map),
      )
    })
    if (currentPosition) {
      markersRef.current.push(
        new mapboxgl.Marker({
          element: markerElement('person'),
          rotation: (route && routeHeading(currentPosition, route.coordinates)) ?? 0,
          rotationAlignment: 'map',
        })
          .setLngLat([currentPosition[1], currentPosition[0]])
          .addTo(map),
      )
    }
  }, [route, currentPosition, avoidedHazards, onAvoidHazard, threeDimensional, navigationActive, editableHazards, selectedHazardId, onHazardClick, suggestionPoints, verifiedPath])

  function toggleDimension() {
    const next = !threeDimensional
    setThreeDimensional(next)
    mapRef.current?.easeTo({ pitch: next ? 62 : 0, bearing: next ? -18 : 0, duration: 650 })
  }

  if (!MAPBOX_TOKEN) {
    return (
      <div className="map map-config-error" role="alert">
        <strong>Mapbox token needed</strong>
        <span>Add VITE_MAPBOX_ACCESS_TOKEN to frontend/.env to load the Mapbox Standard 3D campus map.</span>
      </div>
    )
  }

  return (
    <div className="mapbox-shell">
      <div ref={containerRef} className="map" aria-label="Interactive Mapbox Standard 3D campus route map" />
      <button type="button" className="mapbox-3d-toggle" onClick={toggleDimension} aria-pressed={threeDimensional}>
        {threeDimensional ? '2D view' : '3D view'}
      </button>
    </div>
  )
}
