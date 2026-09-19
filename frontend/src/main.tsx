import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

// Mocks are on with VITE_USE_MOCKS=true, or ?mock=1 in the URL (works on the deployed site too).
async function enableMocks() {
  const useMocks =
    import.meta.env.VITE_USE_MOCKS === 'true' || new URLSearchParams(location.search).get('mock') === '1'
  if (!useMocks) return
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledRequest: 'bypass', quiet: true })
  console.info('[mocks] Mock backend is on')
}

enableMocks().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  )
})
