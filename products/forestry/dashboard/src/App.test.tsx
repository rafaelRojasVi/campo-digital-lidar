import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App.tsx'
import { ApiError, NoSnapshotError } from './api.ts'
import {
  testCollection,
  testComparison,
  testDetail,
  testSnapshot,
  testSummary,
} from './test/fixtures.ts'
import type { GeoFeature } from './types.ts'

// Leaflet needs a real canvas/layout engine; the map component is exercised
// in browser QA. Here it is replaced by a stub that exposes the same
// synchronization surface (filtered features in, selection out).
vi.mock('./components/MapView.tsx', () => ({
  MapView: ({
    filteredFeatures,
    onSelect,
  }: {
    filteredFeatures: GeoFeature[]
    onSelect: (ordinal: number | null) => void
  }) => (
    <div data-testid="map-stub">
      <p>Mapa: {filteredFeatures.length} visibles</p>
      {filteredFeatures.map((feature) => (
        <button
          key={feature.properties.feature_ordinal}
          type="button"
          onClick={() => onSelect(feature.properties.feature_ordinal)}
        >
          mapa-seleccionar-{feature.properties.feature_ordinal}
        </button>
      ))}
    </div>
  ),
}))

vi.mock('./api.ts', async (importOriginal) => {
  const original = await importOriginal<typeof import('./api.ts')>()
  return {
    ...original,
    fetchLatestIngestedSnapshot: vi.fn(),
    fetchSnapshotSummary: vi.fn(),
    fetchFeatureCollection: vi.fn(),
    fetchComparison: vi.fn(),
    fetchFeatureDetail: vi.fn(),
  }
})

const api = vi.mocked(await import('./api.ts'))

function mockHappyApi() {
  api.fetchLatestIngestedSnapshot.mockResolvedValue(testSnapshot())
  api.fetchSnapshotSummary.mockResolvedValue(testSummary())
  api.fetchFeatureCollection.mockResolvedValue(testCollection())
  api.fetchComparison.mockResolvedValue(testComparison())
  api.fetchFeatureDetail.mockImplementation((_snapshotId, featureOrdinal) =>
    Promise.resolve(testDetail(featureOrdinal)),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('loading and failure states', () => {
  it('shows the loading state before data arrives', async () => {
    api.fetchLatestIngestedSnapshot.mockReturnValue(new Promise(() => {}))

    render(<App />)

    expect(screen.getByText(/Conectando con la API/)).toBeInTheDocument()
  })

  it('shows the no-source state when no snapshot is persisted', async () => {
    api.fetchLatestIngestedSnapshot.mockRejectedValue(new NoSnapshotError())

    render(<App />)

    expect(await screen.findByText('Sin datos de origen')).toBeInTheDocument()
    expect(screen.getByText(/make forestry-dev/)).toBeInTheDocument()
  })

  it('shows the API-unavailable state and retries successfully', async () => {
    const user = userEvent.setup()
    api.fetchLatestIngestedSnapshot.mockRejectedValueOnce(new ApiError(0, 'network unreachable'))

    render(<App />)

    expect(await screen.findByText('API no disponible')).toBeInTheDocument()

    mockHappyApi()
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))

    expect(await screen.findByText('Patrimonio Degenfeld')).toBeInTheDocument()
  })
})

