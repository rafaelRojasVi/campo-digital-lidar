import { act, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { TranselecEditHistory } from '../api'
import { WebEditsContext } from '../lib/webEditsState'
import { ROUTES, RouterProvider } from '../router'
import { makeHistory, makeHistoryEntry } from '../test/factories'
import { WebEditsPill } from './WebEditsPill'

function renderPill(history: TranselecEditHistory | null, canEdit = true) {
  return render(
    <RouterProvider initialPath={ROUTES.resumen}>
      <WebEditsContext.Provider
        value={{ history, status: history ? 'ready' : 'error', refresh: vi.fn(), openLog: vi.fn() }}
      >
        <WebEditsPill canEdit={canEdit} />
      </WebEditsContext.Provider>
    </RouterProvider>,
  )
}

describe('the «ediciones web» pill', () => {
  it('names the full count at every width and points at the log', () => {
    renderPill(makeHistory({ in_force_count: 5, needs_review_count: 2 }))
    const pill = screen.getByRole('button', { name: '5 ediciones web · 2 por revisar' })
    expect(pill).toHaveAttribute('popovertarget', 'edit-log')
    expect(pill).toHaveAttribute('aria-haspopup', 'dialog')
    expect(pill).toHaveAttribute('aria-controls', 'edit-log')
    expect(pill).toHaveAttribute('aria-expanded', 'false')
    expect(pill).toHaveAttribute('title', '5 ediciones web · 2 por revisar')
    expect(pill.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(pill).not.toHaveTextContent('✎')
  })

  it('is singular for one edit and has no review part when nothing needs review', () => {
    renderPill(makeHistory({ in_force_count: 1 }))
    expect(screen.getByRole('button', { name: '1 edición web' })).toBeInTheDocument()
    expect(screen.getByTestId('edits-pill')).not.toHaveTextContent('por revisar')
  })

  it.each([
    ['before a successful load or after an error', null],
    [
      'with nothing in force or to review',
      makeHistory({ in_force_count: 0, needs_review_count: 0 }),
    ],
  ])('is absent %s', (_, history) => {
    renderPill(history)
    expect(screen.queryByTestId('edits-pill')).not.toBeInTheDocument()
    expect(screen.queryByTestId('edit-log')).not.toBeInTheDocument()
  })
})

describe('the edits log', () => {
  const entries = [
    makeHistoryEntry({ id: 9, state: 'aplicada', source_row_number: 7, pmf: 'MP009' }),
    makeHistoryEntry({ id: 8, state: 'en_conflicto', source_row_number: 3 }),
    makeHistoryEntry({ id: 7, state: 'huerfana', source_row_number: null }),
    makeHistoryEntry({ id: 6, state: 'incorporada' }),
    makeHistoryEntry({
      id: 5,
      state: 'superseded',
      source_row_number: null,
      ended_by_display_name: 'Ana',
    }),
    makeHistoryEntry({
      id: 4,
      state: 'discarded',
      source_row_number: null,
      ended_by_display_name: 'Ana',
    }),
    makeHistoryEntry({
      id: 3,
      state: 'kept',
      source_row_number: null,
      ended_by_display_name: 'Luis',
    }),
    makeHistoryEntry({
      id: 2,
      state: 'incorporated',
      source_row_number: null,
      planilla_value_at_edit: null,
    }),
    makeHistoryEntry({ id: 1 }),
    makeHistoryEntry({ id: 0 }),
  ]

  it('is a named dialog popover with the counts beside its heading', () => {
    renderPill(makeHistory({ in_force_count: 5, needs_review_count: 2, entries }))
    const log = screen.getByTestId('edit-log')
    expect(log).toHaveAttribute('popover', 'auto')
    expect(log).toHaveAttribute('role', 'dialog')
    expect(log).toHaveAttribute('aria-labelledby', 'edit-log-heading')
    expect(
      within(log).getByRole('heading', { name: 'Ediciones web', hidden: true }),
    ).toHaveAttribute('tabindex', '-1')
    expect(log).toHaveTextContent('5 en vigor')
    expect(log).toHaveTextContent('2 por revisar')
  })

  it('shows the latest 8 with their labels, greys what no longer applies, and says how many more', () => {
    renderPill(makeHistory({ entries }))
    const log = screen.getByTestId('edit-log')
    expect(within(log).getAllByRole('listitem', { hidden: true })).toHaveLength(8)
    expect(log).toHaveTextContent('y 2 más')
    expect(screen.getByTestId('edit-log-9')).not.toHaveAttribute('data-muted')
    expect(screen.getByTestId('edit-log-8')).toHaveTextContent('en conflicto: la planilla cambió')
    expect(screen.getByTestId('edit-log-8')).not.toHaveAttribute('data-muted')
    expect(screen.getByTestId('edit-log-7')).toHaveTextContent('sin fila en la versión activa')
    expect(screen.getByTestId('edit-log-6')).toHaveTextContent('ya está en la planilla')
    expect(screen.getByTestId('edit-log-5')).toHaveTextContent(
      'reemplazada por una edición posterior',
    )
    expect(screen.getByTestId('edit-log-4')).toHaveTextContent(
      'revertida al valor de la planilla · Ana',
    )
    expect(screen.getByTestId('edit-log-3')).toHaveTextContent(
      'conservada al resolver un conflicto · Luis',
    )
    expect(screen.getByTestId('edit-log-2')).toHaveTextContent('(vacío)')
    expect(screen.getByTestId('edit-log-4')).toHaveAttribute('data-muted', 'true')
  })

  it('links only entries with a row, to the Explorador with that row open', () => {
    renderPill(makeHistory({ entries }))
    expect(
      within(screen.getByTestId('edit-log-9')).getByRole('link', { hidden: true }),
    ).toHaveAttribute('href', '/transelec/explorador?q=MP009&fila=7')
    expect(
      within(screen.getByTestId('edit-log-4')).queryByRole('link', { hidden: true }),
    ).not.toBeInTheDocument()
    expect(
      within(screen.getByTestId('edit-log-7')).queryByRole('link', { hidden: true }),
    ).not.toBeInTheDocument()
  })

  it('keeps each full value for screen readers and on hover', () => {
    const long = 'Un valor largo '.repeat(20).trim()
    renderPill(makeHistory({ entries: [makeHistoryEntry({ web_value: long })] }))
    expect(screen.getByTitle(long)).toHaveTextContent(long)
  })

  it('offers Ediciones web and the download to operators and administrators only', () => {
    const { unmount } = renderPill(makeHistory(), true)
    expect(
      screen.getByRole('link', { name: 'Ver todas en Ediciones web →', hidden: true }),
    ).toHaveAttribute('href', '/transelec/ediciones')
    expect(
      screen.getByRole('button', { name: 'Descargar planilla con ediciones (.xlsx)', hidden: true }),
    ).toBeInTheDocument()
    unmount()

    renderPill(makeHistory(), false)
    expect(
      screen.queryByRole('link', { name: /Ediciones web/, hidden: true }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Descargar/, hidden: true })).not.toBeInTheDocument()
  })
})

describe('the pill while its log is open', () => {
  function toggle(newState: 'open' | 'closed') {
    const event = Object.assign(new Event('toggle'), { newState, oldState: newState === 'open' ? 'closed' : 'open' })
    act(() => {
      screen.getByTestId('edit-log').dispatchEvent(event)
    })
  }

  function view(history: TranselecEditHistory | null) {
    return (
      <RouterProvider initialPath={ROUTES.resumen}>
        <WebEditsContext.Provider
          value={{ history, status: history ? 'ready' : 'error', refresh: vi.fn(), openLog: vi.fn() }}
        >
          <WebEditsPill canEdit />
        </WebEditsContext.Provider>
      </RouterProvider>
    )
  }

  it('stays, with the last entries, if a refresh empties it while the log is open', () => {
    const { rerender } = render(view(makeHistory({ in_force_count: 2 })))
    toggle('open')
    expect(screen.getByTestId('edits-pill')).toHaveAttribute('aria-expanded', 'true')

    rerender(view(makeHistory({ in_force_count: 0, needs_review_count: 0, entries: [] })))
    expect(screen.getByTestId('edit-log')).toBeInTheDocument()
    expect(screen.getByTestId('edits-pill')).toHaveAttribute('aria-label', '2 ediciones web')

    toggle('closed')
    expect(screen.queryByTestId('edits-pill')).not.toBeInTheDocument()
  })

  it('comes back closed after it went away', () => {
    const { rerender } = render(view(makeHistory({ in_force_count: 2 })))
    toggle('open')
    toggle('closed')
    rerender(view(null))
    rerender(view(makeHistory({ in_force_count: 3 })))
    expect(screen.getByTestId('edits-pill')).toHaveAttribute('aria-expanded', 'false')
  })
})
