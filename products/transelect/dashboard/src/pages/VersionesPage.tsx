/**
 * The Datos section's versions pane — version history and restore.
 *
 * `GET /transelec/imports` returns one row per activation event
 * (`transelec_publish_event`), not one per import: an import activated twice
 * appears twice, each with its own actor, timestamp and event type. That is
 * the audit trail Javier's current workflow has no equivalent of — rolling
 * back today means re-sending a whole HTML file by hand.
 *
 * Restore is the same activation primitive as publish, recorded with
 * `event_type='restore'`. It never re-validates, because an invalid import
 * can never have been committed in the first place. The confirmation dialog
 * states exactly which import is about to become active again before the
 * mutation fires.
 *
 * The shipped version rendered this as a ten-column table whose `Acción` cell
 * for the current row was a disabled button reading "Versión activa", with
 * the active version's own summary repeated in a second card underneath. It
 * is a timeline now: the active version is the anchored first entry carrying
 * its full provenance inline, and each prior activation is an entry with its
 * actor, its event type and its restore action. Same rows, same events, same
 * endpoint — read as a history with a present, rather than as a report.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  type TranselecActiveImport,
  type TranselecImportHistoryRow,
  type TranselecImportReport,
  getImportReport,
  listImportHistory,
  restoreImport,
} from '../api'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { LayoutReview } from '../components/LayoutReview'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { formatBytes, formatDateTime, formatInteger, formatNumber, shortHash } from '../format'
import { classifyFailure, type ApiFailure, type FailureView } from '../lib/apiState'
import { Link, ROUTES } from '../router'
import { SectionHeader } from '../ui/Primitives'

/**
 * The active version's persisted layout review, loaded on request.
 *
 * The review an operator saw before publishing stays with the import, so the
 * warnings a version was published with can be re-read later by anyone who
 * can import. Imports validated before contract V2 kept no review; that is
 * said plainly rather than shown as "no warnings".
 */
function ActiveImportReview({ importId }: { importId: number }) {
  const [report, setReport] = useState<TranselecImportReport | null>(null)
  const [error, setError] = useState<FailureView | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const result = await getImportReport(importId)
    setLoading(false)
    if (result.ok) setReport(result.data)
    else setError(classifyFailure(result))
  }, [importId])

  if (report) {
    return report.mapping_report ? (
      <LayoutReview report={report.mapping_report} heading="Revisión de la versión activa" />
    ) : (
      <p className="hint" data-testid="review-unavailable">
        Esta versión se validó con el contrato anterior, que no guardaba un informe de columnas.
      </p>
    )
  }

  return (
    <div className="stack-tight">
      {error && <AlertBanner title={error.title}>{error.message}</AlertBanner>}
      <div className="btns no-print">
        <button
          type="button"
          className="btn alt small"
          onClick={() => void load()}
          disabled={loading}
          data-testid="load-review"
        >
          {loading ? 'Cargando la revisión…' : 'Ver la revisión de columnas y advertencias'}
        </button>
      </div>
    </div>
  )
}

