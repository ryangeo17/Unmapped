import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { addCampusLayers, loadCampusData, setCampusVisibility } from './campusLayers'
import type { Hazard, LatLng, RouteResult } from './types'

const HOMEWOOD: [number, number] = [-76.6205, 39.3299]
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN || ''

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
  element.textContent = kind === 'person' ? '●' : kind === 'start' ? 'A' : 'B'
  return element
}

interface MapViewProps {
  route?: RouteResult
  currentPosition?: LatLng
  suggestionPoints: LatLng[]
  suggestionMode: boolean
  showGraph: boolean
  showCampus: boolean
  nighttime?: boolean
  avoidedHazards: string[]
  onAvoidHazard: (hazard: Hazard) => void
  onSuggestionPoint: (point: LatLng) => void
}

export default function MapView({
  route,
  currentPosition,
  suggestionPoints,
  suggestionMode,
  showGraph,
  showCampus,
  nighttime = false,
  avoidedHazards,
  onAvoidHazard,
  onSuggestionPoint,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<mapboxgl.Map>()
  const markersRef = useRef<mapboxgl.Marker[]>([])
  const [threeDimensional, setThreeDimensional] = useState(true)
  const clickState = useRef({ suggestionMode, onSuggestionPoint })
  clickState.current = { suggestionMode, onSuggestionPoint }

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
      if (clickState.current.suggestionMode) {
        clickState.current.onSuggestionPoint([event.lngLat.lat, event.lngLat.lng])
      }
    })
    map.on('style.load', () => {
      map.addSource('unmapped-route', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addSource('unmapped-suggestion', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
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
      // The routing graph is now 4,903 real segments; shipping it inside every
      // route response was 2.2 MB a time. It is a campus layer of its own.
      if (map.getLayer('campus-pathways')) {
        for (const id of ['campus-pathways', 'campus-pathways-stairs']) {
          map.setLayoutProperty(id, 'visibility',
            showGraph || showCampus ? 'visible' : 'none')
        }
        if (showGraph) void loadCampusData(map)
      }
      setLineData(map, 'unmapped-suggestion', suggestionPoints.length > 1 ? [suggestionPoints] : [])
    }
    if (map.isStyleLoaded()) update()
    else map.once('style.load', update)
  }, [route, showGraph, showCampus, suggestionPoints])

  // The campus overlay is ~4 MB of GeoJSON, so it is fetched the first time it
  // is switched on and kept thereafter.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const update = () => {
      setCampusVisibility(map, showCampus)
      if (showCampus) void loadCampusData(map)
    }
    if (map.isStyleLoaded()) update()
    else map.once('style.load', update)
  }, [showCampus])

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
      map.fitBounds(bounds, { padding: 70, maxZoom: 17.5, pitch: threeDimensional ? 62 : 0, duration: 700 })
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
      avoid.addEventListener('click', () => onAvoidHazard(hazard))
      popupContent.append(status, avoid)
      const popup = new mapboxgl.Popup({ offset: 18, maxWidth: '270px' }).setDOMContent(popupContent)
      markersRef.current.push(
        new mapboxgl.Marker({ element }).setLngLat([hazard.coordinates[1], hazard.coordinates[0]]).setPopup(popup).addTo(map),
      )
    })
    if (currentPosition) {
      markersRef.current.push(
        new mapboxgl.Marker({ element: markerElement('person') })
          .setLngLat([currentPosition[1], currentPosition[0]])
          .addTo(map),
      )
    }
  }, [route, currentPosition, avoidedHazards, onAvoidHazard, threeDimensional])

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
