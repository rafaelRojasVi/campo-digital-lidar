/**
 * The header's «N ediciones web» pill and its log (indicator spec §4-§5).
 *
 * The log is a native popover: the platform gives it Esc, light dismiss and
 * the top layer, so nothing here handles an outside click or a z-index. The
 * `toggle` event keeps `aria-expanded` true to the popover, moves focus to
 * the heading on open and back to the pill on close. CSS anchor positioning
 * puts it under the pill (components.css), with a fixed place under the bar
 * where that is unsupported. The pill is not a live region: its numbers
 * change only after the reader's own edits or a tab refocus.
 *
 * On screen it is the pencil and the numbers only («✎ 5 · 2»), at every
 * width: measured on 2026-10-05, the words never fit beside the version
 * stamp, the name and the session control — the bar overflowed by up to
 * 148 px at 1280 px, and even at the bar's 1440 px maximum the name gave way
 * entirely. The full text is the pill's accessible name and its tooltip, and
 * the log's heading says it again in words.
 */
import { useEffect, useRef, useState } from 'react'
import { EDIT_LOG_ID, pillLabel, pillVisible } from '../lib/editLog'
import { useWebEdits } from '../lib/webEditsState'
import { EditLogBody } from './EditLog'

function PencilIcon() {
  return (
    <svg
      className="edits-pill-icon"
      width="12"
      height="12"
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M11.2 1.8a1.6 1.6 0 0 1 2.3 0l.7.7a1.6 1.6 0 0 1 0 2.3L5 14l-3.5.9.9-3.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function WebEditsPill({ canEdit }: { canEdit: boolean }) {
  const { history } = useWebEdits()
  const visible = pillVisible(history)
  const pillRef = useRef<HTMLButtonElement>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const log = logRef.current
    if (!log) return undefined
    const onToggle = (event: Event) => {
      const opened = (event as ToggleEvent).newState === 'open'
      setOpen(opened)
      if (opened) {
        headingRef.current?.focus()
        return
      }
      const focused = document.activeElement
      if (!focused || focused === document.body || log.contains(focused)) pillRef.current?.focus()
    }
    log.addEventListener('toggle', onToggle)
    return () => log.removeEventListener('toggle', onToggle)
  }, [visible])

  if (!visible) return null

  const label = pillLabel(history)

  const close = () => {
    const log = logRef.current
    if (log && typeof log.hidePopover === 'function' && log.matches(':popover-open')) {
      log.hidePopover()
    }
  }

  return (
    <>
      <button
        ref={pillRef}
        type="button"
        className="edits-pill"
        popoverTarget={EDIT_LOG_ID}
        aria-haspopup="dialog"
        aria-controls={EDIT_LOG_ID}
        aria-expanded={open}
        aria-label={label}
        title={label}
        data-testid="edits-pill"
      >
        <PencilIcon />
        <span>{history.in_force_count}</span>
        {history.needs_review_count > 0 && (
          <span className="edits-pill-review">· {history.needs_review_count}</span>
        )}
      </button>
      <div
        ref={logRef}
        id={EDIT_LOG_ID}
        popover="auto"
        role="dialog"
        aria-labelledby="edit-log-heading"
        className="edit-log no-print"
        data-testid="edit-log"
      >
        <EditLogBody
          history={history}
          canEdit={canEdit}
          headingRef={headingRef}
          onNavigate={close}
        />
      </div>
    </>
  )
}
