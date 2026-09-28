/**
 * What the reforestation section may and may not claim.
 *
 * Marianne asked for a property count and an owner count. The source
 * supports neither cleanly, and this panel has to say so rather than
 * producing a number that would be quoted back as fact.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Reforestacion } from '../api'
import { ReforestacionPanel } from './ReforestacionPanel'

function makeReforestacion(overrides: Partial<Reforestacion> = {}): Reforestacion {
  return {
    definicion:
      'Valores distintos y no vacíos de «Predio Ref», excluyendo el literal «Sin reforestacion».',
    predio_ref_labels: ['Ref001_Rubi', 'Ref005_ Kompatzki'],
    predio_ref_count: 2,
    rol_ref_count: 3,
    sentinel_label: 'Sin reforestacion',
    sentinel_row_count: 1,
    etiquetas_compuestas: [],
    propietarios: 'No disponible en el origen',
    ...overrides,
  }
}

describe('ReforestacionPanel', () => {
  it('labels the property metric with the exact field it counts', () => {
    render(<ReforestacionPanel reforestacion={makeReforestacion()} />)

    expect(screen.getByTestId('kpi-ref-predios')).toHaveTextContent('2')
    expect(screen.getByText(/Etiquetas de «Predio Ref»/)).toBeInTheDocument()
    expect(screen.getByTestId('reforestacion-definition')).toHaveTextContent('Predio Ref')
  })

  it('shows no numeric owner count, because the source identifies no owner', () => {
    render(<ReforestacionPanel reforestacion={makeReforestacion()} />)

    const owners = screen.getByTestId('kpi-ref-propietarios')
    expect(owners).toHaveTextContent('No disponible en el origen')
    expect(owners.textContent).not.toMatch(/\d/)
    expect(screen.getByText(/no tiene un campo de propietario/)).toBeInTheDocument()
  })

  it('never renders the owner slot as a zero', () => {
    render(<ReforestacionPanel reforestacion={makeReforestacion({ predio_ref_count: 0 })} />)
    expect(screen.getByTestId('kpi-ref-propietarios')).not.toHaveTextContent('0')
  })

  it('explains that the excluded sentinel is an absence, not a property', () => {
    render(<ReforestacionPanel reforestacion={makeReforestacion({ sentinel_row_count: 4 })} />)
    expect(
      screen.getByText(/ausencia de reforestación, no un predio, por lo que no se cuenta/),
    ).toBeInTheDocument()
  })

  it('discloses the labels that name more than one property', () => {
    render(
      <ReforestacionPanel
        reforestacion={makeReforestacion({
          etiquetas_compuestas: ['Ref036_ Reyes y Ref037_ Reyes', 'Rubi + Marin'],
        })}
      />,
    )

    const note = screen.getByTestId('reforestacion-composite')
    expect(note).toHaveTextContent('Ref036_ Reyes y Ref037_ Reyes')
    expect(note).toHaveTextContent(/cota inferior/)
  })

  it('names the source fields that would make the question answerable', () => {
    render(<ReforestacionPanel reforestacion={makeReforestacion()} />)

    expect(screen.getByText('id_predio_reforestacion')).toBeInTheDocument()
    expect(screen.getByText('id_propietario_reforestacion')).toBeInTheDocument()
    expect(screen.getByText('nombre_propietario_reforestacion')).toBeInTheDocument()
  })
})
