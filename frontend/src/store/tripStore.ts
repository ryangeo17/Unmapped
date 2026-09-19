import { create } from 'zustand'
import type { AnnotationKind, Mode, Place, RouteRequest } from '../types/domain'
import { resolveLeaveAt, timeOfDayAt } from '../utils/time'

export type TripField = 'start' | 'end'

interface TripState {
  start: Place | null
  end: Place | null
  mode: Mode
  preferences: string
  leaveAt: string | null // "HH:MM", or null for "now"
  selectedRouteId: string | null
  selectedSegmentIndex: number | null
  activeOverlays: Set<AnnotationKind>
  compareMode: boolean
  // The search box the next map click fills with a dropped pin (the last one focused).
  pinTarget: TripField | null
  // The last trip sent with "Find route". useRoute fetches whatever this is.
  submittedRequest: RouteRequest | null
  submitCount: number // bumps on every "Find route" click, so it always re-fetches

  setPlace: (field: TripField, place: Place | null) => void
  swapPlaces: () => void
  setMode: (mode: Mode) => void
  setPreferences: (text: string) => void
  setLeaveAt: (hhmm: string | null) => void
  setSelectedRouteId: (id: string | null) => void
  setSelectedSegmentIndex: (index: number | null) => void
  toggleOverlay: (kind: AnnotationKind) => void
  setCompareMode: (on: boolean) => void
  setPinTarget: (field: TripField | null) => void
  submitRoute: () => void
}

// The departure time and time of day to send with a route request.
function departure(leaveAt: string | null) {
  const at = resolveLeaveAt(leaveAt)
  return { departAt: at.toISOString(), timeOfDay: timeOfDayAt(at) }
}

export const useTripStore = create<TripState>()((set) => ({
  start: null,
  end: null,
  mode: 'walk',
  preferences: '',
  leaveAt: null,
  selectedRouteId: null,
  selectedSegmentIndex: null,
  activeOverlays: new Set(),
  compareMode: false,
  pinTarget: null,
  submittedRequest: null,
  submitCount: 0,

  setPlace: (field, place) =>
    set((s) => ({ [field]: place, pinTarget: place && s.pinTarget === field ? null : s.pinTarget })),
  swapPlaces: () => set((s) => ({ start: s.end, end: s.start })),
  // Once a route is showing, switching mode or leaving time re-fetches it straight away.
  setMode: (mode) => set((s) => ({ mode, submittedRequest: s.submittedRequest && { ...s.submittedRequest, mode } })),
  setPreferences: (preferences) => set({ preferences }),
  setLeaveAt: (leaveAt) =>
    set((s) => ({ leaveAt, submittedRequest: s.submittedRequest && { ...s.submittedRequest, ...departure(leaveAt) } })),
  setSelectedRouteId: (selectedRouteId) => set({ selectedRouteId }),
  setSelectedSegmentIndex: (selectedSegmentIndex) => set({ selectedSegmentIndex }),
  toggleOverlay: (kind) =>
    set((s) => {
      const next = new Set(s.activeOverlays)
      if (next.has(kind)) next.delete(kind)
      else next.add(kind)
      return { activeOverlays: next }
    }),
  setCompareMode: (compareMode) => set({ compareMode }),
  setPinTarget: (pinTarget) => set({ pinTarget }),
  submitRoute: () =>
    set((s) =>
      s.start && s.end
        ? {
            submittedRequest: { start: s.start, end: s.end, mode: s.mode, preferences: s.preferences, ...departure(s.leaveAt) },
            submitCount: s.submitCount + 1,
            selectedRouteId: null,
            selectedSegmentIndex: null,
          }
        : {},
    ),
}))
