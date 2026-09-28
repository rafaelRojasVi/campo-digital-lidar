import type { SourceFieldChange } from '../types.ts'

export interface PairCount {
  before: string
  after: string
  count: number
}

/** Group literal before→after value pairs with occurrence counts. */
export function groupChangePairs(changes: SourceFieldChange[]): PairCount[] {
  const counts = new Map<string, PairCount>()

  for (const change of changes) {
    const before = change.before ?? '(vacío)'
    const after = change.after ?? '(vacío)'
    const key = `${before}→${after}`
    const entry = counts.get(key)

    if (entry === undefined) {
      counts.set(key, { before, after, count: 1 })
    } else {
      entry.count += 1
    }
  }

  return [...counts.values()].sort(
    (a, b) => b.count - a.count || a.before.localeCompare(b.before, 'es'),
  )
}
