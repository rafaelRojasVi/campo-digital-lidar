/**
 * Minimal history-based router.
 *
 * Same shape as apps/portal/src/router/Router.tsx — this platform's frontends
 * deliberately do not carry a routing library for a handful of static routes.
 *
 * What changed in the UX rearchitecture: the router now owns the *search*
 * string as well as the pathname. The dashboard's filter state lives in the
 * URL (see lib/filterUrl.ts), so a filtered view is linkable, survives a
 * reload, and is carried between the four reading sections from one source of
 * truth rather than from four copies of component state.
 *
 * `/transelec/importar` and `/transelec/versiones` are kept as live routes
 * that resolve into the Datos section's two panes, so every link, bookmark
 * and test navigation that predates the rearchitecture still lands correctly.
 */
import type { ReactNode } from 'react'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

export const ROUTES = {
  resumen: '/transelec',
  explorador: '/transelec/explorador',
  pendientes: '/transelec/pendientes',
  aef: '/transelec/seguimiento-aef',
  calidad: '/transelec/calidad',
  datos: '/transelec/datos',
  importar: '/transelec/importar',
  versiones: '/transelec/versiones',
  accesos: '/transelec/accesos',
} as const

export type Route = (typeof ROUTES)[keyof typeof ROUTES]

/** The routes only an operator or administrator may open. */
export const ADMIN_ROUTES: readonly Route[] = [
  ROUTES.datos,
  ROUTES.importar,
  ROUTES.versiones,
  ROUTES.accesos,
]

interface RouterContextValue {
  pathname: string
  search: string
  navigate: (path: string, options?: { replace?: boolean }) => void
}

const RouterContext = createContext<RouterContextValue | undefined>(undefined)

function splitLocation(value: string): { pathname: string; search: string } {
  const index = value.indexOf('?')
  if (index === -1) return { pathname: value, search: '' }
  return { pathname: value.slice(0, index), search: value.slice(index) }
}

export function RouterProvider({
  children,
  initialPath,
}: {
  children: ReactNode
  initialPath?: string
}) {
  const [location, setLocation] = useState(() =>
    initialPath !== undefined
      ? splitLocation(initialPath)
      : { pathname: window.location.pathname, search: window.location.search },
  )

  useEffect(() => {
    const onPopState = () =>
      setLocation({ pathname: window.location.pathname, search: window.location.search })
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((path: string, options?: { replace?: boolean }) => {
    const next = splitLocation(path)
    const current = `${window.location.pathname}${window.location.search}`

    if (path !== current) {
      // A filter change is a replace, not a push: typing six characters into
      // the search box must not bury the previous page under six history
      // entries the reader has to press Back through.
      if (options?.replace) window.history.replaceState({}, '', path)
      else window.history.pushState({}, '', path)
    }

    setLocation((previous) =>
      previous.pathname === next.pathname && previous.search === next.search ? previous : next,
    )

    // Only a real section change returns to the top. A filter change leaves
    // the reader where they were looking.
    if (!options?.replace) window.scrollTo({ top: 0 })
  }, [])

  const value = useMemo<RouterContextValue>(
    () => ({ pathname: location.pathname, search: location.search, navigate }),
    [location.pathname, location.search, navigate],
  )

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterContextValue {
  const context = useContext(RouterContext)
  if (!context) throw new Error('useRouter must be used inside a RouterProvider')
  return context
}

/**
 * `data-*` attributes reach the anchor.
 *
 * Without this, TypeScript silently accepts a hyphenated attribute on a
 * component and React then drops it, so `<Link data-tone="late">` compiles,
 * renders, and styles nothing — which is exactly what had happened to the
 * Resumen's attention cards: every `.attention-card[data-tone=...]` rule in
 * the stylesheet had no element to match.
 */
interface LinkProps {
  to: string
  children: ReactNode
  className?: string
  current?: boolean
  onNavigate?: () => void
  [dataAttribute: `data-${string}`]: string | undefined | ReactNode | boolean | (() => void)
}

export function Link({ to, children, className, current, onNavigate, ...rest }: LinkProps) {
  const { navigate } = useRouter()
  return (
    <a
      {...(rest as Record<`data-${string}`, string | undefined>)}
      href={to}
      className={className}
      aria-current={current ? 'page' : undefined}
      onClick={(event) => {
        // Cmd/Ctrl/Shift click and middle click keep their native meaning:
        // these are real anchors with real hrefs, not div handlers.
        if (event.metaKey || event.ctrlKey || event.shiftKey) return
        event.preventDefault()
        navigate(to)
        onNavigate?.()
      }}
    >
      {children}
    </a>
  )
}

/** Normalize a pathname (trailing slash tolerant) to one of the routes. */
export function resolveRoute(pathname: string): Route {
  const normalized = pathname.replace(/\/+$/, '') || '/'
  for (const route of Object.values(ROUTES)) {
    if (normalized === route) return route
  }
  return ROUTES.resumen
}

/** True when this route belongs to the operator-only Datos section. */
export function isAdminRoute(route: Route): boolean {
  return ADMIN_ROUTES.includes(route)
}
