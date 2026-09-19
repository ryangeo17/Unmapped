import { useEffect, useState } from 'react'
import { ArrowLeft, Check, Database, LogOut, Play, RefreshCw, ShieldCheck, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from './api'
import MapView from './MapView'
import type { GraphJob, Submission, SubmissionStatus } from './types'

export default function AdminPage() {
  const [token, setToken] = useState(() => sessionStorage.getItem('unmapped-admin-token') || '')
  const [password, setPassword] = useState('')
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [job, setJob] = useState<GraphJob>()
  const [demoClosure, setDemoClosure] = useState(false)
  const [selectedSubmissionId, setSelectedSubmissionId] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) return
    setLoading(true)
    api
      .getSubmissions(token)
      .then(setSubmissions)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [token])

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

  async function createJob() {
    setLoading(true)
    setError('')
    try {
      setJob(await api.createGraphJob(token))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create graph job')
    } finally {
      setLoading(false)
    }
  }

  async function runJob(action: 'simulate' | 'publish') {
    if (!job) return
    setLoading(true)
    try {
      setJob(action === 'simulate' ? await api.simulateGraphJob(job.id, token) : await api.publishGraphJob(job.id, token))
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not ${action} graph`)
    } finally {
      setLoading(false)
    }
  }

  async function toggleDemoClosure() {
    setLoading(true)
    setError('')
    try {
      const result = await api.setDemoClosure(!demoClosure, token)
      setDemoClosure(result.closed)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update the demo closure')
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
          <p>Review community suggestions and publish approved routing graph updates.</p>
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

  const selectedSubmission =
    submissions.find((item) => item.id === selectedSubmissionId)
    || submissions.find((item) => item.coordinates.length > 1)

  return (
    <main className="admin-page">
      <header className="admin-header">
        <div>
          <p className="eyebrow">UnMapped operations</p>
          <h1>Route review dashboard</h1>
        </div>
        <div className="header-actions">
          <Link to="/" className="secondary-button"><ArrowLeft size={17} /> Map</Link>
          <button className="secondary-button" onClick={() => { sessionStorage.removeItem('unmapped-admin-token'); setToken('') }}><LogOut size={17} /> Sign out</button>
        </div>
      </header>
      {error && <div className="alert alert--error" role="alert">{error}</div>}
      <section className="admin-stats" aria-label="Submission summary">
        <div><strong>{submissions.length}</strong><span>Total suggestions</span></div>
        <div><strong>{submissions.filter((item) => item.status === 'pending').length}</strong><span>Awaiting review</span></div>
        <div><strong>{submissions.filter((item) => item.status === 'approved').length}</strong><span>Approved</span></div>
      </section>
      <div className="admin-grid">
        <section className="admin-card">
          <div className="section-title"><div><p className="eyebrow">Community queue</p><h2>Route suggestions</h2></div><RefreshCw size={20} /></div>
          {loading && !submissions.length ? <div className="empty-state">Loading submissions…</div> : !submissions.length ? <div className="empty-state">No suggestions have arrived yet.</div> : (
            <div className="submission-list">
              {submissions.map((item) => (
                <article className="submission" key={item.id}>
                  <div className="submission-top"><span className={`status status--${item.status}`}>{item.status}</span><time>{new Date(item.createdAt).toLocaleDateString()}</time></div>
                  <h3>{item.description}</h3><p>{item.reason}</p><small>{item.reference} · {item.coordinates.length} points</small>
                  {item.coordinates.length > 1 && <button className="text-button" onClick={() => setSelectedSubmissionId(item.id)}>Inspect trace on map</button>}
                  {item.status === 'pending' && <div className="submission-actions">
                    <button className="approve-button" onClick={() => setStatus(item.id, 'approved')}><Check size={16} /> Approve</button>
                    <button className="reject-button" onClick={() => setStatus(item.id, 'rejected')}><X size={16} /> Reject</button>
                  </div>}
                </article>
              ))}
            </div>
          )}
        </section>
        <section className="admin-card job-card">
          {selectedSubmission && selectedSubmission.coordinates.length > 1 && (
            <div className="admin-map" aria-label={`Submitted trace ${selectedSubmission.reference}`}>
              <MapView
                route={{
                  id: selectedSubmission.id,
                  coordinates: selectedSubmission.coordinates,
                  distanceMeters: 0,
                  durationMinutes: 0,
                  accessibilityScore: 0,
                  safetyScore: 0,
                  verifiedPercent: 0,
                  explanation: '',
                  steps: [],
                  hazards: [],
                }}
                suggestionPoints={[]}
                suggestionMode={false}
                showGraph={false}
                avoidedHazards={[]}
                onAvoidHazard={() => undefined}
                onSuggestionPoint={() => undefined}
              />
            </div>
          )}
          <div className="brand-mark brand-mark--small"><Database size={22} /></div>
          <p className="eyebrow">Graph pipeline</p><h2>Build routing update</h2>
          <p>Compile approved lines, simulate affected routes, then publish the new graph.</p>
          <button className="secondary-button full" onClick={toggleDemoClosure} disabled={loading}>
            {demoClosure ? 'Reopen demo ramp segment' : 'Activate temporary closure'}
          </button>
          <small>{demoClosure ? 'The Recreation Center–MSE ramp is closed and routing will recompute.' : 'Demo closure is currently inactive.'}</small>
          {!job ? <button className="primary-button" onClick={createJob} disabled={loading}>Create graph job</button> : (
            <div className="job">
              <div className="submission-top"><strong>{job.label || `Job ${job.id}`}</strong><span className={`status status--${job.status}`}>{job.status}</span></div>
              <div className="progress-track" aria-label={`${job.progress}% complete`}><span style={{ width: `${job.progress}%` }} /></div>
              <p>{job.progress}% complete</p>
              <button className="secondary-button full" onClick={() => runJob('simulate')} disabled={loading || job.status === 'published'}><Play size={17} /> Simulate routes</button>
              <button className="primary-button" onClick={() => runJob('publish')} disabled={loading || job.status !== 'complete'}>Publish graph</button>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