export function VersionesPage({
  activeImport,
  onActiveVersionChanged,
}: {
  activeImport: TranselecActiveImport | null
  onActiveVersionChanged: () => void
}) {
  const [history, setHistory] = useState<TranselecImportHistoryRow[] | null>(null)
  const [failure, setFailure] = useState<ApiFailure | null>(null)
  const [loading, setLoading] = useState(true)
  const [target, setTarget] = useState<TranselecImportHistoryRow | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [restoreError, setRestoreError] = useState<FailureView | null>(null)
  const [restored, setRestored] = useState<number | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void listImportHistory().then((result) => {
      if (cancelled) return
      if (result.ok) {
        setHistory(result.data)
        setFailure(null)
      } else {
        setHistory(null)
        setFailure({ status: result.status, error: result.error })
      }
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [reloadToken])

  const confirmRestore = useCallback(async () => {
    if (!target) return
    setRestoring(true)
    setRestoreError(null)
    const result = await restoreImport(target.import_id)
    setRestoring(false)
    if (!result.ok) {
      setRestoreError(classifyFailure(result))
      setTarget(null)
      return
    }
    setRestored(result.data.import_id)
    setTarget(null)
    onActiveVersionChanged()
    setReloadToken((value) => value + 1)
  }, [onActiveVersionChanged, target])

  if (loading && !history) {
    return <LoadingBlock label="Cargando el historial de versiones…" lines={4} />
  }

  if (failure) {
    return <StateBlock view={classifyFailure(failure)} />
  }

  const rows = history ?? []

  return (
    <div className="stack datos-pane">
      <section>
        <SectionHeader
          title="Versiones publicadas"
          meta="Cada entrada es una activación registrada, con quién la hizo y cuándo."
        />
        <p className="prose" style={{ marginBottom: 'var(--s-6)' }}>
          Una misma importación puede aparecer más de una vez si volvió a activarse. Restaurar no
          vuelve a validar la planilla: una importación inválida nunca llega a existir.
        </p>

        {restored !== null && (
          <AlertBanner tone="ok" title="Versión restaurada">
            La importación #{restored} vuelve a ser la versión activa del panel.
          </AlertBanner>
        )}
        {restoreError && (
          <AlertBanner title={restoreError.title}>{restoreError.message}</AlertBanner>
        )}

        {rows.length === 0 ? (
          <div className="empty" data-testid="versions-empty">
            Todavía no se ha publicado ninguna versión.{' '}
            <Link to={ROUTES.importar}>Importe una planilla</Link> para comenzar.
          </div>
        ) : (
          <ol className="timeline" style={{ marginTop: 'var(--s-5)' }}>
            {rows.map((row) => (
              <li
                className={`timeline-entry version-row${row.is_active ? ' active' : ''}`}
                key={row.publish_event_id}
                data-testid={`version-${row.publish_event_id}`}
              >
                <span className="timeline-dot" aria-hidden="true">
                  <i />
                </span>
                <div className="timeline-card">
                  <div className="timeline-head">
                    <span className="timeline-title">
                      Importación #{row.import_id}
                      <span
                        className={`version-badge${row.event_type === 'restore' ? ' restore' : ''}`}
                      >
                        {row.event_type === 'restore' ? 'Restauración' : 'Publicación'}
                      </span>
                      {row.is_active && <span className="version-badge active">Activa</span>}
                    </span>
                    <button
                      type="button"
                      className="btn alt small no-print"
                      disabled={row.is_active || restoring}
                      onClick={() => {
                        setRestoreError(null)
                        setRestored(null)
                        setTarget(row)
                      }}
                      data-testid={`restore-${row.import_id}`}
                    >
                      {row.is_active ? 'Versión activa' : 'Restaurar'}
                    </button>
                  </div>

                  <div className="timeline-meta">
                    <span>{formatDateTime(row.occurred_at)}</span>
                    <span>{row.actor_display_name ?? `Usuario ${row.actor_app_user_id}`}</span>
                    <span>{row.filename ?? 'Sin nombre registrado'}</span>
                    <span>
                      <code>{shortHash(row.sha256)}…</code>
                    </span>
                  </div>
                  <div className="timeline-meta">
                    <span>{formatInteger(row.business_rows)} filas</span>
                    <span>{formatInteger(row.distinct_pmf)} PMF</span>
                    <span>
                      {formatInteger(row.distinct_provisional_predio_ids)} identificadores prediales
                    </span>
                    <span>{formatNumber(row.surface_total)} ha</span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      {/*
        TR-FUNC-043/046 — the provenance the dashboard footer used to carry.
        It belongs beside the history that produced it, not at the bottom of a
        page of operational numbers, and it is still the active version's real
        provenance rather than a static filename string.
      */}
      {activeImport && (
        <section className="ruled" data-testid="provenance-footer">
          <SectionHeader title="Procedencia de la versión activa" />
          <dl className="defs">
            <dt>Versión</dt>
            <dd>
              #{activeImport.import_id} · publicada {formatDateTime(activeImport.published_at)}
              {activeImport.published_by_display_name
                ? ` por ${activeImport.published_by_display_name}`
                : ''}
              {activeImport.published_event_type === 'restore'
                ? ' (restauración de una versión anterior)'
                : ''}
            </dd>
            <dt>Archivo</dt>
            <dd>
              {activeImport.filename ?? 'Sin nombre registrado'} ·{' '}
              {formatBytes(activeImport.byte_size)}
            </dd>
            <dt>Huella</dt>
            <dd>
              <code>{shortHash(activeImport.sha256)}…</code>
            </dd>
            <dt>Contrato</dt>
            <dd>
              {activeImport.schema_contract_version} · {activeImport.parser_version}
            </dd>
            <dt>Validada</dt>
            <dd>{formatDateTime(activeImport.validated_at)}</dd>
            <dt>Advertencias</dt>
            <dd data-testid="active-warning-count">
              {activeImport.warning_count === 0
                ? 'Ninguna registrada'
                : `${formatInteger(activeImport.warning_count)} revisadas al publicar`}
            </dd>
            <dt>Contenido</dt>
            <dd>
              {formatInteger(activeImport.business_rows)} filas ·{' '}
              {formatInteger(activeImport.distinct_pmf)} PMF ·{' '}
              {formatInteger(activeImport.distinct_provisional_predio_ids)} identificadores
              prediales · {formatNumber(activeImport.surface_total)} ha
            </dd>
          </dl>
          <div style={{ marginTop: 'var(--s-5)' }}>
            <ActiveImportReview key={activeImport.import_id} importId={activeImport.import_id} />
          </div>
          <p className="hint" style={{ marginTop: 'var(--s-5)' }}>
            Fuente: hoja «Resumen» de la planilla maestra publicada. Las hojas históricas no se
            suman para evitar duplicidad y la hoja «Pendientes» no se cruza automáticamente. Esta
            aplicación lee la proyección publicada en la base de datos y nunca modifica la planilla
            de origen.
          </p>
          <p className="hint">
            Las marcas de Campo Digital y Transelec se muestran como identificación textual
            provisional: los logotipos originales no se reutilizan mientras no exista autorización
            expresa sobre esos archivos.
          </p>
        </section>
      )}

      {!activeImport && (
        <section className="ruled" data-testid="provenance-footer">
          <p className="hint">Sin versión publicada: todavía no hay procedencia que citar.</p>
          <p className="hint">
            Las marcas de Campo Digital y Transelec se muestran como identificación textual
            provisional: los logotipos originales no se reutilizan mientras no exista autorización
            expresa sobre esos archivos.
          </p>
        </section>
      )}

      {target && (
        <ConfirmDialog
          title="Restaurar una versión anterior"
          confirmLabel={`Activar la importación #${target.import_id}`}
          busy={restoring}
          tone="danger"
          onConfirm={() => void confirmRestore()}
          onCancel={() => setTarget(null)}
        >
          <p data-testid="restore-confirm-message">
            Está a punto de volver a activar la importación #{target.import_id}. Desde ese momento
            el panel mostrará ese contenido ({formatInteger(target.business_rows)} filas ·{' '}
            {formatInteger(target.distinct_pmf)} PMF · {formatNumber(target.surface_total)} ha) en
            lugar de la versión vigente.
          </p>
          <p>
            La restauración queda registrada con su nombre y la fecha, y puede deshacerse volviendo
            a publicar cualquier otra versión de esta lista.
          </p>
        </ConfirmDialog>
      )}
    </div>
  )
}
