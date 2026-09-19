import { useCampusData } from '../../hooks/useCampusData'
import { useLayerStore } from '../../store/useLayerStore'
import { ACCESS_COLORS, SURFACE_COLORS } from '../../lib/campusData'

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-3 w-3 shrink-0 rounded-sm border border-black/15"
        style={{ backgroundColor: color }}
      />
      <span className="text-xs text-gray-600">{label}</span>
    </div>
  )
}

export default function LocalDataToggle() {
  const showLocalData = useLayerStore((s) => s.showLocalData)
  const toggleLocalData = useLayerStore((s) => s.toggleLocalData)
  const { isLoading, loaded, total, failed } = useCampusData(showLocalData)

  return (
    <section className="space-y-3">
      <label className="flex cursor-pointer items-start gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={showLocalData}
          onClick={toggleLocalData}
          className={`mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors ${
            showLocalData ? 'bg-blue-600' : 'bg-gray-300'
          }`}
        >
          <span
            className={`block h-5 w-5 rounded-full bg-white shadow transition-transform ${
              showLocalData ? 'translate-x-5.5' : 'translate-x-0.5'
            }`}
          />
        </button>
        <span>
          <span className="block text-sm font-medium text-gray-900">Campus data</span>
          <span className="block text-xs text-gray-500">
            {showLocalData ? 'JHU official data' : 'Online basemap only'}
          </span>
        </span>
      </label>

      {showLocalData && (
        <div className="space-y-3 rounded-md bg-gray-50 p-3">
          {isLoading && (
            <p className="text-xs text-gray-500">
              Loading… {loaded}/{total}
            </p>
          )}

          {failed.length > 0 && (
            <p className="text-xs text-red-600">Failed: {failed.join(', ')}</p>
          )}

          <div className="space-y-1">
            <p className="text-xs font-medium text-gray-700">Pathway accessibility</p>
            <Swatch color={ACCESS_COLORS.FullyCompliant} label="Fully compliant" />
            <Swatch color={ACCESS_COLORS.PartiallyCompliant} label="Partially compliant" />
            <Swatch color={ACCESS_COLORS.NonCompliant} label="May have hazards" />
          </div>

          <div className="space-y-1">
            <p className="text-xs font-medium text-gray-700">Entryways</p>
            <Swatch color="#2563eb" label="Step-free entrance" />
            <Swatch color="#64748b" label="Not step-free" />
          </div>

          <div className="space-y-1">
            <p className="text-xs font-medium text-gray-700">Surfaces</p>
            <Swatch color={SURFACE_COLORS.stairs} label="Stairs (red outline)" />
            <Swatch color={SURFACE_COLORS.ramp} label="Ramp" />
            <Swatch color={SURFACE_COLORS.sidewalkBrick} label="Brick paver" />
            <Swatch color={SURFACE_COLORS.sidewalkOther} label="Sidewalk, other" />
          </div>

          <p className="border-t border-gray-200 pt-2 text-xs text-gray-500">
            Surface polygons cover the Decker Quad area only. Buildings, pathways
            and entryways are campus-wide.
          </p>
        </div>
      )}
    </section>
  )
}
