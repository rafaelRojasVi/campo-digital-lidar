/**
 * The drawer's «Campos editables» block (web edits, spec §6).
 *
 * Operators and administrators change one cell at a time. Every save sends
 * the value the editor saw, so a concurrent change or a newly published
 * version is refused (409) instead of overwritten. Viewers see which values
 * came from the web and who changed them, and nothing else. A field the
 * published planilla has no column for is not offered: it could never be
 * written back into the download.
 *
 * Keyboard: Escape cancels the open editor (or the confirmation) and stops
 * there, so it does not also close the drawer; focus goes back to the button
 * that opened it. Who edited a value is visible text, not a tooltip.
 */
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import {
  type EditableFieldName,
  type OverrideConflictCode,
  type ResumenRow,
  type TranselecOverride,
  discardOverride,
  overrideConflictCode,
  saveOverride,
} from '../api'
import {
  EDITABLE_FIELDS,
  type EditableFieldSpec,
  displayValue,
  isWebField,
  overrideFor,
  webTooltip,
} from '../lib/webEdits'
import { ConfirmDialog } from './ConfirmDialog'
import { SourceDate } from './SourceDate'
import { AlertBanner } from './StateViews'
import { WebChip } from './WebChip'

const RELOAD_COPY = {
  version_changed:
    'Se publicó otra versión de la planilla mientras editaba. Recargue para ver la versión activa.',
  value_changed:
    'Otra persona cambió este valor mientras lo editaba. Recargue para ver el valor actual.',
} as const

const FOCUSABLE = 'button:not([disabled])'

