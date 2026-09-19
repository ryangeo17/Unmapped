import type { Route } from '../../types/domain'

export function formatDuration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60))
  if (minutes < 60) return `${minutes} min`
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

export function formatDistance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres / 10) * 10} m`
  return `${(metres / 1000).toFixed(1)} km`
}

export interface Fact {
  icon: string
  text: string
  tone: 'good' | 'warn' | 'neutral'
}

// Quick facts about a route, derived from its segments. Empty if the backend
// sent no segment data.
export function routeFacts(route: Route): Fact[] {
  const segments = route.segments ?? []
  if (segments.length === 0) return []
  const facts: Fact[] = []

  const stairs = segments.filter((s) => s.tags.stairs).length
  facts.push(stairs ? { icon: '🪜', text: 'Includes stairs', tone: 'warn' } : { icon: '✓', text: 'Step-free', tone: 'good' })

  if (segments.some((s) => s.tags.offroad)) facts.push({ icon: '🌱', text: 'Cuts across grass', tone: 'neutral' })

  const maxGrade = Math.max(...segments.map((s) => Math.abs(s.gradePct ?? 0)))
  facts.push(maxGrade >= 5 ? { icon: '⛰️', text: `Hill up to ${maxGrade}%`, tone: 'warn' } : { icon: '➖', text: 'Mostly flat', tone: 'good' })

  if (segments.some((s) => (s.tags.roughness ?? 0) >= 0.5 || s.tags.surface === 'brick' || s.tags.surface === 'gravel')) {
    facts.push({ icon: '〰️', text: 'Rough surface', tone: 'warn' })
  }

  const unverified = segments.filter((s) => s.confidence !== undefined && s.confidence < 0.5).length
  if (unverified) facts.push({ icon: '❔', text: `${unverified} unverified stretch${unverified > 1 ? 'es' : ''}`, tone: 'warn' })

  if (segments.some((s) => s.tags.lit === false)) facts.push({ icon: '🌑', text: 'Unlit stretch', tone: 'warn' })

  return facts
}

// Word label for a safety score; colour classes are only a visual hint.
export function safetyLevel(score: number) {
  if (score >= 80) return { label: 'Good', className: 'border-green-300 bg-green-50 text-green-900' }
  if (score >= 60) return { label: 'Fair', className: 'border-amber-300 bg-amber-50 text-amber-950' }
  return { label: 'Low', className: 'border-red-300 bg-red-50 text-red-900' }
}
