import type { ReactNode } from 'react'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'

interface RouterContextValue {
  pathname: string
  navigate: (path: string) => void
}

const RouterContext = createContext<RouterContextValue | undefined>(undefined)

export function RouterProvider({ children }: { children: ReactNode }) {
  const [pathname, setPathname] = useState(() => window.location.pathname)

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = (path: string) => {
    if (path !== window.location.pathname) {
      window.history.pushState({}, '', path)
    }
    setPathname(path)
  }

  const value = useMemo(() => ({ pathname, navigate }), [pathname])

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter(): RouterContextValue {
  const context = useContext(RouterContext)
  if (!context) {
    throw new Error('useRouter must be used inside a RouterProvider')
  }
  return context
}

export function Link({
  to,
  children,
  className,
}: {
  to: string
  children: ReactNode
  className?: string
}) {
  const { navigate } = useRouter()

  return (
    <a
      href={to}
      className={className}
      onClick={(event) => {
        event.preventDefault()
        navigate(to)
      }}
    >
      {children}
    </a>
  )
}
