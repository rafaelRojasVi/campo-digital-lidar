import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusPill } from './StatusPill'

describe('StatusPill', () => {
  it('tones the four known Estado resumido values', () => {
    const { rerender, container } = render(<StatusPill value="Aprobado" />)
    expect(container.querySelector('.pill')).toHaveClass('pill-aprobado')

    rerender(<StatusPill value="En tramite" />)
    expect(container.querySelector('.pill')).toHaveClass('pill-en-tramite')

    rerender(<StatusPill value="Pendiente" />)
    expect(container.querySelector('.pill')).toHaveClass('pill-pendiente')

    rerender(<StatusPill value="Tachado" />)
    expect(container.querySelector('.pill')).toHaveClass('pill-tachado')
  })

  it('still renders an unrecognised value rather than dropping it', () => {
    const { container } = render(<StatusPill value="Desistida" />)
    expect(screen.getByText('Desistida')).toBeInTheDocument()
    expect(container.querySelector('.pill')).toHaveClass('pill-otro')
  })

  it('renders a dash for a blank value', () => {
    render(<StatusPill value={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('escapes markup in a workbook-derived value', () => {
    const { container } = render(<StatusPill value="<b>Aprobado</b>" />)
    expect(container.querySelector('b')).toBeNull()
    expect(container.textContent).toBe('<b>Aprobado</b>')
  })
})
