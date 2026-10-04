/**
 * One PMF's CONAF term in the «Estado» table: a status pill and the date
 * line. A dash when the read has no entry for the PMF; «Calculando…» while
 * the read is on its way.
 */
import type { PlazoPmf } from '../api'
import { PLAZO_ESTADO_LABELS, PLAZO_ESTADO_PILL, plazoText } from '../lib/plazo'

export function PlazoCell({ plazo, loading = false }: { plazo: PlazoPmf | undefined; loading?: boolean }) {
  if (!plazo) return <span className="hint">{loading ? 'Calculando…' : '—'}</span>
  return (
    <span className="plazo-cell" data-testid={`plazo-${plazo.source_row_number}`}>
      <span className={`pill ${PLAZO_ESTADO_PILL[plazo.estado]}`}>
        {PLAZO_ESTADO_LABELS[plazo.estado]}
      </span>
      <span className="hint">{plazoText(plazo)}</span>
    </span>
  )
}
