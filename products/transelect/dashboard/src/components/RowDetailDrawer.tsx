/**
 * One PMF's detail, in a side panel.
 *
 * The shipped interface could show a row only as a row: thirteen cells in a
 * horizontally scrolling table, with no way to see the rest of the contract
 * fields or the other áreas de corta that belong to the same PMF. This panel
 * makes the connection between PMF, predio, rol and source row explicit,
 * using `GET /transelec/pmfs/{pmf}`.
 *
 * Reading order (dashboard UI pass): what an operator opens a PMF for comes
 * first — its tramitación (estado, motivo, ingreso, plazos, empresa) and its
 * AEF tracking — then every row of the PMF with the selected one marked, then
 * the full field list of the selected área de corta. The source row stays in
 * the fixed header the whole time, so provenance never scrolls away. Two
 * columns of short facts replace one long label/value column, which roughly
 * halves the panel's length.
 *
 * Choosing another row of the same PMF re-targets the panel to that row,
 * without another request and without closing it.
 *
 * AEF has two explicitly separate readings: the server-resolved PMF summary
 * (with source rows and conflicts) and the selected row's original cells.
 * Nothing is borrowed into a blank row. Older versions without AEF columns
 * say so instead of implying a row has missing data.
 */
import { useEffect, useRef, useState } from 'react'
import {
  EMPTY_FILTERS,
  type AefPmf,
  type AefPmfField,
  type LifecycleRow,
  type ResumenRow,
  type EditableFieldName,
  type TranselecOverride,
  type TranselecPmfDetail,
  getAef,
  getPmfDetail,
  listOverrides,
} from '../api'
import { cell, formatDate, formatInteger, formatNumber } from '../format'
import {
  AEF_FIELDS,
  AEF_FIELD_LABELS,
  aefInSource,
  chronologyFlagsOf,
  chronologyLabel,
  hasAefTracking,
} from '../lib/aef'
import { ingreso2InSource } from '../lib/ingreso'
import {
  LIFECYCLE_FLAG_LABELS,
  LIFECYCLE_GROUP_LABELS,
  lifecycleStepText,
} from '../lib/lifecycle'
import { isWebField, loadSuggestions } from '../lib/webEdits'
import { classifyFailure, type FailureView } from '../lib/apiState'
import type { PlazoDetail } from '../lib/plazo'
import { Drawer } from '../ui/Drawer'
import { DrawerConfirm } from './DrawerConfirm'
import { EditableFieldsSection, type EditState } from './EditableFieldsSection'
import { AlertBanner, LoadingBlock } from './StateViews'
import { Fact } from './Fact'
import { OficinaVirtualLink } from './OficinaVirtualLink'
import { PlazoDrawerNotice, PlazoDrawerSection, type PlazoDrawerStatus } from './PlazoDrawerSection'
import { SourceDate } from './SourceDate'
import { StatusPill } from './StatusPill'

function rowsLabel(rows: readonly number[]): string {
  return `${rows.length === 1 ? 'fila' : 'filas'} ${rows.join(', ')}`
}

/** The source rows shared by every resolved field, or null when they differ or conflict. */
function sharedSourceRows(pmf: AefPmf): number[] | null {
  const fields = AEF_FIELDS.map((key) => pmf.fields[key]).filter((f) => f.status !== 'blank')
  if (fields.length === 0 || fields.some((f) => f.status === 'conflict')) return null
  const first = fields[0].source_rows.join(',')
  return fields.every((f) => f.source_rows.join(',') === first) ? fields[0].source_rows : null
}

function AefPmfValue({ field, showRows }: { field: AefPmfField; showRows: boolean }) {
  if (field.status === 'blank') return <>Sin dato en este PMF</>
  if (field.status === 'conflict') {
    return (
      <>
        <strong>Valores distintos; requiere revisión</strong>
        <ul className="variant-list">
          {field.variants.map((variant) => (
            <li key={variant.source_rows.join('-')}>
              {variant.value} · {rowsLabel(variant.source_rows)}
            </li>
          ))}
        </ul>
      </>
    )
  }
  return (
    <>
      {field.value_kind === 'date' && field.value
        ? formatDate(field.value)
        : field.value}
      {field.value_kind === 'raw_text' && ' · texto sin fecha interpretada'}
      {showRows && <span className="source-row">{rowsLabel(field.source_rows)}</span>}
    </>
  )
}

