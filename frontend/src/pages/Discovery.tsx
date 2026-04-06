import { useState, useEffect, useRef } from 'react'
import { SceneManager } from '../scene/SceneManager'
import { useAppStore }  from '../store'
import { fetchJournalEntries, createJournalEntry, describePoint,
         fetchVoronoiVertices }
  from '../api/client'
import type { JournalEntry, VoronoiVertex } from '../types'

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

  // Absence Catalogue
  const [absenceOpen,     setAbsenceOpen]     = useState(false)
  const [voronoiVerts,    setVoronoiVerts]    = useState<VoronoiVertex[]>([])
  const [absenceLoading,  setAbsenceLoading]  = useState(false)
  const [absenceDesc,     setAbsenceDesc]     = useState<Record<string, string>>({})
  const [absenceDescBusy, setAbsenceDescBusy] = useState<string | null>(null)
  const absenceLoadedRef = useRef(false)

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

  const openAbsenceCatalogue = async () => {
    setAbsenceOpen(o => !o)
    if (absenceLoadedRef.current) return
    setAbsenceLoading(true)
    try {
      const { vertices } = await fetchVoronoiVertices()
      // Top 50 by equidistance (already ranked; rank 1 = highest)
      const top50 = [...vertices].sort((a, b) => a.rank - b.rank).slice(0, 50)
      setVoronoiVerts(top50)
      absenceLoadedRef.current = true
    } finally {
      setAbsenceLoading(false)
    }
  }

  const describeVoronoi = async (v: VoronoiVertex) => {
    if (absenceDescBusy) return
    setAbsenceDescBusy(v.id)
    try {
      const nearest = v.parents.map(p => ({
        term:             p.term,
        distance:         p.distance,
        roget_categories: [p.category_name],
        roget_class:      p.class_name ?? null,
      }))
      const resp = await describePoint({
        coordinates_2d:   [v.x, v.y],
        desert_value:     v.mean_dist,
        nearest_concepts: nearest,
      })
      setAbsenceDesc(d => ({ ...d, [v.id]: resp.description }))
      // Auto-save to journal
      const entry = await createJournalEntry({
        type:                 'voronoi',
        coordinates_2d:       [v.x, v.y],
        desert_value:         v.mean_dist,
        nearest_concepts:     nearest,
        generated_description: resp.description,
      })
      setJournalEntries(prev => [entry, ...prev])
    } catch (e) {
      setAbsenceDesc(d => ({ ...d, [v.id]: `[Error: ${e}]` }))
    } finally {
      setAbsenceDescBusy(null)
    }
  }

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

      {/* Absence Catalogue toggle */}
      <button
        onClick={openAbsenceCatalogue}
        style={{
          position:'absolute', top:'1rem', right:'1rem',
          ...btnStyle, width:'auto', padding:'0.3rem 0.75rem',
        }}>
        {absenceOpen ? 'Hide Absences' : 'Absence Catalogue'}
      </button>

      {/* Absence Catalogue panel */}
      {absenceOpen && (
        <div style={{
          position:'absolute', top:'3rem', right:'1rem',
          background:'rgba(10,10,15,0.96)', border:'1px solid #222',
          padding:'0.75rem', borderRadius:'4px', width:'300px',
          maxHeight:'70vh', overflowY:'auto', zIndex:20,
        }}>
          <div style={{ fontSize:'0.7rem', color:'#555', marginBottom:'0.5rem',
                        textTransform:'uppercase', letterSpacing:'0.08em' }}>
            Absence Catalogue — top 50 voids
          </div>
          {absenceLoading && (
            <div style={{ fontSize:'0.75rem', color:'#444' }}>Loading…</div>
          )}
          {voronoiVerts.map(v => (
            <div key={v.id} style={{
              borderBottom:'1px solid #1a1a1a', paddingBottom:'0.5rem',
              marginBottom:'0.5rem',
            }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline' }}>
                <span style={{ fontSize:'0.72rem', color:'#888' }}>
                  #{v.rank}
                  <span style={{ color:'#555', marginLeft:'0.4rem' }}>
                    eq={v.equidistance.toFixed(4)}
                  </span>
                </span>
                <div style={{ display:'flex', gap:'0.3rem' }}>
                  <button
                    onClick={() => {
                      const sm = SceneManager.getInstance()
                      const pos = sm.umapToScene(v.x, v.y)
                      sm.flyTo(pos)
                    }}
                    style={btnSmall}>Fly To</button>
                  <button
                    onClick={() => describeVoronoi(v)}
                    disabled={absenceDescBusy === v.id}
                    style={btnSmall}>
                    {absenceDescBusy === v.id ? '…' : 'Describe'}
                  </button>
                </div>
              </div>
              <div style={{ fontSize:'0.68rem', color:'#555', marginTop:'0.2rem' }}>
                {v.parents.slice(0, 3).map(p => p.term).join(', ')}
              </div>
              {absenceDesc[v.id] && (
                <div style={{ fontSize:'0.68rem', color:'#777', fontStyle:'italic',
                              marginTop:'0.3rem', borderLeft:'2px solid #222',
                              paddingLeft:'0.4rem' }}>
                  {absenceDesc[v.id]}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Journal toggle */}
      <button
        onClick={() => setJournalOpen(o => !o)}
        style={{
          position:'absolute', top:'1rem', right:'calc(1rem + 180px)',
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
