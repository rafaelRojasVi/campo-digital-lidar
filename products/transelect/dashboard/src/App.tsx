import { useCallback, useEffect, useState } from 'react'
import {
  type ApiResult,
  type Me,
  type TranselecActiveImport,
  canPublish as canPublishFor,
  getActiveImport,
  getMe,
  isTranselecAdmin,
} from './api'
import { AppHeader } from './components/AppHeader'
import { LoginCard } from './components/LoginCard'
import { LoadingBlock, StateBlock } from './components/StateViews'
import { classifyFailure, type ApiFailure } from './lib/apiState'
import { useFilters } from './lib/useFilters'
import { CalidadPage } from './pages/CalidadPage'
import { DatosPage } from './pages/DatosPage'
import { ExploradorPage } from './pages/ExploradorPage'
import { AefPage } from './pages/AefPage'
import { PendientesPage } from './pages/PendientesPage'
import { ResumenPage } from './pages/ResumenPage'
import { ROUTES, RouterProvider, isAdminRoute, resolveRoute, useRouter } from './router'
import { demoSignInAvailable } from './runtime/environment'

function Shell() {
  const { pathname } = useRouter()
  const route = resolveRoute(pathname)

  // One filter state for the whole application, read from and written to the
  // URL. Held here rather than per page so moving between sections carries
  // the current scope instead of silently resetting it.
  const filterController = useFilters()

  const [me, setMe] = useState<Me | null>(null)
  const [sessionFailure, setSessionFailure] = useState<ApiFailure | null>(null)
  const [sessionLoading, setSessionLoading] = useState(true)

  const [activeImport, setActiveImport] = useState<TranselecActiveImport | null>(null)
  const [provenanceVersion, setProvenanceVersion] = useState(0)

  /**
   * Adopt whatever `GET /auth/me` now says — the one place session state is
   * written, so the mount path and the sign-in/sign-out path cannot drift.
   *
   * `GET /auth/me` stays the only source of truth: nothing is inferred from
   * the body of a login call, so a session that did not actually take can
   * never render as one that did.
   */
  const adoptSession = useCallback((result: ApiResult<Me>) => {
    if (result.ok) {
      setMe(result.data)
      setSessionFailure(null)
    } else {
      setMe(null)
      setSessionFailure({ status: result.status, error: result.error })
    }
    setSessionLoading(false)
  }, [])

  useEffect(() => {
    let cancelled = false
    void getMe().then((result) => {
      if (cancelled) return
      adoptSession(result)
    })
    return () => {
      cancelled = true
    }
  }, [adoptSession])

  /**
   * Re-read the session, showing "Verificando la sesión…" while it is in
   * flight. This is what the sign-in and sign-out handlers call, and it is
   * why switching identity needs no browser reload: the previous answer is
   * stale the moment either happens, and continuing to render it would be a
   * lie. The mount effect deliberately does not go through here — it already
   * starts in that state, and it alone needs the unmount guard.
   */
  const refreshSession = useCallback(async () => {
    setSessionLoading(true)
    adoptSession(await getMe())
  }, [adoptSession])

  /**
   * Called once `POST /auth/logout` has already succeeded. The local state is
   * cleared first so no frame can show the previous user's name or version
   * stamp, then the session is re-read to establish the real new state.
   */
  const onSignedOut = useCallback(() => {
    setMe(null)
    setActiveImport(null)
    void refreshSession()
  }, [refreshSession])

  // Active-version provenance: refetched whenever a publish or restore in
  // this session changes which import is active, so the shell's version chip
  // and the Datos provenance never show a version that is no longer live.
  // Gated on a confirmed session so an unauthenticated visitor produces
  // exactly one 401 (the session check itself) rather than a burst of them.
  useEffect(() => {
    if (!me) {
      setActiveImport(null)
      return
    }
    let cancelled = false
    void getActiveImport().then((result) => {
      if (cancelled) return
      setActiveImport(result.ok ? result.data : null)
    })
    return () => {
      cancelled = true
    }
  }, [me, provenanceVersion])

  const onActiveVersionChanged = useCallback(() => {
    setProvenanceVersion((value) => value + 1)
  }, [])

  const publisher = canPublishFor(me)

  const body = () => {
    if (sessionLoading) {
      return (
        <div className="page">
          <LoadingBlock label="Verificando la sesión…" lines={2} />
        </div>
      )
    }

    // 401 is not an error to report, it is the signed-out state: it gets the
    // sign-in screen. Every other session failure (an unreachable platform,
    // for instance) is still a real failure and keeps its own block, so a
    // backend outage is never mistaken for "please sign in".
    if (sessionFailure?.status === 401) {
      return <LoginCard demoAvailable={demoSignInAvailable()} onSignedIn={refreshSession} />
    }

    if (sessionFailure) {
      return (
        <div className="page">
          <StateBlock view={classifyFailure(sessionFailure)} />
        </div>
      )
    }

    if (isAdminRoute(route) && !publisher) {
      return (
        <div className="page">
          <StateBlock
            view={{
              kind: 'forbidden',
              title: 'Sin autorización',
              message:
                'Sólo las cuentas con rol de operador o administrador sobre Transelec pueden importar planillas o cambiar la versión publicada. Su cuenta puede consultar el panel.',
            }}
          />
        </div>
      )
    }

    switch (route) {
      case ROUTES.explorador:
        return (
          <ExploradorPage
            filterController={filterController}
            activeImportId={activeImport?.import_id ?? null}
            sourceFields={activeImport?.source_fields ?? null}
          />
        )
      case ROUTES.pendientes:
        return (
          <PendientesPage
            filterController={filterController}
            sourceFields={activeImport?.source_fields ?? null}
          />
        )
      case ROUTES.aef:
        return (
          <AefPage
            filterController={filterController}
            sourceFields={activeImport?.source_fields ?? null}
          />
        )
      case ROUTES.calidad:
        return <CalidadPage filterController={filterController} />
      case ROUTES.datos:
      case ROUTES.importar:
      case ROUTES.versiones:
      case ROUTES.accesos:
        return (
          <DatosPage
            route={route}
            activeImport={activeImport}
            onActiveVersionChanged={onActiveVersionChanged}
            isAdmin={isTranselecAdmin(me)}
          />
        )
      default:
        return (
          <ResumenPage
            activeImport={activeImport}
            canPublish={publisher}
            filterController={filterController}
          />
        )
    }
  }

  return (
    <>
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>
      <AppHeader
        me={me}
        activeImport={activeImport}
        currentPath={route}
        canPublish={publisher}
        demoMode={demoSignInAvailable()}
        onSignedOut={onSignedOut}
      />
      <main id="contenido">{body()}</main>
    </>
  )
}

export default function App({ initialPath }: { initialPath?: string } = {}) {
  return (
    <RouterProvider initialPath={initialPath}>
      <Shell />
    </RouterProvider>
  )
}