function PmfAefSection({
  pmf,
  loading,
  failed,
}: {
  pmf: AefPmf | null
  loading: boolean
  failed: boolean
}) {
  const shared = pmf ? sharedSourceRows(pmf) : null
  return (
    <section className="drawer-section" data-testid="drawer-pmf-aef">
      <h3>Seguimiento AEF del PMF</h3>
      {loading ? (
        <p className="hint">Cargando los datos de todas las filas del PMF…</p>
      ) : failed ? (
        <p className="hint">No se pudo cargar el resumen AEF de este PMF.</p>
      ) : pmf ? (
        <dl className="facts">
          {AEF_FIELDS.map((key) => (
            <Fact key={key} label={AEF_FIELD_LABELS[key]} wide={pmf.fields[key].status === 'conflict'}>
              <AefPmfValue field={pmf.fields[key]} showRows={shared === null} />
            </Fact>
          ))}
        </dl>
      ) : (
        <p className="hint">Este PMF no tiene seguimiento AEF registrado.</p>
      )}
      {shared ? (
        <p className="hint" data-testid="drawer-pmf-aef-rows">
          Todos los valores de este PMF vienen de {shared.length === 1 ? 'la' : 'las'} {rowsLabel(shared)} de la hoja «Resumen».
          Las celdas vacías de otras filas siguen vacías.
        </p>
      ) : (
        <p className="hint">
          Valores del PMF reunidos desde todas sus filas; cada valor indica su fila de origen.
          Las celdas vacías de otras filas siguen vacías.
        </p>
      )}
    </section>
  )
}

function AefSection({
  row,
  detail,
  sourceHasAef,
}: {
  row: ResumenRow
  detail: TranselecPmfDetail | null
  sourceHasAef: boolean | null
}) {
  if (sourceHasAef === false) {
    return (
      <section className="drawer-section" data-testid="drawer-aef">
        <h3>Seguimiento AEF</h3>
        <p className="hint">
          La planilla publicada no incluye las columnas de seguimiento AEF, por lo que no hay
          información AEF para ninguna fila de esta versión.
        </p>
      </section>
    )
  }

  const tracked = detail?.rows.filter(hasAefTracking) ?? []
  const rowTracked = hasAefTracking(row)
  const missing = 'Sin registro en esta fila'

  return (
    <section className="drawer-section" data-testid="drawer-aef">
      <h3>AEF de esta fila de origen</h3>
      {chronologyFlagsOf(row).length > 0 && (
        <AlertBanner tone="warn" title="Fechas a revisar en la planilla">
          {chronologyFlagsOf(row).map(chronologyLabel).join('; ')}. Se muestran tal como vienen en
          la fila {formatInteger(row.source_row_number)}; no se corrigen.
        </AlertBanner>
      )}
      <dl className="facts">
        <Fact label="AEF">{cell(row.aef, missing)}</Fact>
        <Fact label="Quién solicita">{cell(row.quien_solicita, missing)}</Fact>
        <Fact label="Fecha solicitud">
          <SourceDate row={row} field="fecha_solicitud" missing={missing} />
        </Fact>
        <Fact label="Fecha corta">
          <SourceDate row={row} field="fecha_corta" missing={missing} />
        </Fact>
        <Fact label="Fecha término">
          <SourceDate row={row} field="fecha_termino" missing={missing} />
        </Fact>
      </dl>
      {detail && (
        <p className="hint" data-testid="drawer-aef-coverage">
          {formatInteger(tracked.length)} de {formatInteger(detail.row_count)} filas de{' '}
          {detail.pmf} tienen registro AEF.
          {!rowTracked &&
            tracked.length > 0 &&
            ` El seguimiento de este PMF está en ${tracked.length === 1 ? 'la fila' : 'las filas'} ${tracked
              .map((entry) => entry.source_row_number)
              .join(', ')}; esta fila no lo repite y se muestra vacía, como en la planilla.`}
        </p>
      )}
    </section>
  )
}

