/**
 * The «Estado» table's columns, and the one extension point it has.
 *
 * Kept in `lib/` rather than beside the component so the component module
 * exports only components (oxlint `react/only-export-components`). A later
 * basis — the 90 días hábiles «Plazo CONAF» — adds a column by passing
 * `extraColumns` to `EstadoTable` (with `after: 'pmf'` to sit beside the PMF);
 * it never edits this list.
 */
import type { ReactNode } from 'react'
import type { EditableFieldName, LifecycleRow } from '../api'
import { OficinaVirtualLink } from '../components/OficinaVirtualLink'
import { cell } from '../format'
import {
  LIFECYCLE_FLAG_LABELS,
  LIFECYCLE_GROUP_LABELS,
  LIFECYCLE_GROUP_PILL,
  lifecycleStepText,
} from './lifecycle'

export interface EstadoColumn {
  key: string
  header: string
  render: (row: LifecycleRow) => ReactNode
  /** An extra column only: the base column it follows (default: after the last). */
  after?: string
  /** The fields this column shows; an edit to any of them marks the cell «web». */
  webFields?: readonly EditableFieldName[]
}

export const ESTADO_COLUMNS: readonly EstadoColumn[] = [
  { key: 'pmf', header: 'PMF', render: (row) => <b>{row.pmf}</b> },
  {
    key: 'grupo',
    header: 'Grupo',
    webFields: ['estado_resumido', 'estado'],
    render: (row) => (
      <span className={`pill ${LIFECYCLE_GROUP_PILL[row.lifecycle_group]}`}>
        {LIFECYCLE_GROUP_LABELS[row.lifecycle_group]}
      </span>
    ),
  },
  {
    key: 'paso',
    header: 'Paso',
    webFields: ['estado_resumido', 'estado'],
    // The step or the reason, plus any flag: both are long, so the cell wraps.
    render: (row) => (
      <>
        {row.lifecycle_step === 'rechazado_esperando_recurso' ? (
          <span className="estado-attention">{lifecycleStepText(row)}</span>
        ) : (
          lifecycleStepText(row)
        )}
        {row.lifecycle_flags.map((flag) => (
          <span className="hint estado-flag" key={flag}>
            {LIFECYCLE_FLAG_LABELS[flag]}
          </span>
        ))}
      </>
    ),
  },
  {
    key: 'tipo_rechazo',
    header: 'Tipo de rechazo',
    webFields: ['tipo_rechazo'],
    render: (row) => cell(row.tipo_rechazo, '—'),
  },
  {
    key: 'ingresos',
    header: 'N.º ingreso (1\u00a0/\u00a02)',
    webFields: ['numero_ingreso', 'numero_ingreso_2'],
    render: (row) => `${cell(row.numero_ingreso, 'Sin ingreso')} / ${cell(row.numero_ingreso_2, '—')}`,
  },
  {
    key: 'reingresos',
    header: 'Reingreso Tec / Legal / RecRep',
    webFields: ['reingreso_tec', 'reingreso_legal', 'reingreso_recrep'],
    // Raw, as the planilla has them: their meaning is an open question.
    render: (row) =>
      [row.reingreso_tec, row.reingreso_legal, row.reingreso_recrep]
        .map((value) => cell(value, '—'))
        .join(' / '),
  },
  {
    key: 'oficina',
    header: 'Oficina Virtual',
    // The most recent ingreso, as the 90-day clock counts from it.
    render: (row) => (
      <OficinaVirtualLink
        numero={row.numero_ingreso_2 ?? row.numero_ingreso}
        compact
        testId={`estado-ov-${row.source_row_number}`}
      />
    ),
  },
]
