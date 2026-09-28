/**
 * TR-FUNC-039's pagination controls.
 *
 * The API paginates by opaque cursor, so "previous" is served by a cursor
 * stack the caller keeps rather than by a page number. The range readout is
 * derived from the true filtered `total_count`, which makes a silent
 * truncation impossible to hide: if the page ever showed fewer rows than the
 * range claims, the readout would disagree.
 */
import { formatInteger } from '../format'

export const PAGE_SIZES = [25, 50, 100, 200]

export function Pagination({
  pageIndex,
  pageSize,
  pageRows,
  totalCount,
  hasMore,
  loading,
  onPrev,
  onNext,
  onPageSizeChange,
}: {
  pageIndex: number
  pageSize: number
  pageRows: number
  totalCount: number
  hasMore: boolean
  loading: boolean
  onPrev: () => void
  onNext: () => void
  onPageSizeChange: (size: number) => void
}) {
  const firstRow = totalCount === 0 ? 0 : pageIndex * pageSize + 1
  const lastRow = pageIndex * pageSize + pageRows

  return (
    <div className="pagination no-print">
      <span data-testid="pagination-range">
        Mostrando {formatInteger(firstRow)}–{formatInteger(lastRow)} de{' '}
        {formatInteger(totalCount)} filas
      </span>
      <div className="pagination-controls">
        <label>
          Filas por página{' '}
          <select
            value={pageSize}
            aria-label="Filas por página"
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {PAGE_SIZES.map((size) => (
              <option value={size} key={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn alt"
          onClick={onPrev}
          disabled={pageIndex === 0 || loading}
          data-testid="page-prev"
        >
          Anterior
        </button>
        <button
          type="button"
          className="btn alt"
          onClick={onNext}
          disabled={!hasMore || loading}
          data-testid="page-next"
        >
          Siguiente
        </button>
      </div>
    </div>
  )
}
