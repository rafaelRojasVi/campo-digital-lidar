import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ReforestationChips } from './ReforestationChips'

describe('ReforestationChips (TR-FUNC-012)', () => {
  it('renders one chip per distinct «Predio Ref» label', () => {
    render(<ReforestationChips predios={['Fundo Dos', 'Fundo Uno']} />)
    expect(screen.getByTestId('reforestation-count')).toHaveTextContent('2')
    expect(screen.getByText('Fundo Uno')).toBeInTheDocument()
    expect(screen.getByText('Fundo Dos')).toBeInTheDocument()
    expect(screen.getByTestId('reforestation')).toHaveTextContent('2 etiquetas distintas')
  })

  it('uses the singular noun for a single label', () => {
    render(<ReforestationChips predios={['Fundo Uno']} />)
    expect(screen.getByTestId('reforestation')).toHaveTextContent('1 etiqueta distinta')
  })

  it('collapses the tail into an overflow chip past ten values', () => {
    const predios = Array.from({ length: 14 }, (_, index) => `Fundo ${index + 1}`)
    render(<ReforestationChips predios={predios} />)

    expect(screen.getByTestId('reforestation-count')).toHaveTextContent('14')
    expect(screen.getByTestId('reforestation-overflow')).toHaveTextContent('Muchos · 14 en total')
    expect(screen.getByText('Fundo 10')).toBeInTheDocument()
    expect(screen.queryByText('Fundo 11')).not.toBeInTheDocument()
  })

  it('shows an explicit empty message when the filtered scope has none', () => {
    render(<ReforestationChips predios={[]} />)
    expect(
      screen.getByText('Sin predios de reforestación informados para el filtro actual.'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('reforestation-overflow')).not.toBeInTheDocument()
  })
})