export function EditableFieldsSection({
  row,
  activeImportId,
  canEdit,
  sourceFields,
  overrides,
  overridesStatus = 'ready',
  suggestions,
  onSaved,
  onReload,
  onRowEdited,
}: {
  row: ResumenRow
  activeImportId: number | null
  canEdit: boolean
  /** The published version's source fields; null while unknown. */
  sourceFields: readonly string[] | null
  overrides: readonly TranselecOverride[]
  /** State of the «who edited» fetch; the values themselves never wait for it. */
  overridesStatus?: 'loading' | 'ready' | 'error'
  suggestions: Partial<Record<EditableFieldName, string[]>>
  onSaved: (row: ResumenRow) => void
  onReload: () => void
  /** Called after a revert or reload so surfaces showing this row can refresh it. */
  onRowEdited?: () => void
}) {
  const [editing, setEditing] = useState<EditableFieldName | null>(null)
  const [draft, setDraft] = useState('')
  // The value the editor saw when it opened; what a save is checked against.
  const [seenValue, setSeenValue] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{
    field: EditableFieldName
    code: OverrideConflictCode | null
    message: string
    reload: boolean
  } | null>(null)
  const [status, setStatus] = useState('')
  const [reverting, setReverting] = useState<{
    override: TranselecOverride
    spec: EditableFieldSpec
  } | null>(null)
  // The control that should take focus once the editor or dialog is gone.
  const focusTarget = useRef<string | null>(null)
  const setFocusTarget = (id: string) => {
    focusTarget.current = id
  }

  useEffect(() => {
    if (!focusTarget.current || editing !== null || reverting !== null) return
    document.querySelector<HTMLElement>(`[data-focus-id="${focusTarget.current}"]`)?.focus()
    focusTarget.current = null
  })

  const editable = (spec: EditableFieldSpec) =>
    canEdit && activeImportId !== null && (sourceFields === null || sourceFields.includes(spec.name))

  const start = (spec: EditableFieldSpec) => {
    setEditing(spec.name)
    setDraft(row[spec.name] ?? '')
    setSeenValue(row[spec.name] ?? null)
    setError(null)
    setStatus('')
  }

  const cancel = (spec: EditableFieldSpec) => {
    setEditing(null)
    setError(null)
    setFocusTarget(`edit-${spec.name}`)
  }

  const submit = async (spec: EditableFieldSpec) => {
    if (activeImportId === null) return
    setBusy(true)
    setError(null)
    setStatus(`Guardando ${spec.label}…`)
    const result = await saveOverride({
      importId: activeImportId,
      sourceRowNumber: row.source_row_number,
      field: spec.name,
      value: draft.trim() === '' ? null : draft,
      expectedValue: seenValue,
    })
    setBusy(false)
    if (!result.ok) {
      setStatus('')
      const code = overrideConflictCode(result.payload)
      if (code === 'version_changed' || code === 'value_changed') {
        setError({ field: spec.name, code, message: RELOAD_COPY[code], reload: true })
      } else {
        setError({ field: spec.name, code: null, message: result.error, reload: false })
      }
      return
    }
    setEditing(null)
    setFocusTarget(`edit-${spec.name}`)
    setStatus(
      !result.data.changed
        ? `${spec.label} ya tenía ese valor; no hubo cambios.`
        : draft.trim() === ''
          ? `${spec.label} se dejó vacío.`
          : `Se guardó el cambio en ${spec.label}.`,
    )
    onSaved(result.data.row)
  }

  const revert = async (override: TranselecOverride, spec: EditableFieldSpec) => {
    setBusy(true)
    setError(null)
    const result = await discardOverride(override.id)
    setBusy(false)
    setReverting(null)
    setFocusTarget(`edit-${spec.name}`)
    if (!result.ok) {
      setError({ field: spec.name, code: null, message: result.error, reload: false })
      return
    }
    setStatus(`${spec.label} volvió al valor de la planilla.`)
    onReload()
    onRowEdited?.()
  }

  /** «Recargar»: close the stale editor and refetch, so the next edit starts from the fresh value. */
  const reloadAfterConflict = (spec: EditableFieldSpec) => {
    if (error?.code === 'version_changed') {
      // The active version changed: every save would be refused until the page knows the new one.
      window.location.reload()
      return
    }
    setError(null)
    setEditing(null)
    setSeenValue(null)
    setDraft('')
    setFocusTarget(`edit-${spec.name}`)
    setStatus(`Se recargó ${spec.label}. Revise el valor actual y vuelva a editar si corresponde.`)
    onReload()
    onRowEdited?.()
  }

  /** Escape closes only what is open here; Tab stays between the editor's own controls. */
  const onEditorKeyDown = (event: KeyboardEvent<HTMLElement>, spec: EditableFieldSpec) => {
    if (event.key !== 'Escape') return
    event.stopPropagation()
    event.preventDefault()
    cancel(spec)
  }

  const onDialogKeyDown = (event: KeyboardEvent<HTMLElement>, spec: EditableFieldSpec) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      event.preventDefault()
      setReverting(null)
      setFocusTarget(`revert-${spec.name}`)
    } else if (event.key === 'Tab') {
      // The drawer's own Tab containment does not know about this dialog.
      const buttons = [...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (buttons.length === 0) return
      event.stopPropagation()
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
  }

  return (
    <section
      className="drawer-section"
      aria-labelledby="drawer-editables"
      data-testid="drawer-editables"
    >
      <h3 id="drawer-editables">Campos editables</h3>
      <p className="hint">
        Los valores marcados «web» se cambiaron en el panel; la planilla publicada no se modifica.
        {!canEdit && ' Sólo operadores y administradores pueden editarlos.'}
      </p>
      <p className="hint" role="status" aria-live="polite" data-testid="editables-status">
        {status}
      </p>
      <dl className="facts">
        {EDITABLE_FIELDS.map((spec) => {
          const web = isWebField(row, spec.name)
          const override = web ? overrideFor(overrides, row, spec.name) : undefined
          const shown = displayValue(spec, row[spec.name])
          const isEditing = editing === spec.name
          return (
            <div
              className={`fact editable-fact${isEditing || web ? ' wide' : ''}`}
              key={spec.name}
              data-testid={`editable-${spec.name}`}
            >
              <dt>{spec.label}</dt>
              <dd>
                {isEditing ? (
                  <>
                  {spec.kind === 'date' && row[spec.name] == null && row.source_text_dates?.[spec.name] && (
                    <span
                      className="editable-provenance"
                      id={`text-date-${spec.name}-note`}
                      data-testid={`text-date-${spec.name}`}
                    >
                      La planilla tiene texto: «{row.source_text_dates[spec.name].raw}». Al guardar una
                      fecha se reemplaza.
                    </span>
                  )}
                  <form
                    className="field-editor"
                    onKeyDown={(event) => onEditorKeyDown(event, spec)}
                    onSubmit={(event) => {
                      event.preventDefault()
                      void submit(spec)
                    }}
                  >
                    <input
                      type={spec.kind === 'date' ? 'date' : 'text'}
                      value={draft}
                      onChange={(event) => setDraft(event.target.value)}
                      list={spec.suggest ? `suggest-${spec.name}` : undefined}
                      aria-label={`Nuevo valor de ${spec.label}`}
                      aria-describedby={
                        spec.kind === 'date' && row[spec.name] == null && row.source_text_dates?.[spec.name]
                          ? `text-date-${spec.name}-note`
                          : undefined
                      }
                      maxLength={500}
                      autoFocus
                    />
                    {spec.suggest && (
                      <datalist id={`suggest-${spec.name}`}>
                        {(suggestions[spec.name] ?? []).map((value) => (
                          <option key={value} value={value} />
                        ))}
                      </datalist>
                    )}
                    <button type="submit" className="btn small" disabled={busy}>
                      Guardar
                    </button>
                    <button
                      type="button"
                      className="btn alt small"
                      disabled={busy}
                      onClick={() => cancel(spec)}
                    >
                      Cancelar
                    </button>
                  </form>
                  </>
                ) : (
                  <>
                    <span className="editable-value">
                      <span>
                        {spec.kind === 'date' ? (
                          <SourceDate
                            row={row}
                            field={spec.name as 'fecha_ingreso'}
                            missing="Sin dato"
                          />
                        ) : (
                          shown || <span className="hint">Sin dato</span>
                        )}
                      </span>
                      {web && <WebChip />}
                    </span>
                    {web && (
                      <span className="editable-provenance" data-testid={`provenance-${spec.name}`}>
                        {override
                          ? webTooltip(override, spec)
                          : overridesStatus === 'loading'
                            ? 'Cargando quién editó este valor…'
                            : overridesStatus === 'error'
                              ? 'No se pudo cargar quién editó este valor.'
                              : webTooltip(undefined, spec)}
                      </span>
                    )}
                    {(editable(spec) || (canEdit && override)) && (
                      <span className="editable-actions">
                        {editable(spec) && (
                          <button
                            type="button"
                            className="btn-link"
                            aria-label={`Editar ${spec.label}`}
                            data-focus-id={`edit-${spec.name}`}
                            onClick={() => start(spec)}
                          >
                            Editar
                          </button>
                        )}
                        {canEdit && override && (
                          <button
                            type="button"
                            className="btn-link"
                            aria-label={`Volver al valor de la planilla de ${spec.label}`}
                            data-focus-id={`revert-${spec.name}`}
                            disabled={busy}
                            onClick={() => setReverting({ override, spec })}
                          >
                            Volver al valor de la planilla
                          </button>
                        )}
                      </span>
                    )}
                  </>
                )}
                {error?.field === spec.name && (
                  <AlertBanner title="No se guardó el cambio">
                    {' '}
                    {error.message}{' '}
                    {error.reload && (
                      <button
                        type="button"
                        className="btn-link"
                        onClick={() => reloadAfterConflict(spec)}
                      >
                        {error.code === 'version_changed' ? 'Recargar la página' : 'Recargar'}
                      </button>
                    )}
                  </AlertBanner>
                )}
              </dd>
            </div>
          )
        })}
      </dl>
      {reverting &&
        createPortal(
          <div onKeyDown={(event) => onDialogKeyDown(event, reverting.spec)}>
            <ConfirmDialog
              title="Volver al valor de la planilla"
              confirmLabel="Volver al valor de la planilla"
              busy={busy}
              onConfirm={() => void revert(reverting.override, reverting.spec)}
              onCancel={() => {
                setReverting(null)
                setFocusTarget(`revert-${reverting.spec.name}`)
              }}
            >
              <p>
                {reverting.spec.label} volverá a «
                {displayValue(reverting.spec, reverting.override.planilla_value_at_edit) ||
                  '(vacía)'}
                », el valor que tenía la planilla cuando se editó. Se pierde el valor puesto en la
                web.
              </p>
            </ConfirmDialog>
          </div>,
          document.body,
        )}
    </section>
  )
}
