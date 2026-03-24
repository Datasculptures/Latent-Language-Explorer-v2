/**
 * dataLoader.ts
 * Fetches terrain and concept data from the backend API and
 * passes it to SceneManager. Called once at app startup.
 */
import { SceneManager } from './SceneManager'

export interface LoadResult {
  ok:       boolean
  concepts: number
  error?:   string
}

export async function loadSceneData(): Promise<LoadResult> {
  try {
    const [terrainResp, conceptsResp] = await Promise.all([
      fetch('/api/terrain'),
      fetch('/api/concepts'),
    ])

    if (!terrainResp.ok || !conceptsResp.ok) {
      // 501 = pipeline not run yet, not an error condition
      if (terrainResp.status === 501 || conceptsResp.status === 501) {
        return { ok: false, concepts: 0, error: 'pipeline_not_run' }
      }
      const which = !terrainResp.ok ? 'terrain' : 'concepts'
      return { ok: false, concepts: 0, error: `${which} fetch failed` }
    }

    const terrain  = await terrainResp.json()
    const concepts = await conceptsResp.json()

    const sm = SceneManager.getInstance()
    sm.loadTerrain(terrain)
    sm.loadConcepts(concepts.concepts ?? [])

    // Load existing journal markers (fire-and-forget, non-blocking)
    sm.loadJournalMarkers()

    return { ok: true, concepts: (concepts.concepts ?? []).length }
  } catch (e) {
    return { ok: false, concepts: 0, error: String(e) }
  }
}
