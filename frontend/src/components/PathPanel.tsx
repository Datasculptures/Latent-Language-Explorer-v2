/**
 * PathPanel
 * Two-term input → POST /api/path → CatmullRom TubeGeometry in scene.
 * N/P keys step through waypoints; Esc clears.
 */
import { useState } from 'react'
import { SceneManager }    from '../scene/SceneManager'
import { findConceptPath } from '../api/client'
import type { PathResult } from '../types'

export default function PathPanel() {
  const [termA,   setTermA]   = useState('')
  const [termB,   setTermB]   = useState('')
  const [result,  setResult]  = useState<PathResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const [open,    setOpen]    = useState(false)

  const findPath = async () => {
    if (!termA.trim() || !termB.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    SceneManager.getInstance().clearConceptPath()
    try {
      const r = await findConceptPath({ term_a: termA.trim(), term_b: termB.trim() })
      setResult(r)
      SceneManager.getInstance().drawConceptPath(r)
    } catch (e: any) {
      setError(e?.message ?? String(e))
    } finally {
      setLoading(false)
    }
  }

  const clear = () => {
    SceneManager.getInstance().clearConceptPath()
    setResult(null)
    setError('')
  }

  const exportPath = () => {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `path_${result.term_a}_${result.term_b}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{
      position:'absolute', bottom:'1rem', left:'1rem',
      background:'rgba(10,10,15,0.92)', border:'1px solid #222',
      borderRadius:'4px', zIndex:10,
      minWidth: open ? '220px' : 'auto',
    }}>
      {/* Header / toggle */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          padding:'0.4rem 0.75rem', cursor:'pointer',
          fontSize:'0.7rem', color:'#555',
          textTransform:'uppercase', letterSpacing:'0.08em',
          display:'flex', alignItems:'center', gap:'0.4rem',
        }}>
        <span style={{ color: open ? '#888' : '#444' }}>▶</span>
        Concept Path
        {result && !open && (
          <span style={{ color:'#555', marginLeft:'0.3rem' }}>
            ({result.step_count} steps)
          </span>
        )}
      </div>

      {open && (
        <div style={{ padding:'0 0.75rem 0.75rem' }}>
          <input
            value={termA}
            onChange={e => setTermA(e.target.value)}
            placeholder="Start concept"
            style={inputStyle}
            onKeyDown={e => e.key === 'Enter' && findPath()}
          />
          <input
            value={termB}
            onChange={e => setTermB(e.target.value)}
            placeholder="End concept"
            style={{ ...inputStyle, marginTop:'0.4rem' }}
            onKeyDown={e => e.key === 'Enter' && findPath()}
          />
          <button onClick={findPath} disabled={loading} style={btnStyle}>
            {loading ? 'Finding…' : 'Find Path'}
          </button>

          {error && (
            <div style={{ fontSize:'0.7rem', color:'#e05050', marginTop:'0.4rem' }}>
              {error}
            </div>
          )}

          {result && (
            <div style={{ marginTop:'0.6rem', fontSize:'0.72rem', color:'#777' }}>
              <div style={{ color:'#aaa', marginBottom:'0.3rem' }}>
                {result.term_a} → {result.term_b}
              </div>
              <div style={{ color:'#555' }}>
                {result.step_count} steps · length {result.total_length.toFixed(3)}
              </div>

              {/* Intermediate concepts (skip first/last) */}
              {result.steps.length > 2 && (
                <div style={{ marginTop:'0.4rem', maxHeight:'100px', overflowY:'auto' }}>
                  {result.steps.slice(1, -1).map((s, i) => (
                    <div key={i} style={{
                      fontSize:'0.68rem', color:'#555', padding:'0.1rem 0',
                      cursor:'pointer',
                    }}
                      onClick={() => {
                        const sm  = SceneManager.getInstance()
                        const pos = sm.umapToScene(s.position_2d[0], s.position_2d[1])
                        sm.flyTo(pos, 600)
                      }}>
                      {i + 1}. {s.term}
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display:'flex', gap:'0.4rem', marginTop:'0.5rem' }}>
                <button onClick={exportPath} style={btnSmall}>Export JSON</button>
                <button onClick={clear}      style={btnSmall}>Clear</button>
              </div>
              <div style={{ fontSize:'0.65rem', color:'#333', marginTop:'0.4rem' }}>
                N / P  step waypoints · Esc clear
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const inputStyle: React.CSSProperties = {
  width:'100%', background:'#111', border:'1px solid #333',
  color:'#e0e0e0', padding:'0.3rem 0.5rem', fontFamily:'monospace',
  fontSize:'0.78rem', borderRadius:'3px', boxSizing:'border-box',
}
const btnStyle: React.CSSProperties = {
  marginTop:'0.5rem', width:'100%', background:'#1a2a3a',
  border:'1px solid #333', color:'#aaa', padding:'0.3rem',
  cursor:'pointer', fontFamily:'monospace', fontSize:'0.78rem',
  borderRadius:'3px',
}
const btnSmall: React.CSSProperties = {
  background:'#111', border:'1px solid #333', color:'#777',
  padding:'0.2rem 0.5rem', cursor:'pointer', fontFamily:'monospace',
  fontSize:'0.68rem', borderRadius:'3px',
}
