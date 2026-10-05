/**
 * Chrome-level components: the application shell (TR-FUNC-041/046), the
 * Consulta documental notice (TR-FUNC-042) and the filter presets that
 * survive from the eight quick-action cards (TR-FUNC-026/028/029/030).
 *
 * The provenance block (TR-FUNC-043) moved to the Datos section's versions
 * pane, where it sits beside the history that produced it; it is covered in
 * `src/pages/VersionesPage.test.tsx`.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppHeader } from './AppHeader'
import { NoticeBanner } from './NoticeBanner'
import { QUICK_ACTIONS, QuickActions } from './QuickActions'
import { ROUTES, RouterProvider } from '../router'
import { makeActiveImport, makeHistory } from '../test/factories'
import { WebEditsContext } from '../lib/webEditsState'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, logout: vi.fn() }
})

const api = await import('../api')

const me = {
  identity_key: 'dev-admin',
  display_name: 'Dev Admin',
  product_grants: [{ product_key: 'transelect', role: 'admin' as const }],
}

function renderWithRouter(node: React.ReactNode) {
  return render(<RouterProvider initialPath={ROUTES.resumen}>{node}</RouterProvider>)
}

function nav() {
  return within(screen.getByRole('navigation', { name: 'Secciones de Transelec' }))
}

describe('AppHeader (TR-FUNC-041/046)', () => {
  it('links back to the project picker only on the unified platform', () => {
    vi.stubEnv('VITE_PLATFORM_FRONT_DOOR', 'true')
    try {
      renderWithRouter(
        <AppHeader
          me={me}
          activeImport={null}
          currentPath={ROUTES.resumen}
          canPublish
          onSignedOut={() => {}}
        />,
      )
      expect(screen.getByRole('link', { name: 'Proyectos' })).toHaveAttribute('href', '/')
      // The front door owns sign-out on the unified platform.
      expect(screen.queryByRole('button', { name: 'Cerrar sesión' })).not.toBeInTheDocument()
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('has no project picker link in a standalone build', () => {
    renderWithRouter(
      <AppHeader me={me} activeImport={null} currentPath={ROUTES.resumen} canPublish />,
    )
    expect(screen.queryByRole('link', { name: 'Proyectos' })).not.toBeInTheDocument()
  })

  it('shows Campo Digital’s own logo, served from the bundle, with the brand as text', () => {
    const { container } = renderWithRouter(
      <AppHeader
        me={me}
        activeImport={makeActiveImport()}
        currentPath={ROUTES.resumen}
        canPublish
      />,
    )
    const logo = screen.getByRole('img', { name: 'Campo Digital' })
    // Served locally from the dashboard's own assets, never hotlinked.
    expect(logo.getAttribute('src')).not.toMatch(/^https?:/)
    expect(logo).toHaveAttribute('width')
    expect(logo).toHaveAttribute('height')
    expect(screen.getByText('Transelec')).toBeInTheDocument()
    // The home link reads as the brand even without the picture.
    expect(screen.getByRole('link', { name: /^Campo Digital\s*·\s*Transelec$/ })).toBeInTheDocument()
    expect(container.querySelectorAll('img')).toHaveLength(1)
  })

  it('stamps the active version’s own publish timestamp, not the current date', () => {
    renderWithRouter(
      <AppHeader
        me={me}
        activeImport={makeActiveImport({ import_id: 42 })}
        currentPath={ROUTES.resumen}
        canPublish
      />,
    )
    expect(screen.getByText('Versión activa #42')).toBeInTheDocument()
    expect(screen.getByText(/Publicada 02-09-2026/)).toBeInTheDocument()
  })

  it('says so plainly when nothing is published', () => {
    renderWithRouter(
      <AppHeader me={me} activeImport={null} currentPath={ROUTES.resumen} canPublish />,
    )
    expect(screen.getByText('Sin versión publicada')).toBeInTheDocument()
  })

  it('offers the four reading sections to everyone', () => {
    renderWithRouter(
      <AppHeader
        me={me}
        activeImport={null}
        currentPath={ROUTES.resumen}
        canPublish={false}
      />,
    )
    for (const label of ['Resumen', 'Explorador', 'Estado', 'Calidad']) {
      expect(nav().getByRole('link', { name: label })).toBeInTheDocument()
    }
  })

  it('hides the whole administration section from a viewer', () => {
    renderWithRouter(
      <AppHeader
        me={me}
        activeImport={null}
        currentPath={ROUTES.resumen}
        canPublish={false}
      />,
    )
    expect(nav().queryByRole('link', { name: 'Datos' })).not.toBeInTheDocument()
  })

  it('marks the current section, including from the two legacy administration routes', () => {
    const { rerender } = renderWithRouter(
      <AppHeader me={me} activeImport={null} currentPath={ROUTES.explorador} canPublish />,
    )
    expect(nav().getByRole('link', { name: 'Explorador' })).toHaveAttribute(
      'aria-current',
      'page',
    )

    for (const legacy of [ROUTES.importar, ROUTES.versiones]) {
      rerender(
        <RouterProvider initialPath={ROUTES.resumen}>
          <AppHeader me={me} activeImport={null} currentPath={legacy} canPublish />
        </RouterProvider>,
      )
      expect(nav().getByRole('link', { name: 'Datos' })).toHaveAttribute('aria-current', 'page')
    }
  })
})

describe('AppHeader sign-out control', () => {
  beforeEach(() => {
    vi.mocked(api.logout).mockReset()
  })

  it('is absent when the header has no session to end', () => {
    renderWithRouter(
      <AppHeader me={null} activeImport={null} currentPath={ROUTES.resumen} canPublish={false} />,
    )
    expect(screen.queryByRole('button', { name: /sesión|usuario/i })).not.toBeInTheDocument()
  })

  it('says «Cambiar usuario» locally, where switching identities is the point', () => {
    renderWithRouter(
      <AppHeader
        me={me}
        activeImport={null}
        currentPath={ROUTES.resumen}
        canPublish
        demoMode
        onSignedOut={() => {}}
      />,
    )
    expect(screen.getByRole('button', { name: 'Cambiar usuario' })).toBeInTheDocument()
  })

  it('says «Cerrar sesión» anywhere else', () => {
    renderWithRouter(
      <AppHeader
        me={me}
        activeImport={null}
        currentPath={ROUTES.resumen}
        canPublish
        onSignedOut={() => {}}
      />,
    )
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument()
  })

  it('notifies the caller only after the server has actually ended the session', async () => {
    vi.mocked(api.logout).mockResolvedValue({ ok: true, data: undefined })
    const onSignedOut = vi.fn()
    renderWithRouter(
      <AppHeader
        me={me}
        activeImport={null}
        currentPath={ROUTES.resumen}
        canPublish
        demoMode
        onSignedOut={onSignedOut}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Cambiar usuario' }))

    expect(api.logout).toHaveBeenCalledTimes(1)
    expect(onSignedOut).toHaveBeenCalledTimes(1)
  })

  it('does not pretend the session ended when the request failed', async () => {
    vi.mocked(api.logout).mockResolvedValue({ ok: false, status: 500, error: 'boom' })
    const onSignedOut = vi.fn()
    renderWithRouter(
      <AppHeader
        me={me}
        activeImport={null}
        currentPath={ROUTES.resumen}
        canPublish
        demoMode
        onSignedOut={onSignedOut}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Cambiar usuario' }))

    expect(onSignedOut).not.toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo cerrar la sesión.')
    // The API's raw detail is never shown in the header chrome.
    expect(screen.queryByText('boom')).not.toBeInTheDocument()
  })
})

describe('NoticeBanner (TR-FUNC-042)', () => {
  it('reproduces the source’s Consulta documental wording', () => {
    render(<NoticeBanner />)
    const banner = screen.getByTestId('notice-banner')
    expect(banner).toHaveTextContent('Consulta documental:')
    expect(banner).toHaveTextContent('N.º de ingreso está asociado directamente a cada PMF')
    expect(banner).toHaveTextContent('La base no incluye un campo separado de N.º de resolución.')
  })
})

describe('QuickActions — the surviving filter presets (TR-FUNC-026/028/029/030)', () => {
  it('renders the four presets, keyed by their original type', () => {
    render(<QuickActions onQuick={() => {}} />)
    expect(QUICK_ACTIONS).toHaveLength(4)
    for (const card of QUICK_ACTIONS) {
      expect(screen.getByText(card.title)).toBeInTheDocument()
    }
  })

  it('dispatches the preset’s own type to the handler', async () => {
    const onQuick = vi.fn()
    render(<QuickActions onQuick={onQuick} />)

    await userEvent.click(screen.getByText('¿Qué expedientes tienen rechazo?'))
    expect(onQuick).toHaveBeenLastCalledWith('rejected')

    await userEvent.click(screen.getByText('¿Dónde está el principal cuello de botella?'))
    expect(onQuick).toHaveBeenLastCalledWith('legal')
  })

  it('still says what the company preset actually does, and does not', () => {
    render(<QuickActions onQuick={() => {}} />)
    expect(
      screen.getByText(/no existe todavía una tabla comparativa por empresa/),
    ).toBeInTheDocument()
  })

  it('describes the two blunt substring searches as such', () => {
    render(<QuickActions onQuick={() => {}} />)
    expect(
      screen.getByText(/Busca «rechaz» en todos los campos, no sólo en Estado/),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Busca «legal» en todos los campos, no sólo en Estado/),
    ).toBeInTheDocument()
  })
})

describe('AppHeader — the «ediciones web» pill (indicator spec §4)', () => {
  function renderHeader(activeImport: ReturnType<typeof makeActiveImport> | null, canPublish = true) {
    return renderWithRouter(
      <WebEditsContext.Provider
        value={{
          history: makeHistory({ in_force_count: 3 }),
          status: 'ready',
          refresh: vi.fn(),
          openLog: vi.fn(),
        }}
      >
        <AppHeader
          me={me}
          activeImport={activeImport}
          currentPath={ROUTES.resumen}
          canPublish={canPublish}
        />
      </WebEditsContext.Provider>,
    )
  }

  it('sits right after the version chip, for every signed-in role', () => {
    const { container } = renderHeader(makeActiveImport(), false)
    const pill = screen.getByRole('button', { name: '3 ediciones web' })
    expect(container.querySelector('.version-chip')?.nextElementSibling).toBe(pill)
  })

  it('is absent when nothing is published', () => {
    renderHeader(null)
    expect(screen.queryByTestId('edits-pill')).not.toBeInTheDocument()
  })
})
