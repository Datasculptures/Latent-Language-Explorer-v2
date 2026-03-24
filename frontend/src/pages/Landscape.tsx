import RogetFilterPanel    from '../components/RogetFilterPanel'
import NearbyConceptsPanel from '../components/NearbyConceptsPanel'
import Minimap             from '../components/Minimap'

export default function LandscapePage() {
  return (
    <>
      <RogetFilterPanel />
      <NearbyConceptsPanel />
      <Minimap />
    </>
  )
}
