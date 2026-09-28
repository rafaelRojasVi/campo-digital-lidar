/**
 * `/transelec/calidad` — source quality and reporting.
 *
 * Five things that all answer "what can I say about this data, and to whom"
 * were scattered across the shipped dashboard as four interchangeable cards
 * between the daily operational blocks: the quality indicators, the
 * conflicting-status evidence, the reforestation references, the
 * owner-status table and the executive report.
 * Grouped here, they stop competing with the work and start reading as one
 * job: produce and defend evidence.
 *
 * The page is written for Javier and the operators: each block leads with what
 * was found, how many plans, predios or rows it affects and what to review,
 * and keeps the exact rule, source columns and API identifier in a closed
 * «Cómo se calcula» detail.
 *
 * The owner-status table keeps its own disagreeing rule and keeps saying so.
 * `owner_stage_legacy` overrides `Estado resumido` with "Rechazado" whenever
 * the raw `Estado` contains "rechaz", so the same predio can be "En trámite"
 * on the Resumen and "Rechazado" here. That is the current behaviour,
 * reproduced rather than reconciled; the section now explains the difference
 * in plain words and shows both predio counts side by side.
 */
import { useCallback } from 'react'
import {
  type TranselecOwnerStatus,
  type TranselecReport,
  type TranselecSummary,
  getOwnerStatus,
  getReport,
  getSummary,
} from '../api'
import { ConflictPanel } from '../components/ConflictPanel'
import { OwnerStatusTable } from '../components/OwnerStatusTable'
import { QualityPanel } from '../components/QualityPanel'
import { ReforestacionPanel } from '../components/ReforestacionPanel'
import { ReforestationChips } from '../components/ReforestationChips'
import { ReportPanel } from '../components/ReportPanel'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { activeFilterChips, withoutChip } from '../lib/filterUrl'
import { useReads, type FilterController } from '../lib/useFilters'
import { Chip, SectionHeader } from '../ui/Primitives'

interface CalidadData {
  summary: TranselecSummary
  ownerStatus: TranselecOwnerStatus
  report: TranselecReport
}

export function CalidadPage({ filterController }: { filterController: FilterController }) {
  const { filters, replaceFilters } = filterController
  const key = JSON.stringify(filters)

  const { data, loading, failure } = useReads<CalidadData>(
    useCallback(async () => {
      const [summary, ownerStatus, report] = await Promise.all([
        getSummary(filters),
        getOwnerStatus(filters),
        getReport(filters),
      ])
      if (!summary.ok) return summary
      if (!ownerStatus.ok) return ownerStatus
      if (!report.ok) return report
      return {
        ok: true,
        data: { summary: summary.data, ownerStatus: ownerStatus.data, report: report.data },
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key]),
    [key],
  )

  const chips = activeFilterChips(filters)

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
        title="Calidad y reportes"
        meta="Qué conviene revisar en la versión publicada antes de informar sus cifras."
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

      {!data && loading && <LoadingBlock label="Cargando los controles de calidad…" lines={5} />}

      {data && (
        <div className="stack">
          <section aria-labelledby="quality-title">
            <SectionHeader
              id="quality-title"
              title="Qué revisar en la planilla"
              meta="Sobre el alcance seleccionado."
            />
            <QualityPanel summary={data.summary} filters={filters} />
          </section>

          <section className="ruled" aria-labelledby="conflict-title">
            <SectionHeader
              id="conflict-title"
              title="PMF con estados distintos entre sus filas"
              meta="Por qué los estados no cuadran si se suman fila a fila."
            />
            <ConflictPanel
              conflicts={data.summary.calidad_pmf_estado_resumido_conflictivo}
              basis={data.summary.basis_estado_resumido}
              filters={filters}
            />
          </section>

          <section className="ruled" aria-labelledby="owner-title">
            <OwnerStatusTable ownerStatus={data.ownerStatus} summary={data.summary} />
          </section>

          <section className="ruled" aria-labelledby="ref-title">
            <SectionHeader
              id="ref-title"
              title="Reforestación"
              meta="Qué se puede contar con la planilla actual, y qué no."
            />
            <ReforestacionPanel reforestacion={data.summary.reforestacion} />
            <div style={{ marginTop: 'var(--s-6)' }}>
              <ReforestationChips predios={data.summary.reforestacion.predio_ref_labels} />
            </div>
          </section>

          <section className="ruled" aria-labelledby="report-title">
            <ReportPanel report={data.report} />
          </section>
        </div>
      )}
    </div>
  )
}
