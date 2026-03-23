import { useAppStore } from './store'
import { useEffect } from 'react'
import { fetchHealth } from './api/client'

export default function App() {
  const { activePage, setActivePage } = useAppStore()

  useEffect(() => {
    fetchHealth()
      .then(h => console.log('Backend:', h.status, h.version))
      .catch(e => console.warn('Backend not reachable:', e.message))
  }, [])

  return (
    <div style={{ padding: '2rem', fontFamily: 'monospace', color: '#e0e0e0' }}>
      <h1 style={{ fontSize: '1.2rem', marginBottom: '1rem', color: '#00b4d8' }}>
        Latent Language Explorer V2
      </h1>
      <p style={{ marginBottom: '1rem', color: '#888' }}>Phase 0 scaffold — pipeline not yet run.</p>
      <nav style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
        {(['landscape', 'discovery'] as const).map(page => (
          <button
            key={page}
            onClick={() => setActivePage(page)}
            style={{
              background: activePage === page ? '#00b4d8' : '#1a1a2e',
              color: activePage === page ? '#000' : '#e0e0e0',
              border: '1px solid #333',
              padding: '0.5rem 1rem',
              cursor: 'pointer',
              fontFamily: 'monospace',
            }}
          >
            {page}
          </button>
        ))}
      </nav>
      <div style={{ color: '#888', fontSize: '0.85rem' }}>
        Active page: <span style={{ color: '#4ecb71' }}>{activePage}</span>
      </div>
    </div>
  )
}
