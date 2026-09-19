import type { TimeOfDay } from '../types/domain'

// "HH:MM" (from <input type="time">) → the next time that clock time happens:
// today, or tomorrow if it has already passed by more than a minute.
export function resolveLeaveAt(hhmm: string | null, now = new Date()): Date {
  if (!hhmm) return now
  const [h, m] = hhmm.split(':').map(Number)
  const d = new Date(now)
  d.setHours(h, m, 0, 0)
  if (d.getTime() < now.getTime() - 60_000) d.setDate(d.getDate() + 1)
  return d
}

// Lighting and safety matter after dark: 7 PM – 6 AM counts as night.
export function timeOfDayAt(date: Date): TimeOfDay {
  const hour = date.getHours()
  return hour >= 19 || hour < 6 ? 'night' : 'day'
}

export function formatClock(date: Date): string {
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export function toHHMM(date: Date): string {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

// Arrival time that agrees with the rounded "N min" duration shown next to it.
export function arrivalTime(leave: Date, durationS: number): Date {
  const minutes = Math.max(1, Math.round(durationS / 60))
  const d = new Date(leave)
  d.setSeconds(0, 0)
  d.setMinutes(d.getMinutes() + minutes)
  return d
}
