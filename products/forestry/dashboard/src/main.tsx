import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'leaflet/dist/leaflet.css'
import './styles.css'
import './workspace.css'
import './draft.css'
import './workflow.css'
import Root from './Root.tsx'

const rootElement = document.getElementById('root')

if (rootElement === null) {
  throw new Error('missing #root element')
}

createRoot(rootElement).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
