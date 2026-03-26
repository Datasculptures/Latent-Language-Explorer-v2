import RogetFilterPanel    from '../components/RogetFilterPanel'
import NearbyConceptsPanel from '../components/NearbyConceptsPanel'
import Minimap             from '../components/Minimap'
import ConceptTooltip      from '../components/ConceptTooltip'
import PathPanel           from '../components/PathPanel'
import { useAppStore }     from '../store'
import { SceneManager }    from '../scene/SceneManager'

export default function LandscapePage() {
  const { atmosphereOn, setAtmosphereOn } = useAppStore()

  const handleAtmToggle = () => {
    const next = !atmosphereOn
    setAtmosphereOn(next)
    SceneManager.getInstance().setAtmosphere(next)
  }

  return (
    <>
      <RogetFilterPanel />
      <NearbyConceptsPanel />
      <Minimap />
      <ConceptTooltip />
      <PathPanel />

      {/* Atmosphere toggle — top-centre of the canvas */}
      <div style={{
        position: 'absolute', top: '0.75rem', left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex', gap: '0.25rem',
        pointerEvents: 'auto', zIndex: 200,
      }}>
        <button
          onClick={handleAtmToggle}
          title="Toggle atmosphere layer (Shift+A)"
          style={{
            background:  atmosphereOn ? '#a070e0' : 'transparent',
            color:       atmosphereOn ? '#fff'    : '#555',
            border:      `1px solid ${atmosphereOn ? '#a070e0' : '#333'}`,
            padding:     '0.2rem 0.6rem',
            cursor:      'pointer',
            fontFamily:  'monospace',
            fontSize:    '0.75rem',
            borderRadius:'3px',
          }}
        >
          Atm
        </button>
      </div>
    </>
  )
}
