/**
 * Owns the shared web-edits history (indicator spec §3).
 *
 * Loads once a version is active, and again whenever the shell re-reads the
 * active version (after a publish or restore in this session). Without one —
 * signed out, or nothing published — it holds nothing. A failed load,
 * including a 401, clears it, so the pill never shows another session's or a
 * stale version's numbers. When the tab becomes visible again it refreshes,
 * at most once a minute, so another tab's or person's edits show up. A
 * refresh keeps the previous history on screen until the answer arrives, and
 * an answer older than the latest request is dropped.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { type TranselecActiveImport, type TranselecEditHistory, getOverrideHistory } from '../api'
import {
  REFOCUS_REFRESH_MS,
  WebEditsContext,
  type WebEditsStatus,
  openEditLog,
} from '../lib/webEditsState'

export function WebEditsProvider({
  activeImport,
  children,
}: {
  /** The shell's active-version read; a new object after every publish or restore. */
  activeImport: TranselecActiveImport | null
  children: ReactNode
}) {
  // The last answer; null until the first one arrives. While a refresh runs
  // the previous answer stays, so the pill never flickers.
  const [answer, setAnswer] = useState<{
    history: TranselecEditHistory | null
    status: 'ready' | 'error'
  } | null>(null)
  const latestRequest = useRef(0)
  const lastStarted = useRef(0)
  const enabled = activeImport !== null

  // Signed out or nothing published: drop what the last version had, during
  // render, so no frame shows another session's numbers.
  if (!enabled && answer !== null) setAnswer(null)

  const load = useCallback(() => {
    const id = ++latestRequest.current
    lastStarted.current = Date.now()
    void getOverrideHistory().then((result) => {
      if (id !== latestRequest.current) return
      setAnswer(
        result.ok ? { history: result.data, status: 'ready' } : { history: null, status: 'error' },
      )
    })
  }, [])

  useEffect(() => {
    if (activeImport === null) {
      latestRequest.current += 1 // an answer still in flight belongs to the old session
      return
    }
    load()
  }, [activeImport, load])

  useEffect(() => {
    if (!enabled) return undefined
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      if (Date.now() - lastStarted.current < REFOCUS_REFRESH_MS) return
      load()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [enabled, load])

  const refresh = useCallback(() => {
    if (enabled) load()
  }, [enabled, load])

  const history = enabled ? (answer?.history ?? null) : null
  const status: WebEditsStatus = !enabled ? 'idle' : (answer?.status ?? 'loading')
  const value = useMemo(
    () => ({ history, status, refresh, openLog: openEditLog }),
    [history, status, refresh],
  )
  return <WebEditsContext.Provider value={value}>{children}</WebEditsContext.Provider>
}
