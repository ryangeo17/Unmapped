import type { LngLat } from '../types/domain'

// [[west, south], [east, north]] around all the given lines.
export function bounds(lines: LngLat[][]): [LngLat, LngLat] {
  const points = lines.flat()
  const lngs = points.map((p) => p[0])
  const lats = points.map((p) => p[1])
  return [
    [Math.min(...lngs), Math.min(...lats)],
    [Math.max(...lngs), Math.max(...lats)],
  ]
}

// The point a fraction `t` (0–1) of the way along a line. Planar maths is fine at campus scale.
export function pointAlong(line: LngLat[], t: number): LngLat {
  const lengths = line.slice(1).map((p, i) => Math.hypot(p[0] - line[i][0], p[1] - line[i][1]))
  let remaining = lengths.reduce((a, b) => a + b, 0) * t
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i]) {
      const f = lengths[i] ? remaining / lengths[i] : 0
      return [line[i][0] + (line[i + 1][0] - line[i][0]) * f, line[i][1] + (line[i + 1][1] - line[i][1]) * f]
    }
    remaining -= lengths[i]
  }
  return line[line.length - 1]
}
