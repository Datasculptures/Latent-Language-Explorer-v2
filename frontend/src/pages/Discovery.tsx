import { useState, useEffect } from 'react'
import { SceneManager } from '../scene/SceneManager'
import { useAppStore }  from '../store'
import { fetchJournalEntries, createJournalEntry, describePoint }
  from '../api/client'
import type { JournalEntry } from '../types'

export default function DiscoveryPage() {
  const { setSurfaceMode } = useAppStore()

  const [termA,          setTermA]          = useState('')
  const [termB,          setTermB]          = useState('')
  const [probeResult,    setProbeResult]    = useState<any>(null)
  const [probing,        setProbing]        = useState(false)
  const [probeError,     setProbeError]     = useState('')
  const [description,    setDescription]    = useState('')
  const [describing,     setDescribing]     = useState(false)
  const [journalEntries, setJournalEntries] = useState<JournalEntry[]>([])
  const [journalOpen,    setJournalOpen]    = useState(false)

  // Switch to desert surface mode while on this page
  useEffect(() => {
    setSurfaceMode('desert')
    SceneManager.getInstance().setSurfaceMode('desert')
    return () => {
      setSurfaceMode('density')
      SceneManager.getInstance().setSurfaceMode('density')
    }
  }, [setSurfaceMode])

  // Load journal on mount
  useEffect(() => {
    fetchJournalEntries({ limit: 50 }).then(r => setJournalEntries(r.entries))
  }, [])

  const runProbe = async () => {
    if (!termA.trim() || !termB.trim()) return
    setProbing(true)
    setProbeError('')
    setDescription('')
    setProbeResult(null)
    SceneManager.getInstance().clearProbe()

    try {
      const resp = await fetch('/api/probe', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ term_a: termA.trim(), term_b: termB.trim() }),
      })
      if (!resp.ok) {
        const err = await resp.json()
        setProbeError(err.detail ?? `HTTP ${resp.status}`)
        return
      }
      const result = await resp.json()
      setProbeResult(result)
      SceneManager.getInstance().drawProbe(result)
    } catch (e) {
      setProbeError(String(e))
    } finally {
      setProbing(false)
    }
  }

  const describe = async () => {
    if (!probeResult) return
    setDescribing(true)
    try {
      const step = probeResult.deepest_step
      const resp = await describePoint({
        coordinates_2d:   [0, 0],
        desert_value:     step.desert_value,
        nearest_concepts: step.nearest_concepts ?? [],
        roget_context:    probeResult.category_id_a ? {
          category_a: probeResult.category_id_a,
          category_b: probeResult.category_id_b,
        } : null,
      })
      setDescription(resp.description)
    } catch (e) {
      setDescription(`[Error: ${e}]`)
    } finally {
      setDescribing(false)
    }
  }

  const saveToJournal = async () => {
    if (!probeResult) return
    const step  = probeResult.deepest_step
    const entry = await createJournalEntry({
      type:          'probe_discovery',
      coordinates_2d: [0, 0],
      desert_value:  probeResult.desert_max,
      nearest_concepts: (step.nearest_concepts ?? []).map((c: any) => ({
        term:             c.term,
        distance:         c.distance,
        roget_categories: null,
        roget_class:      c.class_name ?? null,
      })),
      generated_description: description || null,
      user_notes: `${probeResult.term_a} ↔ ${probeResult.term_b}`,
      tags: ['probe_discovery'],
    })
    setJournalEntries(prev => [entry, ...prev])
    SceneManager.getInstance().addJournalMarker(entry)
  }

  const depthLabel = (d: number) =>
    d >= 0.05 ? '⬛ DEEP' : d >= 0.02 ? '▪ shallow' : '· flat'

  return (
    <>
      {/* Probe panel */}
      <div style={{
        position:'absolute', top:'1rem', left:'1rem',
        background:'rgba(10,10,15,0.94)', border:'1px solid #222',
        padding:'0.75rem', borderRadius:'4px', width:'260px',
        zIndex:10,
      }}>
        <div style={{ fontSize:'0.7rem', color:'#555', marginBottom:'0.5rem',
                      textTransform:'uppercase', letterSpacing:'0.08em' }}>
          Interpolation Probe
        </div>

        <input
          value={termA}
          onChange={e => setTermA(e.target.value)}
          placeholder="Term A"
          style={inputStyle}
          onKeyDown={e => e.key === 'Enter' && runProbe()}
        />
        <input
          value={termB}
          onChange={e => setTermB(e.target.value)}
          placeholder="Term B"
          style={{ ...inputStyle, marginTop:'0.4rem' }}
          onKeyDown={e => e.key === 'Enter' && runProbe()}
        />
        <button
          onClick={runProbe}
          disabled={probing}
          style={btnStyle}>
          {probing ? 'Probing...' : 'Run Probe'}
        </button>

        {probeError && (
          <div style={{ fontSize:'0.7rem', color:'#e05050', marginTop:'0.4rem' }}>
            {probeError}
          </div>
        )}

        {probeResult && (
          <div style={{ marginTop:'0.75rem', fontSize:'0.75rem', color:'#aaa' }}>
            <div style={{ marginBottom:'0.3rem' }}>
              <span style={{ color: probeResult.desert_max >= 0.05
                               ? '#ff4400' : '#888' }}>
                {depthLabel(probeResult.desert_max)}
              </span>
              {' '}desert_max = {probeResult.desert_max.toFixed(4)}
            </div>
            <div style={{ color:'#555', fontSize:'0.7rem' }}>
              deepest near:{' '}
              <span style={{ color:'#aaa' }}>
                {probeResult.deepest_step?.nearest_term}
              </span>
            </div>
            <div style={{ color:'#555', fontSize:'0.7rem' }}>
              measured in: {probeResult.measurement_space}
            </div>

            <div style={{ display:'flex', gap:'0.4rem', marginTop:'0.6rem' }}>
              <button onClick={describe} disabled={describing} style={btnSmall}>
                {describing ? '...' : 'Describe'}
              </button>
              <button onClick={saveToJournal} style={btnSmall}>
                + Journal
              </button>
            </div>

            {description && (
              <div style={{ marginTop:'0.5rem', fontSize:'0.72rem',
                            color:'#ccc', fontStyle:'italic',
                            borderLeft:'2px solid #333', paddingLeft:'0.4rem' }}>
                {description}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Journal toggle */}
      <button
        onClick={() => setJournalOpen(o => !o)}
        style={{
          position:'absolute', top:'1rem', right:'1rem',
          ...btnStyle, width:'auto', padding:'0.3rem 0.75rem',
        }}>
        Journal ({journalEntries.length})
      </button>

      {/* Journal panel */}
      {journalOpen && (
        <div style={{
          position:'absolute', top:'3rem', right:'1rem',
          background:'rgba(10,10,15,0.96)', border:'1px solid #222',
          padding:'0.75rem', borderRadius:'4px', width:'280px',
          maxHeight:'60vh', overflowY:'auto', zIndex:20,
        }}>
          <div style={{ fontSize:'0.7rem', color:'#555', marginBottom:'0.5rem',
                        textTransform:'uppercase', letterSpacing:'0.08em' }}>
            Field Journal
          </div>
          {journalEntries.length === 0 && (
            <div style={{ fontSize:'0.75rem', color:'#444' }}>No entries yet.</div>
          )}
          {journalEntries.map(e => (
            <div key={e.id} style={{
              borderBottom:'1px solid #1a1a1a', paddingBottom:'0.5rem',
              marginBottom:'0.5rem', fontSize:'0.72rem', color:'#888',
            }}>
              <div style={{ color: e.desert_value >= 0.05 ? '#ff6644' : '#aaa' }}>
                {e.user_notes || '(no notes)'}
              </div>
              <div style={{ color:'#444', fontSize:'0.65rem' }}>
                desert={e.desert_value.toFixed(4)} · {e.type}
              </div>
              {e.generated_description && (
                <div style={{ color:'#666', fontStyle:'italic', marginTop:'0.2rem' }}>
                  {e.generated_description.slice(0, 120)}...
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}

const inputStyle: React.CSSProperties = {
  width:'100%', background:'#111', border:'1px solid #333',
  color:'#e0e0e0', padding:'0.3rem 0.5rem', fontFamily:'monospace',
  fontSize:'0.8rem', borderRadius:'3px', boxSizing:'border-box',
}
const btnStyle: React.CSSProperties = {
  marginTop:'0.5rem', width:'100%', background:'#1a2a3a',
  border:'1px solid #333', color:'#aaa', padding:'0.35rem',
  cursor:'pointer', fontFamily:'monospace', fontSize:'0.8rem',
  borderRadius:'3px',
}
const btnSmall: React.CSSProperties = {
  background:'#111', border:'1px solid #333', color:'#888',
  padding:'0.2rem 0.5rem', cursor:'pointer', fontFamily:'monospace',
  fontSize:'0.7rem', borderRadius:'3px',
}
