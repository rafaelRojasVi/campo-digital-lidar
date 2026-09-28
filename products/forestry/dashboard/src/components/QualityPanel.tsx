import type { FilterState, QualityFilter } from '../lib/filters.ts'
import { formatInt } from '../lib/format.ts'
import { QUALITY_FLAG_DESCRIPTIONS, QUALITY_FLAG_LABELS } from '../lib/qualityLabels.ts'
import type { QualityFlag, SnapshotSummary } from '../types.ts'
import { KNOWN_QUALITY_FLAGS } from '../types.ts'

interface QualityPanelProps {
  summary: SnapshotSummary
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
}

// Quality evidence observed in the source snapshot. Deliberately framed as
// "evidencia", never as errors requiring action, priorities, or blockers:
// whether and how each case should be corrected belongs to the stakeholder.
export function QualityPanel({ summary, filters, onFiltersChange }: QualityPanelProps) {
  const toggle = (flag: QualityFilter) => {
    onFiltersChange({ ...filters, quality: filters.quality === flag ? null : flag })
  }

  const totalWithEvidence = KNOWN_QUALITY_FLAGS.reduce(
    (sum, flag) => sum + (summary.quality_flag_counts[flag] ?? 0),
    0,
  )

  return (
    <div className="quality">
      <p className="quality__intro">
        Evidencia de calidad de datos observada en la instantánea de origen. Son hechos
        registrados durante la ingesta, no errores que el sistema corrija ni tareas
        priorizadas; la decisión sobre cada caso corresponde a Campo Digital.
      </p>

      <ul className="quality__list">
        {KNOWN_QUALITY_FLAGS.map((flag: QualityFlag) => {
          const count = summary.quality_flag_counts[flag] ?? 0
          const active = filters.quality === flag

          return (
            <li key={flag} className="quality__item">
              <div className="quality__item-head">
                <h3 className="quality__item-title">{QUALITY_FLAG_LABELS[flag]}</h3>
                <span className="quality__item-count">{formatInt(count)}</span>
              </div>
              <p className="quality__item-description">{QUALITY_FLAG_DESCRIPTIONS[flag]}</p>
              <button
                type="button"
                className={`button${active ? '' : ' button--ghost'}`}
                aria-pressed={active}
                disabled={count === 0}
                onClick={() => toggle(flag)}
              >
                {active ? 'Quitar filtro' : 'Ver en el mapa'}
              </button>
            </li>
          )
        })}
      </ul>

      <p className="quality__footer">
        {formatInt(totalWithEvidence)} marcas de evidencia en total ·{' '}
        {formatInt(summary.geometry_invalid_count)} geometrías inválidas ·{' '}
        {formatInt(summary.geometry_valid_count)} válidas. Las geometrías inválidas se
        almacenan y dibujan tal como vienen en la fuente, sin reparación.
      </p>
    </div>
  )
}
