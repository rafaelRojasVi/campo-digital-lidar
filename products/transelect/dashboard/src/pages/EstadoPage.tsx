/**
 * `/transelec/estado` — where each plan (PMF) stands in CONAF's process, and
 * how much of CONAF's 90-business-day term is left.
 *
 * Replaces «Pendientes» (meeting of 2026-10-02; specs
 * docs/superpowers/specs/2026-10-04-transelec-estado-lifecycle-design.md and
 * docs/superpowers/specs/2026-10-04-transelec-plazo-90-habiles-design.md).
 * `GET /transelec/lifecycle` gives each PMF's group and step
 * (`lifecycle_pmf_v1`); `GET /transelec/plazos` gives its term
 * (`plazo_conaf_90_habiles_v1`), joined to the table by PMF through
 * `EstadoTable`'s `extraColumns`. Both follow the current filter state.
 *
 * TR-FUNC-031 («¿Qué ingresos superaron 90 días?») is answered by the server
 * now: business days in Chile's calendar from the most recent ingreso, with
 * «today» the server's date in Chile. The browser-only panel that compared
 * the planilla's «90 dias» with the response's `Date` header is gone; its
 * rule is kept by the API as `vencimiento_columna_90_dias_legacy` and its
 * count is shown beside the new one. The old «Pendientes prioritarios» rule
 * stays, closed, in `LegacyPendingSection`.
 */
import { useCallback, useMemo, useState } from 'react'
import {
  type LifecycleRow,
  type ResumenRow,
  type TranselecLifecycle,
  type TranselecPlazos,
  getLifecycle,
  getPlazos,
} from '../api'
import { EstadoTable } from '../components/EstadoTable'
import { PlazoFailureBanner } from '../components/PlazoFailureBanner'
import { LegacyPendingSection } from '../components/LegacyPendingSection'
import { RowDetailDrawer } from '../components/RowDetailDrawer'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { formatDate, formatInteger } from '../format'
import { activeFilterChips, withoutChip } from '../lib/filterUrl'
import { lifecycleGroupSegments, lifecycleStepSegments } from '../lib/lifecycle'
import { indexPlazos, plazoDetail } from '../lib/plazo'
import { plazoColumn } from '../lib/plazoColumn'
import { useReads, type FilterController } from '../lib/useFilters'
import { PENDING_QUEUE_HASH, useRouter } from '../router'
import { CompositionBar } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'
import { Chip, SectionHeader } from '../ui/Primitives'

