import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Accessibility,
  Bike,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Clock3,
  Crosshair,
  Footprints,
  Layers3,
  LocateFixed,
  MapPin,
  Menu,
  Moon,
  Navigation,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Route as RouteIcon,
  ShieldCheck,
  Sparkles,
  Sun,
  X,
  Zap,
} from 'lucide-react'
import { Link, Route, Routes } from 'react-router-dom'
import { api } from './api'
import AdminPage from './AdminPage'
import MapView from './MapView'
import type { Hazard, Landmark, LatLng, RouteResult, TravelMode } from './types'

const HOMEWOOD: LatLng = [39.3299, -76.6205]

const MODE_OPTIONS: { value: TravelMode; label: string; Icon: typeof Footprints }[] = [
  { value: 'walking', label: 'Walk', Icon: Footprints },
  { value: 'wheelchair', label: 'Wheelchair', Icon: Accessibility },
  { value: 'scooter', label: 'Scooter', Icon: Zap },
  { value: 'bicycle', label: 'Bicycle', Icon: Bike },
]

const toRadians = (value: number) => (value * Math.PI) / 180
function distanceMeters(a: LatLng, b: LatLng) {
  const dLat = toRadians(b[0] - a[0])
  const dLng = toRadians(b[1] - a[1])
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(toRadians(a[0])) * Math.cos(toRadians(b[0])) * Math.sin(dLng / 2) ** 2
  return 6371000 * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x))
}

