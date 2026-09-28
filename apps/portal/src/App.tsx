import { RouterProvider, useRouter } from './router/Router'
import { Home } from './pages/Home'
import { Archivos } from './pages/Archivos'
import { ModulePage } from './pages/Module'
import { Estado } from './pages/Estado'
import { FrontDoor } from './pages/FrontDoor'
import { getCampoEnvironment } from './runtime/environment'

function Routes() {
  const { pathname } = useRouter()

  if (pathname === '/estado') {
    return <Estado />
  }

  if (pathname === '/archivos') {
    return <Archivos />
  }

  if (pathname.startsWith('/modulo/')) {
    const moduleId = pathname.slice('/modulo/'.length).split('/')[0]
    return <ModulePage moduleId={moduleId} />
  }

  return <Home />
}

export default function App() {
  // The unified platform's front door: sign-in and the project picker only.
  // The module pages, /estado and /archivos belong to the local and staging
  // demo portal.
  if (getCampoEnvironment() === 'production') {
    return <FrontDoor />
  }

  return (
    <RouterProvider>
      <Routes />
    </RouterProvider>
  )
}
