/**
 * `/transelec/explorador` — detailed exploration, as its own working surface.
 *
 * In the shipped interface this table was the ninth block on the dashboard,
 * roughly 2 800 px down, underneath an executive report, with its export and
 * print controls in a left rail 2 500 px above it. It read as an appendix.
 * It is the tool most of the day's work actually happens in, so it gets the
 * page: search first and full width, filters behind a disclosure with their
 * active state always visible as chips, the result count stated once, and the
 * export and print actions in the table's own toolbar, beside the dataset
 * they act on.
 *
 * The API contract is untouched. The 13 columns, the cursor pagination, the
 * page-size control, the true `total_count` readout and the server-side CSV
 * export are exactly what they were.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  EMPTY_FILTERS,
  type ResumenRow,
  type TranselecRowsPage,
  type TranselecSummary,
  exportCsvUrl,
  getSummary,
  listRows,
} from '../api'
import { EMPTY_FILTER_OPTIONS, FilterPanel, type FilterOptions } from '../components/FilterPanel'
import { NoticeBanner } from '../components/NoticeBanner'
import { Pagination } from '../components/Pagination'
import {
  EASEMENT_VALUE,
  QuickActions,
  type QuickActionType,
} from '../components/QuickActions'
import { RowDetailDrawer } from '../components/RowDetailDrawer'
import { RowsTable } from '../components/RowsTable'
import { AlertBanner, LoadingBlock, StateBlock } from '../components/StateViews'
import { formatInteger } from '../format'
import { activeFilterChips, activeFilterCount, withoutChip } from '../lib/filterUrl'
import { collectAllRows, deriveFilterOptions } from '../lib/rowCollection'
import { useReads, type FilterController } from '../lib/useFilters'
import { Chip, Disclosure, SectionHeader, useDisclosure } from '../ui/Primitives'

const DEFAULT_PAGE_SIZE = 25

interface ExplorerData {
  summary: TranselecSummary
  page: TranselecRowsPage
}

export function ExploradorPage({
  filterController,
  activeImportId,
  sourceFields = null,
}: {
  filterController: FilterController
  /** Filter option lists are rebuilt when the published version changes. */
  activeImportId: number | null
  /** Contract fields the published workbook had; null while unknown. */
  sourceFields?: readonly string[] | null
}) {
  const { filters, draftQuery, setQuery, setField, replaceFilters, reset } = filterController
  const key = JSON.stringify(filters)

  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [pageIndex, setPageIndex] = useState(0)
  const [rows, setRows] = useState<ResumenRow[] | null>(null)
  const [rowsMeta, setRowsMeta] = useState({ total: 0, hasMore: false })
  const [rowsLoading, setRowsLoading] = useState(false)
  const [pageFailure, setPageFailure] = useState<string | null>(null)
  const cursorStack = useRef<(string | null)[]>([null])

  const [options, setOptions] = useState<FilterOptions>(EMPTY_FILTER_OPTIONS)
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [optionsTruncated, setOptionsTruncated] = useState(false)

  const [openRow, setOpenRow] = useState<ResumenRow | null>(null)
  const filterDisclosure = useDisclosure(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const empresaRef = useRef<HTMLButtonElement>(null)
  const [empresaOpenSignal, setEmpresaOpenSignal] = useState(0)

  // The summary and the first page of rows are fetched together and committed
  // as one, so the result count and the table can never describe different
  // filter states.
  const { data, loading, failure } = useReads<ExplorerData>(
    useCallback(async () => {
      const [summary, page] = await Promise.all([
        getSummary(filters),
        listRows(filters, { cursor: null, limit: pageSize }),
      ])
      if (!summary.ok) return summary
      if (!page.ok) return page
      return { ok: true, data: { summary: summary.data, page: page.data } }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [key, pageSize]),
    [key, pageSize],
  )

  // Adopt whatever the shared fetch just committed as page zero.
  useEffect(() => {
    if (!data) return
    cursorStack.current = [null, data.page.next_cursor]
    setPageIndex(0)
    setRows(data.page.items)
    setRowsMeta({ total: data.page.total_count, hasMore: data.page.has_more })
    setPageFailure(null)
  }, [data])

  // Filter option lists come from the active version's full row set: the read
  // API exposes no distinct-values endpoint and this work does not change the
  // API. Loaded once per active version, never per filter change.
  useEffect(() => {
    let cancelled = false
    setOptionsLoading(true)

    void collectAllRows(EMPTY_FILTERS).then((result) => {
      if (cancelled) return
      if (result.ok) {
        setOptions(deriveFilterOptions(result.rows))
        setOptionsTruncated(result.truncated)
      }
      setOptionsLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [activeImportId])

  const goToPage = useCallback(
    async (targetIndex: number) => {
      const cursor = cursorStack.current[targetIndex] ?? null
      setRowsLoading(true)
      const result = await listRows(filters, { cursor, limit: pageSize })
      setRowsLoading(false)
      if (!result.ok) {
        setPageFailure(result.error)
        return
      }
      cursorStack.current[targetIndex + 1] = result.data.next_cursor
      setPageIndex(targetIndex)
      setRows(result.data.items)
      setRowsMeta({ total: result.data.total_count, hasMore: result.data.has_more })
      setPageFailure(null)
    },
    [filters, pageSize],
  )

  const downloadCsv = useCallback(() => {
    const anchor = document.createElement('a')
    anchor.href = exportCsvUrl(filters)
    anchor.rel = 'noopener'
    anchor.click()
  }, [filters])

  /**
   * The four filter presets (TR-FUNC-026/028/029/030).
   *
   * Each starts from a clean filter state, exactly as the source's `quick()`
   * did by calling `resetFilters()` before every branch. `company` is the one
   * that genuinely only opens a control, which is what its own copy says.
   */
  const handleQuick = useCallback(
    (type: QuickActionType) => {
      switch (type) {
        case 'easement': {
          const match =
            options.tipo_propietario.find(
              (option) => option.toLocaleLowerCase('es-CL') === EASEMENT_VALUE.toLowerCase(),
            ) ?? EASEMENT_VALUE
          replaceFilters({ ...EMPTY_FILTERS, tipo_propietario: [match] })
          return
        }
        case 'rejected':
          replaceFilters({ ...EMPTY_FILTERS, q: 'rechaz' })
          return
        case 'legal':
          replaceFilters({ ...EMPTY_FILTERS, q: 'legal' })
          return
        case 'company':
          replaceFilters(EMPTY_FILTERS)
          if (!filterDisclosure.open) filterDisclosure.toggle()
          setEmpresaOpenSignal((value) => value + 1)
          window.requestAnimationFrame(() => empresaRef.current?.focus())
      }
    },
    [filterDisclosure, options.tipo_propietario, replaceFilters],
  )

  const chips = activeFilterChips(filters)
  const filterCount = activeFilterCount(filters)

  if (failure && !data) {
    return (
      <div className="page">
        <StateBlock view={failure} />
      </div>
    )
  }

  return (
    <div className="page enter">
      <SectionHeader
        title="Explorador"
        meta="Búsqueda y detalle fila a fila sobre la versión publicada."
      />

      <div className="explorer-head">
        <div className="search-bar no-print">
          <div className="search-field">
            <span className="search-glyph" aria-hidden="true" />
            <input
              id="filter-search"
              type="search"
              ref={searchRef}
              aria-label="Búsqueda general"
              placeholder="PMF, rol, N.º de ingreso, predio, empresa…"
              autoComplete="off"
              spellCheck={false}
              value={draftQuery}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <button
            type="button"
            className="filter-toggle"
            onClick={filterDisclosure.toggle}
            {...filterDisclosure.triggerProps}
          >
            Filtros
            {filterCount > 0 && <span className="filter-count">{filterCount}</span>}
          </button>
          <button type="button" className="btn alt" onClick={reset} disabled={filterCount === 0}>
            Limpiar
          </button>
        </div>

        <NoticeBanner />

        <Disclosure open={filterDisclosure.open} id={filterDisclosure.id}>
          <FilterPanel
            filters={filters}
            options={options}
            optionsLoading={optionsLoading}
            empresaRef={empresaRef}
            empresaOpenSignal={empresaOpenSignal}
            onChange={setField}
          />
          {/*
            The presets live inside the filter panel because that is what they
            are: four filter states somebody asks for often enough to deserve
            a button. Above the table they were a third block of chrome
            between the reader and the data.
          */}
          <QuickActions onQuick={handleQuick} />
        </Disclosure>

        {chips.length > 0 && (
          <div className="active-filters no-print" data-testid="active-filters">
            <span className="eyebrow">Filtros activos</span>
            {chips.map((chip) => (
              <Chip
                key={chip.key}
                onRemove={() => replaceFilters(withoutChip(filters, chip))}
                removeLabel={`Quitar el filtro ${chip.label}: ${chip.value}`}
              >
                {chip.label}: {chip.value}
              </Chip>
            ))}
          </div>
        )}
      </div>

      {optionsTruncated && (
        <AlertBanner tone="warn" title="Opciones de filtro incompletas">
          La versión activa tiene más filas de las que esta página recorre para construir las listas
          de filtros. Los filtros siguen aplicándose en el servidor sobre el total.
        </AlertBanner>
      )}
      {pageFailure && (
        <AlertBanner title="No se pudo cargar esta página">{pageFailure}</AlertBanner>
      )}

      <section className="ruled" aria-labelledby="rows-title">
        <div className="table-toolbar">
          <div className="result-count">
            <h2 id="rows-title" className="eyebrow">
              Detalle filtrado
            </h2>
            <span data-testid="rows-total">
              <b>{formatInteger(rowsMeta.total)}</b> áreas de corta
            </span>
          </div>
          <div className="btns no-print">
            <button type="button" className="btn alt" onClick={downloadCsv} disabled={!data}>
              Exportar CSV
            </button>
            <button type="button" className="btn alt" onClick={() => window.print()}>
              Imprimir / PDF
            </button>
          </div>
        </div>

        {!rows && loading ? (
          <LoadingBlock label="Cargando el alcance seleccionado…" shape="rows" lines={6} />
        ) : (
          <>
            <RowsTable
              rows={rows ?? []}
              loading={rowsLoading || loading}
              onOpenRow={setOpenRow}
              selectedRow={openRow?.source_row_number ?? null}
            />
            <Pagination
              pageIndex={pageIndex}
              pageSize={pageSize}
              pageRows={(rows ?? []).length}
              totalCount={rowsMeta.total}
              hasMore={rowsMeta.hasMore}
              loading={rowsLoading || loading}
              onPrev={() => void goToPage(Math.max(0, pageIndex - 1))}
              onNext={() => void goToPage(pageIndex + 1)}
              onPageSizeChange={setPageSize}
            />
          </>
        )}
      </section>

      {openRow && (
        <RowDetailDrawer
          row={openRow}
          onClose={() => setOpenRow(null)}
          sourceFields={sourceFields}
        />
      )}
    </div>
  )
}
