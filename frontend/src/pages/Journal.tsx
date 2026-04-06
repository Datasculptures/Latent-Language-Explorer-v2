/**
 * JournalPage
 * Scrollable review of all field journal entries.
 * No Three.js — pure React + fetch.
 *
 * Data: fetched once on mount (limit=1000, all entries).
 * Filtering and sorting are client-side.
 * Pagination: 50 rows shown at a time via "Load more".
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchJournalEntries, updateJournalEntry, describePoint } from '../api/client'
import { ROGET_CLASS_COLOURS } from '../types'
import type { JournalEntry, FabricationStatus, RogetClassId } from '../types'

// ── Constants ────────────────────────────────────────────────────────────────

const PAGE_SIZE       = 50
const DEEP_MIN        = 0.70
const SHALLOW_MIN     = 0.50
const RATE_LIMIT_MS   = 3200   // matches LLM_RATE_LIMIT_INTERVAL_SECONDS + buffer
const COST_PER_CALL   = 0.0002

const CLASS_SHORT: Record<number, string> = {
  1: 'AR', 2: 'Sp', 3: 'Ma', 4: 'In', 5: 'Vo', 6: 'Af',
}

const FAB_ORDER: FabricationStatus[] = ['idea', 'planned', 'in_progress', 'complete']

const FAB_DISPLAY: Record<FabricationStatus, { icon: string; color: string; label: string }> = {
  idea:        { icon: '·',  color: '#444',    label: 'idea'        },
  planned:     { icon: 'P',  color: '#ffaa00', label: 'planned'     },
  in_progress: { icon: '▶', color: '#00b4d8', label: 'in progress' },
  complete:    { icon: '✓', color: '#4ecb71', label: 'complete'    },
}

function nextFabStatus(current: FabricationStatus | undefined): FabricationStatus {
  const idx = FAB_ORDER.indexOf(current ?? 'idea')
  return FAB_ORDER[(idx + 1) % FAB_ORDER.length]
}

function fabSortKey(status: FabricationStatus | undefined): number {
  if (status === 'in_progress') return 0
  if (status === 'planned')     return 1
  if (status === 'complete')    return 2
  return 3
}

type Filter    = 'all' | 'deep' | 'shallow' | 'starred' | 'fab'
type Sort      = 'desert' | 'timestamp'
type RunState  = 'idle' | 'confirm' | 'running' | 'done'

// ── Helpers ──────────────────────────────────────────────────────────────────

function parsePair(notes: string): [string, string] {
  const m = notes?.match(/^(.+?)\s+vs\s+(.+)$/i)
  return m ? [m[1].trim(), m[2].trim()] : [notes ?? '', '']
}

function classTagIds(tags: string[]): number[] {
  return tags
    .filter(t => /^class_[1-6]$/.test(t))
    .map(t => Number(t.replace('class_', '')))
    .sort()
}

function desertColour(d: number): string {
  if (d >= DEEP_MIN)    return '#ff4400'
  if (d >= SHALLOW_MIN) return '#ffaa00'
  return '#555'
}

function sleep(ms: number) {
  return new Promise<void>(resolve => setTimeout(resolve, ms))
}

// ── Flash hook ───────────────────────────────────────────────────────────────

function useFlash(durationMs = 1500) {
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set())
  const flash = useCallback((id: string) => {
    setFlashIds(s => new Set(s).add(id))
    setTimeout(
      () => setFlashIds(s => { const n = new Set(s); n.delete(id); return n }),
      durationMs,
    )
  }, [durationMs])
  return { flashIds, flash }
}

// ── Entry Detail (expanded inline panel) ────────────────────────────────────

interface EntryDetailProps {
  entry:    JournalEntry
  onUpdate: (updated: Partial<JournalEntry>) => void
}

function EntryDetail({ entry, onUpdate }: EntryDetailProps) {
  const fab = entry.fabrication_notes
  const [status,     setStatus]     = useState<FabricationStatus>((fab?.status ?? 'idea') as FabricationStatus)
  const [material,   setMaterial]   = useState(fab?.material   ?? '')
  const [method,     setMethod]     = useState(fab?.method     ?? '')
  const [dimensions, setDimensions] = useState(fab?.dimensions ?? '')
  const [notes,      setNotes]      = useState(entry.user_notes ?? '')
  const [saving,     setSaving]     = useState(false)
  const [saved,      setSaved]      = useState(false)
  const [saveError,  setSaveError]  = useState('')

  // Sync local state when entry prop changes (e.g. after fab-cycle from row button)
  useEffect(() => {
    setStatus((entry.fabrication_notes?.status ?? 'idea') as FabricationStatus)
    setMaterial(entry.fabrication_notes?.material   ?? '')
    setMethod(entry.fabrication_notes?.method       ?? '')
    setDimensions(entry.fabrication_notes?.dimensions ?? '')
    setNotes(entry.user_notes ?? '')
  }, [entry.id]) // only re-sync on entry change, not on keystroke

  const save = async () => {
    setSaving(true)
    setSaveError('')
    try {
      const updated = await updateJournalEntry(entry.id, {
        user_notes: notes,
        fabrication_notes: {
          status,
          material,
          method,
          dimensions,
          photos: fab?.photos ?? [],
        },
      })
      onUpdate({
        user_notes:        updated.user_notes,
        fabrication_notes: updated.fabrication_notes,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch (e: any) {
      setSaveError(e?.message ?? 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const fieldStyle: React.CSSProperties = {
    width: '100%', background: '#0d0d18', color: '#ccc',
    border: '1px solid #2a2a3a', borderRadius: '3px',
    padding: '0.3rem 0.5rem', fontFamily: 'monospace', fontSize: '0.75rem',
    outline: 'none', boxSizing: 'border-box',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: '0.7rem', color: '#555', whiteSpace: 'nowrap',
  }

  return (
    <div style={{
      padding: '0.65rem 0.75rem 0.75rem 3.8rem',
      background: 'rgba(0,20,40,0.30)',
      borderBottom: '1px solid #1a1a1a',
    }}>
      {/* Fabrication Notes */}
      <div style={{
        fontSize: '0.62rem', color: '#3a3a5a', textTransform: 'uppercase',
        letterSpacing: '0.07em', marginBottom: '0.45rem',
      }}>
        Fabrication Notes
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: '72px 1fr',
        gap: '0.3rem 0.6rem', alignItems: 'center', marginBottom: '0.6rem',
      }}>
        <span style={labelStyle}>Status</span>
        <select
          value={status}
          onChange={e => setStatus(e.target.value as FabricationStatus)}
          style={{ ...fieldStyle, width: 'auto', cursor: 'pointer' }}
        >
          {FAB_ORDER.map(s => (
            <option key={s} value={s}>
              {FAB_DISPLAY[s].icon}  {FAB_DISPLAY[s].label}
            </option>
          ))}
        </select>

        <span style={labelStyle}>Material</span>
        <input
          value={material}
          onChange={e => setMaterial(e.target.value.slice(0, 200))}
          placeholder="wire, wood, cement, cardboard…"
          style={fieldStyle}
        />

        <span style={labelStyle}>Method</span>
        <input
          value={method}
          onChange={e => setMethod(e.target.value.slice(0, 200))}
          placeholder="layered contour, wire form, cast…"
          style={fieldStyle}
        />

        <span style={labelStyle}>Dimensions</span>
        <input
          value={dimensions}
          onChange={e => setDimensions(e.target.value.slice(0, 200))}
          placeholder='12" × 12" base, 6" max height'
          style={fieldStyle}
        />
      </div>

      {/* Field Notes */}
      <div style={{
        fontSize: '0.62rem', color: '#3a3a5a', textTransform: 'uppercase',
        letterSpacing: '0.07em', marginBottom: '0.3rem',
      }}>
        Field Notes
      </div>
      <textarea
        value={notes}
        onChange={e => setNotes(e.target.value.slice(0, 2000))}
        rows={3}
        style={{
          ...fieldStyle, resize: 'vertical', lineHeight: 1.5,
          marginBottom: '0.5rem',
        }}
      />

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <button
          onClick={save}
          disabled={saving}
          style={{
            background: '#002030', color: '#00b4d8',
            border: '1px solid #00b4d844', borderRadius: '3px',
            padding: '0.25rem 0.8rem',
            cursor: saving ? 'default' : 'pointer',
            fontFamily: 'monospace', fontSize: '0.72rem',
          }}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saved     && <span style={{ fontSize: '0.68rem', color: '#4ecb71' }}>Saved</span>}
        {saveError && <span style={{ fontSize: '0.68rem', color: '#ff4400' }}>{saveError}</span>}
      </div>
    </div>
  )
}

