import { create } from 'zustand'
import type { ActivePage, JournalEntry, RogetClassId, SurfaceMode } from '../types'

export interface RogetFilter {
  activeClassId:    RogetClassId | null
  activeSectionName: string | null
  activeCategoryId: string | null
}

export interface CameraState {
  x: number; y: number; z: number
  targetX: number; targetY: number; targetZ: number
}

interface AppState {
  activePage:    ActivePage
  setActivePage: (page: ActivePage) => void

  surfaceMode:    SurfaceMode
  setSurfaceMode: (mode: SurfaceMode) => void

  atmosphereOn:    boolean
  setAtmosphereOn: (on: boolean) => void

  rogetFilter:      RogetFilter
  setRogetClass:    (classId: RogetClassId | null) => void
  setRogetSection:  (sectionName: string | null) => void
  setRogetCategory: (categoryId: string | null) => void
  clearRogetFilter: () => void

  selectedConceptId:    string | null
  setSelectedConceptId: (id: string | null) => void

  camera:    CameraState
  setCamera: (state: Partial<CameraState>) => void

  journalOpen:          boolean
  setJournalOpen:       (open: boolean) => void
  localJournalEntries:  JournalEntry[]
  addLocalJournalEntry: (entry: JournalEntry) => void
  setLocalJournalEntries: (entries: JournalEntry[]) => void
}

const DEFAULT_CAMERA: CameraState = {
  x: 0, y: 5, z: 10,
  targetX: 0, targetY: 0, targetZ: 0,
}

export const useAppStore = create<AppState>()((set) => ({
  activePage:    'landscape',
  setActivePage: (page) => set({ activePage: page }),

  surfaceMode:    'wireframe',
  setSurfaceMode: (mode) => set({ surfaceMode: mode }),

  atmosphereOn:    false,
  setAtmosphereOn: (on) => set({ atmosphereOn: on }),

  rogetFilter: { activeClassId: null, activeSectionName: null, activeCategoryId: null },
  setRogetClass:    (classId) => set((s) => ({
    rogetFilter: { ...s.rogetFilter, activeClassId: classId, activeSectionName: null, activeCategoryId: null }
  })),
  setRogetSection:  (sectionName) => set((s) => ({
    rogetFilter: { ...s.rogetFilter, activeSectionName: sectionName, activeCategoryId: null }
  })),
  setRogetCategory: (categoryId) => set((s) => ({
    rogetFilter: { ...s.rogetFilter, activeCategoryId: categoryId }
  })),
  clearRogetFilter: () => set({
    rogetFilter: { activeClassId: null, activeSectionName: null, activeCategoryId: null }
  }),

  selectedConceptId:    null,
  setSelectedConceptId: (id) => set({ selectedConceptId: id }),

  camera:    DEFAULT_CAMERA,
  setCamera: (partial) => set((s) => ({ camera: { ...s.camera, ...partial } })),

  journalOpen:    false,
  setJournalOpen: (open) => set({ journalOpen: open }),
  localJournalEntries:    [],
  addLocalJournalEntry:   (entry) => set((s) => ({
    localJournalEntries: [entry, ...s.localJournalEntries]
  })),
  setLocalJournalEntries: (entries) => set({ localJournalEntries: entries }),
}))
