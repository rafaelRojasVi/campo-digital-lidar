/**
 * `/transelec/seguimiento-aef` — the AEF tracking block, as its own reading section.
 *
 * The 09-Sept-2026 workbook added five columns to `Resumen`: `AEF`, `Quien
 * solicita`, `Fecha solicitud`, `Fecha corta` and `Fecha termino`. In that
 * workbook every AEF value sits on its PMF's first row and the PMF's other
 * rows are blank, so the fields read as describing the PMF.
 *
 * This page therefore shows them per PMF, without rewriting any row:
 *
 *  - each PMF-level value names the source row(s) that supplied it;
 *  - when two rows of one PMF carry different values, the page says so and
 *    lists each value with its rows — it never picks one;
 *  - the rows themselves are shown below exactly as the workbook has them:
 *    a blank row stays blank, nothing is filled down;
 *  - AEF values are grouped by their literal spelling only — the source does
 *    not define what each value means, so neither does this page;
 *  - date-order inconsistencies are flagged for review, and the dates are
 *    shown exactly as the workbook has them.
 *
 * When the published version's workbook had no AEF columns, the page says so
 * rather than reporting zero AEF rows, which would be a claim about rows the
 * source never described.
 */
import { useCallback, useState } from 'react'
import { type AefPmf, type AefPmfField, type ResumenRow, type TranselecAef, getAef, getPmfDetail } from '../api'
import { RowDetailDrawer } from '../components/RowDetailDrawer'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { StatusPill } from '../components/StatusPill'
import { cell, formatDate, formatInteger } from '../format'
import { AEF_FIELDS, AEF_FIELD_LABELS, chronologyFlagsOf, chronologyLabel } from '../lib/aef'
import { activeFilterChips, withoutChip } from '../lib/filterUrl'
import { useReads, type FilterController } from '../lib/useFilters'
import { Link, ROUTES } from '../router'
import { Chip, SectionHeader, StatStrip } from '../ui/Primitives'

function ofTotal(part: number, total: number): string {
  return `${formatInteger(part)} de ${formatInteger(total)}`
}

function rowsLabel(rows: readonly number[]): string {
  return `${rows.length === 1 ? 'fila' : 'filas'} ${rows.join(', ')}`
}

function displayValue(value: string, kind: AefPmfField['value_kind']): string {
  return kind === 'date' ? formatDate(value) : value
}

