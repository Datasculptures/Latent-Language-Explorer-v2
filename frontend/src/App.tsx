import { useEffect, useRef, useState } from 'react'
import { SceneManager } from './scene/SceneManager'
import { loadSceneData } from './scene/dataLoader'
import { useAppStore } from './store'
import LandscapePage from './pages/Landscape'
import DiscoveryPage from './pages/Discovery'
import JournalPage   from './pages/Journal'

export default function App() {
  const canvasRef                       = useRef<HTMLCanvasElement>(null)
  const { activePage, setActivePage }   = useAppStore()
  const [loadState, setLoadState]       = useState<'loading'|'ready'|'no_pipeline'|'error'>('loading')
  const [conceptCount, setConceptCount] = useState(0)

  useEffect(() => {
    if (!canvasRef.current) return
    SceneManager.getInstance().init(canvasRef.current)
    loadSceneData().then(result => {
      if (result.ok) {
        setConceptCount(result.concepts)
        setLoadState('ready')
      } else if (result.error === 'pipeline_not_run') {
        setLoadState('no_pipeline')
      } else {
        setLoadState('error')
      }
    })
  }, [])

  return (
    <div style={{ width:'100vw', height:'100vh', overflow:'hidden',
                  background:'#0a0a0f', color:'#e0e0e0', fontFamily:'monospace',
                  display:'flex', flexDirection:'column' }}>

      {/* Navigation bar */}
      <nav style={{ display:'flex', alignItems:'center', gap:'1rem',
                    padding:'0.5rem 1rem', borderBottom:'1px solid #222',
                    background:'rgba(10,10,15,0.95)', zIndex:100, flexShrink:0 }}>
        <span style={{ color:'#00b4d8', fontSize:'0.85rem', fontWeight:'bold' }}>
          LLE v2
        </span>
        {(['landscape','discovery','journal'] as const).map(page => (
          <button key={page}
            onClick={() => setActivePage(page)}
            style={{
              background: activePage === page ? '#00b4d8' : 'transparent',
              color:      activePage === page ? '#000'    : '#888',
              border:     '1px solid #333',
              padding:    '0.25rem 0.75rem',
              cursor:     'pointer',
              fontFamily: 'monospace',
              fontSize:   '0.8rem',
            }}>
            {page}
          </button>
        ))}
        <span style={{ marginLeft:'auto', fontSize:'0.75rem', color:'#444' }}>
          {loadState === 'ready'        ? `${conceptCount.toLocaleString()} concepts` :
           loadState === 'loading'      ? 'loading...' :
           loadState === 'no_pipeline'  ? 'pipeline not run' : 'load error'}
        </span>
      </nav>

      {/* Canvas -- always mounted, never removed */}
      <div style={{ position:'relative', flex:1 }}>
        <canvas ref={canvasRef}
          style={{
            position:'absolute', inset:0, width:'100%', height:'100%',
            // Hide canvas on journal page — keep it mounted so 3D state is preserved
            visibility: activePage === 'journal' ? 'hidden' : 'visible',
          }}
        />

        {/* Page UI panels -- layered over canvas */}
        {activePage === 'landscape' && loadState === 'ready' && <LandscapePage />}
        {activePage === 'discovery' && loadState === 'ready' && <DiscoveryPage />}
        {activePage === 'journal'   && <JournalPage />}

        {/* Status overlays */}
        {loadState === 'no_pipeline' && (
          <div style={{ position:'absolute', top:'50%', left:'50%',
                        transform:'translate(-50%,-50%)', textAlign:'center',
                        color:'#666', fontSize:'0.9rem' }}>
            <div>Pipeline not run.</div>
            <div style={{ fontSize:'0.75rem', marginTop:'0.5rem', color:'#444' }}>
              Run scripts/assemble_bundle.py to generate terrain data.
            </div>
          </div>
        )}
        {loadState === 'loading' && (
          <div style={{ position:'absolute', top:'50%', left:'50%',
                        transform:'translate(-50%,-50%)', color:'#444' }}>
            Loading terrain...
          </div>
        )}
      </div>
    </div>
  )
}
