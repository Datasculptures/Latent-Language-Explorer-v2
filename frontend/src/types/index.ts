/**
 * Shared TypeScript interfaces for LLE V2.
 * These mirror data/schema/journal_entry.schema.json and data_bundle.schema.json.
 */

export type RogetClassId = 1 | 2 | 3 | 4 | 5 | 6

export interface RogetContext {
  category_a: string
  category_b: string
  section_a: string | null
  section_b: string | null
  class_a: string | null
  class_b: string | null
}

export interface NearestConcept {
  term: string
  distance: number
  roget_categories: string[] | null
  roget_class: string | null
}

export interface ContextVariant {
  roget_class_context: string
  position_2d: [number, number]
  distance_from_base: number
}

export interface Concept {
  id: string
  label: string
  roget_category_id: string
  roget_category_name: string
  roget_section_name: string
  roget_class_id: RogetClassId
  roget_class_name: string
  is_polysemous: boolean
  all_roget_categories: string[]
  is_modern_addition: boolean
  position_2d: [number, number]
  context_spread: number | null
  polysemy_score: number | null
  contexts: ContextVariant[]
}

export type JournalEntryType =
  | 'probe_discovery' | 'dig_site' | 'voronoi'
  | 'manual' | 'fabrication_note' | 'v1_import'

export type FabricationStatus = 'idea' | 'planned' | 'in_progress' | 'complete'

export interface FabricationNotes {
  material: string
  method: string
  dimensions: string
  status: FabricationStatus
  photos: string[]
}

export interface JournalEntry {
  id: string
  timestamp: string
  type: JournalEntryType
  coordinates_2d: [number, number]
  coordinates_highD: number[] | null
  desert_value: number
  nearest_concepts: NearestConcept[]
  roget_context: RogetContext | null
  generated_description: string | null
  user_notes: string
  fabrication_notes: FabricationNotes
  tags: string[]
  starred: boolean
  v1_source: Record<string, unknown> | null
  schema_version: number
}

export interface JournalEntryCreate {
  type?: JournalEntryType
  coordinates_2d: [number, number]
  coordinates_highD?: number[] | null
  desert_value?: number
  nearest_concepts?: NearestConcept[]
  roget_context?: RogetContext | null
  generated_description?: string | null
  user_notes?: string
  fabrication_notes?: Partial<FabricationNotes>
  tags?: string[]
  starred?: boolean
}

export interface VoronoiParent {
  term: string
  distance: number
  class_id: number
  class_name: string
  category_name: string
}

export interface VoronoiVertex {
  id: string
  x: number
  y: number
  equidistance: number
  mean_dist: number
  parent_count: number
  parents: VoronoiParent[]
  rank: number
}

export interface PathStep {
  term: string
  position_2d: [number, number]
}

export interface PathResult {
  term_a: string
  term_b: string
  steps: PathStep[]
  total_length: number
  step_count: number
}

export type SurfaceMode = 'wireframe' | 'contour' | 'density' | 'desert'
export type ActivePage  = 'landscape' | 'discovery' | 'journal'

/** Roget class colours. Will expand to section-level tints in Phase 1. */
export const ROGET_CLASS_COLOURS: Record<RogetClassId, string> = {
  1: '#00b4d8',  // Abstract Relations
  2: '#e040a0',  // Space
  3: '#f07020',  // Matter
  4: '#4ecb71',  // Intellect
  5: '#a070e0',  // Volition
  6: '#e05050',  // Affections
}
