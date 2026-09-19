import type { Place } from '../../types/domain'

// APPROXIMATE (from OpenStreetMap search), confirm with campus teammates.
// Mock data only; the real list comes from the backend or api_notes.md.
export const places: Place[] = [
  { id: 'gilman', name: 'Gilman Hall', location: [-76.6216, 39.329], category: 'academic' },
  { id: 'brody', name: 'Brody Learning Commons', location: [-76.6194, 39.3284], category: 'library' },
  { id: 'library', name: 'Milton S. Eisenhower Library', location: [-76.6194, 39.3291], category: 'library' },
  { id: 'malone', name: 'Malone Hall', location: [-76.6208, 39.3262], category: 'academic' },
  { id: 'hodson', name: 'Hodson Hall', location: [-76.6223, 39.3276], category: 'academic' },
  { id: 'levering', name: 'Levering Hall', location: [-76.6217, 39.3281], category: 'student life' },
  { id: 'mudd', name: 'Mudd Hall', location: [-76.6206, 39.3308], category: 'academic' },
  { id: 'shriver', name: 'Shriver Hall', location: [-76.6203, 39.3265], category: 'academic' },
  { id: 'beach', name: 'The Beach', location: [-76.6185, 39.3291], category: 'outdoors' },
  { id: 'rec', name: "Ralph O'Connor Recreation Center", location: [-76.6213, 39.3321], category: 'recreation' },
  { id: 'charles-commons', name: 'Charles Commons', location: [-76.6167, 39.3282], category: 'housing' },
  { id: 'hackerman', name: 'Hackerman Hall', location: [-76.6209, 39.3269], category: 'academic' },
  { id: 'krieger', name: 'Krieger Hall', location: [-76.62, 39.3284], category: 'academic' },
  { id: 'agora', name: 'SNF Agora Institute', location: [-76.6231, 39.3259], category: 'academic' },
  { id: 'ffc', name: 'Fresh Food Café', location: [-76.6207, 39.3316], category: 'dining' },
]

export function placeById(id: string): Place {
  const p = places.find((p) => p.id === id)
  if (!p) throw new Error(`Unknown mock place: ${id}`)
  return p
}
