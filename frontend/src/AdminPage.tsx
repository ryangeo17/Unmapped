import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Check, LogOut, MapPin, Pencil, Plus, RefreshCw, ShieldCheck, Trash2, Undo2, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, API_ORIGIN } from './api'
import MapView from './MapView'
import type { Hazard, Landmark, LatLng, Submission, SubmissionStatus, VerifiedHazard, VerifiedPath } from './types'

type Tool = 'draw' | 'hazard'

const EMPTY_HAZARD = {
  title: '',
  description: '',
  robot_note: '',
  severity: 2,
  kind: 'roughness',
  active_when: 'always' as VerifiedHazard['active_when'],
}

function closestPointOnPath(point: LatLng, path: LatLng[]) {
  if (path.length < 2) return { point, distance: Number.POSITIVE_INFINITY }
  let best = { point: path[0], distance: Number.POSITIVE_INFINITY }
  for (let index = 0; index < path.length - 1; index += 1) {
    const start = path[index]
    const end = path[index + 1]
    const ax = (start[1] - point[1]) * 111320 * Math.cos((point[0] * Math.PI) / 180)
    const ay = (start[0] - point[0]) * 111320
    const bx = (end[1] - point[1]) * 111320 * Math.cos((point[0] * Math.PI) / 180)
    const by = (end[0] - point[0]) * 111320
    const dx = bx - ax
    const dy = by - ay
    const length = dx * dx + dy * dy
    const fraction = length ? Math.min(1, Math.max(0, -(ax * dx + ay * dy) / length)) : 0
    const snapped: LatLng = [start[0] + (end[0] - start[0]) * fraction, start[1] + (end[1] - start[1]) * fraction]
    const distance = Math.hypot(ax + dx * fraction, ay + dy * fraction)
    if (distance < best.distance) best = { point: snapped, distance }
  }
  return best
}

function toMapHazard(hazard: VerifiedHazard): Hazard {
  return {
    id: hazard.id,
    title: hazard.title,
    description: hazard.description,
    severity: hazard.severity >= 3 ? 'high' : hazard.severity === 2 ? 'medium' : 'low',
    coordinates: [hazard.latitude, hazard.longitude],
    verified: hazard.verified,
    evidence: [...new Set(hazard.evidence)].map((path) => (path.startsWith('http') ? path : `${API_ORIGIN}${path}`)),
    robotNote: hazard.robot_note,
    activeWhen: hazard.active_when,
    kind: hazard.kind,
  }
}

