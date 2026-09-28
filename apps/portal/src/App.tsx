import { RouterProvider, useRouter } from './router/Router'
import { Home } from './pages/Home'
import { Archivos } from './pages/Archivos'
import { ModulePage } from './pages/Module'
import { Estado } from './pages/Estado'

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
  return (
    <RouterProvider>
      <Routes />
    </RouterProvider>
  )
}