// ── Entry Row ────────────────────────────────────────────────────────────────

interface EntryRowProps {
  entry:       JournalEntry
  focused:     boolean
  expanded:    boolean
  flashing:    boolean
  fabFlashing: boolean
  onFocus:     () => void
  onExpand:    () => void
  onStar:      () => void
  onFabCycle:  () => void
  onUpdate:    (updated: Partial<JournalEntry>) => void
}

function EntryRow({
  entry, focused, expanded, flashing, fabFlashing,
  onFocus, onExpand, onStar, onFabCycle, onUpdate,
}: EntryRowProps) {
  const [termA, termB] = parsePair(entry.user_notes)
  const classIds       = classTagIds(entry.tags)
  const desert         = entry.desert_value ?? 0
  const fabStatus      = (entry.fabrication_notes?.status ?? 'idea') as FabricationStatus
  const fabDisp        = FAB_DISPLAY[fabStatus]
  const desc           = entry.generated_description ?? ''
  const descTrunc      = desc.length > 120 ? desc.slice(0, 120) + '…' : desc

  return (
    <>
      <div
        tabIndex={0}
        onClick={() => { onFocus(); onExpand() }}
        onFocus={onFocus}
        style={{
          display:      'flex',
          alignItems:   'flex-start',
          gap:          '0.6rem',
          padding:      '0.55rem 0.75rem',
          borderBottom: expanded ? 'none' : '1px solid #1a1a1a',
          background:   focused ? 'rgba(0,180,216,0.06)' : 'transparent',
          cursor:       'default',
          outline:      'none',
        }}
      >
        {/* ★ Toggle */}
        <button
          onClick={e => { e.stopPropagation(); onStar() }}
          title="Toggle starred"
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: '1rem',
            color: flashing ? '#ffe066' : entry.starred ? '#ffd700' : '#333',
            padding: '0 0.1rem', flexShrink: 0, lineHeight: 1,
            marginTop: '0.1rem', transition: 'color 0.15s',
          }}
        >★</button>

        {/* Fab cycle button */}
        <button
          onClick={e => { e.stopPropagation(); onFabCycle() }}
          title={`Fab: ${fabDisp.label} — click to advance`}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            fontSize: fabStatus === 'idea' ? '1.1rem' : '0.82rem',
            fontWeight: 'bold',
            color: fabFlashing ? '#ffffff' : fabDisp.color,
            padding: '0 0.1rem', flexShrink: 0, lineHeight: 1,
            marginTop: '0.1rem', transition: 'color 0.15s',
            fontFamily: 'monospace', width: '1rem', textAlign: 'center',
          }}
        >{fabDisp.icon}</button>

        {/* Desert badge */}
        <div style={{
          flexShrink: 0, minWidth: '3.8rem', textAlign: 'right',
          fontSize: '0.78rem', fontWeight: 'bold',
          color: desertColour(desert), fontFamily: 'monospace', paddingTop: '0.1rem',
        }}>
          {desert > 0 ? desert.toFixed(4) : '—'}
        </div>

        {/* Center: pair + pills + description */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '0.82rem', color: '#ddd', marginBottom: '0.2rem', wordBreak: 'break-word' }}>
            {termB ? (
              <>
                <span style={{ fontWeight: 'bold' }}>{termA}</span>
                <span style={{ color: '#444', margin: '0 0.3rem' }}>↔</span>
                <span style={{ fontWeight: 'bold' }}>{termB}</span>
              </>
            ) : (
              <span style={{ color: '#888' }}>{termA.slice(0, 60)}{termA.length > 60 ? '…' : ''}</span>
            )}
          </div>

          {classIds.length > 0 && (
            <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', marginBottom: '0.2rem' }}>
              {classIds.map(cid => (
                <span key={cid} style={{
                  fontSize: '0.62rem', padding: '0.05rem 0.35rem', borderRadius: '999px',
                  border:     `1px solid ${ROGET_CLASS_COLOURS[cid as RogetClassId]}44`,
                  color:      ROGET_CLASS_COLOURS[cid as RogetClassId],
                  background: ROGET_CLASS_COLOURS[cid as RogetClassId] + '18',
                  fontFamily: 'monospace',
                }}>
                  {CLASS_SHORT[cid]}
                </span>
              ))}
            </div>
          )}

          {descTrunc && (
            <div style={{ fontSize: '0.72rem', color: '#666', fontStyle: 'italic', wordBreak: 'break-word' }}>
              {descTrunc}
            </div>
          )}
        </div>

        {/* Right: no-desc indicator */}
        <div style={{ flexShrink: 0, textAlign: 'right', fontSize: '0.68rem' }}>
          {!desc && <span style={{ color: '#333' }}>no description</span>}
        </div>
      </div>

      {/* Inline expanded detail */}
      {expanded && (
        <EntryDetail entry={entry} onUpdate={onUpdate} />
      )}
    </>
  )
}

