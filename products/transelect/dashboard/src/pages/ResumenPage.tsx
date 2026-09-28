/**
 * `/transelec` — the operational command centre.
 *
 * The page answers, in this order, the questions the people who use it
 * actually ask — and the visual weight follows that order:
 *
 *   1. ¿Cuál es el estado de los planes de manejo?   headline, PMF grain
 *   2. ¿En qué estado de tramitación exactamente?    detailed drill-down
 *   3. ¿Cómo se reparte entre empresas?              company matrix
 *   4. ¿Qué necesita atención?                       attention row
 *   5. ¿Cuántos predios de reforestación son?        reforestación section
 *   6. ¿Qué hago ahora?                              work queue, Explorador
 *
 * Question 1 is Javier's recurring one, asked of Marianne every reporting
 * cycle and answered by her off the workbook's `Estado resumido` column. It
 * is therefore the first analytical section and the page's largest figure,
 * at the grain the question is asked in: plans, not detail rows.
 *
 * Questions 5's honest answer is "not exactly" — see `ReforestacionPanel`.
 *
 * Every value comes from `GET /transelec/summary` and `GET /transelec/pending`
 * under the current filter state, which is read from the URL. Nothing here
 * recomputes a business number, and the two disagreeing legacy rules behind
 * these figures are named on screen rather than reconciled.
 *
 * The two reads are issued together and committed in one update (see
 * `useReads`), so the lead figure, the bars and the queue can never describe
 * two different filter states.
 */
import { useCallback, useState } from 'react'
import {
  type ResumenRow,
  type TranselecActiveImport,
  type TranselecPending,
  type TranselecSummary,
  getPending,
  getSummary,
} from '../api'
import { CompanyMatrix } from '../components/CompanyMatrix'
import { RowDetailDrawer } from '../components/RowDetailDrawer'
import { EstadoDetalleTable } from '../components/EstadoDetalleTable'
import { ReforestacionPanel } from '../components/ReforestacionPanel'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { StatusHeadline } from '../components/StatusHeadline'
import { cell, formatDateTime, formatInteger, formatNumber } from '../format'
import { activeFilterChips, withoutChip } from '../lib/filterUrl'
import { PENDING_STAGE_LABELS } from '../lib/pendingStage'
import {
  approvalSegments,
  buildAttentionItems,
  buildScaleStats,
  estadoResumidoSegments,
} from '../lib/summaryView'
import { useReads, type FilterController } from '../lib/useFilters'
import { Link, ROUTES } from '../router'
import { CompositionBar } from '../ui/CompositionBar'
import { HowCalculated } from '../ui/HowCalculated'
import { Chip, SectionHeader, StatStrip } from '../ui/Primitives'

const QUEUE_LIMIT = 6

interface ResumenData {
  summary: TranselecSummary
  pending: TranselecPending
}

