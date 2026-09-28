import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('local unavailable reads "Demo no iniciada", unchanged from today', () => {
    render(<StatusBadge status="unavailable" environment="local" />)
    expect(screen.getByText('Demo no iniciada')).toBeInTheDocument()
  })

  it('staging unavailable reads an honest not-hosted label, never "Demo no iniciada"', () => {
    render(<StatusBadge status="unavailable" environment="staging" />)
    expect(screen.getByText('No desplegado en este entorno')).toBeInTheDocument()
    expect(screen.queryByText('Demo no iniciada')).not.toBeInTheDocument()
  })

  it('available reads "Disponible" in both environments', () => {
    const { rerender } = render(<StatusBadge status="available" environment="local" />)
    expect(screen.getByText('Disponible')).toBeInTheDocument()
    rerender(<StatusBadge status="available" environment="staging" />)
    expect(screen.getByText('Disponible')).toBeInTheDocument()
  })
})
