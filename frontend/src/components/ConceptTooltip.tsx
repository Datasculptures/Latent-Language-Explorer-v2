/**
 * ConceptTooltip
 * Raycasts against concept spheres and Voronoi vertices on mousemove and
 * shows a floating detail panel near the cursor.
 *
 * Throttled to one raycast per animation frame.
 */
import { useState, useEffect, useRef } from 'react'
import { SceneManager } from '../scene/SceneManager'
import { ROGET_CLASS_COLOURS } from '../types'
import type { Concept, VoronoiVertex, RogetClassId } from '../types'
import { useAppStore } from '../store'

type HitConcept  = { kind: 'concept';  data: Concept }
type HitVoronoi  = { kind: 'voronoi';  data: VoronoiVertex }
type HitVariant  = { kind: 'variant';  data: { concept: any; contextKey: string; distFromBase: number } }
type Hit = HitConcept | HitVoronoi | HitVariant | null

const OFFSET_X = 16
const OFFSET_Y = -8
const PANEL_W  = 220

export default function ConceptTooltip() {
  const [hit,      setHit]      = useState<Hit>(null)
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 })
  const pendingRef = useRef<{ x: number; y: number } | null>(null)
  const rafRef     = useRef<number>(0)
  const { atmosphereOn } = useAppStore()

  useEffect(() => {
    const onMove  = (e: MouseEvent) => { pendingRef.current = { x: e.clientX, y: e.clientY } }
    const onLeave = () => setHit(null)

    const tick = () => {
      rafRef.current = requestAnimationFrame(tick)
      const pos = pendingRef.current
      if (!pos) return
      pendingRef.current = null
      setMousePos(pos)

      const sm = SceneManager.getInstance()

      // Check variant spheres first (they sit above base spheres)
      if (useAppStore.getState().atmosphereOn) {
        const variant = sm.pickVariant(pos.x, pos.y)
        if (variant) { setHit({ kind: 'variant', data: variant }); return }
      }

      const concept = sm.pickConcept(pos.x, pos.y) as Concept | null
      if (concept) { setHit({ kind: 'concept', data: concept }); return }
      const vor = sm.pickVoronoi(pos.x, pos.y) as VoronoiVertex | null
      if (vor)     { setHit({ kind: 'voronoi', data: vor });     return }
      setHit(null)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseleave', onLeave)
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseleave', onLeave)
      cancelAnimationFrame(rafRef.current)
    }
  }, [])

  if (!hit) return null

  const vpW  = window.innerWidth
  const vpH  = window.innerHeight
  const left = mousePos.x + OFFSET_X + PANEL_W > vpW
    ? mousePos.x - OFFSET_X - PANEL_W
    : mousePos.x + OFFSET_X
  const top  = Math.max(8, Math.min(mousePos.y + OFFSET_Y, vpH - 200))

  const panelBase: React.CSSProperties = {
    position:'fixed', left, top, width:`${PANEL_W}px`,
    background:'rgba(10,10,15,0.95)',
    borderRadius:'4px', padding:'0.6rem 0.75rem',
    pointerEvents:'none', zIndex:500, fontFamily:'monospace',
  }

  // ── Base concept sphere ──────────────────────────────────────────────
  if (hit.kind === 'concept') {
    const c           = hit.data
    const classColour = ROGET_CLASS_COLOURS[c.roget_class_id as RogetClassId] ?? '#888'

    // Find most divergent context (excluding neutral, index 6)
    let mostDivergentKey = ''
    if (Array.isArray(c.contexts) && c.contexts.length === 7) {
      let maxDist = -Infinity
      for (let ci = 0; ci < 6; ci++) {
        const d = c.contexts[ci]?.distance_from_base ?? 0
        if (d > maxDist) { maxDist = d; mostDivergentKey = c.contexts[ci]?.roget_class_context ?? '' }
      }
    }

    return (
      <div style={{
        ...panelBase,
        border:`1px solid ${classColour}44`, borderLeft:`3px solid ${classColour}`,
      }}>
        <div style={{ fontSize:'0.9rem', fontWeight:'bold', color:classColour, marginBottom:'0.3rem' }}>
          {c.label}
        </div>
        <div style={{ fontSize:'0.72rem', color:'#666', marginBottom:'0.15rem' }}>{c.roget_class_name}</div>
        <div style={{ fontSize:'0.72rem', color:'#555' }}>
          {c.roget_section_name && <span>{c.roget_section_name} › </span>}
          {c.roget_category_name}
        </div>
        {c.is_polysemous && (
          <div style={{ marginTop:'0.3rem', fontSize:'0.68rem', color:'#444' }}>
            {c.all_roget_categories.length} categories
          </div>
        )}
        {c.is_modern_addition && (
          <div style={{ marginTop:'0.25rem', fontSize:'0.65rem', color:'#4ecb71', opacity:0.7 }}>
            modern addition
          </div>
        )}
        {/* Polysemy info — always shown when data is present */}
        {c.context_spread != null && (
          <div style={{ marginTop:'0.4rem', borderTop:'1px solid #1a1a2a', paddingTop:'0.35rem' }}>
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:'0.68rem', color:'#555', marginBottom:'0.1rem' }}>
              <span>Context spread</span>
              <span style={{ color:'#444' }}>{c.context_spread.toFixed(4)}</span>
            </div>
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:'0.68rem', color:'#555', marginBottom:'0.1rem' }}>
              <span>Polysemy</span>
              <span style={{ color:'#444' }}>{((c.polysemy_score ?? 0) * 100).toFixed(0)}%</span>
            </div>
            {atmosphereOn && mostDivergentKey && (
              <div style={{ fontSize:'0.65rem', color:'#3a3a5a', marginTop:'0.15rem' }}>
                Divergent: {mostDivergentKey}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  // ── Context variant sphere ───────────────────────────────────────────
  if (hit.kind === 'variant') {
    const { concept: c, contextKey, distFromBase } = hit.data
    const classColour = ROGET_CLASS_COLOURS[c.roget_class_id as RogetClassId] ?? '#888'
    return (
      <div style={{
        ...panelBase,
        border:`1px solid ${classColour}33`, borderLeft:`3px solid ${classColour}88`,
      }}>
        <div style={{ fontSize:'0.72rem', color:'#555', marginBottom:'0.25rem', textTransform:'uppercase', letterSpacing:'0.05em' }}>
          context variant
        </div>
        <div style={{ fontSize:'0.88rem', fontWeight:'bold', color:classColour, marginBottom:'0.2rem' }}>
          {c.label}
        </div>
        <div style={{ fontSize:'0.72rem', color:'#555', marginBottom:'0.15rem' }}>
          Context: {contextKey}
        </div>
        <div style={{ fontSize:'0.7rem', color:'#444' }}>
          Distance from base: {distFromBase.toFixed(4)}
        </div>
      </div>
    )
  }

  // ── Voronoi vertex ───────────────────────────────────────────────────
  const v = hit.data as VoronoiVertex
  return (
    <div style={{
      ...panelBase,
      border:'1px solid #ffffff22', borderLeft:'3px solid #ffffff66',
    }}>
      <div style={{ fontSize:'0.85rem', fontWeight:'bold', color:'#ccc', marginBottom:'0.3rem' }}>
        Voronoi vertex #{v.rank}
      </div>
      <div style={{ fontSize:'0.72rem', color:'#666', marginBottom:'0.2rem' }}>
        equidistance {v.equidistance.toFixed(4)}
      </div>
      {v.parents.slice(0, 3).map((p, i) => (
        <div key={i} style={{ fontSize:'0.7rem', color:'#555', marginTop:'0.1rem' }}>
          {p.term}
          <span style={{ color:'#333' }}> · {p.category_name}</span>
        </div>
      ))}
    </div>
  )
}
