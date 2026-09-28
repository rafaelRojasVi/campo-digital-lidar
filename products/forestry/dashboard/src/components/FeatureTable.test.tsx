import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FeatureTable } from './FeatureTable.tsx'
import { makeFeature } from '../test/fixtures.ts'

function manyFeatures(count: number) {
  return Array.from({ length: count }, (_, index) =>
    makeFeature({
      feature_ordinal: index + 1,
      source_objectid: 1000 + index,
      n_rodal: String(index + 1),
      sup_ha: index + 1,
    }),
  )
}

describe('FeatureTable pagination', () => {
  it('bounds the page to 25 rows and navigates between pages', async () => {
    const user = userEvent.setup()
    const features = manyFeatures(60)

    render(
      <FeatureTable
        features={features}
        selectedOrdinal={null}
        onSelectFeature={() => {}}
        snapshotId={1}
      />,
    )

    expect(screen.getByText(/página 1 de 3/)).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(1 + 25)

    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Siguiente' }))
    expect(screen.getByText(/página 2 de 3/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Siguiente' }))
    expect(screen.getByText(/página 3 de 3/)).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(1 + 10)
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  })

  it('jumps to the page containing an externally selected polygon', () => {
    const features = manyFeatures(60)

    const { rerender } = render(
      <FeatureTable
        features={features}
        selectedOrdinal={null}
        onSelectFeature={() => {}}
        snapshotId={1}
      />,
    )

    rerender(
      <FeatureTable
        features={features}
        selectedOrdinal={40}
        onSelectFeature={() => {}}
        snapshotId={1}
      />,
    )

    expect(screen.getByText(/página 2 de 3/)).toBeInTheDocument()
    // Ordinal 40 carries rodal '40' in this fixture set.
    const selectedRow = screen.getByText('40').closest('tr')
    expect(selectedRow).toHaveClass('table__row--selected')
  })

  it('sorts by Sup_ha when the column header is clicked', async () => {
    const user = userEvent.setup()
    const features = manyFeatures(30)

    render(
      <FeatureTable
        features={features}
        selectedOrdinal={null}
        onSelectFeature={() => {}}
        snapshotId={1}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Ordenar por Sup. (ha)' }))
    await user.click(screen.getByRole('button', { name: 'Ordenar por Sup. (ha)' }))

    const firstDataRow = screen.getAllByRole('row')[1] as HTMLElement
    expect(within(firstDataRow).getByText('30,00')).toBeInTheDocument()
  })

  it('notifies row selection', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()

    render(
      <FeatureTable
        features={manyFeatures(3)}
        selectedOrdinal={null}
        onSelectFeature={onSelect}
        snapshotId={1}
      />,
    )

    await user.click(screen.getByText('2'))
    expect(onSelect).toHaveBeenCalledWith(2)
  })
})