function PmfFieldCell({ field, blankLabel }: { field: AefPmfField; blankLabel: string }) {
  if (field.status === 'blank') return <span className="aef-empty">{blankLabel}</span>
  if (field.status === 'conflict') {
    return (
      <div data-status="conflict">
        <span className="flag">Valores distintos</span>
        <ul className="variant-list">
          {field.variants.map((variant) => (
            <li key={variant.source_rows.join('-')}>
              {/^\d{4}-\d{2}-\d{2}$/.test(variant.value)
                ? formatDate(variant.value)
                : variant.value}
              <span className="source-row">{rowsLabel(variant.source_rows)}</span>
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <div data-status="value">
      {field.value_kind === 'raw_text' ? (
        <>
          <span className="raw-text">{field.value}</span>{' '}
          <span className="flag">Texto sin fecha</span>
        </>
      ) : (
        displayValue(field.value ?? '', field.value_kind)
      )}
      <span className="source-row">{rowsLabel(field.source_rows)}</span>
    </div>
  )
}

const BLANK_LABELS: Record<(typeof AEF_FIELDS)[number], string> = {
  aef: 'Sin AEF',
  quien_solicita: 'Sin solicitante',
  fecha_solicitud: '—',
  fecha_corta: '—',
  fecha_termino: '—',
}

function CountTable({
  caption,
  blankLabel,
  entries,
  testId,
}: {
  caption: string
  blankLabel: string
  entries: TranselecAef['pmf_por_aef']
  testId: string
}) {
  return (
    <div className="stack-tight">
      <h3>{caption}</h3>
      <div className="tablewrap short">
        <table data-testid={testId}>
          <thead>
            <tr>
              <th scope="col">Valor en la planilla</th>
              <th scope="col" className="numeric">
                PMF
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.label ?? '__blank__'}>
                <td>{entry.label ?? <span className="aef-empty">{blankLabel}</span>}</td>
                <td className="numeric">{formatInteger(entry.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function PmfTable({
  pmfs,
  onOpen,
  openingPmf,
}: {
  pmfs: AefPmf[]
  onOpen: (entry: AefPmf) => void
  openingPmf: string | null
}) {
  return (
    <div className="tablewrap">
      <table className="rows-table" data-testid="aef-pmfs">
        <thead>
          <tr>
            <th scope="col">PMF</th>
            <th scope="col" className="numeric">
              Filas
            </th>
            {AEF_FIELDS.map((field) => (
              <th scope="col" key={field}>
                {AEF_FIELD_LABELS[field]}
              </th>
            ))}
            <th scope="col">Revisión</th>
          </tr>
        </thead>
        <tbody>
          {pmfs.map((entry) => (
            <tr
              key={entry.pmf}
              data-testid={`aef-pmf-${entry.pmf}`}
              tabIndex={0}
              aria-haspopup="dialog"
              aria-label={`Abrir detalle del PMF ${entry.pmf}`}
              aria-busy={openingPmf === entry.pmf}
              onClick={() => onOpen(entry)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onOpen(entry)
                }
              }}
            >
              <td>
                <b>{entry.pmf}</b>
              </td>
              <td className="numeric">{formatInteger(entry.total_rows)}</td>
              {AEF_FIELDS.map((field) => (
                <td key={field}>
                  <PmfFieldCell field={entry.fields[field]} blankLabel={BLANK_LABELS[field]} />
                </td>
              ))}
              <td>
                {entry.has_conflict && <span className="flag">Conflicto entre filas</span>}
                {entry.chronology_flags.map((flag) => (
                  <span className="flag" key={flag}>
                    {chronologyLabel(flag)}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AefPage({
  filterController,
  sourceFields = null,
}: {
  filterController: FilterController
  sourceFields?: readonly string[] | null
}) {
  const { filters, replaceFilters } = filterController
  const key = JSON.stringify(filters)
  const [openRow, setOpenRow] = useState<ResumenRow | null>(null)
  const [openingPmf, setOpeningPmf] = useState<string | null>(null)
  const [openError, setOpenError] = useState<string | null>(null)

  const { data, loading, failure } = useReads<TranselecAef>(
    useCallback(
      () => getAef(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )

  const chips = activeFilterChips(filters)

  async function openPmf(entry: AefPmf) {
    if (openingPmf !== null) return
    setOpeningPmf(entry.pmf)
    setOpenError(null)
    try {
      const result = await getPmfDetail(entry.pmf)
      if (!result.ok) {
        setOpenError(`No se pudo abrir el PMF ${entry.pmf}: ${result.error}`)
        return
      }
      const row = result.data.rows.find(
        (candidate) => candidate.source_row_number === entry.source_row_numbers[0],
      ) ?? result.data.rows[0]
      if (!row) {
        setOpenError(`El PMF ${entry.pmf} no tiene filas de detalle disponibles.`)
        return
      }
      setOpenRow(row)
    } finally {
      setOpeningPmf(null)
    }
  }

  if (failure && !data) {
    return (
      <div className="page">
        <StateBlock view={failure} />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page">
        <LoadingBlock label="Cargando el seguimiento AEF…" shape="rows" lines={5} />
      </div>
    )
  }

  if (data.source_fields.length === 0) {
    return (
      <div className="page enter">
        <SectionHeader title="Seguimiento AEF" />
        <StateBlock
          view={{
            kind: 'empty',
            title: 'Esta versión no incluye columnas AEF',
            message:
              'La planilla publicada no tiene las columnas AEF, Quién solicita ni las fechas de solicitud, corta y término. Aparecerán aquí cuando se publique una planilla que las incluya.',
          }}
        />
      </div>
    )
  }

  const missingColumns = 5 - data.source_fields.length

  return (
    <div className="page enter" aria-busy={loading}>
      <SectionHeader
        title="Seguimiento AEF"
        meta="AEF, solicitante y fechas de cada PMF, con la fila de la hoja «Resumen» de la que viene cada valor."
      />

      {chips.length > 0 && (
        <div className="active-filters no-print" style={{ paddingBottom: 'var(--s-5)' }}>
          <span className="eyebrow">Alcance filtrado</span>
          {chips.map((chip) => (
            <Chip
              key={chip.key}
              onRemove={() => replaceFilters(withoutChip(filters, chip))}
              removeLabel={`Quitar el filtro ${chip.label}: ${chip.value}`}
            >
              {chip.label}: {chip.value}
            </Chip>
          ))}
        </div>
      )}

      <AlertBanner tone="info" title="Valores por PMF, con su fila de origen">
        En la planilla, el AEF aparece en una sola fila de cada PMF. Aquí se muestra como valor del
        PMF indicando esa fila; las demás filas no se modifican y siguen vacías en el detalle por
        fila. Si dos filas de un PMF tienen valores distintos, se marca para revisión y no se elige
        ninguno. Campo Digital aún no confirma qué significa cada valor de AEF ni si se registra
        por PMF o por área de corta.
        {chips.length > 0 &&
          ' Los PMF mostrados tienen alguna fila en el alcance filtrado; sus valores consideran todas sus filas.'}
        {missingColumns > 0 &&
          ` La planilla publicada no incluye ${missingColumns === 1 ? 'una' : missingColumns} de las cinco columnas de seguimiento.`}
      </AlertBanner>

      {data.pmf_with_conflict > 0 && (
        <AlertBanner tone="warn" title="Valores distintos dentro de un PMF">
          {formatInteger(data.pmf_with_conflict)}{' '}
          {data.pmf_with_conflict === 1 ? 'PMF tiene' : 'PMF tienen'} valores distintos en sus
          filas. Revise las filas indicadas en la planilla.
        </AlertBanner>
      )}

      <StatStrip
        testId="aef-kpis"
        items={[
          {
            id: 'aef-pmf',
            label: 'PMF con AEF',
            value: ofTotal(data.pmf_with_aef, data.pmf_count),
            sub: 'PMF del alcance',
          },
          {
            id: 'aef-tracking',
            label: 'PMF con seguimiento',
            value: formatInteger(data.pmf_with_tracking),
            sub: `${formatInteger(data.rows_with_any_tracking)} ${data.rows_with_any_tracking === 1 ? 'fila' : 'filas'} con algún valor`,
          },
          {
            id: 'aef-conflicts',
            label: 'PMF con conflicto',
            value: formatInteger(data.pmf_with_conflict),
            sub: 'valores distintos entre filas',
          },
          {
            id: 'aef-chronology',
            label: 'Fechas a revisar',
            value: formatInteger(data.pmf_with_chronology_warning),
            sub: 'PMF con fechas en orden inconsistente',
          },
        ]}
      />

      {data.pmfs.length === 0 ? (
        <section className="ruled" style={{ marginTop: 'var(--s-6)' }}>
          <p className="empty" data-testid="aef-empty">
            No hay PMF con seguimiento AEF en el alcance seleccionado.
            {chips.length > 0 && ' Quite un filtro para ampliar el alcance.'}
          </p>
        </section>
      ) : (
        <>
          <section className="ruled" aria-labelledby="aef-pmfs-title" style={{ marginTop: 'var(--s-6)' }}>
            <div className="table-toolbar">
              <div className="result-count">
                <h2 id="aef-pmfs-title" className="eyebrow">
                  Seguimiento por PMF
                </h2>
                <span data-testid="aef-pmfs-total">
                  <b>{formatInteger(data.pmfs.length)}</b> PMF
                </span>
              </div>
            </div>
            {openError && <AlertBanner tone="warn" title="No se pudo abrir el detalle">{openError}</AlertBanner>}
            <PmfTable pmfs={data.pmfs} onOpen={(entry) => { void openPmf(entry) }} openingPmf={openingPmf} />
          </section>

          <section className="ruled split-two" style={{ marginTop: 'var(--s-6)' }}>
            <CountTable
              caption="PMF por valor de AEF"
              blankLabel="Sin AEF"
              entries={data.pmf_por_aef}
              testId="aef-by-value"
            />
            <CountTable
              caption="PMF por solicitante"
              blankLabel="Sin solicitante"
              entries={data.pmf_por_solicitante}
              testId="aef-by-requester"
            />
          </section>

          <section className="ruled" aria-labelledby="aef-rows-title" style={{ marginTop: 'var(--s-6)' }}>
            <div className="table-toolbar">
              <div className="result-count">
                <h2 id="aef-rows-title" className="eyebrow">
                  Detalle por fila
                </h2>
                <span data-testid="aef-rows-total">
                  <b>{formatInteger(data.rows_with_any_tracking)}</b>{' '}
                  {data.rows_with_any_tracking === 1 ? 'fila' : 'filas'} con algún valor de
                  seguimiento
                </span>
              </div>
            </div>
            {data.rows.length === 0 ? (
              <p className="empty">
                Ninguna fila del alcance filtrado tiene valores propios de seguimiento.
              </p>
            ) : (
              <div className="tablewrap">
                <table className="rows-table">
                  <thead>
                    <tr>
                      <th scope="col" className="numeric">
                        Fila
                      </th>
                      <th scope="col">PMF</th>
                      <th scope="col">Área corta</th>
                      <th scope="col">Estado resumido</th>
                      <th scope="col">AEF</th>
                      <th scope="col">Quién solicita</th>
                      <th scope="col">Fecha solicitud</th>
                      <th scope="col">Fecha corta</th>
                      <th scope="col">Fecha término</th>
                      <th scope="col">Revisión</th>
                    </tr>
                  </thead>
                  <tbody data-testid="aef-rows">
                    {data.rows.map((row) => (
                      <tr
                        key={row.source_row_number}
                        tabIndex={0}
                        data-testid={`aef-row-${row.source_row_number}`}
                        onClick={() => setOpenRow(row)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            setOpenRow(row)
                          }
                        }}
                      >
                        <td className="numeric">{row.source_row_number}</td>
                        <td>
                          <b>{row.pmf}</b>
                        </td>
                        <td>{cell(row.numero_area_corta)}</td>
                        <td>
                          <StatusPill value={row.estado_resumido} />
                        </td>
                        <td>{cell(row.aef) || <span className="aef-empty">Sin AEF</span>}</td>
                        <td>
                          {cell(row.quien_solicita) || (
                            <span className="aef-empty">Sin solicitante</span>
                          )}
                        </td>
                        <td>{formatDate(row.fecha_solicitud) || <span className="aef-empty">—</span>}</td>
                        <td>{formatDate(row.fecha_corta) || <span className="aef-empty">—</span>}</td>
                        <td>{formatDate(row.fecha_termino) || <span className="aef-empty">—</span>}</td>
                        <td>
                          {chronologyFlagsOf(row).map((flag) => (
                            <span className="flag" key={flag}>
                              {chronologyLabel(flag)}
                            </span>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="hint">
              Cada fila muestra solo sus propios valores, tal como vienen en la planilla; una fecha
              marcada para revisar no se corrige aquí. Para verlas junto al resto de las filas, use
              el <Link to={ROUTES.explorador}>Explorador</Link> con el filtro AEF.
            </p>
          </section>
        </>
      )}

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          onClose={() => setOpenRow(null)}
          sourceFields={sourceFields}
        />
      )}
    </div>
  )
}
