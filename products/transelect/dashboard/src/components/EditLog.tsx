/**
 * The edits log's entries (indicator spec §5-§6), shared by the header
 * popover and the «Historial» in Ediciones web, and the popover's body.
 *
 * An entry still acting on a row (in force or in conflict) links to the
 * Explorador with that row's drawer open; the rest are plain text, greyed
 * when the edit no longer changes what the dashboard shows. Each value is
 * clamped to two lines on screen; the full text stays in the DOM for screen
 * readers and in `title` on hover.
 */
import type { Ref } from 'react'
import type { TranselecEditHistory, TranselecHistoryEntry } from '../api'
import {
  LOG_PREVIEW_COUNT,
  entryHref,
  formatEditWhen,
  isMuted,
  logValue,
  stateLabel,
} from '../lib/editLog'
import { specFor } from '../lib/webEdits'
import { DOWNLOAD_BUSY, DOWNLOAD_LABEL, useXlsxDownload } from '../lib/xlsxDownload'
import { Link, ROUTES } from '../router'

function EditLogItem({
  entry,
  onNavigate,
}: {
  entry: TranselecHistoryEntry
  onNavigate?: () => void
}) {
  const label = stateLabel(entry)
  const before = logValue(entry.field, entry.planilla_value_at_edit)
  const after = logValue(entry.field, entry.web_value)
  const href = entryHref(entry)
  const body = (
    <>
      <span className="edit-log-what">
        <b>{entry.pmf}</b> · {specFor(entry.field).label}
      </span>
      <span className="edit-log-change">
        <span className="sr-only">de </span>
        <span className="edit-log-value" title={before}>
          {before}
        </span>
        <span aria-hidden="true"> → </span>
        <span className="sr-only"> a </span>
        <span className="edit-log-value" title={after}>
          {after}
        </span>
      </span>
      <span className="edit-log-who">
        {entry.created_by_display_name} ·{' '}
        <time dateTime={entry.created_at}>{formatEditWhen(entry.created_at)}</time>
      </span>
      {label && (
        <span className="edit-log-state" data-state={entry.state}>
          {label}
        </span>
      )}
    </>
  )
  return (
    <li
      className="edit-log-entry"
      data-state={entry.state}
      data-muted={isMuted(entry.state) ? 'true' : undefined}
      data-testid={`edit-log-${entry.id}`}
    >
      {href ? (
        <Link to={href} className="edit-log-target" onNavigate={onNavigate}>
          {body}
        </Link>
      ) : (
        <div className="edit-log-target">{body}</div>
      )}
    </li>
  )
}

export function EditLogList({
  entries,
  onNavigate,
}: {
  entries: readonly TranselecHistoryEntry[]
  onNavigate?: () => void
}) {
  return (
    <ol className="edit-log-list">
      {entries.map((entry) => (
        <EditLogItem key={entry.id} entry={entry} onNavigate={onNavigate} />
      ))}
    </ol>
  )
}

function DownloadLink() {
  const { downloading, error, download } = useXlsxDownload()
  return (
    <>
      <button
        type="button"
        className="btn-link"
        aria-disabled={downloading}
        onClick={() => void download()}
      >
        {downloading ? DOWNLOAD_BUSY : DOWNLOAD_LABEL}
      </button>
      {error && (
        <p className="hint edit-log-error" role="alert">
          No se pudo descargar la planilla. {error}
        </p>
      )}
    </>
  )
}

export function EditLogBody({
  history,
  canEdit,
  headingRef,
  onNavigate,
}: {
  history: TranselecEditHistory
  canEdit: boolean
  headingRef: Ref<HTMLHeadingElement>
  onNavigate: () => void
}) {
  const shown = history.entries.slice(0, LOG_PREVIEW_COUNT)
  const more = history.entries.length - shown.length
  return (
    <>
      <div className="edit-log-head">
        <h2 id="edit-log-heading" ref={headingRef} tabIndex={-1}>
          Ediciones web
        </h2>
        <span className="edit-log-counts">
          {history.in_force_count} en vigor
          {history.needs_review_count > 0 && (
            <>
              {' · '}
              <span className="edit-log-review">{history.needs_review_count} por revisar</span>
            </>
          )}
        </span>
      </div>
      {shown.length === 0 ? (
        <p className="hint">Todavía no hay ediciones web.</p>
      ) : (
        <EditLogList entries={shown} onNavigate={onNavigate} />
      )}
      {more > 0 && <p className="hint edit-log-more">y {more} más</p>}
      {canEdit && (
        <div className="edit-log-foot">
          <Link to={ROUTES.ediciones} onNavigate={onNavigate}>
            Ver todas en Ediciones web →
          </Link>
          <DownloadLink />
        </div>
      )}
    </>
  )
}
