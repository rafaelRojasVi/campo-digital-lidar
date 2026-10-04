/**
 * The «Plazo CONAF» column, added to the «Estado» table through
 * `EstadoTable`'s `extraColumns`, right after «PMF», and joined to each lifecycle row by PMF.
 * Kept in `lib/` so component modules export only components.
 */
import type { PlazoPmf } from '../api'
import { PlazoCell } from '../components/PlazoCell'
import type { EstadoColumn } from './estadoColumns'

export function plazoColumn(byPmf: ReadonlyMap<string, PlazoPmf>, loading: boolean): EstadoColumn {
  return {
    key: 'plazo',
    header: 'Plazo CONAF',
    after: 'pmf',
    render: (row) => <PlazoCell plazo={byPmf.get(row.pmf)} loading={loading} />,
  }
}
