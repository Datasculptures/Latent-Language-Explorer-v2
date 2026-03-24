/**
 * RogetFilterPanel
 * Hierarchical Roget class filter. Replaces V1's flat domain toggle buttons.
 * Floats over the canvas on the Landscape page.
 */
import { useAppStore } from '../store'
import { SceneManager } from '../scene/SceneManager'
import { ROGET_CLASS_COLOURS } from '../types'
import type { RogetClassId } from '../types'

const CLASS_NAMES: Record<RogetClassId, string> = {
  1: 'Abstract Relations',
  2: 'Space',
  3: 'Matter',
  4: 'Intellect',
  5: 'Volition',
  6: 'Affections',
}

export default function RogetFilterPanel() {
  const { rogetFilter, setRogetClass, clearRogetFilter } = useAppStore()
  const active = rogetFilter.activeClassId

  const handleClick = (classId: RogetClassId) => {
    const next = active === classId ? null : classId
    setRogetClass(next)
    SceneManager.getInstance().applyRogetFilter(next)
  }

  const handleClear = () => {
    clearRogetFilter()
    SceneManager.getInstance().applyRogetFilter(null)
  }

  return (
    <div style={{
      position:'absolute', top:'1rem', right:'1rem',
      background:'rgba(10,10,15,0.92)', border:'1px solid #222',
      padding:'0.75rem', borderRadius:'4px', minWidth:'180px',
      userSelect:'none',
    }}>
      <div style={{ fontSize:'0.7rem', color:'#555', marginBottom:'0.5rem',
                    textTransform:'uppercase', letterSpacing:'0.08em' }}>
        Roget Class
      </div>
      {(Object.entries(CLASS_NAMES) as [string, string][]).map(([id, name]) => {
        const cid    = Number(id) as RogetClassId
        const colour = ROGET_CLASS_COLOURS[cid]
        const isOn   = active === cid
        return (
          <div key={id}
            onClick={() => handleClick(cid)}
            style={{
              display:'flex', alignItems:'center', gap:'0.5rem',
              padding:'0.3rem 0.5rem', cursor:'pointer',
              background:  isOn ? 'rgba(255,255,255,0.08)' : 'transparent',
              borderRadius:'3px', marginBottom:'2px',
            }}>
            <div style={{
              width:'10px', height:'10px', borderRadius:'50%',
              background: isOn ? colour : '#333',
              border:     `1px solid ${colour}`,
              flexShrink: 0,
            }} />
            <span style={{ fontSize:'0.75rem', color: isOn ? colour : '#666' }}>
              {name}
            </span>
          </div>
        )
      })}
      {active !== null && (
        <div onClick={handleClear}
          style={{ marginTop:'0.5rem', fontSize:'0.7rem', color:'#444',
                   cursor:'pointer', textAlign:'center' }}>
          clear filter
        </div>
      )}
    </div>
  )
}