export default function AdminPage() {
  const [token, setToken] = useState(() => sessionStorage.getItem('unmapped-admin-token') || '')
  const [password, setPassword] = useState('')
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [path, setPath] = useState<VerifiedPath | null>(null)
  const [points, setPoints] = useState<LatLng[]>([])
  const [tool, setTool] = useState<Tool>('draw')
  const [pendingPoint, setPendingPoint] = useState<LatLng>()
  const [editingHazard, setEditingHazard] = useState<VerifiedHazard | null>(null)
  const [hazardForm, setHazardForm] = useState(EMPTY_HAZARD)
  const [hazardPhoto, setHazardPhoto] = useState<File>()
  const [pathName, setPathName] = useState('Robot verified path')
  const [fromLandmark, setFromLandmark] = useState('')
  const [toLandmark, setToLandmark] = useState('')
  const [landmarks, setLandmarks] = useState<Landmark[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const publishedGeometry = path?.geometry || []
  const drawing = tool === 'draw'
  const previewPoints = drawing ? points : publishedGeometry

  const mapHazards = useMemo(
    () => (path?.hazards || []).map(toMapHazard),
    [path],
  )

  useEffect(() => {
    if (!token) return
    setLoading(true)
    Promise.all([api.getSubmissions(token), api.getVerifiedPath(token), api.listLandmarks()])
      .then(([nextSubmissions, result, nextLandmarks]) => {
        setSubmissions(nextSubmissions)
        setLandmarks(nextLandmarks)
        applyPath(result.path)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [token])

  function applyPath(next: VerifiedPath | null) {
    setPath(next)
    setPoints(next?.geometry || [])
    setPathName(next?.name || 'Robot verified path')
    setFromLandmark(next?.from_landmark || '')
    setToLandmark(next?.to_landmark || '')
    setTool(next ? 'hazard' : 'draw')
    setPendingPoint(undefined)
    setEditingHazard(null)
    setHazardForm(EMPTY_HAZARD)
  }

  function startNewPath() {
    setTool('draw')
    setPoints([])
    setPendingPoint(undefined)
    setEditingHazard(null)
    setHazardForm(EMPTY_HAZARD)
    setError('')
  }

  async function removePath() {
    setLoading(true)
    setError('')
    try {
      await api.deleteVerifiedPath(token)
      applyPath(null)
      setPoints([])
      setFromLandmark('')
      setToLandmark('')
      setPathName('Robot verified path')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the verified path')
    } finally {
      setLoading(false)
    }
  }

  async function login(event: React.FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await api.adminLogin(password)
      sessionStorage.setItem('unmapped-admin-token', result.token)
      setToken(result.token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in')
    } finally {
      setLoading(false)
    }
  }

  async function setStatus(id: string, status: SubmissionStatus) {
    setError('')
    try {
      const updated = await api.updateSubmission(id, status, token)
      setSubmissions((items) => items.map((item) => (item.id === id ? updated : item)))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update submission')
    }
  }

  async function publishPath() {
    if (points.length < 2) {
      setError('Click at least two points on the map to draw the path.')
      return
    }
    if (!fromLandmark || !toLandmark) {
      setError('Choose a start and destination so people can search for this path.')
      return
    }
    if (fromLandmark === toLandmark) {
      setError('Start and destination must be different places.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const saved = await api.saveVerifiedPath(token, {
        geometry: points,
        name: pathName,
        from_landmark: fromLandmark,
        to_landmark: toLandmark,
      })
      applyPath(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not publish the verified path')
    } finally {
      setLoading(false)
    }
  }

  function startHazardAt(point: LatLng) {
    const snapped = closestPointOnPath(point, previewPoints)
    if (snapped.distance > 35) {
      setError('Click on the green path to drop a hazard.')
      return
    }
    setError('')
    setEditingHazard(null)
    setHazardForm(EMPTY_HAZARD)
    setHazardPhoto(undefined)
    setPendingPoint(snapped.point)
  }

  function editHazard(hazard: VerifiedHazard | Hazard) {
    const record = path?.hazards.find((item) => item.id === hazard.id)
    if (!record) return
    setTool('hazard')
    setEditingHazard(record)
    setPendingPoint([record.latitude, record.longitude])
    setHazardForm({
      title: record.title,
      description: record.description,
      robot_note: record.robot_note,
      severity: record.severity,
      kind: record.kind,
      active_when: record.active_when,
    })
    setHazardPhoto(undefined)
    setError('')
  }

  async function saveHazard(event: React.FormEvent) {
    event.preventDefault()
    if (!pendingPoint) {
      setError('Click a point on the verified path first.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const payload = {
        ...hazardForm,
        latitude: pendingPoint[0],
        longitude: pendingPoint[1],
        active: true,
        verified: true,
      }
      const saved = editingHazard
        ? await api.updateVerifiedHazard(token, editingHazard.id, payload)
        : await api.createVerifiedHazard(token, payload)
      if (hazardPhoto) await api.uploadVerifiedHazardEvidence(token, saved.id, hazardPhoto)
      const result = await api.getVerifiedPath(token)
      applyPath(result.path)
      setTool('hazard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the hazard')
    } finally {
      setLoading(false)
    }
  }

  async function removeHazard() {
    if (!editingHazard) return
    setLoading(true)
    setError('')
    try {
      await api.deleteVerifiedHazard(token, editingHazard.id)
      const result = await api.getVerifiedPath(token)
      applyPath(result.path)
      setTool('hazard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete the hazard')
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <main className="admin-login">
        <Link to="/" className="back-link"><ArrowLeft size={18} /> Return to map</Link>
        <form className="login-card" onSubmit={login}>
          <div className="brand-mark"><ShieldCheck size={28} /></div>
          <p className="eyebrow">Restricted workspace</p>
          <h1>Admin sign in</h1>
          <p>Draw one robot-verified path, then click it to add and edit hazards.</p>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          </label>
          {error && <div className="alert alert--error" role="alert">{error}</div>}
          <button className="primary-button" disabled={loading}>{loading ? 'Signing in…' : 'Sign in securely'}</button>
        </form>
      </main>
    )
  }

  return (
    <main className="admin-page admin-workspace">
      <header className="admin-header">
        <div>
          <p className="eyebrow">UnMapped operations</p>
          <h1>Robot-verified path</h1>
        </div>
        <div className="header-actions">
          <Link to="/" className="secondary-button"><ArrowLeft size={17} /> Map</Link>
          <button className="secondary-button" onClick={() => { sessionStorage.removeItem('unmapped-admin-token'); setToken('') }}><LogOut size={17} /> Sign out</button>
        </div>
      </header>
      {error && <div className="alert alert--error" role="alert">{error}</div>}
      <div className="admin-workspace-body">
        <aside className="admin-card admin-tools">
          <div className="section-title">
            <div>
              <p className="eyebrow">One verified walkway</p>
              <h2>{path ? 'Edit the published path' : 'Draw the path'}</h2>
            </div>
          </div>
          <ol className="admin-steps">
            <li className={!fromLandmark || !toLandmark ? 'is-current' : ''}>Pick the start and destination people will search for.</li>
            <li className={drawing ? 'is-current' : ''}>Click the map to trace the walkway, the same way people suggest shortcuts.</li>
            <li className={path && tool === 'hazard' && !pendingPoint ? 'is-current' : ''}>Publish it, then click a point on the green line to drop a hazard.</li>
            <li className={pendingPoint ? 'is-current' : ''}>Fill in the caution, robot notes, and optional photo.</li>
          </ol>
          <div className="admin-tool-toggle">
            <button type="button" className={drawing ? 'selected' : ''} onClick={() => { setTool('draw'); setPendingPoint(undefined); setEditingHazard(null) }}>
              <MapPin size={16} /> Draw path
            </button>
            <button type="button" className={!drawing ? 'selected' : ''} disabled={!path} onClick={() => setTool('hazard')}>
              <Pencil size={16} /> Add hazard
            </button>
          </div>
          <label>
            Start
            <select value={fromLandmark} onChange={(event) => setFromLandmark(event.target.value)} required>
              <option value="">Choose a starting place</option>
              {landmarks.map((place) => (
                <option key={place.id} value={place.id}>{place.name}</option>
              ))}
            </select>
          </label>
          <label>
            Destination
            <select value={toLandmark} onChange={(event) => setToLandmark(event.target.value)} required>
              <option value="">Choose a destination</option>
              {landmarks.map((place) => (
                <option key={`to-${place.id}`} value={place.id}>{place.name}</option>
              ))}
            </select>
          </label>
          <label>
            Path name
            <input value={pathName} onChange={(event) => setPathName(event.target.value)} placeholder="Optional label" />
          </label>
          <p className="admin-help">
            {drawing
              ? `${points.length} point${points.length === 1 ? '' : 's'} on the map. Click to add, undo to step back.`
              : 'Click the green path — or an existing yellow bubble — to edit a hazard.'}
          </p>
          {drawing && (
            <div className="submission-actions">
              <button type="button" className="secondary-button" onClick={() => setPoints((current) => current.slice(0, -1))} disabled={!points.length}>
                <Undo2 size={16} /> Undo
              </button>
              <button type="button" className="reject-button" onClick={() => setPoints([])} disabled={!points.length}>
                <X size={16} /> Clear
              </button>
            </div>
          )}
          <button className="primary-button" onClick={publishPath} disabled={loading || points.length < 2 || !fromLandmark || !toLandmark}>
            {path ? 'Replace verified path' : 'Publish verified path'}
          </button>
          {path && (
            <div className="submission-actions">
              <button type="button" className="secondary-button" onClick={startNewPath} disabled={loading}>
                <Plus size={16} /> Draw new path
              </button>
              <button type="button" className="reject-button" onClick={removePath} disabled={loading}>
                <Trash2 size={16} /> Delete path
              </button>
            </div>
          )}
          {pendingPoint && (
            <form className="admin-form" onSubmit={saveHazard}>
              <p className="eyebrow">{editingHazard ? 'Edit hazard' : 'New hazard'}</p>
              <label>Title<input value={hazardForm.title} onChange={(event) => setHazardForm((current) => ({ ...current, title: event.target.value }))} required /></label>
              <label>When it applies
                <select value={hazardForm.active_when} onChange={(event) => setHazardForm((current) => ({ ...current, active_when: event.target.value as typeof hazardForm.active_when }))}>
                  <option value="always">Day and night</option>
                  <option value="day">Day only</option>
                  <option value="night">Night only</option>
                </select>
              </label>
              <label>Kind
                <select value={hazardForm.kind} onChange={(event) => setHazardForm((current) => ({ ...current, kind: event.target.value }))}>
                  <option value="roughness">Roughness</option>
                  <option value="lighting">Lighting</option>
                  <option value="slope">Slope</option>
                  <option value="closure">Closure</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label>Severity
                <select value={hazardForm.severity} onChange={(event) => setHazardForm((current) => ({ ...current, severity: Number(event.target.value) }))}>
                  <option value={1}>Low</option>
                  <option value={2}>Medium</option>
                  <option value={3}>High</option>
                </select>
              </label>
              <label>What people should know<textarea value={hazardForm.description} onChange={(event) => setHazardForm((current) => ({ ...current, description: event.target.value }))} rows={3} /></label>
              <label>Robot insights<textarea value={hazardForm.robot_note} onChange={(event) => setHazardForm((current) => ({ ...current, robot_note: event.target.value }))} rows={4} /></label>
              <label>Evidence photo<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setHazardPhoto(event.target.files?.[0])} /></label>
              <button className="primary-button" disabled={loading}>{editingHazard ? 'Save hazard' : 'Add hazard'}</button>
              {editingHazard && <button type="button" className="reject-button" onClick={removeHazard} disabled={loading}>Delete hazard</button>}
            </form>
          )}
          {(path?.hazards.length || 0) > 0 && !pendingPoint && (
            <ul className="hazard-admin-list">
              {path?.hazards.map((hazard) => (
                <li key={hazard.id}>
                  <button type="button" className="text-button" onClick={() => editHazard(hazard)}>
                    <strong>{hazard.title}</strong>
                    <small>{hazard.active_when === 'always' ? 'Day & night' : hazard.active_when === 'night' ? 'Night only' : 'Day only'}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        <section className="admin-map-full" aria-label="Verified path editor">
          <MapView
            suggestionPoints={drawing ? points : []}
            suggestionMode={drawing}
            verifiedPath={!drawing ? publishedGeometry : []}
            showCampus
            showGraph
            editableHazards={mapHazards}
            selectedHazardId={editingHazard?.id}
            onSuggestionPoint={(point) => setPoints((current) => [...current, point])}
            onMapClick={tool === 'hazard' ? startHazardAt : undefined}
            onHazardClick={editHazard}
          />
          {drawing && (
            <div className="map-instruction">
              <MapPin size={18} />
              <span>
                <strong>Draw the robot-verified path</strong>
                Click 2+ points along the walkway · {points.length} added
              </span>
              <button className="text-button" onClick={() => setPoints((current) => current.slice(0, -1))} disabled={!points.length}>Undo</button>
            </div>
          )}
          {tool === 'hazard' && !pendingPoint && (
            <div className="map-instruction">
              <Pencil size={18} />
              <span>
                <strong>Place a hazard</strong>
                Click a point on the green path, or an existing bubble to edit it
              </span>
            </div>
          )}
        </section>
      </div>
      <section className="admin-card admin-queue">
        <div className="section-title"><div><p className="eyebrow">Community queue</p><h2>Route suggestions</h2></div><RefreshCw size={20} /></div>
        {loading && !submissions.length ? <div className="empty-state">Loading submissions…</div> : !submissions.length ? <div className="empty-state">No suggestions have arrived yet.</div> : (
          <div className="submission-list">
            {submissions.map((item) => (
              <article className="submission" key={item.id}>
                <div className="submission-top"><span className={`status status--${item.status}`}>{item.status}</span><time>{new Date(item.createdAt).toLocaleDateString()}</time></div>
                <h3>{item.description}</h3><p>{item.reason}</p><small>{item.reference} · {item.coordinates.length} points</small>
                {item.status === 'pending' && <div className="submission-actions">
                  <button className="approve-button" onClick={() => setStatus(item.id, 'approved')}><Check size={16} /> Approve</button>
                  <button className="reject-button" onClick={() => setStatus(item.id, 'rejected')}><X size={16} /> Reject</button>
                </div>}
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
