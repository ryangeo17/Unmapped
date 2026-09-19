import type { Mode } from '../../types/domain'

// Per-mode look, used by the mode buttons and by Compare mode's map lines.
// Colour, dash pattern and a sideways offset all differ, so routes that share a
// path stay distinguishable (and never rely on colour alone).
export const MODES: {
  id: Mode
  label: string
  icon: string
  color: string
  dash?: number[] // multiples of the line width
  offset: number // px sideways, for modes that often share a path
  markerAt: number // 0–1 along the route, so shared paths don't stack icons
}[] = [
  { id: 'walk', label: 'Walk', icon: '🚶', color: '#2563eb', offset: 0, markerAt: 0.5 },
  { id: 'wheelchair', label: 'Wheelchair', icon: '♿', color: '#7c3aed', dash: [2, 1], offset: -6, markerAt: 0.3 },
  { id: 'skateboard', label: 'Skateboard', icon: '🛹', color: '#ea580c', dash: [0.6, 1], offset: -6, markerAt: 0.3 },
  { id: 'bike', label: 'Bike', icon: '🚲', color: '#059669', dash: [3, 1, 0.6, 1], offset: 6, markerAt: 0.7 },
  { id: 'scooter', label: 'E-scooter', icon: '🛴', color: '#db2777', dash: [1.2, 1.2], offset: 6, markerAt: 0.7 },
]
