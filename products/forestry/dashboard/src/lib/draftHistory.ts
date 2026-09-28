import type { DraftCoordinates } from './draftGeometry.ts'

/**
 * In-memory undo/redo stack for the local draft editor. Holds full
 * coordinate snapshots for simplicity (draft polygons are small enough that
 * this is cheap); nothing here is persisted or sent to a server.
 */
export interface DraftHistoryState {
  past: DraftCoordinates[]
  future: DraftCoordinates[]
}

export function createDraftHistory(): DraftHistoryState {
  return { past: [], future: [] }
}

/** Record `previous` (the state right before a just-applied change) as undoable. */
export function pushDraftHistory(
  history: DraftHistoryState,
  previous: DraftCoordinates,
): DraftHistoryState {
  return { past: [...history.past, previous], future: [] }
}

export interface DraftHistoryStep {
  history: DraftHistoryState
  coordinates: DraftCoordinates
}

export function undoDraftHistory(
  history: DraftHistoryState,
  current: DraftCoordinates,
): DraftHistoryStep | null {
  const target = history.past.at(-1)
  if (target === undefined) return null

  return {
    history: { past: history.past.slice(0, -1), future: [current, ...history.future] },
    coordinates: target,
  }
}

export function redoDraftHistory(
  history: DraftHistoryState,
  current: DraftCoordinates,
): DraftHistoryStep | null {
  const target = history.future[0]
  if (target === undefined) return null

  return {
    history: { past: [...history.past, current], future: history.future.slice(1) },
    coordinates: target,
  }
}
