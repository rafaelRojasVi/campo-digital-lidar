/**
 * TR-FUNC-012 — "Predios de reforestación".
 *
 * `Predio Ref` is one of the fields v0 left completely unused and
 * Actualizable revived. The API returns the distinct, non-blank, sorted
 * values for the current filter state; this renders the first ten and
 * collapses the rest into the source's own overflow chip.
 */
import { formatInteger } from '../format'

const VISIBLE_CHIPS = 10

export function ReforestationChips({ predios }: { predios: string[] }) {
  const shown = predios.slice(0, VISIBLE_CHIPS)
  const hasOverflow = predios.length > VISIBLE_CHIPS

  return (
    <div data-testid="reforestation">
      <p className="hint" style={{ marginBottom: 'var(--s-4)' }}>
        <b data-testid="reforestation-count">{formatInteger(predios.length)}</b>{' '}
        {predios.length === 1 ? 'etiqueta distinta' : 'etiquetas distintas'} de «Predio Ref» en el
        alcance seleccionado.
      </p>
      <div className="refchips">
        {shown.map((name) => (
          <span className="refchip" key={name}>
            {name}
          </span>
        ))}
        {hasOverflow && (
          <span className="refchip refmany" data-testid="reforestation-overflow">
            Muchos · {formatInteger(predios.length)} en total
          </span>
        )}
        {predios.length === 0 && (
          <span className="hint">
            Sin predios de reforestación informados para el filtro actual.
          </span>
        )}
      </div>
    </div>
  )
}