export function RowDetailDrawer({
  row,
  onClose,
  sourceFields,
  lifecycle = null,
  plazo = null,
  plazoStatus,
  canEdit = false,
  activeImportId = null,
  onRowEdited,
}: {
  row: ResumenRow
  onClose: () => void
  /** The published version's source fields; null/undefined while unknown. */
  sourceFields?: readonly string[] | null
  /** Where the PMF stands (`lifecycle_pmf_v1`), when the Estado section opens it. */
  lifecycle?: LifecycleRow | null
  /** CONAF's 90-business-day term for this PMF, when the Estado section opens it. */
  plazo?: PlazoDetail | null
  /** Shown instead of the term while it is pending, failed or absent. */
  plazoStatus?: PlazoDrawerStatus
  /** Operator/admin: offer web edits (the server re-enforces Action.EDIT). */
  canEdit?: boolean
  activeImportId?: number | null
  onRowEdited?: (row: ResumenRow) => void
}) {
  const sourceHasAef = aefInSource(sourceFields)
  const sourceHasIngreso2 = ingreso2InSource(sourceFields)
  const [current, setCurrent] = useState<ResumenRow>(row)
  const [openedFrom, setOpenedFrom] = useState<ResumenRow>(row)
  const [detail, setDetail] = useState<TranselecPmfDetail | null>(null)
  const [failure, setFailure] = useState<FailureView | null>(null)
  const [loading, setLoading] = useState(true)
  const [pmfAef, setPmfAef] = useState<AefPmf | null>(null)
  const [pmfAefLoading, setPmfAefLoading] = useState(sourceHasAef !== false)
  const [pmfAefFailed, setPmfAefFailed] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  // Set after a revert or reload: the next fetched copy of the row is also
  // handed to the page behind (its table row and «web» chip).
  const [refreshRow, setRefreshRow] = useState(false)
  const [overrides, setOverrides] = useState<TranselecOverride[]>([])
  const [overridesStatus, setOverridesStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [suggestions, setSuggestions] = useState<Partial<Record<EditableFieldName, string[]>>>({})
  // What «Campos editables» holds: an unsaved change makes a row switch ask
  // first; a save in flight holds row switches until it answers.
  const [editState, setEditState] = useState<EditState>('idle')
  const [pendingRow, setPendingRow] = useState<ResumenRow | null>(null)
  const switchTrigger = useRef<HTMLElement | null>(null)

  // A different row chosen behind the panel replaces the one shown here.
  // Adjusted during render rather than in an effect, so the panel never
  // paints one frame of the previous row.
  const currentRowRef = useRef(current.source_row_number)
  const refreshRowRef = useRef(false)
  const onRowEditedRef = useRef(onRowEdited)
  useEffect(() => {
    currentRowRef.current = current.source_row_number
    refreshRowRef.current = refreshRow
    onRowEditedRef.current = onRowEdited
  })

  if (openedFrom !== row) {
    setOpenedFrom(row)
    setCurrent(row)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setDetail(null)
    setFailure(null)

    void getPmfDetail(row.pmf).then((result) => {
      if (cancelled) return
      if (result.ok) {
        setDetail(result.data)
        // After a save or a reload, show the fresh copy of the row being read.
        if (reloadToken > 0) {
          const fresh = result.data.rows.find(
            (entry) => entry.source_row_number === currentRowRef.current,
          )
          if (fresh) {
            setCurrent(fresh)
            if (refreshRowRef.current) {
              refreshRowRef.current = false
              setRefreshRow(false)
              onRowEditedRef.current?.(fresh)
            }
          }
        }
      } else setFailure(classifyFailure({ status: result.status, error: result.error }))
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [row.pmf, reloadToken])

  useEffect(() => {
    let cancelled = false
    void listOverrides({ pmf: row.pmf }).then((result) => {
      if (cancelled) return
      setOverrides(result.ok ? result.data : [])
      setOverridesStatus(result.ok ? 'ready' : 'error')
    })
    return () => {
      cancelled = true
    }
  }, [row.pmf, reloadToken])

  useEffect(() => {
    if (!canEdit || activeImportId === null) return
    let cancelled = false
    void loadSuggestions(activeImportId).then((values) => {
      if (!cancelled) setSuggestions(values)
    })
    return () => {
      cancelled = true
    }
  }, [canEdit, activeImportId])

  useEffect(() => {
    if (sourceHasAef === false) {
      setPmfAef(null)
      setPmfAefLoading(false)
      setPmfAefFailed(false)
      return
    }
    let cancelled = false
    setPmfAef(null)
    setPmfAefLoading(true)
    setPmfAefFailed(false)
    void getAef({ ...EMPTY_FILTERS, q: row.pmf }).then((result) => {
      if (cancelled) return
      if (result.ok) setPmfAef(result.data.pmfs.find((entry) => entry.pmf === row.pmf) ?? null)
      else setPmfAefFailed(true)
      setPmfAefLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [row.pmf, sourceHasAef])

  const rows = detail
    ? [...detail.rows].sort((a, b) => a.source_row_number - b.source_row_number)
    : []
  const firstRow = rows[0] ?? null
  // The PMF is counted under its first row's «Estado resumido». Say so only
  // when the row being read disagrees, which is when it matters.
  const countedDifferently =
    detail !== null &&
    firstRow !== null &&
    firstRow.source_row_number !== current.source_row_number &&
    cell(detail.estado_resumido) !== cell(current.estado_resumido)

  const chooseRow = (entry: ResumenRow) => {
    if (editState === 'saving') return
    if (editState === 'idle') {
      setCurrent(entry)
      return
    }
    switchTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    setPendingRow(entry)
  }

  // Keyed by row, so another row starts with no open editor and no stale
  // «Se guardó el cambio». For editors it leads the panel; viewers keep it
  // where it was, after Tramitación.
  const editables = (canEdit || (current.web_fields ?? []).length > 0) && (
    <EditableFieldsSection
      key={current.source_row_number}
      row={current}
      activeImportId={activeImportId}
      canEdit={canEdit}
      sourceFields={sourceFields ?? null}
      overrides={overrides}
      overridesStatus={overridesStatus}
      suggestions={suggestions}
      onEditStateChange={setEditState}
      onSaved={(updated) => {
        // A save answers for the row its editor was opened on. If the reader
        // has moved to another row since, the panel stays where it is.
        if (updated.source_row_number === currentRowRef.current) setCurrent(updated)
        setReloadToken((value) => value + 1)
        onRowEdited?.(updated)
      }}
      onReload={() => setReloadToken((value) => value + 1)}
      onRowEdited={() => setRefreshRow(true)}
    />
  )

  const where = [
    cell(current.predio_ref, 'Sin predio de reforestación informado'),
    current.rol ? `rol ${current.rol}` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <Drawer
      title={current.pmf}
      eyebrow="Plan de manejo (PMF)"
      subtitle={where}
      onClose={onClose}
      testId="row-drawer"
      headerExtra={
        <div className="drawer-meta">
          <StatusPill value={current.estado_resumido} />
          <span className="provenance" data-testid="drawer-provenance">
            Fila de origen {formatInteger(current.source_row_number)} de la hoja «Resumen»
          </span>
        </div>
      }
    >
      <div className="drawer-sections">
        {canEdit && editables}

        {countedDifferently && (
          <p className="drawer-note" data-testid="drawer-counted-as">
            En las cifras del panel este PMF se cuenta como «{cell(detail?.estado_resumido, 'sin estado')}»,
            el «Estado resumido» de su primera fila (fila {formatInteger(firstRow?.source_row_number)}).
          </p>
        )}

        {lifecycle && (
          <section
            className="drawer-section"
            aria-labelledby="drawer-proceso"
            data-testid="drawer-lifecycle"
          >
            <h3 id="drawer-proceso">
              Proceso CONAF <span className="hint">(provisional)</span>
            </h3>
            <dl className="facts">
              <Fact label="Grupo">{LIFECYCLE_GROUP_LABELS[lifecycle.lifecycle_group]}</Fact>
              <Fact label={lifecycle.lifecycle_reason ? 'Para revisar en la planilla' : 'Paso'}>
                {lifecycleStepText(lifecycle)}
              </Fact>
            </dl>
            {lifecycle.lifecycle_flags.map((flag) => (
              <p className="hint" key={flag}>
                {LIFECYCLE_FLAG_LABELS[flag]}.
              </p>
            ))}
            <p className="hint">
              Según la primera fila del PMF (fila {formatInteger(lifecycle.source_row_number)}).
              Categorías provisionales hasta que Campo Digital las confirme.
            </p>
          </section>
        )}

        {plazo ? (
          <PlazoDrawerSection detail={plazo} />
        ) : (
          plazoStatus && <PlazoDrawerNotice status={plazoStatus} />
        )}

        <section className="drawer-section" aria-labelledby="drawer-tramitacion">
          <h3 id="drawer-tramitacion">Tramitación</h3>
          {/* Editors read and change these in «Campos editables» above; the
              same values twice pushed the editor ~1,100 px down. */}
          <dl className="facts">
            {!canEdit && (
              <>
                <Fact label="Estado vigente" wide web={isWebField(current, 'estado')}>
                  {cell(current.estado, 'Sin información')}
                </Fact>
                <Fact label="Motivo" wide web={isWebField(current, 'tipo_rechazo')}>
                  {cell(current.tipo_rechazo, 'Sin motivo registrado')}
                </Fact>
                <Fact label="N.º ingreso" web={isWebField(current, 'numero_ingreso')}>
                  {cell(current.numero_ingreso, 'Sin ingreso')}
                  <OficinaVirtualLink
                    key={current.numero_ingreso ?? ''}
                    numero={current.numero_ingreso}
                    testId="drawer-ov-1"
                  />
                </Fact>
                <Fact label="Fecha ingreso" web={isWebField(current, 'fecha_ingreso')}>
                  <SourceDate row={current} field="fecha_ingreso" missing="Sin fecha" />
                </Fact>
              </>
            )}
            {sourceHasIngreso2 === false ? (
              <Fact label="Segundo ingreso" wide>
                <span className="hint" data-testid="drawer-ingreso-2-absent">
                  La planilla publicada no incluye las columnas «Fecha de ingreso2» y «N
                  Ingreso2».
                </span>
              </Fact>
            ) : (
              !canEdit && (
                <>
                  <Fact label="N.º ingreso 2" web={isWebField(current, 'numero_ingreso_2')}>
                    <span data-testid="drawer-numero-ingreso-2">
                      {cell(current.numero_ingreso_2, 'Sin segundo ingreso')}
                    </span>
                    {current.numero_ingreso_2 && (
                      <OficinaVirtualLink
                        key={current.numero_ingreso_2}
                        numero={current.numero_ingreso_2}
                        testId="drawer-ov-2"
                      />
                    )}
                  </Fact>
                  <Fact label="Fecha ingreso 2" web={isWebField(current, 'fecha_ingreso_2')}>
                    <span data-testid="drawer-fecha-ingreso-2">
                      <SourceDate row={current} field="fecha_ingreso_2" missing="Sin fecha" />
                    </span>
                  </Fact>
                </>
              )
            )}
            {!canEdit && (
              <Fact label="«90 dias» de la planilla" web={isWebField(current, 'fecha_90_dias')}>
                <SourceDate row={current} field="fecha_90_dias" missing="Sin fecha" />
              </Fact>
            )}
            <Fact label="PAS">{cell(current.pas, 'Sin información')}</Fact>
            <Fact label="Empresa">{cell(current.empresa, 'Sin información')}</Fact>
            <Fact label="Propietario">{cell(current.tipo_propietario, 'Sin información')}</Fact>
          </dl>
        </section>

        {!canEdit && editables}

        {sourceHasAef !== false && (
          <PmfAefSection pmf={pmfAef} loading={pmfAefLoading} failed={pmfAefFailed} />
        )}
        <AefSection row={current} detail={detail} sourceHasAef={sourceHasAef} />

        <section className="drawer-section" aria-labelledby="drawer-rows">
          <h3 id="drawer-rows">
            Filas de {current.pmf}{' '}
            {detail && (
              <span className="hint" data-testid="drawer-sibling-count">
                ({formatInteger(detail.row_count)}{' '}
                {detail.row_count === 1 ? 'fila en total' : 'filas en total'})
              </span>
            )}
          </h3>
          {loading && <LoadingBlock label="Buscando las filas de este PMF…" lines={2} />}
          {failure && <AlertBanner title={failure.title}>{failure.message}</AlertBanner>}
          {detail &&
            (rows.length > 1 ? (
              <>
                <p className="hint">Elija una fila para ver su detalle aquí mismo.</p>
                <div className="tablewrap short">
                  <table className="drawer-rows">
                    <thead>
                      <tr>
                        <th scope="col">Fila</th>
                        <th scope="col">Rol</th>
                        <th scope="col">Área</th>
                        <th scope="col" className="numeric">
                          Sup. ha
                        </th>
                        <th scope="col">Estado</th>
                        {sourceHasAef !== false && <th scope="col">AEF</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((entry) => {
                        const selected = entry.source_row_number === current.source_row_number
                        return (
                          <tr
                            key={entry.source_row_number}
                            aria-current={selected ? 'true' : undefined}
                            data-testid={`drawer-row-${entry.source_row_number}`}
                          >
                            <td className="numeric">
                              {selected ? (
                                <span className="row-here">
                                  {entry.source_row_number}
                                  <span className="row-here-tag">esta fila</span>
                                </span>
                              ) : (
                                <button
                                  type="button"
                                  className="row-switch"
                                  onClick={() => chooseRow(entry)}
                                  disabled={editState === 'saving'}
                                  aria-label={`Ver la fila ${entry.source_row_number}`}
                                >
                                  {entry.source_row_number}
                                </button>
                              )}
                            </td>
                            <td>{cell(entry.rol)}</td>
                            <td>{cell(entry.numero_area_corta)}</td>
                            <td className="numeric">{formatNumber(entry.superficie_corta)}</td>
                            <td>
                              <StatusPill value={entry.estado_resumido} />
                            </td>
                            {sourceHasAef !== false && (
                              <td>{cell(entry.aef) || <span className="aef-empty">—</span>}</td>
                            )}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p className="hint">Este PMF tiene una sola fila de origen en la versión publicada.</p>
            ))}
        </section>

        <section className="drawer-section" aria-labelledby="drawer-area">
          <h3 id="drawer-area">
            Área de corta de la fila {formatInteger(current.source_row_number)}
          </h3>
          <dl className="facts">
            <Fact label="Predio ref." wide>
              {cell(current.predio_ref, 'Sin información')}
            </Fact>
            <Fact label="Rol">{cell(current.rol, 'Sin rol')}</Fact>
            <Fact label="Predio">{cell(current.numero_predio, 'Sin información')}</Fact>
            <Fact label="Área corta">{cell(current.numero_area_corta, 'Sin información')}</Fact>
            <Fact label="Superficie">
              {formatNumber(current.superficie_corta)} ha de un total de{' '}
              {formatNumber(current.superficie_total_corta)} ha
            </Fact>
            <Fact label="Sector">{cell(current.sector, 'Sin información')}</Fact>
            <Fact label="ID predial">{cell(current.id_predio_unico, 'Sin identificador')}</Fact>
            <Fact label="Carpeta PMF">{cell(current.carpeta_source, 'Sin información')}</Fact>
            <Fact label="Carpeta normalizada">
              {cell(current.carpeta_normalizada, 'Sin información')}
            </Fact>
          </dl>
        </section>
      </div>
      {pendingRow && (
        <DrawerConfirm
          title="¿Descartar el cambio sin guardar?"
          confirmLabel="Descartar el cambio"
          tone="danger"
          onConfirm={() => {
            setEditState('idle')
            setCurrent(pendingRow)
            setPendingRow(null)
          }}
          onCancel={() => {
            setPendingRow(null)
            switchTrigger.current?.focus()
          }}
        >
          <p>
            Hay un cambio sin guardar en la fila {formatInteger(current.source_row_number)}. Si abre
            la fila {formatInteger(pendingRow.source_row_number)}, ese cambio se pierde.
          </p>
        </DrawerConfirm>
      )}
    </Drawer>
  )
}
