/**
 * NearbyConceptsPanel
 * Shows the 8 nearest concepts to the current camera position.
 * Updates every 500ms via setInterval.
 */
import { useState, useEffect } from 'react'
import { SceneManager } from '../scene/SceneManager'
import { ROGET_CLASS_COLOURS } from '../types'
import type { RogetClassId } from '../types'

export default function NearbyConceptsPanel() {
  const [nearby, setNearby] = useState<any[]>([])

  useEffect(() => {
    const id = setInterval(() => {
      setNearby(SceneManager.getInstance().getNearestConcepts(8))
    }, 500)
    return () => clearInterval(id)
  }, [])

  if (!nearby.length) return null

  const flyTo = (c: any) => {
    const sm  = SceneManager.getInstance()
    const pos = sm.umapToScene(c.position_2d[0], c.position_2d[1])
    sm.flyTo(pos)
  }

  return (
    <div style={{
      position:'absolute', bottom:'1rem', left:'1rem',
      background:'rgba(10,10,15,0.92)', border:'1px solid #222',
      padding:'0.6rem', borderRadius:'4px', minWidth:'200px',
      maxWidth:'240px',
    }}>
      <div style={{ fontSize:'0.7rem', color:'#555', marginBottom:'0.4rem',
                    textTransform:'uppercase', letterSpacing:'0.08em' }}>
        Nearby Concepts
      </div>
      {nearby.map((c, i) => (
        <div key={i}
          onClick={() => flyTo(c)}
          style={{ display:'flex', alignItems:'center', gap:'0.4rem',
                   padding:'0.2rem 0', cursor:'pointer',
                   borderBottom: i < nearby.length-1 ? '1px solid #1a1a1a' : 'none' }}>
          <div style={{
            width:'6px', height:'6px', borderRadius:'50%', flexShrink:0,
            background: ROGET_CLASS_COLOURS[c.roget_class_id as RogetClassId] ?? '#888',
          }} />
          <span style={{ fontSize:'0.75rem', color:'#aaa', flex:1 }}>
            {c.label}
          </span>
          <span style={{ fontSize:'0.65rem', color:'#444' }}>
            {c._dist?.toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  )
}
