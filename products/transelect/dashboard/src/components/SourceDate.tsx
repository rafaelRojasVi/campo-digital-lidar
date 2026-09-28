/**
 * A date field of one row, shown with the raw text its cell held when the
 * cell was text rather than an Excel date.
 *
 * Only one written-out Spanish date (`13 de noviembre de 2024`) is read as a
 * date by the importer; the original text is still shown beside it. Every
 * other text — several dates in one cell, `-`, a numeric day/month form — is
 * shown as written, marked as not read as a date. Nothing is guessed here.
 */
import type { ResumenRow, TextDateResolution } from '../api'
import { formatDate } from '../format'

const TEXT_DATE_LABELS: Record<TextDateResolution, string> = {
  parsed_spanish_long: 'Fecha escrita en texto',
  multiple_dates: 'Varias fechas en la celda',
  placeholder: 'Guion en lugar de fecha',
  unrecognized: 'Texto no leído como fecha',
}

export function SourceDate({
  row,
  field,
  missing,
}: {
  row: ResumenRow
  field: 'fecha_ingreso' | 'fecha_90_dias' | 'fecha_solicitud' | 'fecha_corta' | 'fecha_termino'
  missing: string
}) {
  const evidence = row.source_text_dates?.[field]
  const date = formatDate(row[field])
  if (!evidence) return <>{date || missing}</>
  if (evidence.parsed) {
    return (
      <span data-text-date="parsed">
        {date}
        <span className="source-row">
          {TEXT_DATE_LABELS[evidence.resolution]}: «{evidence.raw}»
        </span>
      </span>
    )
  }
  return (
    <span data-text-date={evidence.resolution}>
      <span className="raw-text">{evidence.raw}</span>{' '}
      <span className="flag">{TEXT_DATE_LABELS[evidence.resolution]}</span>
    </span>
  )
}
