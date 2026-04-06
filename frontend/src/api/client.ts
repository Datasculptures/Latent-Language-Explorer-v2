/**
 * Typed API client. All API calls go through this module.
 */
import type { JournalEntry, JournalEntryCreate, VoronoiVertex, PathResult } from '../types'

const API_BASE = '/api'

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, body.detail ?? 'Unknown error', path)
  }
  return response.json() as Promise<T>
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly path: string,
  ) {
    super(`API ${status} at ${path}: ${message}`)
    this.name = 'ApiError'
  }
}

export async function fetchHealth(): Promise<{ status: string; version: string }> {
  return apiFetch('/health')
}

export interface JournalListResponse {
  entries: JournalEntry[]
  total: number
}

export interface JournalQueryParams {
  tags?: string[]
  min_desert?: number
  starred?: boolean
  entry_type?: string
  fabrication_status?: string
  roget_class?: string
  limit?: number
  offset?: number
}

export async function fetchJournalEntries(
  params: JournalQueryParams = {}
): Promise<JournalListResponse> {
  const q = new URLSearchParams()
  if (params.limit           !== undefined) q.set('limit',              String(params.limit))
  if (params.offset          !== undefined) q.set('offset',             String(params.offset))
  if (params.min_desert      !== undefined) q.set('min_desert',         String(params.min_desert))
  if (params.starred         !== undefined) q.set('starred',            String(params.starred))
  if (params.entry_type)                    q.set('entry_type',         params.entry_type)
  if (params.fabrication_status)            q.set('fabrication_status', params.fabrication_status)
  if (params.roget_class)                   q.set('roget_class',        params.roget_class)
  params.tags?.forEach(t => q.append('tags', t))
  const qs = q.toString()
  return apiFetch(`/journal${qs ? `?${qs}` : ''}`)
}

export async function createJournalEntry(
  entry: JournalEntryCreate
): Promise<JournalEntry> {
  return apiFetch('/journal', { method: 'POST', body: JSON.stringify(entry) })
}

export async function updateJournalEntry(
  id: string,
  update: Partial<Pick<JournalEntry,
    'user_notes' | 'fabrication_notes' | 'tags' | 'starred' | 'generated_description'
  >>
): Promise<JournalEntry> {
  return apiFetch(`/journal/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(update),
  })
}

export interface DescribePointRequest {
  coordinates_2d: [number, number]
  coordinates_highD?: number[] | null
  desert_value: number
  nearest_concepts: Array<{
    term: string
    distance: number
    roget_category_name?: string
  }>
  roget_context?: {
    category_a: string; category_b: string
    section_a?: string; section_b?: string
    class_a?: string;   class_b?: string
  } | null
}

export async function describePoint(
  req: DescribePointRequest
): Promise<{ description: string; desert_value: number }> {
  return apiFetch('/describe-point', { method: 'POST', body: JSON.stringify(req) })
}

export async function fetchVoronoiVertices(): Promise<{ meta: Record<string, unknown>; vertices: VoronoiVertex[] }> {
  return apiFetch('/voronoi-vertices')
}

export interface PathRequest {
  term_a: string
  term_b: string
}

export async function findConceptPath(req: PathRequest): Promise<PathResult> {
  return apiFetch('/path', { method: 'POST', body: JSON.stringify(req) })
}