describe('ready application', () => {
  beforeEach(() => {
    mockHappyApi()
  })

  it('renders provenance and factual KPIs', async () => {
    render(<App />)

    expect(await screen.findByText('Patrimonio Degenfeld')).toBeInTheDocument()

    // Provenance is labeled as ingestion order, never as official currency.
    expect(screen.getByText('Última ingesta')).toBeInTheDocument()
    expect(screen.getByText('Gdb_Test_mv')).toBeInTheDocument()
    expect(screen.getByText('EPSG:32718')).toBeInTheDocument()

    const kpis = screen.getByLabelText('Resumen factual de la instantánea')
    expect(within(kpis).getByText('Polígonos de origen')).toBeInTheDocument()
    expect(within(kpis).getByText('27,10 ha')).toBeInTheDocument()
    expect(within(kpis).getByText('Geometrías inválidas')).toBeInTheDocument()
  })

  it('filters by uso 2026 and keeps map and table synchronized', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    await user.selectOptions(screen.getByLabelText('Uso 2026'), 'BOSQUE NATIVO')

    expect(screen.getByText('Mapa: 1 visibles')).toBeInTheDocument()
    expect(screen.getByText(/1 polígono ·/)).toBeInTheDocument()

    const table = screen.getByRole('table')
    expect(within(table).getByText('San Sebastian')).toBeInTheDocument()
    expect(within(table).queryByText('Lumaco')).not.toBeInTheDocument()
  })

  it('searches accent-insensitively', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    await user.type(screen.getByLabelText('Buscar'), 'vegetacion')

    expect(screen.getByText('Mapa: 1 visibles')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('Lumaco')).toBeInTheDocument()
  })

  it('shows the empty-results state and can clear filters', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    await user.type(screen.getByLabelText('Buscar'), 'noexiste')

    expect(screen.getByText('Sin resultados para los filtros actuales.')).toBeInTheDocument()
    expect(screen.getByText('Mapa: 0 visibles')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Limpiar filtros/ }))
    expect(screen.getByText('Mapa: 6 visibles')).toBeInTheDocument()
  })

  it('opens the inspector from a map selection with full source evidence', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    await user.click(screen.getByRole('button', { name: 'mapa-seleccionar-5' }))

    const inspector = await screen.findByLabelText('Detalle del polígono seleccionado')
    expect(within(inspector).getByText('OBJECTID (evidencia de fuente)')).toBeInTheDocument()
    expect(within(inspector).getByText('105')).toBeInTheDocument()
    expect(within(inspector).getByText('Inválida')).toBeInTheDocument()
    expect(
      await within(inspector).findByText('Self-intersection[620000 5490000]'),
    ).toBeInTheDocument()
    expect(within(inspector).getByText('Código de uso 2026 truncado')).toBeInTheDocument()

    // Full source attribute row behind progressive disclosure.
    await user.click(
      within(inspector).getByRole('button', { name: /Atributos originales/ }),
    )
    expect(within(inspector).getByText('Editada')).toBeInTheDocument()

    await user.click(within(inspector).getByRole('button', { name: 'Cerrar detalle' }))
    expect(
      screen.queryByLabelText('Detalle del polígono seleccionado'),
    ).not.toBeInTheDocument()
  })

  it('selects a polygon from a table row', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    await user.click(within(screen.getByRole('table')).getByText('Purretrun'))

    const inspector = await screen.findByLabelText('Detalle del polígono seleccionado')
    expect(within(inspector).getByText('Anomalía código/nombre de predio')).toBeInTheDocument()
  })

  it('shows the literal 2024 vs 2026 comparison and filters the map from it', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    await user.click(screen.getByRole('tab', { name: /2024 → 2026/ }))

    expect(
      screen.getByText(/Diferencias literales entre los campos 2024 y 2026/),
    ).toBeInTheDocument()
    expect(screen.getByText('ENSAYO')).toBeInTheDocument()

    const pairs = screen.getByLabelText('Pares de valores más frecuentes')
    expect(within(pairs).getByText('En11')).toBeInTheDocument()

    await user.click(
      screen.getByRole('button', { name: 'Filtrar mapa: solo con diferencia' }),
    )
    expect(screen.getByText('Mapa: 2 visibles')).toBeInTheDocument()
  })

  it('surfaces quality evidence with counts and map filtering', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    await user.click(screen.getByRole('tab', { name: 'Calidad de datos' }))

    expect(screen.getByText(/Evidencia de calidad de datos observada/)).toBeInTheDocument()
    expect(screen.getByText('Rodal en blanco')).toBeInTheDocument()

    const blankRodalCard = screen
      .getByText('Rodal en blanco')
      .closest('li') as HTMLElement
    await user.click(within(blankRodalCard).getByRole('button', { name: 'Ver en el mapa' }))

    expect(screen.getByText('Mapa: 1 visibles')).toBeInTheDocument()
  })

  it('filters from a legend entry click', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    const legend = screen.getByLabelText('Leyenda del mapa')
    await user.click(within(legend).getByRole('button', { name: /BOSQUE NATIVO/ }))

    expect(screen.getByText('Mapa: 1 visibles')).toBeInTheDocument()

    // Clicking again clears the filter.
    await user.click(within(legend).getByRole('button', { name: /BOSQUE NATIVO/ }))
    expect(screen.getByText('Mapa: 6 visibles')).toBeInTheDocument()
  })

  it('switches the color dimension and updates the legend', async () => {
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Patrimonio Degenfeld')

    await user.selectOptions(
      screen.getByLabelText('Colorear por'),
      'Comparación 2024 → 2026',
    )

    const legend = screen.getByLabelText('Leyenda del mapa')
    expect(within(legend).getByText('Campos 2024/2026 distintos')).toBeInTheDocument()
    expect(
      within(legend).getByText(/no representan avance ni gestión realizada/),
    ).toBeInTheDocument()
  })
})
