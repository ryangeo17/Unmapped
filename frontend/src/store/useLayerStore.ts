import { create } from 'zustand'
import type { RouteMode } from '../lib/routes'

type LayerState = {
  /** false = online basemap only, true = render the local campus data on top. */
  showLocalData: boolean
  toggleLocalData: () => void
  /** Trip id from lib/routes TRIPS, or null for none. */
  selectedTrip: string | null
  selectTrip: (trip: string | null) => void
  /** Only one mode is drawn at a time. */
  selectedMode: RouteMode
  selectMode: (mode: RouteMode) => void
}

export const useLayerStore = create<LayerState>((set) => ({
  showLocalData: false,
  toggleLocalData: () => set((s) => ({ showLocalData: !s.showLocalData })),
  selectedTrip: null,
  selectTrip: (trip) => set({ selectedTrip: trip }),
  selectedMode: 'walking',
  selectMode: (mode) => set({ selectedMode: mode }),
}))
