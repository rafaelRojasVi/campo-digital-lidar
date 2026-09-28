/**
 * TR-FUNC-034 / 035 / 036 — executive report, copy to clipboard, download TXT.
 *
 * The report text is generated server-side from the same filtered view every
 * other section reads, using Javier's own `renderReport()` template. The one
 * deliberate change is the "Corte de información" line: the source hardcodes
 * `14-08-2026`, and the API substitutes the active import's own publish
 * date, so the report can never claim a frozen date again.
 *
 * The text is rendered inside a `<pre>` so its line breaks survive. It is a
 * plain string and is escaped by React like any other value — no
 * `dangerouslySetInnerHTML` anywhere in this application.
 */
import { useEffect, useRef, useState } from 'react'
import type { TranselecReport } from '../api'
import { formatDateTime } from '../format'
import { HowCalculated } from '../ui/HowCalculated'

const FILE_NAME = 'reporte_ejecutivo_conaf.txt'

type CopyState = { tone: 'ok' | 'err'; message: string } | null

export function ReportPanel({ report }: { report: TranselecReport }) {
  const [copyState, setCopyState] = useState<CopyState>(null)
  const timeoutRef = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timeoutRef.current), [])

  const announce = (state: CopyState) => {
    setCopyState(state)
    window.clearTimeout(timeoutRef.current)
    timeoutRef.current = window.setTimeout(() => setCopyState(null), 4000)
  }

  const copyReport = async () => {
    try {
      await navigator.clipboard.writeText(report.text)
      announce({ tone: 'ok', message: 'Reporte copiado al portapapeles.' })
    } catch {
      announce({
        tone: 'err',
        message: 'El navegador no permitió copiar. Seleccione el texto y cópielo manualmente.',
      })
    }
  }

  const downloadReport = () => {
    // Explicit, safe MIME type; the browser saves it as an attachment via the
    // download attribute rather than rendering it.
    const blob = new Blob([report.text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = FILE_NAME
    anchor.rel = 'noopener'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div data-testid="report-panel">
      <h2 id="report-title">Reporte ejecutivo breve</h2>
      <pre className="report" data-testid="report-text" style={{ marginTop: 'var(--s-4)' }}>
        {report.text}
      </pre>
      <p className="hint" style={{ marginTop: 'var(--s-4)' }}>
        Corte de información tomado de la versión activa ({formatDateTime(report.generated_at)}),
        no de la fecha de consulta.
      </p>
      <HowCalculated
        bases={[report.basis_estado_resumido, report.basis_pending_priority]}
        testId="report-how"
      />
      <div className="btns no-print" style={{ marginTop: 'var(--s-4)' }}>
        <button type="button" className="btn alt" onClick={copyReport} data-testid="copy-report">
          Copiar reporte
        </button>
        <button
          type="button"
          className="btn alt"
          onClick={downloadReport}
          data-testid="download-report"
        >
          Descargar TXT
        </button>
      </div>
      {copyState && (
        <p className={`copy-status${copyState.tone === 'err' ? ' err' : ''}`} role="status">
          {copyState.message}
        </p>
      )}
    </div>
  )
}
