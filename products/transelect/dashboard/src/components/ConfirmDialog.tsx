import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

/**
 * A confirmation the user must answer before a mutation fires.
 *
 * Used for publish and for restore — the design doc requires restore in
 * particular to state, explicitly, which import is about to become active
 * again before the request is sent.
 */
export function ConfirmDialog({
  title,
  confirmLabel,
  busy,
  tone = 'primary',
  onConfirm,
  onCancel,
  children,
}: {
  title: string
  confirmLabel: string
  busy?: boolean
  tone?: 'primary' | 'danger'
  onConfirm: () => void
  onCancel: () => void
  children: ReactNode
}) {
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    confirmRef.current?.focus()
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onCancel])

  return (
    <div className="dialog-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="confirm-title">{title}</h2>
        <div>{children}</div>
        <div className="btns">
          <button type="button" className="btn alt" onClick={onCancel} disabled={busy}>
            Cancelar
          </button>
          <button
            type="button"
            ref={confirmRef}
            className={`btn${tone === 'danger' ? ' danger' : ''}`}
            onClick={onConfirm}
            disabled={busy}
            data-testid="confirm-accept"
          >
            {busy ? 'Procesando…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
