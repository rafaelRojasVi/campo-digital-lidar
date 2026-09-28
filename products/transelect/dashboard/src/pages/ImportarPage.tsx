/**
 * The Datos section's import pane — the replacement for TR-FUNC-040.
 *
 * The source dashboard's "Actualizar base Excel" button read the workbook in
 * the browser with a hand-rolled ZIP/XLSX reader, applied zero schema
 * validation, silently collapsed the two `Carpeta` columns, and kept the
 * result in tab memory only: reloading the page reverted it, and sharing an
 * update meant re-sending the whole HTML file by hand. None of that is
 * reproduced. This drives the real three-step pipeline instead:
 *
 *   1. upload            POST /transelec/uploads          (bounded, hashed, stored)
 *   2. validate/project  POST .../validate-and-project    (layout review + projection)
 *   3. publish           POST .../publish                 (explicit, audited, atomic)
 *
 * Since contract V2 step 2 recognizes the `Resumen` columns by header and
 * returns a layout report either way: on success (what matched, what was
 * ignored, warnings to review) and on refusal (every blocking issue with its
 * row and column references). A version with warnings can be published only
 * after the operator explicitly acknowledges having reviewed them.
 *
 * Validating never publishes. A validated import sits there until an operator
 * deliberately publishes it, which is why step 3 is a separate, confirmed
 * action rather than an automatic consequence of step 2.
 *
 * What changed visually: the three steps were three static bordered boxes
 * with no progression and no legible current step. They are now a real
 * stepper — a numbered rail whose markers change state as the pipeline runs —
 * and the file input is a drop zone that accepts a dragged workbook. The
 * pipeline, its ordering and its guarantees are untouched.
 */
import { useCallback, useRef, useState } from 'react'
import {
  type ActivationResult,
  type LayoutReport,
  type UploadResult,
  type ValidateAndProjectResult,
  layoutReportFromFailure,
  listRecentUploads,
  publishImport,
  uploadWorkbook,
  validateAndProject,
} from '../api'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { LayoutReview } from '../components/LayoutReview'
import { AlertBanner } from '../components/StateViews'
import { formatBytes, formatDateTime, formatInteger, formatNumber, shortHash } from '../format'
import { classifyFailure, type FailureView } from '../lib/apiState'
import { Link, ROUTES } from '../router'
import { SectionHeader } from '../ui/Primitives'

type Stage = 'upload' | 'validate' | 'publish'

type StepState = 'idle' | 'active' | 'done' | 'failed'

const RUN_LOOKUP_FAILED: FailureView = {
  kind: 'error',
  title: 'No se pudo continuar con la validación',
  message:
    'La carga se almacenó, pero no fue posible identificar su proceso de ingesta para validarla. Vuelva a intentarlo; si persiste, contacte a soporte.',
}

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

