import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./MapView', () => ({ default: () => <div data-testid="map">Campus map</div> }))

const overlayResponse = {
  nodes: [
    { id: 'mse', name: 'MSE Library', latitude: 39.3289, longitude: -76.6194 },
    { id: 'gilman', name: 'Gilman Hall', latitude: 39.3283, longitude: -76.6219 },
  ],
  edges: [{ id: 'edge-1', from_node: 'mse', to_node: 'gilman', closed: false, verified: true }],
  hazards: [],
}
const landmarksResponse = [
  {
    id: 'lm-mse',
    node_id: 'mse',
    name: 'MSE Library',
    description: 'Milton S. Eisenhower Library',
    latitude: 39.3289,
    longitude: -76.6194,
  },
  {
    id: 'lm-gilman',
    node_id: 'gilman',
    name: 'Gilman Hall',
    description: 'Humanities hub',
    latitude: 39.3283,
    longitude: -76.6219,
  },
]

const routeResponse = {
  start_node: 'mse',
  end_node: 'gilman',
  geometry: [[-76.6194, 39.3289], [-76.6219, 39.3283]],
  edge_ids: ['edge-1'],
  scores: { accessibility: 92, safety: 88 },
  verified_stats: { distance_m: 540, estimated_seconds: 480, verified_percent: 84 },
  explanation: ['Uses smooth, well-lit paths with curb cuts.'],
  steps: [{ instruction: 'Head west toward the Beach', distance_m: 120 }],
  hazards: [],
}

const response = (body: unknown, ok = true, status = 200) => ({
  ok,
  status,
  json: async () => body,
  text: async () => typeof body === 'string' ? body : JSON.stringify(body),
})

function renderApp() {
  return render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)
}

async function chooseRoute(user: ReturnType<typeof userEvent.setup>) {
  const start = screen.getByPlaceholderText('Where are you now?')
  await user.type(start, 'Eisenhower')
  await user.click(await screen.findByRole('option', { name: /Milton S. Eisenhower Library/i }))
  const destination = screen.getByPlaceholderText('Where are you going?')
  await user.type(destination, 'Gilman')
  await user.click(await screen.findByRole('option', { name: /Gilman Hall/i }))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('route planner', () => {
  it('renders route stats and steps after a successful request', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/graph/overlay')) return Promise.resolve(response(overlayResponse))
      if (url.includes('/landmarks')) return Promise.resolve(response(landmarksResponse))
      return Promise.resolve(response(routeResponse))
    }))
    const user = userEvent.setup()
    renderApp()
    await chooseRoute(user)
    await user.click(screen.getByRole('button', { name: /find my route/i }))

    expect(await screen.findByText('540 m · 8 min')).toBeInTheDocument()
    expect(screen.getByText('92/100')).toBeInTheDocument()
    expect(screen.getByText('Head west toward the Beach')).toBeInTheDocument()
    expect(screen.getByText(/84% verified/i)).toBeInTheDocument()
  })

  it('shows a useful API error without losing the route form', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/graph/overlay')) return Promise.resolve(response(overlayResponse))
      if (url.includes('/landmarks')) return Promise.resolve(response(landmarksResponse))
      return Promise.resolve(response('Routing service is warming up', false, 503))
    }))
    const user = userEvent.setup()
    renderApp()
    await chooseRoute(user)
    await user.click(screen.getByRole('button', { name: /find my route/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Routing service is warming up')
    expect(screen.getByPlaceholderText('Where are you going?')).toHaveValue('Gilman Hall')
    await waitFor(() => expect(screen.getByRole('button', { name: /find my route/i })).toBeEnabled())
  })
})