function SearchField({
  label,
  value,
  selected,
  onChange,
  onSelect,
  onCurrentLocation,
}: {
  label: string
  value: string
  selected?: Landmark
  onChange: (value: string) => void
  onSelect: (landmark: Landmark) => void
  onCurrentLocation?: () => void
}) {
  const [open, setOpen] = useState(false)
  const [remote, setRemote] = useState<Landmark[]>([])
  const matches = useMemo(() => remote.slice(0, 6), [remote])

  useEffect(() => {
    if (value.trim().length < 2 || selected?.name === value) {
      setRemote([])
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      api.searchLandmarks(value, controller.signal).then(setRemote).catch(() => setRemote([]))
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [value, selected])

  return (
    <div className="search-field">
      <label>{label}</label>
      <div className="input-shell">
        <MapPin size={18} aria-hidden="true" />
        <input
          value={value}
          onChange={(event) => { onChange(event.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          placeholder={label === 'Starting point' ? 'Where are you now?' : 'Where are you going?'}
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          autoComplete="off"
        />
        {onCurrentLocation && <button type="button" className="icon-button" onMouseDown={(event) => event.preventDefault()} onClick={onCurrentLocation} aria-label="Use current location"><LocateFixed size={18} /></button>}
      </div>
      {open && value && !selected && (
        <div className="autocomplete" role="listbox">
          {matches.length ? matches.map((landmark) => (
            <button type="button" role="option" key={landmark.id} onMouseDown={(event) => event.preventDefault()} onClick={() => { onSelect(landmark); setOpen(false) }}>
              <span className="place-icon"><MapPin size={16} /></span><span><strong>{landmark.name}</strong><small>{landmark.subtitle}</small></span>
            </button>
          )) : <p>No matching campus landmarks</p>}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, Icon }: { label: string; value: string; Icon: typeof ShieldCheck }) {
  return <div className="result-stat"><Icon size={18} /><span><strong>{value}</strong><small>{label}</small></span></div>
}

function MainMapPage() {
  const [startText, setStartText] = useState('')
  const [destinationText, setDestinationText] = useState('')
  const [start, setStart] = useState<Landmark>()
  const [destination, setDestination] = useState<Landmark>()
  const [mode, setMode] = useState<TravelMode>('walking')
  const [time, setTime] = useState<'day' | 'night'>('day')
  const [route, setRoute] = useState<RouteResult>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showGraph, setShowGraph] = useState(false)
  const [panelOpen, setPanelOpen] = useState(true)
  const [avoidedHazards, setAvoidedHazards] = useState<string[]>([])
  const [suggestionOpen, setSuggestionOpen] = useState(false)
  const [suggestionDrawing, setSuggestionDrawing] = useState(false)
  const [suggestionPoints, setSuggestionPoints] = useState<LatLng[]>([])
  const [suggestionDescription, setSuggestionDescription] = useState('')
  const [suggestionReason, setSuggestionReason] = useState('')
  const [suggestionPhoto, setSuggestionPhoto] = useState<File>()
  const [suggestionReference, setSuggestionReference] = useState('')
  const [suggestionError, setSuggestionError] = useState('')
  const [livePosition, setLivePosition] = useState<LatLng>()
  const [geoError, setGeoError] = useState('')
  const [navigating, setNavigating] = useState(false)
  const [demoRunning, setDemoRunning] = useState(false)
  const [demoProgress, setDemoProgress] = useState(0)
  const [demoSpeed, setDemoSpeed] = useState(1)
  const watchId = useRef<number>()

  const demoPosition = useMemo<LatLng | undefined>(() => {
    if (!route?.coordinates.length) return
    const position = (route.coordinates.length - 1) * demoProgress
    const index = Math.min(Math.floor(position), route.coordinates.length - 2)
    const fraction = position - index
    const a = route.coordinates[index]
    const b = route.coordinates[index + 1]
    return [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction]
  }, [route, demoProgress])
  const currentPosition = demoProgress > 0 || demoRunning ? demoPosition : livePosition
  const stepIndex = route ? Math.min(Math.floor(demoProgress * route.steps.length), route.steps.length - 1) : 0
  const nearHazard = route?.hazards.find((hazard) => currentPosition && distanceMeters(currentPosition, hazard.coordinates) < 45)
  const offRoute = Boolean(route && livePosition && !demoRunning && demoProgress === 0 && Math.min(...route.coordinates.map((point) => distanceMeters(livePosition, point))) > 60)

  useEffect(() => {
    if (offRoute && !loading) void calculateRoute()
    // Recalculate once when the user first moves meaningfully off-route.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offRoute])

  useEffect(() => {
    if (!demoRunning || !route) return
    const timer = window.setInterval(() => {
      setDemoProgress((progress) => {
        const next = progress + 0.005 * demoSpeed
        if (next >= 1) {
          setDemoRunning(false)
          return 1
        }
        return next
      })
    }, 120)
    return () => window.clearInterval(timer)
  }, [demoRunning, demoSpeed, route])

  useEffect(() => () => {
    if (watchId.current !== undefined) navigator.geolocation?.clearWatch(watchId.current)
  }, [])

  function useCurrentLocation() {
    setGeoError('')
    if (!navigator.geolocation) {
      setGeoError('Geolocation is not available in this browser.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coordinates: LatLng = [position.coords.latitude, position.coords.longitude]
        setLivePosition(coordinates)
        const place = { id: 'current', name: 'Current location', subtitle: 'GPS position', coordinates }
        setStart(place)
        setStartText(place.name)
      },
      () => setGeoError('We could not access your location. Check browser permissions.'),
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  function toggleNavigation() {
    if (navigating) {
      if (watchId.current !== undefined) navigator.geolocation.clearWatch(watchId.current)
      watchId.current = undefined
      setNavigating(false)
      return
    }
    if (!navigator.geolocation) {
      setGeoError('Geolocation is not available in this browser.')
      return
    }
    watchId.current = navigator.geolocation.watchPosition(
      (position) => {
        setLivePosition([position.coords.latitude, position.coords.longitude])
        setGeoError('')
      },
      () => setGeoError('Live navigation lost your GPS signal.'),
      { enableHighAccuracy: true, maximumAge: 2000 },
    )
    setNavigating(true)
  }

  async function calculateRoute(avoidIds = avoidedHazards) {
    if (!start || !destination) {
      setError('Choose both a starting point and destination.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const result = await api.calculateRoute({
        start: start.id === 'current' ? start.coordinates : start.id,
        destination: destination.id === 'current' ? destination.coordinates : destination.id,
        mode,
        time,
        avoidHazardIds: avoidIds,
      })
      setRoute(result)
      setDemoProgress(0)
      setPanelOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'We could not calculate this route.')
    } finally {
      setLoading(false)
    }
  }

  function avoidHazard(hazard: Hazard) {
    if (avoidedHazards.includes(hazard.id)) return
    const next = [...avoidedHazards, hazard.id]
    setAvoidedHazards(next)
    void calculateRoute(next)
  }

  async function submitSuggestion(event: React.FormEvent) {
    event.preventDefault()
    if (suggestionPoints.length < 2) {
      setSuggestionError('Add at least two points on the map.')
      return
    }
    setLoading(true)
    setSuggestionError('')
    try {
      const result = await api.submitSuggestion({
        coordinates: suggestionPoints,
        description: suggestionDescription,
        reason: suggestionReason,
        photo: suggestionPhoto,
      })
      setSuggestionReference(result.reference)
    } catch (err) {
      setSuggestionError(err instanceof Error ? err.message : 'Could not submit your suggestion.')
    } finally {
      setLoading(false)
    }
  }

  const distance = route ? route.distanceMeters >= 1000 ? `${(route.distanceMeters / 1000).toFixed(1)} km` : `${Math.round(route.distanceMeters)} m` : ''

  return (
    <main className={`app ${time === 'night' ? 'night' : ''}`}>
      <a className="skip-link" href="#route-planner">Skip to route planner</a>
      <header className="topbar">
        <button className="mobile-menu icon-button" aria-label="Toggle route panel" onClick={() => setPanelOpen((open) => !open)}><Menu /></button>
        <div className="brand"><span className="brand-logo"><RouteIcon size={22} /></span><span><strong>UnMapped</strong><small>Routes for every body</small></span></div>
        <div className="top-actions">
          <button className={`secondary-button overlay-button ${showGraph ? 'active' : ''}`} onClick={() => setShowGraph((show) => !show)} aria-pressed={showGraph}><Layers3 size={17} /> Graph</button>
          <button className="secondary-button" onClick={() => { setSuggestionOpen(true); setSuggestionDrawing(true); setSuggestionReference('') }}><Plus size={17} /> Suggest a route</button>
          <Link className="admin-link" to="/admin">Admin</Link>
        </div>
      </header>

      <section className="workspace">
        <aside id="route-planner" className={`route-panel ${panelOpen ? 'open' : ''}`} aria-label="Route planner">
          <button className="panel-handle" onClick={() => setPanelOpen((open) => !open)} aria-label={panelOpen ? 'Collapse panel' : 'Expand panel'}><span /><ChevronDown size={18} /></button>
          <div className="panel-scroll">
            <div className="panel-intro"><p className="eyebrow">Homewood campus</p><h1>Find the route that fits.</h1><p>Navigate with accessibility, safety, and community knowledge built in.</p></div>
            <div className="route-inputs">
              <span className="connector" aria-hidden="true" />
              <SearchField
                label="Starting point"
                value={startText}
                selected={start}
                onChange={(value) => { setStartText(value); setStart(undefined) }}
                onSelect={(place) => { setStart(place); setStartText(place.name) }}
                onCurrentLocation={useCurrentLocation}
              />
              <SearchField
                label="Destination"
                value={destinationText}
                selected={destination}
                onChange={(value) => { setDestinationText(value); setDestination(undefined) }}
                onSelect={(place) => { setDestination(place); setDestinationText(place.name) }}
              />
            </div>
            <fieldset className="mode-picker">
              <legend>How are you moving?</legend>
              <div>{MODE_OPTIONS.map(({ value, label, Icon }) => <button type="button" key={value} className={mode === value ? 'selected' : ''} aria-pressed={mode === value} onClick={() => setMode(value)}><Icon size={20} /><span>{label}</span></button>)}</div>
            </fieldset>
            <div className="preference-row"><span><strong>Route conditions</strong><small>Safety scoring adapts by time</small></span><div className="time-toggle"><button className={time === 'day' ? 'selected' : ''} onClick={() => setTime('day')} aria-label="Day route"><Sun size={17} /> Day</button><button className={time === 'night' ? 'selected' : ''} onClick={() => setTime('night')} aria-label="Night route"><Moon size={17} /> Night</button></div></div>
            {(error || geoError) && <div className="alert alert--error" role="alert"><CircleAlert size={18} /><span>{error || geoError}</span></div>}
            <button className="primary-button route-button" onClick={() => calculateRoute()} disabled={loading}>{loading ? <><span className="spinner" /> Finding your best route…</> : <><Navigation size={19} /> Find my route</>}</button>

            {route && <section className="route-result" aria-live="polite">
              <div className="result-heading"><div><p className="eyebrow">Recommended route</p><h2>{distance} · {route.durationMinutes} min</h2></div><span className="verified-badge"><CheckCircle2 size={16} /> {route.verifiedPercent}% verified</span></div>
              <p className="route-reason"><Sparkles size={18} /> {route.explanation}</p>
              <div className="stats-grid">
                <Stat label="Distance" value={distance} Icon={RouteIcon} />
                <Stat label="Estimated" value={`${route.durationMinutes} min`} Icon={Clock3} />
                <Stat label="Accessible" value={`${route.accessibilityScore}/100`} Icon={Accessibility} />
                <Stat label={`${time} safety`} value={`${route.safetyScore}/100`} Icon={ShieldCheck} />
              </div>
              {route.hazards.length > 0 && (
                <div className="route-cautions">
                  <h3>Cautions on this route</h3>
                  {route.hazards.map((hazard) => (
                    <article key={hazard.id}>
                      <CircleAlert size={18} />
                      <span>
                        <strong>{hazard.title}</strong>
                        <small>{hazard.verified ? 'Robot verified demo observation' : 'Unverified report'} · {hazard.description}</small>
                        {hazard.evidence?.map((source) => (
                          <img key={source} className="route-caution-evidence" src={source} alt={`Demo robot evidence for ${hazard.title}`} />
                        ))}
                      </span>
                      <button type="button" className="text-button" onClick={() => avoidHazard(hazard)}>Avoid</button>
                    </article>
                  ))}
                </div>
              )}
              <button className={`primary-button route-button ${navigating ? 'danger' : ''}`} onClick={toggleNavigation}><Crosshair size={18} /> {navigating ? 'Stop live navigation' : 'Start live navigation'}</button>
              {(offRoute || nearHazard) && <div className={`navigation-alert ${offRoute ? 'navigation-alert--danger' : ''}`} role="alert"><CircleAlert size={20} /><span><strong>{offRoute ? 'You’re off route' : `${nearHazard?.title} ahead`}</strong><small>{offRoute ? 'Return to the blue line or recalculate.' : nearHazard?.description}</small></span></div>}
              <div className="steps"><h3>Step-by-step</h3>{route.steps.map((step, index) => <div className={`step ${index === stepIndex && (demoRunning || demoProgress > 0) ? 'current' : ''}`} key={`${step.instruction}-${index}`}><span>{index + 1}</span><p><strong>{step.instruction}</strong><small>{step.distance}</small></p></div>)}</div>
              <div className="demo-controls">
                <div><p className="eyebrow">Demo GPS</p><strong>{Math.round(demoProgress * 100)}% · Step {stepIndex + 1}</strong></div>
                <div className="progress-track"><span style={{ width: `${demoProgress * 100}%` }} /></div>
                <div className="demo-buttons"><button className="icon-button" onClick={() => setDemoRunning((running) => !running)} aria-label={demoRunning ? 'Pause demo' : 'Start demo'}>{demoRunning ? <Pause /> : <Play />}</button><button className="icon-button" onClick={() => { setDemoRunning(false); setDemoProgress(0) }} aria-label="Reset demo"><RotateCcw /></button><label>Speed <select value={demoSpeed} onChange={(event) => setDemoSpeed(Number(event.target.value))}><option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option></select></label></div>
              </div>
            </section>}
          </div>
        </aside>

        <div className="map-wrap">
          <MapView route={route} currentPosition={currentPosition} suggestionPoints={suggestionPoints} suggestionMode={suggestionDrawing && !suggestionReference} showGraph={showGraph} nighttime={time === 'night'} navigationActive={navigating || demoRunning || demoProgress > 0} avoidedHazards={avoidedHazards} onAvoidHazard={avoidHazard} onSuggestionPoint={(point) => setSuggestionPoints((points) => [...points, point])} />
          <div className="legend" aria-label="Map legend">
            <strong>Map key</strong>
            <span><i className="legend-line legend-line--route" /> Selected route</span>
            <span><i className="legend-line legend-line--verified" /> ✓ Robot verified</span>
            <span><i className="legend-line legend-line--jhu-full" /> JHU fully accessible</span>
            <span><i className="legend-line legend-line--jhu-partial" /> JHU partial</span>
            <span><i className="legend-line legend-line--unverified" /> Unverified fallback</span>
            <span><i className="legend-symbol">⇅</i> Stairs</span>
            <span><i className="legend-dot" /> Caution</span>
            <span><i className="legend-symbol legend-symbol--closed">×</i> Closure</span>
            <span><i className="legend-symbol legend-symbol--submission">+</i> User submission</span>
            {showGraph && <span><i className="legend-line legend-line--graph" /> Routing graph</span>}
          </div>
          {suggestionDrawing && !suggestionReference && <div className="map-instruction"><MapPin size={18} /><span><strong>Draw your better route</strong>Click 2+ points on the map · {suggestionPoints.length} added</span><button className="text-button" onClick={() => setSuggestionPoints((points) => points.slice(0, -1))} disabled={!suggestionPoints.length}>Undo</button><button className="text-button" onClick={() => setSuggestionOpen(true)}>Finish</button></div>}
        </div>
      </section>

      {suggestionOpen && <div className="modal-backdrop" role="presentation">
        <section className="suggestion-modal" role="dialog" aria-modal="true" aria-labelledby="suggestion-title">
          <button className="modal-close icon-button" aria-label="Close suggestion form" onClick={() => { setSuggestionOpen(false); setSuggestionDrawing(false); setSuggestionPoints([]) }}><X /></button>
          {suggestionReference ? <div className="confirmation"><span className="confirmation-icon"><CheckCircle2 size={34} /></span><p className="eyebrow">Suggestion received</p><h2 id="suggestion-title">Thanks for mapping what we missed.</h2><p>Our route team will review your submission before it becomes part of the public graph.</p><div className="reference"><small>Status reference</small><strong>{suggestionReference}</strong></div><button className="primary-button" onClick={() => { setSuggestionOpen(false); setSuggestionPoints([]) }}>Back to map</button></div> : (
            <form onSubmit={submitSuggestion}>
              <p className="eyebrow">Community mapping</p><h2 id="suggestion-title">Suggest a better route</h2><p>Close this panel to click points on the map, then reopen it from the header to finish. Your current line stays saved.</p>
              <div className="point-count"><RouteIcon size={19} /><strong>{suggestionPoints.length} map points</strong><button type="button" className="text-button" onClick={() => { setSuggestionOpen(false); setSuggestionDrawing(true) }}>Add points</button></div>
              <label>Describe this path<textarea rows={3} required value={suggestionDescription} onChange={(event) => setSuggestionDescription(event.target.value)} placeholder="e.g. Smooth ramp behind Gilman Hall" /></label>
              <label>Why is it better?<select required value={suggestionReason} onChange={(event) => setSuggestionReason(event.target.value)}><option value="">Choose a reason</option><option>More accessible</option><option>Better lit</option><option>Avoids construction</option><option>Shorter or easier</option><option>Other</option></select></label>
              <label className="file-input">Photo <small>Optional, JPG or PNG</small><input type="file" accept="image/png,image/jpeg" onChange={(event) => setSuggestionPhoto(event.target.files?.[0])} /></label>
              {suggestionError && <div className="alert alert--error" role="alert">{suggestionError}</div>}
              <button className="primary-button" disabled={loading}>{loading ? 'Submitting…' : 'Submit for review'}</button>
            </form>
          )}
        </section>
      </div>}
    </main>
  )
}

export default function App() {
  return <Routes><Route path="/" element={<MainMapPage />} /><Route path="/admin" element={<AdminPage />} /></Routes>
}
