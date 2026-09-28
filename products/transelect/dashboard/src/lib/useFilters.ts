/**
 * Filter state and the read that consumes it.
 *
 * Two guarantees live here, and both are structural rather than conventional:
 *
 *  1. **One filter state.** Every section derives its filters from the URL,
 *     so two sections cannot hold different ones. Editing a filter writes the
 *     URL; nothing keeps a private copy except the search box's own
 *     keystroke buffer, which is debounced into the URL and then read back.
 *
 *  2. **One commit per filter state.** `useReads` fetches a section's
 *     endpoints together and commits them to state in a single update, so no
 *     section can render one figure from the current filter state next to
 *     another from the previous one. This is TR-FUNC-017 as a data-flow
 *     property, not as a review checklist item.
 *
 * A stale response can never win: each run takes a monotonic id and a commit
 * is dropped unless its id is still the latest.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApiResult, TranselecFilterState } from '../api'
import { useRouter } from '../router'
import { filtersFromSearch, searchFromFilters } from './filterUrl'
import { classifyFailure, type ApiFailure, type FailureView } from './apiState'

const FILTER_DEBOUNCE_MS = 250

export interface FilterController {
  /** The committed filter state: what the URL says and what the API is asked. */
  filters: TranselecFilterState
  /** What the search box currently shows, which may lead `filters` by a beat. */
  draftQuery: string
  setQuery: (value: string) => void
  setField: (field: keyof TranselecFilterState, value: string[]) => void
  replaceFilters: (next: TranselecFilterState) => void
  reset: () => void
}

/**
 * Read the filter state from the URL and write changes back to it.
 *
 * `pathname` is passed in rather than read here so a caller can move the
 * reader to another section while keeping the filters — the Resumen's links
 * into the Explorador do exactly that.
 */
export function useFilters(): FilterController {
  const { pathname, search, navigate } = useRouter()
  const filters = filtersFromSearch(search)

  // The search box is the one control that cannot be driven straight from the
  // URL: a keystroke must show immediately, while the fetch it implies should
  // happen once for a burst of typing, not once per character.
  const [draftQuery, setDraftQuery] = useState(filters.q)
  const lastCommitted = useRef(filters.q)

  // Adopt the URL's value whenever it changes from anywhere other than this
  // box — a chip removal, a reset, the Back button, or a link that arrives
  // carrying filters.
  useEffect(() => {
    if (filters.q !== lastCommitted.current) {
      lastCommitted.current = filters.q
      setDraftQuery(filters.q)
    }
  }, [filters.q])

  const write = useCallback(
    (next: TranselecFilterState) => {
      navigate(`${pathname}${searchFromFilters(next)}`, { replace: true })
    },
    [navigate, pathname],
  )

  useEffect(() => {
    if (draftQuery === lastCommitted.current) return
    const handle = window.setTimeout(() => {
      lastCommitted.current = draftQuery
      write({ ...filtersFromSearch(window.location.search), q: draftQuery })
    }, FILTER_DEBOUNCE_MS)
    return () => window.clearTimeout(handle)
  }, [draftQuery, write])

  const setField = useCallback(
    (field: keyof TranselecFilterState, value: string[]) => {
      write({ ...filters, [field]: value })
    },
    [filters, write],
  )

  const replaceFilters = useCallback(
    (next: TranselecFilterState) => {
      lastCommitted.current = next.q
      setDraftQuery(next.q)
      write(next)
    },
    [write],
  )

  const reset = useCallback(() => {
    lastCommitted.current = ''
    setDraftQuery('')
    navigate(pathname, { replace: true })
  }, [navigate, pathname])

  return { filters, draftQuery, setQuery: setDraftQuery, setField, replaceFilters, reset }
}

export interface ReadState<T> {
  data: T | null
  loading: boolean
  failure: FailureView | null
  rawFailure: ApiFailure | null
  reload: () => void
}

/**
 * Run one section's reads together and commit them as a unit.
 *
 * `run` returns whatever shape the section needs; it is written by the caller
 * as a single `Promise.all` so that either every value for this filter state
 * arrives or none of them does. The first failure decides the section's
 * state — a section never renders half its numbers beside an error.
 */
export function useReads<T>(
  run: () => Promise<ApiResult<T>>,
  deps: readonly unknown[],
): ReadState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [rawFailure, setRawFailure] = useState<ApiFailure | null>(null)
  const [reloadToken, setReloadToken] = useState(0)
  const requestId = useRef(0)

  useEffect(() => {
    const id = ++requestId.current
    let cancelled = false
    setLoading(true)

    void run().then((result) => {
      if (cancelled || id !== requestId.current) return
      if (result.ok) {
        setData(result.data)
        setRawFailure(null)
      } else {
        setData(null)
        setRawFailure({ status: result.status, error: result.error })
      }
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
    // `run` is re-created every render by design; the caller's `deps` are the
    // real inputs, plus the manual reload token.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadToken])

  const reload = useCallback(() => setReloadToken((value) => value + 1), [])

  return {
    data,
    loading,
    failure: rawFailure ? classifyFailure(rawFailure) : null,
    rawFailure,
    reload,
  }
}
