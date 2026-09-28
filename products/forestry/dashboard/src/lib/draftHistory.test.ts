import { describe, expect, it } from 'vitest'
import {
  createDraftHistory,
  pushDraftHistory,
  redoDraftHistory,
  undoDraftHistory,
} from './draftHistory.ts'
import type { DraftCoordinates } from './draftGeometry.ts'

const stateA: DraftCoordinates = [[[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]]
const stateB: DraftCoordinates = [[[[0, 0], [20, 0], [20, 10], [0, 10], [0, 0]]]]
const stateC: DraftCoordinates = [[[[0, 0], [30, 0], [30, 10], [0, 10], [0, 0]]]]

describe('draft history', () => {
  it('undoes to the previously pushed state and redoes back', () => {
    let history = createDraftHistory()
    history = pushDraftHistory(history, stateA)

    const undone = undoDraftHistory(history, stateB)
    expect(undone).not.toBeNull()
    expect(undone?.coordinates).toEqual(stateA)

    const redone = redoDraftHistory(undone!.history, stateB)
    expect(redone).not.toBeNull()
    expect(redone?.coordinates).toEqual(stateB)
  })

  it('supports multiple undo steps in order', () => {
    let history = createDraftHistory()
    history = pushDraftHistory(history, stateA)
    history = pushDraftHistory(history, stateB)

    const firstUndo = undoDraftHistory(history, stateC)
    expect(firstUndo?.coordinates).toEqual(stateB)

    const secondUndo = undoDraftHistory(firstUndo!.history, firstUndo!.coordinates)
    expect(secondUndo?.coordinates).toEqual(stateA)
    expect(secondUndo?.history.past).toHaveLength(0)
  })

  it('clears the redo stack once a new change is pushed', () => {
    let history = createDraftHistory()
    history = pushDraftHistory(history, stateA)
    const undone = undoDraftHistory(history, stateB)!
    expect(undone.history.future).toHaveLength(1)

    const afterNewEdit = pushDraftHistory(undone.history, undone.coordinates)
    expect(afterNewEdit.future).toHaveLength(0)
    expect(redoDraftHistory(afterNewEdit, stateC)).toBeNull()
  })

  it('returns null when there is nothing to undo or redo', () => {
    const history = createDraftHistory()
    expect(undoDraftHistory(history, stateA)).toBeNull()
    expect(redoDraftHistory(history, stateA)).toBeNull()
  })
})