export function EstadoPage({
  filterController,
  sourceFields = null,
  activeImportId = null,
  canEdit = false,
}: {
  filterController: FilterController
  /** Contract fields the published workbook had, for the detail drawer. */
  sourceFields?: readonly string[] | null
  activeImportId?: number | null
  /** Operator/admin: the drawer offers web edits. */
  canEdit?: boolean
}) {
  const { filters, replaceFilters, reset } = filterController
  const { hash } = useRouter()
  const key = JSON.stringify(filters)

  const { data, loading, failure, reload } = useReads<TranselecLifecycle>(
    useCallback(
      () => getLifecycle(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )

  // A separate read: the lifecycle table stands on its own if the plazo
  // calculation fails, with a dash in its column and one banner.
  const plazos = useReads<TranselecPlazos>(
    useCallback(
      () => getPlazos(filters),
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [key],
    ),
    [key],
  )
  const plazoIndex = useMemo(() => indexPlazos(plazos.data), [plazos.data])

  const [openRow, setOpenRow] = useState<ResumenRow | null>(null)
  const [soloVencidos, setSoloVencidos] = useState(false)

  // Without a plazo read there is nothing to filter by: leave the view, so the
  // table never shows every PMF under a stuck «Ver todos los PMF».
  if (plazos.failure && soloVencidos) setSoloVencidos(false)

  const chips = activeFilterChips(filters)
  const openLifecycle: LifecycleRow | null =
    openRow && data ? (data.rows.find((entry) => entry.pmf === openRow.pmf) ?? null) : null
  const rows =
    data && soloVencidos && plazos.data
      ? data.rows.filter((row) => plazoIndex.get(row.pmf)?.estado === 'vencido')
      : (data?.rows ?? [])
  const sinContar = plazos.data
    ? plazos.data.estados.sin_fecha_texto + plazos.data.estados.conflicto
    : 0
  const openPlazo = openRow ? plazoDetail(plazos.data, openRow.pmf) : null
  const plazoStatus = plazos.failure
    ? 'error'
    : plazos.loading && !plazos.data
      ? 'loading'
      : 'empty'

  if (failure && !data) {
    return (
      <div className="page">
        <StateBlock view={failure} />
      </div>
    )
  }

  return (
    <div className="page enter">
      <SectionHeader
        title={
          <>
            Estado <span className="hint">(provisional)</span>
          </>
        }
        meta="Dónde está cada PMF en la tramitación CONAF y cuánto le queda del plazo de 90 días hábiles. Un rechazo es un paso, no un final."
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

      {failure && data && <AlertBanner title={failure.title}>{failure.message}</AlertBanner>}
      {plazos.failure && (
        <div style={{ marginBottom: 'var(--s-5)' }}>
          <PlazoFailureBanner
            failure={plazos.failure}
            rawFailure={plazos.rawFailure}
            loading={plazos.loading}
            onRetry={plazos.reload}
            scope="El servidor no pudo contar los días hábiles. La columna «Plazo CONAF» y la pregunta de vencidos no están disponibles; el resto de la página sí."
          />
        </div>
      )}

      {!data && loading && <LoadingBlock label="Cargando el estado de los PMF…" shape="bar" />}

      {data && (
        <section id="estadozone" data-testid="estado-zone">
          <div className="pending-lead">
            <CompositionBar
              title="PMF por grupo"
              noun="PMF"
              testId="estado-group"
              segments={lifecycleGroupSegments(data)}
            />
            <CompositionBar
              title="En trámite, por paso"
              noun="PMF en trámite"
              testId="estado-step"
              lead={false}
              segments={lifecycleStepSegments(data)}
            />
          </div>

          <p className="hint">
            El grupo sale del «Estado resumido» de la primera fila de cada PMF; el paso, de su
            «Estado». «Rechazado» es un paso dentro de «En trámite»: todo rechazo termina en
            «Aprobado», «Descartado» o «Desistido». Lo que esta regla no reconoce queda «Sin
            clasificar» y se lista en Calidad. El plazo CONAF cuenta 90 días hábiles desde el
            ingreso más reciente. Categorías y plazo provisionales hasta que Campo Digital los
            confirme.
          </p>
          <HowCalculated
            bases={[
              data.basis,
              ...(plazos.data ? [plazos.data.basis, plazos.data.legacy_basis] : []),
            ]}
            testId="estado-how"
          />

          <div className="btns no-print" style={{ margin: 'var(--s-5) 0' }}>
            {chips.length > 0 && (
              <button
                type="button"
                className="btn alt"
                onClick={reset}
                data-testid="clear-estado-filters"
              >
                Quitar filtros y ver todos los PMF
              </button>
            )}
            <button
              type="button"
              className={soloVencidos ? 'btn' : 'btn alt'}
              disabled={!plazos.data}
              onClick={() => setSoloVencidos((value) => !value)}
              data-quick="overdue"
            >
              {soloVencidos ? 'Ver todos los PMF' : '¿Qué PMF superaron los 90 días hábiles?'}
            </button>
          </div>

          <div role="status">
            {soloVencidos && plazos.data && (
              <p
                className="hint"
                data-testid="plazo-vencidos-note"
                style={{ marginBottom: 'var(--s-5)' }}
              >
                <b data-testid="plazo-vencidos-count">
                  {formatInteger(plazos.data.estados.vencido)}
                </b>{' '}
                PMF con el plazo CONAF vencido al <b>{formatDate(plazos.data.observed_on)}</b>, la
                fecha del servidor en Chile, no una fecha fija. Con la regla anterior (fecha «90
                dias» de la planilla anterior a hoy, sin «Aprobado») serían{' '}
                <b data-testid="plazo-legacy-count">
                  {formatInteger(plazos.data.legacy_vencido_row_count)}
                </b>{' '}
                áreas de corta.
                {sinContar > 0 && (
                  <>
                    {' '}
                    Sin contar <b>{formatInteger(sinContar)}</b> PMF cuya fecha de ingreso no se
                    pudo leer o difiere entre filas.
                  </>
                )}
              </p>
            )}
          </div>

          <section className="ruled" aria-labelledby="estado-rows-title">
            <SectionHeader
              id="estado-rows-title"
              title={soloVencidos ? 'PMF con el plazo CONAF vencido' : 'PMF del alcance'}
              meta={
                soloVencidos && plazos.data
                  ? `${formatInteger(rows.length)} de ${formatInteger(data.rows.length)} PMF · vencidos al ${formatDate(plazos.data.observed_on)}`
                  : `${formatInteger(rows.length)} PMF · seleccione uno para ver su detalle`
              }
            />
            <EstadoTable
              rows={rows}
              selectedRow={openRow?.source_row_number ?? null}
              onOpen={setOpenRow}
              extraColumns={[plazoColumn(plazoIndex, plazos.loading)]}
              emptyText={soloVencidos ? 'Ningún PMF del alcance superó el plazo.' : undefined}
            />
          </section>

          <section className="ruled">
            <LegacyPendingSection
              filters={filters}
              reveal={hash === PENDING_QUEUE_HASH}
              selectedRow={openRow?.source_row_number ?? null}
              onOpenRow={setOpenRow}
            />
          </section>
        </section>
      )}

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          lifecycle={openLifecycle}
          plazo={openPlazo}
          plazoStatus={plazoStatus}
          onClose={() => setOpenRow(null)}
          sourceFields={sourceFields}
          canEdit={canEdit}
          activeImportId={activeImportId}
          // An edit can move the PMF to another group or change its term.
          onRowEdited={() => {
            reload()
            plazos.reload()
          }}
        />
      )}
    </div>
  )
}
