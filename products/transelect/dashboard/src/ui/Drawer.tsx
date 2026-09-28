/**
 * A side panel that holds one record's detail.
 *
 * The Explorador's rows open here rather than navigating away, because the
 * job is "look at this one, then carry on down the list" — losing the table,
 * its page and its scroll position to look at a single PMF is the wrong
 * trade. On a phone the same component becomes a bottom sheet (see the
 * breakpoint in components.css); the behaviour is identical.
 *
 * Focus is moved into the panel on open and returned to whatever opened it on
 * close, Escape closes, and a click on the backdrop closes. Tab is contained
 * inside the panel while it is open, so a keyboard reader cannot end up
 * driving the table behind a modal surface they cannot see.
 *
 * The panel is portalled to `<body>`. Rendered inside a section, it sat in
 * that section's stacking context (its entrance animation uses a transform),
 * so the sticky top bar was painted over the backdrop and stayed live beside
 * a modal. The page behind is also kept from scrolling while the panel is
 * open, so a scroll that reaches the end of the panel does not move the list.
 */
import { useCallback, useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'

export function Drawer({
  title,
  eyebrow,
  subtitle,
  headerExtra,
  onClose,
  children,
  testId,
}: {
  title: string
  /** A short label above the title naming what kind of record this is. */
  eyebrow?: ReactNode
  subtitle?: ReactNode
  /** Content that stays in the fixed header, such as a status and provenance. */
  headerExtra?: ReactNode
  onClose: () => void
  children: ReactNode
  testId?: string
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const returnFocusTo = useRef<HTMLElement | null>(null)

  const close = useCallback(() => {
    onClose()
  }, [onClose])

  useEffect(() => {
    returnFocusTo.current = document.activeElement as HTMLElement | null
    const panel = panelRef.current
    panel?.querySelector<HTMLElement>(FOCUSABLE)?.focus()

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        close()
        return
      }
      if (event.key !== 'Tab' || !panel) return

      const focusable = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      // Returning focus is what makes "open a row, read it, close it, keep
      // going" work without the keyboard reader losing their place.
      returnFocusTo.current?.focus?.()
    }
  }, [close])

  return createPortal(
    <>
      <div className="drawer-backdrop no-print" role="presentation" onClick={close} />
      <aside
        className="drawer no-print"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        data-testid={testId}
        ref={panelRef}
      >
        <div className="drawer-head">
          <div className="drawer-head-row">
            <div className="drawer-title">
              {eyebrow && <p className="eyebrow">{eyebrow}</p>}
              <h2>{title}</h2>
              {subtitle && <p className="hint">{subtitle}</p>}
            </div>
            <button
              type="button"
              className="drawer-close"
              aria-label="Cerrar el detalle"
              title="Cerrar (Esc)"
              onClick={close}
              data-testid={testId && `${testId}-close`}
            >
              <span aria-hidden="true">×</span>
              <span className="drawer-close-text" aria-hidden="true">
                Cerrar
              </span>
            </button>
          </div>
          {headerExtra}
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>,
    document.body,
  )
}
