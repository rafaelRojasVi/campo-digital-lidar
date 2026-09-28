import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Pagination } from './Pagination'

const base = {
  pageIndex: 0,
  pageSize: 25,
  pageRows: 25,
  totalCount: 729,
  hasMore: true,
  loading: false,
  onPrev: () => {},
  onNext: () => {},
  onPageSizeChange: () => {},
}

describe('Pagination (TR-FUNC-039)', () => {
  it('reports the visible range against the true filtered total', () => {
    render(<Pagination {...base} />)
    expect(screen.getByTestId('pagination-range')).toHaveTextContent(
      'Mostrando 1–25 de 729 filas',
    )
  })

  it('advances the range readout with the page index', () => {
    render(<Pagination {...base} pageIndex={2} pageRows={25} />)
    expect(screen.getByTestId('pagination-range')).toHaveTextContent('Mostrando 51–75 de 729')
  })

  it('handles a final short page', () => {
    render(<Pagination {...base} pageIndex={29} pageRows={4} hasMore={false} />)
    expect(screen.getByTestId('pagination-range')).toHaveTextContent('Mostrando 726–729 de 729')
    expect(screen.getByTestId('page-next')).toBeDisabled()
  })

  it('shows a zero range instead of "1-0" for an empty result set', () => {
    render(<Pagination {...base} pageRows={0} totalCount={0} hasMore={false} />)
    expect(screen.getByTestId('pagination-range')).toHaveTextContent('Mostrando 0–0 de 0 filas')
  })

  it('disables previous on the first page and next when there is no more data', () => {
    render(<Pagination {...base} hasMore={false} />)
    expect(screen.getByTestId('page-prev')).toBeDisabled()
    expect(screen.getByTestId('page-next')).toBeDisabled()
  })

  it('calls the navigation handlers', async () => {
    const onNext = vi.fn()
    const onPrev = vi.fn()
    render(<Pagination {...base} pageIndex={1} onNext={onNext} onPrev={onPrev} />)

    await userEvent.click(screen.getByTestId('page-next'))
    await userEvent.click(screen.getByTestId('page-prev'))

    expect(onNext).toHaveBeenCalledTimes(1)
    expect(onPrev).toHaveBeenCalledTimes(1)
  })

  it('lets the reader change the page size', async () => {
    const onPageSizeChange = vi.fn()
    render(<Pagination {...base} onPageSizeChange={onPageSizeChange} />)
    await userEvent.selectOptions(screen.getByLabelText('Filas por página'), '100')
    expect(onPageSizeChange).toHaveBeenCalledWith(100)
  })

  it('disables navigation while a page is loading', () => {
    render(<Pagination {...base} pageIndex={1} loading />)
    expect(screen.getByTestId('page-prev')).toBeDisabled()
    expect(screen.getByTestId('page-next')).toBeDisabled()
  })
})
