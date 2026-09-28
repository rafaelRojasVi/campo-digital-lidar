import type { GeoFeature } from '../types.ts'

export type SortKey = 'ordinal' | 'predio' | 'rodal' | 'uso2026' | 'codigo2026' | 'supHa'

export interface SortState {
  key: SortKey
  ascending: boolean
}

function compareRodal(a: string | null, b: string | null): number {
  const aNumber = a === null || a === '' ? Number.NaN : Number(a)
  const bNumber = b === null || b === '' ? Number.NaN : Number(b)

  if (!Number.isNaN(aNumber) && !Number.isNaN(bNumber)) {
    return aNumber - bNumber
  }
  if (!Number.isNaN(aNumber)) return -1
  if (!Number.isNaN(bNumber)) return 1
  return (a ?? '').localeCompare(b ?? '', 'es')
}

/** Stable sort of the filtered features by one factual column. */
export function sortFeatures(features: GeoFeature[], sort: SortState): GeoFeature[] {
  const sorted = [...features]
  const direction = sort.ascending ? 1 : -1

  sorted.sort((a, b) => {
    const pa = a.properties
    const pb = b.properties

    let result: number
    switch (sort.key) {
      case 'ordinal':
        result = pa.feature_ordinal - pb.feature_ordinal
        break
      case 'predio':
        result = (pa.nom_predio ?? '').localeCompare(pb.nom_predio ?? '', 'es')
        break
      case 'rodal':
        result = compareRodal(pa.n_rodal, pb.n_rodal)
        break
      case 'uso2026':
        result = (pa.uso_2026 ?? '').localeCompare(pb.uso_2026 ?? '', 'es')
        break
      case 'codigo2026':
        result = (pa.cod_uso_2026 ?? '').localeCompare(pb.cod_uso_2026 ?? '', 'es')
        break
      case 'supHa':
        result = (pa.sup_ha ?? 0) - (pb.sup_ha ?? 0)
        break
    }

    if (result === 0) {
      result = pa.feature_ordinal - pb.feature_ordinal
    }

    return result * direction
  })

  return sorted
}