export function ImportarPage({ onActiveVersionChanged }: { onActiveVersionChanged: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [upload, setUpload] = useState<UploadResult | null>(null)
  const [validation, setValidation] = useState<ValidateAndProjectResult | null>(null)
  const [activation, setActivation] = useState<ActivationResult | null>(null)
  const [busy, setBusy] = useState<Stage | null>(null)
  const [failure, setFailure] = useState<{ stage: Stage; view: FailureView } | null>(null)
  const [refusalReport, setRefusalReport] = useState<LayoutReport | null>(null)
  const [warningsAcknowledged, setWarningsAcknowledged] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setFile(null)
    setUpload(null)
    setValidation(null)
    setActivation(null)
    setFailure(null)
    setRefusalReport(null)
    setWarningsAcknowledged(false)
    setBusy(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const runUploadAndValidate = useCallback(async (selected: File) => {
    setUpload(null)
    setValidation(null)
    setActivation(null)
    setFailure(null)
    setRefusalReport(null)
    setWarningsAcknowledged(false)

    setBusy('upload')
    const uploaded = await uploadWorkbook(selected)
    if (!uploaded.ok) {
      setBusy(null)
      setFailure({ stage: 'upload', view: classifyFailure(uploaded) })
      return
    }
    setUpload(uploaded.data)

    // POST /transelec/uploads returns the shared UploadResponse, which does
    // not carry the ingestion_run_id the validate step needs; the recent-runs
    // read route resolves it from the snapshot id this upload produced.
    const runs = await listRecentUploads()
    if (!runs.ok) {
      setBusy(null)
      setFailure({ stage: 'validate', view: classifyFailure(runs) })
      return
    }
    const run = runs.data.find(
      (entry) => entry.source_snapshot_id === uploaded.data.source_snapshot_id,
    )
    if (!run) {
      setBusy(null)
      setFailure({ stage: 'validate', view: RUN_LOOKUP_FAILED })
      return
    }

    setBusy('validate')
    const validated = await validateAndProject(run.ingestion_run_id)
    setBusy(null)
    if (!validated.ok) {
      setFailure({ stage: 'validate', view: classifyFailure(validated) })
      setRefusalReport(layoutReportFromFailure(validated.payload))
      return
    }
    setValidation(validated.data)
  }, [])

  const confirmPublish = useCallback(async () => {
    if (!validation) return
    setBusy('publish')
    const result = await publishImport(validation.import_id, {
      acknowledgeWarnings: validation.warning_count > 0 && warningsAcknowledged,
    })
    setBusy(null)
    setConfirming(false)
    if (!result.ok) {
      setFailure({ stage: 'publish', view: classifyFailure(result) })
      return
    }
    setActivation(result.data)
    setFailure(null)
    onActiveVersionChanged()
  }, [onActiveVersionChanged, validation, warningsAcknowledged])

  const stepState = (stage: Stage): StepState => {
    if (failure?.stage === stage) return 'failed'
    if (busy === stage) return 'active'
    if (stage === 'upload' && upload) return 'done'
    if (stage === 'validate' && validation) return 'done'
    if (stage === 'publish' && activation) return 'done'
    return 'idle'
  }

  const contractEvidence = upload?.validation_evidence as
    | { contract_error?: string | null; resumen_row_count?: number | null }
    | undefined

  const warningCount = validation?.warning_count ?? 0
  const canPublishNow =
    validation !== null &&
    !validation.is_active &&
    validation.status !== 'already_current' &&
    (warningCount === 0 || warningsAcknowledged)

  /** A dropped file is the same input as a chosen one; nothing else changes. */
  const acceptDrop = (dropped: File | undefined) => {
    setDragging(false)
    if (!dropped) return
    setFile(dropped)
    setFailure(null)
  }

  return (
    <div className="stack datos-pane">
      <section>
        <SectionHeader
          title="Importar planilla"
          meta="La versión que ve el panel sólo cambia cuando usted publica."
        />
        <p className="prose" style={{ marginBottom: 'var(--s-6)' }}>
          Cargue la planilla maestra (<code>.xlsx</code>). La plataforma valida el contrato de
          origen antes de proyectar cualquier fila, y una validación correcta no publica nada por sí
          sola.
        </p>

        <ol className="stepper">
          <li data-state={stepState('upload')} data-step="upload">
            <div className="step-body">
              <b>Cargar archivo</b>
              <span>
                La planilla se almacena con su huella SHA-256; una carga idéntica se reconoce como
                la misma versión.
              </span>
            </div>
          </li>
          <li data-state={stepState('validate')} data-step="validate">
            <div className="step-body">
              <b>Validar y proyectar</b>
              <span>
                Se reconocen las columnas de la hoja «Resumen» por su encabezado y se proyectan las
                filas. Verá qué se reconoció, qué se ignoró y qué revisar; si algo bloquea la
                importación, no queda ninguna importación a medias.
              </span>
            </div>
          </li>
          <li data-state={stepState('publish')} data-step="publish">
            <div className="step-body">
              <b>Publicar</b>
              <span>
                Activa la versión importada para todo el panel y queda registrada en la auditoría.
              </span>
            </div>
          </li>
        </ol>

        {!activation && (
          <div
            className={`dropzone no-print${dragging ? ' dragging' : ''}`}
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              acceptDrop(event.dataTransfer.files?.[0])
            }}
          >
            <p>
              Arrastre la planilla aquí o elija un archivo. Formato admitido: .xlsx. Tamaño máximo:
              2&nbsp;GiB.
            </p>
            <input
              ref={fileInputRef}
              id="workbook-file"
              type="file"
              accept={`.xlsx,${XLSX_MIME}`}
              aria-label="Planilla maestra (.xlsx)"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null)
                setFailure(null)
              }}
            />
            <label className="dropzone-pick" htmlFor="workbook-file">
              Elegir archivo
            </label>
            {file && (
              <p className="dropzone-file">
                Seleccionado: <b>{file.name}</b> · {formatBytes(file.size)}
              </p>
            )}
            <div className="btns">
              <button
                type="button"
                className="btn"
                disabled={!file || busy !== null}
                onClick={() => file && void runUploadAndValidate(file)}
                data-testid="upload-submit"
              >
                {busy === 'upload'
                  ? 'Cargando…'
                  : busy === 'validate'
                    ? 'Validando…'
                    : 'Cargar y validar'}
              </button>
              <button type="button" className="btn alt" onClick={reset} disabled={busy !== null}>
                Limpiar
              </button>
            </div>
          </div>
        )}

        {busy !== null && (
          <p
            className="loading-row"
            role="status"
            style={{ marginTop: 'var(--s-4)' }}
            data-testid="import-busy"
          >
            {busy === 'upload' && 'Cargando la planilla en la plataforma…'}
            {busy === 'validate' && 'Validando el contrato de origen y proyectando las filas…'}
            {busy === 'publish' && 'Publicando la versión…'}
          </p>
        )}
      </section>

      {failure && (
        <section className="stack-tight" data-testid="import-failure">
          <AlertBanner
            tone={failure.view.kind === 'invalid_upload' ? 'warn' : 'error'}
            title={failure.view.title}
          >
            {failure.view.message}
          </AlertBanner>
          {refusalReport && (
            <LayoutReview report={refusalReport} heading="Qué hay que corregir en la planilla" />
          )}
          {failure.stage !== 'upload' && (
            <p className="hint">
              La versión publicada actualmente no ha cambiado. Puede corregir la planilla y volver a
              cargarla sin riesgo para los datos en uso.
            </p>
          )}
          <div className="btns">
            <button type="button" className="btn alt" onClick={reset}>
              Cargar otra planilla
            </button>
          </div>
        </section>
      )}

      {upload && !failure && (
        <section className="stack-tight" data-testid="upload-evidence">
          <h2>Archivo recibido</h2>
          <div className="summary-grid">
            <div>
              <b>{shortHash(upload.sha256)}…</b>
              huella SHA-256
            </div>
            <div>
              <b>{formatBytes(upload.byte_size)}</b>
              tamaño
            </div>
            {typeof contractEvidence?.resumen_row_count === 'number' && (
              <div>
                <b>{formatInteger(contractEvidence.resumen_row_count)}</b>
                filas detectadas en «Resumen»
              </div>
            )}
          </div>
          {contractEvidence?.contract_error && (
            <AlertBanner tone="info" title="Observación de la inspección inicial">
              La inspección al momento de la carga registró una observación sobre el contrato de
              origen. Es evidencia, no un rechazo: la validación del paso 2 es la que decide.
            </AlertBanner>
          )}
        </section>
      )}

      {validation && !activation && (
        <section className="stack-tight" data-testid="validation-result">
          {validation.status === 'validated' && (
            <AlertBanner tone="ok" title="Planilla validada">
              La planilla cumple el contrato de origen y sus filas quedaron proyectadas como la
              importación #{validation.import_id}. Todavía no está publicada.
            </AlertBanner>
          )}
          {validation.status === 'already_imported' && (
            <AlertBanner tone="warn" title="Esta planilla ya había sido importada">
              El contenido cargado es idéntico a una importación existente (#{validation.import_id}
              ), por lo que no se volvió a proyectar. No está publicada: puede publicarla ahora.
            </AlertBanner>
          )}
          {validation.status === 'already_current' && (
            <AlertBanner tone="info" title="Esta planilla ya es la versión vigente">
              El contenido cargado corresponde a la importación #{validation.import_id}, que ya es
              la versión activa. No hay nada que publicar.
            </AlertBanner>
          )}

          <div className="summary-grid">
            <div>
              <b>{formatInteger(validation.business_rows)}</b>
              filas proyectadas
            </div>
            <div>
              <b>{formatInteger(validation.distinct_pmf)}</b>
              PMF distintos
            </div>
            <div>
              <b>{formatInteger(validation.distinct_provisional_predio_ids)}</b>
              identificadores prediales
            </div>
            <div>
              <b>{formatNumber(validation.surface_total)}</b>
              ha de superficie de corta
            </div>
          </div>
          <p className="hint">
            Contrato {validation.schema_contract_version} · parser {validation.parser_version} ·
            validada {formatDateTime(validation.validated_at)}
          </p>

          {validation.mapping_report ? (
            <LayoutReview report={validation.mapping_report} />
          ) : (
            <p className="hint">
              Esta importación se validó con el contrato anterior, que no guardaba un informe de
              columnas.
            </p>
          )}

          {warningCount > 0 && !validation.is_active && validation.status !== 'already_current' && (
            <label className="ack no-print">
              <input
                type="checkbox"
                checked={warningsAcknowledged}
                onChange={(event) => setWarningsAcknowledged(event.target.checked)}
                data-testid="warnings-ack"
              />
              <span>
                Revisé {warningCount === 1 ? 'la advertencia' : `las ${warningCount} advertencias`}{' '}
                y quiero poder publicar esta versión tal como viene. Los datos no se corrigen
                automáticamente.
              </span>
            </label>
          )}

          <div className="btns no-print">
            <button
              type="button"
              className="btn"
              disabled={!canPublishNow || busy !== null}
              onClick={() => setConfirming(true)}
              data-testid="publish-open"
            >
              Publicar esta versión
            </button>
            <button type="button" className="btn alt" onClick={reset} disabled={busy !== null}>
              Cargar otra planilla
            </button>
          </div>
        </section>
      )}

      {activation && (
        <section className="stack-tight" data-testid="publish-result">
          <AlertBanner tone="ok" title="Versión publicada">
            La importación #{activation.import_id} es ahora la versión activa del panel (
            {formatDateTime(activation.occurred_at)}).
            {activation.previous_import_id !== null
              ? ` Reemplaza a la versión #${activation.previous_import_id}, que sigue disponible para restaurar.`
              : ' Es la primera versión publicada.'}
          </AlertBanner>
          <div className="btns">
            <Link to={ROUTES.resumen} className="btn">
              Ver el resumen
            </Link>
            <Link to={ROUTES.versiones} className="btn alt">
              Ver el historial de versiones
            </Link>
            <button type="button" className="btn alt" onClick={reset}>
              Cargar otra planilla
            </button>
          </div>
        </section>
      )}

      {confirming && validation && (
        <ConfirmDialog
          title="Publicar la versión importada"
          confirmLabel={`Publicar la importación #${validation.import_id}`}
          busy={busy === 'publish'}
          onConfirm={() => void confirmPublish()}
          onCancel={() => setConfirming(false)}
        >
          <p>
            Está a punto de hacer que la importación #{validation.import_id} sea la versión activa
            del panel para todas las personas autorizadas. Se registrará quién publicó y cuándo.
          </p>
          <p>
            Contenido: {formatInteger(validation.business_rows)} filas ·{' '}
            {formatInteger(validation.distinct_pmf)} PMF ·{' '}
            {formatNumber(validation.surface_total)} ha.
          </p>
          {warningCount > 0 && (
            <p>
              Se publica con {formatInteger(warningCount)}{' '}
              {warningCount === 1 ? 'advertencia revisada' : 'advertencias revisadas'}; quedan
              registradas con la versión.
            </p>
          )}
        </ConfirmDialog>
      )}
    </div>
  )
}
