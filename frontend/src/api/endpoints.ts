// One function per backend capability: endpoints → client → adapters.
// Paths are provisional until agreed with the backend (claude/api_notes.md).
import type { RouteRequest } from '../types/domain'
import {
  fromRouteRequest,
  toAnnotation,
  toCoverage,
  toList,
  toObservation,
  toPlace,
  toRouteResult,
} from './adapters'
import { apiFetch } from './client'

export async function searchPlaces(q: string, signal?: AbortSignal) {
  const raw = await apiFetch(`/places?q=${encodeURIComponent(q)}`, { signal })
  return toList(raw, toPlace)
}

export async function getRoute(req: RouteRequest, signal?: AbortSignal) {
  const raw = await apiFetch('/route', { method: 'POST', body: fromRouteRequest(req), signal })
  return toRouteResult(raw)
}

export async function getAnnotations(signal?: AbortSignal) {
  const raw = await apiFetch('/annotations', { signal })
  return toList(raw, toAnnotation)
}

export async function getObservations(signal?: AbortSignal) {
  const raw = await apiFetch('/observations/recent', { signal })
  return toList(raw, toObservation)
}

export async function getCoverage(signal?: AbortSignal) {
  const raw = await apiFetch('/coverage', { signal })
  return toCoverage(raw)
}
