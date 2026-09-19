import { create } from 'zustand'

type LayerState = {
  /** false = online basemap only, true = render the local campus data on top. */
  showLocalData: boolean
  toggleLocalData: () => void
  /** Trip id, or null for none. */
  selectedTrip: string | null
  selectTrip: (trip: string | null) => void
}

export const useLayerStore = create<LayerState>((set) => ({
  showLocalData: false,
  toggleLocalData: () => set((s) => ({ showLocalData: !s.showLocalData })),
  selectedTrip: null,
  selectTrip: (trip) => set({ selectedTrip: trip }),
}))
