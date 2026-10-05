import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiResult, TranselecEditHistory } from '../api'
import { useWebEdits } from '../lib/webEditsState'
import { makeActiveImport, makeHistory } from '../test/factories'
import { WebEditsProvider } from './WebEditsProvider'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, getOverrideHistory: vi.fn() }
})
const { getOverrideHistory } = await import('../api')

function Probe() {
  const { history, status, refresh } = useWebEdits()
  return (
    <>
      <span data-testid="status">{status}</span>
      <span data-testid="count">{history ? history.in_force_count : 'none'}</span>
      <button type="button" onClick={refresh}>
        refresh
      </button>
    </>
  )
}

function deferred() {
  let resolve!: (value: ApiResult<TranselecEditHistory>) => void
  const promise = new Promise<ApiResult<TranselecEditHistory>>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

const ok = (in_force_count: number): ApiResult<TranselecEditHistory> => ({
  ok: true,
  data: makeHistory({ in_force_count }),
})

describe('WebEditsProvider', () => {
  beforeEach(() => vi.mocked(getOverrideHistory).mockReset())
  afterEach(() => vi.restoreAllMocks())

  it('loads once a version is active and clears when none is', async () => {
    vi.mocked(getOverrideHistory).mockResolvedValue(ok(3))
    const { rerender } = render(
      <WebEditsProvider activeImport={null}>
        <Probe />
      </WebEditsProvider>,
    )
    expect(getOverrideHistory).not.toHaveBeenCalled()
    expect(screen.getByTestId('status')).toHaveTextContent('idle')

    rerender(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(screen.getByTestId('status')).toHaveTextContent('ready')

    rerender(
      <WebEditsProvider activeImport={null}>
        <Probe />
      </WebEditsProvider>,
    )
    expect(screen.getByTestId('count')).toHaveTextContent('none')
    expect(screen.getByTestId('status')).toHaveTextContent('idle')
  })

  it('reloads when the active version is read again (publish or restore)', async () => {
    vi.mocked(getOverrideHistory).mockResolvedValue(ok(1))
    const { rerender } = render(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    await screen.findByText('1')
    rerender(
      <WebEditsProvider activeImport={makeActiveImport({ import_id: 13 })}>
        <Probe />
      </WebEditsProvider>,
    )
    expect(getOverrideHistory).toHaveBeenCalledTimes(2)
  })

  it('keeps the previous history while a refresh runs and drops an out-of-order answer', async () => {
    const first = deferred()
    const second = deferred()
    vi.mocked(getOverrideHistory)
      .mockResolvedValueOnce(ok(1))
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    render(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    await screen.findByText('1')

    await userEvent.click(screen.getByRole('button', { name: 'refresh' }))
    await userEvent.click(screen.getByRole('button', { name: 'refresh' }))
    expect(screen.getByTestId('count')).toHaveTextContent('1') // no flicker
    expect(screen.getByTestId('status')).toHaveTextContent('ready')

    await act(async () => second.resolve(ok(5)))
    await act(async () => first.resolve(ok(2))) // the older request: ignored
    expect(screen.getByTestId('count')).toHaveTextContent('5')
  })

  it('clears on a failed load', async () => {
    vi.mocked(getOverrideHistory)
      .mockResolvedValueOnce(ok(4))
      .mockResolvedValueOnce({ ok: false, status: 401, error: 'Not authenticated.' })
    render(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    await screen.findByText('4')
    await userEvent.click(screen.getByRole('button', { name: 'refresh' }))
    expect(await screen.findByText('none')).toBeInTheDocument()
    expect(screen.getByTestId('status')).toHaveTextContent('error')
  })

  it('refreshes when the tab is visible again, at most once a minute', async () => {
    vi.mocked(getOverrideHistory).mockResolvedValue(ok(1))
    const now = vi.spyOn(Date, 'now').mockReturnValue(1_000_000)
    render(
      <WebEditsProvider activeImport={makeActiveImport()}>
        <Probe />
      </WebEditsProvider>,
    )
    await screen.findByText('1')
    const visible = () => act(() => void document.dispatchEvent(new Event('visibilitychange')))

    now.mockReturnValue(1_000_000 + 59_000)
    visible()
    expect(getOverrideHistory).toHaveBeenCalledTimes(1)

    now.mockReturnValue(1_000_000 + 61_000)
    visible()
    expect(getOverrideHistory).toHaveBeenCalledTimes(2)
  })
})
