/**
 * Display formatting.
 *
 * `formatNumber` reproduces the source dashboards' own `fmt()` helper
 * (`Intl.NumberFormat('es-CL', { maximumFractionDigits: 2 })`) so a surface
 * total or an approval percentage reads the same way Javier reads it today.
 * Nothing here computes a business value — every number is already decided
 * by the API.
 */

const numberFormat = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 2 })
const integerFormat = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 0 })

export function formatNumber(value: number | null | undefined): string {
  return numberFormat.format(value ?? 0)
}

export function formatInteger(value: number | null | undefined): string {
  return integerFormat.format(value ?? 0)
}

export function formatPercent(value: number | null | undefined): string {
  return `${numberFormat.format(value ?? 0)}%`
}

/** A blank-safe cell value: never renders "null" or "undefined". */
export function cell(value: string | null | undefined, fallback = ''): string {
  const text = (value ?? '').trim()
  return text === '' ? fallback : text
}

/** ISO date (YYYY-MM-DD) or datetime rendered as DD-MM-YYYY, else verbatim. */
export function formatDate(value: string | null | undefined): string {
  const text = (value ?? '').trim()
  if (text === '') return ''
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(text)
  if (!match) return text
  return `${match[3]}-${match[2]}-${match[1]}`
}

/** An ISO timestamp rendered in local civil time, or '' when unparseable. */
export function formatDateTime(value: string | null | undefined): string {
  const text = (value ?? '').trim()
  if (text === '') return ''
  const parsed = new Date(text)
  if (Number.isNaN(parsed.getTime())) return text
  return parsed.toLocaleString('es-CL', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** First 12 hex characters of a content hash — enough to cite, short enough to read. */
export function shortHash(sha256: string | null | undefined): string {
  const text = (sha256 ?? '').trim()
  return text === '' ? '' : text.slice(0, 12)
}

export function formatBytes(bytes: number | null | undefined): string {
  const value = bytes ?? 0
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${numberFormat.format(value / 1024)} KiB`
  return `${numberFormat.format(value / (1024 * 1024))} MiB`
}
