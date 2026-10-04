import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PlazoFailureBanner } from './PlazoFailureBanner'
import type { FailureView } from '../lib/apiState'

const FAILURE: FailureView = { kind: 'error', title: 'Error', message: 'No se pudo leer.' }

function banner(loading: boolean, onRetry: () => void) {
  return (
    <PlazoFailureBanner
      failure={FAILURE}
      rawFailure={null}
      loading={loading}
      onRetry={onRetry}
      scope="Sin plazo."
    />
  )
}

describe('PlazoFailureBanner', () => {
  it('keeps keyboard focus on «Reintentar» while it retries, and ignores a second activation', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    const { rerender } = render(banner(false, onRetry))

    const button = screen.getByRole('button', { name: 'Reintentar' })
    await user.tab()
    expect(button).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(onRetry).toHaveBeenCalledTimes(1)

    rerender(banner(true, onRetry))
    const busy = screen.getByRole('button', { name: 'Reintentando…' })
    expect(busy).toBe(button)
    expect(busy).toHaveAttribute('aria-disabled', 'true')
    expect(busy).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(busy).toHaveFocus()
  })
})
