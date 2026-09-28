import type { ReactNode } from 'react'
import type { FailureView } from '../lib/apiState'

/**
 * Full-page state block: empty, unauthorized, unavailable, or an error.
 *
 * These are first-class screens, not fallbacks. The coloured rule above the
 * heading is the one signal that separates "nothing published yet, here is
 * what to do" from "something went wrong": a calm accent for the states that
 * are a normal part of the workflow, a warm one for the states that are not.
 * The distinction is carried by the heading and body copy as well, never by
 * the rule's colour alone.
 */
export function StateBlock({
  view,
  children,
}: {
  view: FailureView
  children?: ReactNode
}) {
  return (
    <section
      className="panel panel-pad state-block"
      data-state-kind={view.kind}
      aria-live="polite"
    >
      <span className="state-mark" aria-hidden="true" />
      <h2>{view.title}</h2>
      <p>{view.message}</p>
      {children}
    </section>
  )
}

/** Inline banner for a recoverable failure that leaves the page usable. */
export function AlertBanner({
  tone = 'error',
  title,
  children,
}: {
  tone?: 'error' | 'warn' | 'ok' | 'info'
  title: string
  children?: ReactNode
}) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <strong>{title}</strong>
      {children}
    </div>
  )
}

/**
 * A skeleton shaped like the thing it will become.
 *
 * `shape` lets a caller ask for the rhythm of the content that replaces it —
 * a composition bar is one tall block, a table is a stack of rows — so the
 * swap to real content does not move the page underneath the reader.
 */
export function LoadingBlock({
  label,
  lines = 3,
  shape = 'text',
}: {
  label: string
  lines?: number
  shape?: 'text' | 'bar' | 'rows'
}) {
  return (
    <div className="loading-block" role="status" aria-live="polite" aria-busy="true">
      <span className="loading-row">{label}</span>
      {Array.from({ length: shape === 'bar' ? 2 : lines }, (_, index) => (
        <span
          className={`skeleton${shape === 'text' ? '' : ' tall'}`}
          key={index}
          aria-hidden="true"
        />
      ))}
    </div>
  )
}
