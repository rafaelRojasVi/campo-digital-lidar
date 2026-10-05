/**
 * The shell's shared web-edits state (indicator spec §3): the edit history
 * the header pill, its log, the Resumen hint and Ediciones web all read.
 *
 * The context lives apart from its provider so component modules export only
 * components (oxlint `react/only-export-components`). Outside a provider, as
 * in most component tests, it is inert: no history, and `refresh` and
 * `openLog` do nothing.
 */
import { createContext, useContext } from 'react'
import type { TranselecEditHistory } from '../api'
import { EDIT_LOG_ID } from './editLog'

export type WebEditsStatus = 'idle' | 'loading' | 'ready' | 'error'

/** A tab that becomes visible again re-reads the history at most this often. */
export const REFOCUS_REFRESH_MS = 60_000

export interface WebEditsValue {
  /** The last successful load. Kept while a refresh runs; cleared by a failed one. */
  history: TranselecEditHistory | null
  status: WebEditsStatus
  /** Re-read the history. Call after every save, revert, discard or keep. */
  refresh: () => void
  /** Open the header's edits log, if it is on the page. */
  openLog: () => void
}

export const WebEditsContext = createContext<WebEditsValue>({
  history: null,
  status: 'idle',
  refresh: () => {},
  openLog: () => {},
})

export function useWebEdits(): WebEditsValue {
  return useContext(WebEditsContext)
}

/** Show the log popover; nothing where it is absent, already open, or the Popover API is missing. */
export function openEditLog(): void {
  const log = document.getElementById(EDIT_LOG_ID)
  if (!log || typeof log.showPopover !== 'function' || log.matches(':popover-open')) return
  log.showPopover()
}
