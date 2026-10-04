/**
 * «Abrir Oficina Virtual CONAF» and «Copiar N.º», beside an N.º de ingreso.
 *
 * CONAF's consulta page is a form that POSTs `nsolicitud` to `action.php`
 * (read 2026-10-04): no address opens one expediente, and the production CSP
 * (`form-action 'self'`) forbids posting a form to another site anyway. So
 * this opens the page in a new tab and copies the number for the reader to
 * paste. Whether CONAF's «N.º de solicitud» is the planilla's `N Ingreso` is
 * still an open question, so the copy says «N.º».
 *
 * Used inside clickable table rows: a click here belongs to the link or the
 * button, never to the row behind it. Enter and Space are stopped for the same
 * reason; every other key (Escape, Tab) must still reach the drawer's
 * document-level handlers, so they are not.
 */
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

export const OFICINA_VIRTUAL_CONAF_URL = 'https://oficinavirtual.conaf.cl/consultas/index.php'

function keepActivationKeys(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') event.stopPropagation()
}

export function OficinaVirtualLink({
  numero,
  compact = false,
  testId = 'oficina-virtual',
}: {
  numero: string | null
  /** «Abrir» instead of the full label, for a table cell. */
  compact?: boolean
  testId?: string
}) {
  const [copied, setCopied] = useState<'ok' | 'err' | null>(null)
  const timeoutRef = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timeoutRef.current), [])

  const value = numero?.trim() ?? ''

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied('ok')
    } catch {
      setCopied('err')
    }
    window.clearTimeout(timeoutRef.current)
    timeoutRef.current = window.setTimeout(() => setCopied(null), 4000)
  }

  return (
    <span
      className="oficina-virtual no-print"
      data-testid={testId}
      onClick={(event) => event.stopPropagation()}
      onKeyDown={keepActivationKeys}
    >
      <a
        href={OFICINA_VIRTUAL_CONAF_URL}
        target="_blank"
        rel="noopener noreferrer"
        data-testid={`${testId}-link`}
      >
        {compact ? 'Abrir' : 'Abrir Oficina Virtual CONAF'}{' '}
        <span className="sr-only">
          {compact ? 'Oficina Virtual CONAF ' : ''}(se abre en una pestaña nueva)
        </span>
      </a>
      {value !== '' && (
        <button
          type="button"
          className="btn-link"
          onClick={() => void copy()}
          aria-label={`Copiar el N.º ${value}`}
          data-testid={`${testId}-copy`}
        >
          Copiar N.º
        </button>
      )}
      <span role="status" aria-live="polite" className="hint">
        {copied === 'ok' ? 'N.º copiado.' : copied === 'err' ? 'El navegador no permitió copiar.' : ''}
      </span>
    </span>
  )
}