// ── Describe Runner Modal ────────────────────────────────────────────────────

interface RunProgress {
  current:   number
  total:     number
  written:   number
  failed:    number
  skipped:   number
  lastPair:  string
  lastDesc:  string
  lastError: string
}

function DescribeRunner({
  targets,
  onClose,
  onUpdateEntry,
}: {
  targets:       JournalEntry[]
  onClose:       () => void
  onUpdateEntry: (id: string, desc: string) => void
}) {
  const [runState, setRunState] = useState<RunState>('confirm')
  const [progress, setProgress] = useState<RunProgress>({
    current: 0, total: targets.length, written: 0, failed: 0, skipped: 0,
    lastPair: '', lastDesc: '', lastError: '',
  })
  const cancelRef = useRef(false)

  const estCost    = targets.length * COST_PER_CALL
  const estMinutes = (targets.length * RATE_LIMIT_MS) / 60000

  const startRun = useCallback(async () => {
    cancelRef.current = false
    setRunState('running')

    let written = 0, failed = 0, skipped = 0

    for (let i = 0; i < targets.length; i++) {
      if (cancelRef.current) break
      const entry = targets[i]
      const [ta, tb] = parsePair(entry.user_notes)
      const pair = tb ? `${ta} vs ${tb}` : ta

      setProgress(p => ({ ...p, current: i + 1, lastPair: pair }))

      const body = {
        coordinates_2d:    entry.coordinates_2d,
        coordinates_highD: entry.coordinates_highD ?? null,
        desert_value:      entry.desert_value,
        nearest_concepts:  (entry.nearest_concepts ?? []).map(nc => ({
          term:                nc.term,
          distance:            nc.distance,
          roget_category_name: nc.roget_class ?? undefined,
        })),
        roget_context: entry.roget_context
          ? {
              category_a: entry.roget_context.category_a,
              category_b: entry.roget_context.category_b,
              section_a:  entry.roget_context.section_a  ?? undefined,
              section_b:  entry.roget_context.section_b  ?? undefined,
              class_a:    entry.roget_context.class_a    ?? undefined,
              class_b:    entry.roget_context.class_b    ?? undefined,
            }
          : null,
      }

      try {
        const result = await describePoint(body)
        const desc   = result.description?.trim() ?? ''
        if (!desc) { skipped++; continue }

        await updateJournalEntry(entry.id, { generated_description: desc })
        onUpdateEntry(entry.id, desc)
        written++
        setProgress(p => ({
          ...p, written, failed, skipped,
          lastDesc: desc.slice(0, 100) + (desc.length > 100 ? '…' : ''),
        }))
      } catch (e: any) {
        failed++
        const msg: string = e?.message ?? String(e)
        setProgress(p => ({ ...p, written, failed, skipped, lastError: msg }))

        const isFatal = e?.status === 503 || msg.includes('API key') || msg.includes('key not configured')
        if (isFatal) {
          cancelRef.current = true
          break
        }
      }

      if (i < targets.length - 1 && !cancelRef.current) {
        await sleep(RATE_LIMIT_MS)
      }
    }

    setRunState('done')
  }, [targets, onUpdateEntry])

  const pct = progress.total > 0
    ? Math.round((progress.current / progress.total) * 100)
    : 0

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.80)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={runState === 'confirm' ? onClose : undefined}
    >
      <div
        style={{
          background: '#0f0f18', border: '1px solid #2a2a3a',
          borderRadius: '6px', padding: '1.5rem 2rem',
          width: '440px', fontFamily: 'monospace', color: '#ccc',
        }}
        onClick={e => e.stopPropagation()}
      >
        {runState === 'confirm' && (
          <>
            <div style={{ fontSize: '1rem', fontWeight: 'bold', marginBottom: '1rem', color: '#ffd700' }}>
              Describe {targets.length} starred {targets.length === 1 ? 'entry' : 'entries'}
            </div>
            <div style={{ fontSize: '0.82rem', color: '#666', lineHeight: 1.6, marginBottom: '1.2rem' }}>
              <div>Estimated cost: <span style={{ color: '#ccc' }}>~${estCost.toFixed(4)} USD</span></div>
              <div>Estimated time: <span style={{ color: '#ccc' }}>~{estMinutes.toFixed(1)} min</span></div>
              <div style={{ marginTop: '0.5rem', color: '#444', fontSize: '0.72rem' }}>
                Descriptions are written back to the journal incrementally.
                Progress is preserved if you cancel.
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button onClick={onClose}   style={btnStyle('#1a1a1a', '#555')}>Cancel</button>
              <button onClick={startRun}  style={btnStyle('#002030', '#00b4d8')}>Start</button>
            </div>
          </>
        )}

        {runState === 'running' && (
          <>
            <div style={{ fontSize: '0.9rem', fontWeight: 'bold', marginBottom: '0.75rem', color: '#00b4d8' }}>
              Describing… {progress.current}/{progress.total}
            </div>
            <div style={{ background: '#1a1a2a', borderRadius: '3px', height: '4px', marginBottom: '0.75rem' }}>
              <div style={{
                width: `${pct}%`, height: '100%',
                background: '#00b4d8', borderRadius: '3px', transition: 'width 0.3s',
              }} />
            </div>
            <div style={{ fontSize: '0.75rem', color: '#555', marginBottom: '0.3rem' }}>
              {progress.lastPair || '…'}
            </div>
            {progress.lastDesc && (
              <div style={{
                fontSize: '0.72rem', color: '#444', fontStyle: 'italic',
                marginBottom: '0.75rem', lineHeight: 1.4,
              }}>
                {progress.lastDesc}
              </div>
            )}
            <div style={{ fontSize: '0.7rem', color: '#333', marginBottom: '0.5rem' }}>
              ✓ {progress.written} written
              {progress.failed  > 0 && <span style={{ color: '#ff4400', marginLeft: '0.75rem' }}>✗ {progress.failed} failed</span>}
              {progress.skipped > 0 && <span style={{ color: '#555',    marginLeft: '0.75rem' }}>— {progress.skipped} skipped</span>}
            </div>
            {progress.lastError && (
              <div style={{
                fontSize: '0.7rem', color: '#ff6644', marginBottom: '0.75rem',
                background: '#1a0a0a', border: '1px solid #3a1a1a',
                borderRadius: '3px', padding: '0.35rem 0.5rem', wordBreak: 'break-word',
              }}>
                {progress.lastError}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={() => { cancelRef.current = true }} style={btnStyle('#1a1a1a', '#555')}>
                Cancel
              </button>
            </div>
          </>
        )}

        {runState === 'done' && (
          <>
            <div style={{ fontSize: '0.9rem', fontWeight: 'bold', marginBottom: '0.75rem', color: '#4ecb71' }}>
              {cancelRef.current ? 'Cancelled' : 'Complete'}
            </div>
            <div style={{ fontSize: '0.82rem', color: '#666', lineHeight: 1.8, marginBottom: '0.75rem' }}>
              <div>Descriptions written: <span style={{ color: '#ccc' }}>{progress.written}</span></div>
              {progress.failed  > 0 && <div>Failed:  <span style={{ color: '#ff4400' }}>{progress.failed}</span></div>}
              {progress.skipped > 0 && <div>Skipped: <span style={{ color: '#555'    }}>{progress.skipped}</span></div>}
            </div>
            {progress.lastError && (
              <div style={{
                fontSize: '0.72rem', color: '#ff6644', marginBottom: '1rem',
                background: '#1a0a0a', border: '1px solid #3a1a1a',
                borderRadius: '3px', padding: '0.35rem 0.5rem', wordBreak: 'break-word',
              }}>
                {progress.lastError}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={onClose} style={btnStyle('#002030', '#00b4d8')}>Close</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function btnStyle(bg: string, col: string) {
  return {
    background: bg, color: col,
    border: `1px solid ${col}44`, borderRadius: '3px',
    padding: '0.35rem 0.9rem', cursor: 'pointer',
    fontFamily: 'monospace', fontSize: '0.78rem',
  } as const
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function JournalPage() {
  const [allEntries,   setAllEntries]   = useState<JournalEntry[]>([])
  const [loading,      setLoading]      = useState(true)
  const [filter,       setFilter]       = useState<Filter>('all')
  const [sort,         setSort]         = useState<Sort>('desert')
  const [displayCount, setDisplayCount] = useState(PAGE_SIZE)
  const [focusedIdx,   setFocusedIdx]   = useState(0)
  const [expandedId,   setExpandedId]   = useState<string | null>(null)
  const [showRunner,   setShowRunner]   = useState(false)

  const { flashIds: starFlashIds, flash: flashStar } = useFlash()
  const { flashIds: fabFlashIds,  flash: flashFab  } = useFlash()

  const containerRef = useRef<HTMLDivElement>(null)

  // ── Fetch all entries once ──────────────────────────────────────────────
  useEffect(() => {
    setLoading(true)
    fetchJournalEntries({ limit: 1000 })
      .then(res => setAllEntries(res.entries))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // ── Reset display count when filter/sort changes ───────────────────────
  useEffect(() => { setDisplayCount(PAGE_SIZE); setFocusedIdx(0) }, [filter, sort])

  // ── Derived lists ──────────────────────────────────────────────────────
  const filtered = allEntries.filter(e => {
    const d = e.desert_value ?? 0
    if (filter === 'deep')    return d >= DEEP_MIN
    if (filter === 'shallow') return d >= SHALLOW_MIN && d < DEEP_MIN
    if (filter === 'starred') return e.starred
    if (filter === 'fab')     return (e.fabrication_notes?.status ?? 'idea') !== 'idea'
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    if (filter === 'fab') {
      return fabSortKey(a.fabrication_notes?.status as FabricationStatus | undefined)
           - fabSortKey(b.fabrication_notes?.status as FabricationStatus | undefined)
    }
    return sort === 'desert'
      ? (b.desert_value ?? 0) - (a.desert_value ?? 0)
      : new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  })

  const displayed = sorted.slice(0, displayCount)

  // ── Starred targets for describe runner ────────────────────────────────
  const describeTargets = allEntries.filter(
    e => e.starred && !e.generated_description && (e.nearest_concepts?.length ?? 0) > 0
  )

  // ── Keyboard navigation ────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (showRunner) return
      if (document.activeElement !== document.body &&
          !containerRef.current?.contains(document.activeElement)) return
      if      (e.key === 'ArrowDown') { e.preventDefault(); setFocusedIdx(i => Math.min(i + 1, displayed.length - 1)) }
      else if (e.key === 'ArrowUp')   { e.preventDefault(); setFocusedIdx(i => Math.max(i - 1, 0)) }
      else if (e.key === 's' || e.key === 'S') { const en = displayed[focusedIdx]; if (en) toggleStar(en) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [displayed, focusedIdx, showRunner])

  // ── Star toggle ────────────────────────────────────────────────────────
  const toggleStar = useCallback((entry: JournalEntry) => {
    const next = !entry.starred
    setAllEntries(prev => prev.map(e => e.id === entry.id ? { ...e, starred: next } : e))
    flashStar(entry.id)
    updateJournalEntry(entry.id, { starred: next }).catch(() => {
      setAllEntries(prev => prev.map(e => e.id === entry.id ? { ...e, starred: entry.starred } : e))
    })
  }, [flashStar])

  // ── Fab cycle ──────────────────────────────────────────────────────────
  const toggleFab = useCallback((entry: JournalEntry) => {
    const next    = nextFabStatus(entry.fabrication_notes?.status as FabricationStatus | undefined)
    const newFab  = { ...(entry.fabrication_notes ?? {}), status: next }
    setAllEntries(prev => prev.map(e =>
      e.id === entry.id ? { ...e, fabrication_notes: { ...e.fabrication_notes, ...newFab } } : e
    ))
    flashFab(entry.id)
    updateJournalEntry(entry.id, { fabrication_notes: newFab }).catch(() => {
      setAllEntries(prev => prev.map(e =>
        e.id === entry.id ? { ...e, fabrication_notes: entry.fabrication_notes } : e
      ))
    })
  }, [flashFab])

  // ── Entry update (from detail panel save) ─────────────────────────────
  const handleEntryUpdate = useCallback((id: string, updated: Partial<JournalEntry>) => {
    setAllEntries(prev => prev.map(e => e.id === id ? { ...e, ...updated } : e))
  }, [])

  // ── Runner description callback ────────────────────────────────────────
  const handleUpdateEntry = useCallback((id: string, desc: string) => {
    setAllEntries(prev => prev.map(e => e.id === id ? { ...e, generated_description: desc } : e))
  }, [])

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div style={{
      position: 'absolute', inset: 0,
      background: '#0a0a0f', color: '#e0e0e0', fontFamily: 'monospace',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* ── Controls bar ────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.5rem',
        padding: '0.5rem 0.75rem', borderBottom: '1px solid #1a1a1a',
        flexShrink: 0, flexWrap: 'wrap', background: 'rgba(10,10,15,0.98)',
      }}>
        {/* Filter buttons */}
        {(['all', 'deep', 'shallow', 'starred', 'fab'] as Filter[]).map(f => {
          const active = filter === f
          const col    = f === 'fab' ? '#c060ff' : '#00b4d8'
          const label  = f === 'deep' ? 'Deep ≥0.70'
                       : f === 'shallow' ? 'Shallow'
                       : f === 'starred' ? '★ Starred'
                       : f === 'fab'     ? 'FAB'
                       : 'All'
          return (
            <button key={f} onClick={() => setFilter(f)} style={{
              background:    active ? (f === 'fab' ? '#1a0a2a' : '#1a2a3a') : 'transparent',
              color:         active ? col : '#555',
              border:        `1px solid ${active ? col : '#222'}`,
              borderRadius:  '3px', padding: '0.2rem 0.65rem',
              cursor: 'pointer', fontFamily: 'monospace', fontSize: '0.72rem',
              textTransform: 'uppercase', letterSpacing: '0.05em',
            }}>
              {label}
            </button>
          )
        })}

        <div style={{ width: '1px', height: '16px', background: '#1f1f1f', margin: '0 0.25rem' }} />

        {filter !== 'fab' && (
          <>
            <span style={{ fontSize: '0.68rem', color: '#333' }}>sort:</span>
            {(['desert', 'timestamp'] as Sort[]).map(s => (
              <button key={s} onClick={() => setSort(s)} style={{
                background:   sort === s ? '#1a1a2a' : 'transparent',
                color:        sort === s ? '#a070e0' : '#444',
                border:       `1px solid ${sort === s ? '#a070e0' : '#1f1f1f'}`,
                borderRadius: '3px', padding: '0.2rem 0.55rem',
                cursor: 'pointer', fontFamily: 'monospace', fontSize: '0.7rem',
              }}>
                {s === 'desert' ? 'depth' : 'date'}
              </button>
            ))}
          </>
        )}

        <span style={{ marginLeft: 'auto', fontSize: '0.7rem', color: '#333' }}>
          {loading ? 'loading…' : `${Math.min(displayCount, sorted.length)} of ${sorted.length}`}
        </span>

        {/* Describe starred button */}
        <button
          onClick={() => setShowRunner(true)}
          disabled={describeTargets.length === 0}
          title={describeTargets.length === 0
            ? 'No starred entries without descriptions'
            : `Describe ${describeTargets.length} starred entries`}
          style={{
            background:   'transparent',
            color:        describeTargets.length > 0 ? '#ffd700' : '#333',
            border:       `1px solid ${describeTargets.length > 0 ? '#ffd70044' : '#1f1f1f'}`,
            borderRadius: '3px', padding: '0.2rem 0.6rem',
            cursor:       describeTargets.length > 0 ? 'pointer' : 'default',
            fontFamily:   'monospace', fontSize: '0.68rem',
          }}
        >
          ★ describe {describeTargets.length > 0 ? `(${describeTargets.length})` : ''}
        </button>
      </div>

      {/* ── Entry list ─────────────────────────────────────────── */}
      <div
        ref={containerRef}
        style={{ flex: 1, overflowY: 'auto' }}
        tabIndex={-1}
      >
        {loading && (
          <div style={{ padding: '2rem', color: '#333', textAlign: 'center', fontSize: '0.8rem' }}>
            Loading journal…
          </div>
        )}
        {!loading && sorted.length === 0 && (
          <div style={{ padding: '2rem', color: '#333', textAlign: 'center', fontSize: '0.8rem' }}>
            No entries match this filter.
          </div>
        )}
        {displayed.map((entry, i) => (
          <EntryRow
            key={entry.id}
            entry={entry}
            focused={focusedIdx === i}
            expanded={expandedId === entry.id}
            flashing={starFlashIds.has(entry.id)}
            fabFlashing={fabFlashIds.has(entry.id)}
            onFocus={() => setFocusedIdx(i)}
            onExpand={() => setExpandedId(id => id === entry.id ? null : entry.id)}
            onStar={() => toggleStar(entry)}
            onFabCycle={() => toggleFab(entry)}
            onUpdate={updated => handleEntryUpdate(entry.id, updated)}
          />
        ))}
        {displayCount < sorted.length && (
          <div style={{ padding: '0.75rem', textAlign: 'center' }}>
            <button
              onClick={() => setDisplayCount(c => c + PAGE_SIZE)}
              style={{
                background: 'transparent', color: '#444', border: '1px solid #222',
                borderRadius: '3px', padding: '0.35rem 1.2rem',
                cursor: 'pointer', fontFamily: 'monospace', fontSize: '0.75rem',
              }}
            >
              load more ({sorted.length - displayCount} remaining)
            </button>
          </div>
        )}
      </div>

      {/* ── Describe runner ────────────────────────────────────── */}
      {showRunner && (
        <DescribeRunner
          targets={describeTargets}
          onClose={() => setShowRunner(false)}
          onUpdateEntry={handleUpdateEntry}
        />
      )}
    </div>
  )
}
