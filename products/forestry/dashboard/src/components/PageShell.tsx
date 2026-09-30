import type { ReactNode } from 'react'
import { Header } from './Header.tsx'
import type { Route } from '../router.ts'
import type { ForestryRole, VersionStatus } from '../types.ts'
import { STATUS_LABELS } from '../lib/versions.ts'

/** The header plus one scrollable, readable column: Versiones, Cargar, Revisión. */
export function PageShell({
  active,
  role,
  children,
}: {
  active: Route
  role: ForestryRole | null
  children: ReactNode
}) {
  return (
    <div className="page-app">
      <Header active={active} role={role} />
      <main className="page">{children}</main>
    </div>
  )
}

export function StatusChip({ status }: { status: VersionStatus }) {
  return <span className={`version-chip version-chip--${status}`}>{STATUS_LABELS[status]}</span>
}

export function Notice({
  tone,
  title,
  children,
}: {
  tone: 'info' | 'success' | 'warn' | 'error'
  title?: string
  children: ReactNode
}) {
  return (
    <div className={`notice notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {title !== undefined ? <p className="notice__title">{title}</p> : null}
      <div className="notice__body">{children}</div>
    </div>
  )
}
