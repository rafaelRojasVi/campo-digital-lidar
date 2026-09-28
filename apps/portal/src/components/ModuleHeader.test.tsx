import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RouterProvider } from '../router/Router'
import { ModuleHeader } from './ModuleHeader'
import { MODULES } from '../data/modules'

const forestal = MODULES.find((module) => module.id === 'forestal')!

describe('ModuleHeader', () => {
  it('shows the external-open action for a safe loopback URL', () => {
    render(
      <RouterProvider>
        <ModuleHeader module={forestal} url="http://127.0.0.1:5175/" environment="local" />
      </RouterProvider>,
    )

    const link = screen.getByText('Abrir en pestaña nueva')
    expect(link).toHaveAttribute('href', 'http://127.0.0.1:5175/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('hides the external-open action instead of using an unsafe URL', () => {
    render(
      <RouterProvider>
        <ModuleHeader module={forestal} url="javascript:alert(1)" environment="local" />
      </RouterProvider>,
    )

    expect(screen.queryByText('Abrir en pestaña nueva')).not.toBeInTheDocument()
  })

  it('hides the external-open action when no URL is known yet', () => {
    render(
      <RouterProvider>
        <ModuleHeader module={forestal} url={undefined} environment="local" />
      </RouterProvider>,
    )

    expect(screen.queryByText('Abrir en pestaña nueva')).not.toBeInTheDocument()
  })

  it('accepts the known staging hosted origin as a safe external-open target', () => {
    render(
      <RouterProvider>
        <ModuleHeader
          module={forestal}
          url="https://campo-digital-lidar-staging.onrender.com/"
          environment="staging"
        />
      </RouterProvider>,
    )

    expect(screen.getByText('Abrir en pestaña nueva')).toHaveAttribute(
      'href',
      'https://campo-digital-lidar-staging.onrender.com/',
    )
  })

  it('in staging, rejects a loopback URL that would only be safe locally', () => {
    render(
      <RouterProvider>
        <ModuleHeader module={forestal} url="http://127.0.0.1:5175/" environment="staging" />
      </RouterProvider>,
    )

    expect(screen.queryByText('Abrir en pestaña nueva')).not.toBeInTheDocument()
  })
})
