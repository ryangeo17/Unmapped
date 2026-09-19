import type { Mode } from '../../types/domain'

export const MODES: { id: Mode; label: string; icon: string }[] = [
  { id: 'walk', label: 'Walk', icon: '🚶' },
  { id: 'wheelchair', label: 'Wheelchair', icon: '♿' },
  { id: 'skateboard', label: 'Skateboard', icon: '🛹' },
  { id: 'bike', label: 'Bike', icon: '🚲' },
  { id: 'scooter', label: 'E-scooter', icon: '🛴' },
]