export function ResumenPage({
  activeImport,
  canPublish,
  filterController,
}: {
  activeImport: TranselecActiveImport | null
  canPublish: boolean
  filterController: FilterController
}) {
  const { filters, replaceFilters } = filterController
  const key = JSON.stringify(filters)

  const { data, loading, failure } = useReads<ResumenData>(
    useCallback(async () => {
      const [summary, pending] = await Promise.all([getSummary(filters), getPending(filters)])
      if (!summary.ok) return summary
      if (!pending.ok) return pending
      return { ok: true, data: { summary: summary.data, pending: pending.data } }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]),
    [key],
  )

  const chips = activeFilterChips(filters)
  const [openRow, setOpenRow] = useState<ResumenRow | null>(null)

  if (failure && !data) {
    return (
      <div className="page">
        <StateBlock view={failure}>
          {failure.kind === 'empty' && canPublish && (
            <Link to={ROUTES.datos} className="btn">
              Importar planilla
            </Link>
          )}
        </StateBlock>
      </div>
    )
  }

  return (
    <div className="page enter">
      <div className="context-strip">
        <span className="client">Transmisora del Pacífico – Transelec</span>
        <span className="sep">/</span>
        <span>Seguimiento de Planes de Manejo Forestal · ingresos CONAF</span>
        {activeImport && (
          <>
            <span className="sep">/</span>
            <span>
              Versión #{activeImport.import_id}, publicada{' '}
              {formatDateTime(activeImport.published_at)}
              {activeImport.published_by_display_name
                ? ` por ${activeImport.published_by_display_name}`
                : ''}
            </span>
          </>
        )}
      </div>

      {chips.length > 0 && (
        <div className="active-filters" style={{ paddingTop: 'var(--s-5)' }}>
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

      {!data && loading && (
        <div className="stack" style={{ paddingTop: 'var(--s-7)' }}>
          <LoadingBlock label="Cargando el alcance seleccionado…" shape="bar" />
          <LoadingBlock label="" shape="rows" lines={4} />
        </div>
      )}

      {data && (
        <>
          <StatusHeadline summary={data.summary} filters={filters} />

          <section className="ruled" aria-labelledby="detalle-title">
            <SectionHeader
              id="detalle-title"
              title="Estado detallado de tramitación"
              meta={`Desglose del encabezado sobre los mismos ${formatInteger(
                data.summary.pmf_count,
              )} PMF · evaluación, rechazos y recursos`}
            />
            <EstadoDetalleTable summary={data.summary} />
          </section>

          <section className="ruled" aria-labelledby="empresa-title">
            <SectionHeader
              id="empresa-title"
              title="Por empresa"
              meta="Cada PMF pertenece a una sola empresa, por lo que los subtotales suman el total."
            />
            <CompanyMatrix summary={data.summary} filters={filters} />
          </section>

          <section className="ruled" aria-labelledby="atencion-title" data-testid="attention-row">
            <SectionHeader
              id="atencion-title"
              title="Requiere atención"
              meta="Cada tarjeta lleva a la sección que resuelve el caso."
            />
            <div className="attention">
              {buildAttentionItems(data.summary, {
                pendientes: ROUTES.pendientes,
                calidad: ROUTES.calidad,
              }).map((item) => (
                <Link
                  key={item.id}
                  to={item.href}
                  className="attention-card"
                  data-attention={item.id}
                  data-tone={item.tone}
                >
                  <span className="attention-value" data-testid={`kpi-${item.id}`}>
                    {formatInteger(item.value)}
                  </span>
                  <span className="attention-label">{item.label}</span>
                  <span className="attention-sub">{item.sub}</span>
                  <span className="attention-go">{item.action} →</span>
                </Link>
              ))}
            </div>
            <p className="hint" style={{ marginTop: 'var(--s-4)' }}>
              «Pendientes prioritarios» no se basa en el «Estado resumido» como «Aprobado» y «En
              trámite»: mira si falta el N.º de ingreso o si el «Estado» menciona un rechazo. Por
              eso un mismo PMF puede figurar «En trámite» y a la vez ser pendiente prioritario.
            </p>
            <HowCalculated
              bases={[data.summary.basis_pending_priority, data.summary.basis_estado_resumido]}
              testId="attention-how"
            />
          </section>

          <section className="ruled" aria-labelledby="alcance-title" data-testid="kpi-row">
            <SectionHeader
              id="alcance-title"
              title="Alcance medido"
              meta="Conteos de referencia del alcance seleccionado."
            />
            <StatStrip items={buildScaleStats(data.summary)} />
          </section>

          <section className="ruled" aria-labelledby="reforestacion-title">
            <SectionHeader
              id="reforestacion-title"
              title="Reforestación"
              meta="Lo que la planilla puede responder sobre reforestación, y lo que no."
            />
            <ReforestacionPanel reforestacion={data.summary.reforestacion} />
          </section>

          {/*
            The predio grain, kept and demoted rather than dropped. It answers
            a different question from the headline — a plan covers several
            cutting properties, so 159 PMF and 272 predios are two genuine
            denominators — and it is the grain the shipped interface led with.
            It stays available, below the question people actually ask.
          */}
          <section className="ruled" aria-labelledby="estado-predio-title">
            <SectionHeader
              id="estado-predio-title"
              title="Estado resumido por predio"
              meta={`${formatInteger(
                data.summary.predio_count,
              )} predios únicos del alcance seleccionado · un denominador distinto del de los PMF`}
            />
            <CompositionBar
              noun="predios aprobados"
              testId="status-hero"
              segments={estadoResumidoSegments(data.summary)}
            />
            <CompositionBar
              title="Agrupado como aprobado / en trámite / resto"
              noun="predios aprobados"
              testId="composition-predios"
              segments={approvalSegments(data.summary.avance_por_predio)}
            />
            <HowCalculated bases={[data.summary.basis_estado_resumido]} testId="predio-how" />
          </section>

          <section className="ruled" aria-labelledby="cola-title" data-testid="work-queue">
            <SectionHeader
              id="cola-title"
              title="Cola de trabajo"
              meta={
                <>
                  {formatInteger(data.pending.pending_pmf_count)} de{' '}
                  {formatInteger(data.pending.total_pmf_count)} PMF ·{' '}
                  {formatNumber(data.pending.pending_pmf_percentage)}%
                </>
              }
            />
            {data.pending.rows.length === 0 ? (
              <div className="queue">
                <p className="empty">
                  No hay PMF pendientes prioritarios para el alcance seleccionado.
                </p>
              </div>
            ) : (
              <div className="queue">
                {data.pending.rows.slice(0, QUEUE_LIMIT).map((row) => (
                  <button
                    type="button"
                    className="queue-row"
                    key={row.source_row_number}
                    data-testid={`queue-row-${row.source_row_number}`}
                    aria-haspopup="dialog"
                    aria-label={`Ver el detalle de ${row.pmf}, fila ${row.source_row_number}`}
                    data-selected={openRow?.source_row_number === row.source_row_number}
                    onClick={() => setOpenRow(row)}
                  >
                    <span className="queue-pmf">{row.pmf}</span>
                    <span className="queue-where">
                      {cell(row.predio_ref, 'Sin predio de reforestación informado')}
                      {row.rol ? ` · rol ${row.rol}` : ''}
                    </span>
                    <span className="queue-stage">{PENDING_STAGE_LABELS[row.pending_stage]}</span>
                    <span className="queue-stage">
                      {cell(row.numero_ingreso, 'Sin ingreso')}
                    </span>
                  </button>
                ))}
              </div>
            )}
            <div className="btns no-print" style={{ marginTop: 'var(--s-4)' }}>
              <Link to={ROUTES.pendientes} className="btn">
                Ver todos los pendientes
              </Link>
              <Link to={ROUTES.explorador} className="btn alt">
                Abrir el explorador
              </Link>
            </div>
            <HowCalculated
              bases={[data.pending.basis, data.pending.stage_basis]}
              testId="queue-how"
            />
          </section>
        </>
      )}

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          onClose={() => setOpenRow(null)}
          sourceFields={activeImport?.source_fields ?? null}
        />
      )}
    </div>
  )
}
