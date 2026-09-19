import { create } from 'zustand'
import type { RouteOk } from '../api/planner'

type LayerState = {
  /** false = online basemap only, true = render the local campus data on top. */
  showLocalData: boolean
  toggleLocalData: () => void
  /** The solved route currently drawn, or null. */
  route: RouteOk | null
  setRoute: (route: RouteOk | null) => void
}

export const useLayerStore = create<LayerState>((set) => ({
  showLocalData: false,
  toggleLocalData: () => set((s) => ({ showLocalData: !s.showLocalData })),
  route: null,
  setRoute: (route) => set({ route }),
}))
