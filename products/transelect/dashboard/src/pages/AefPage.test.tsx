import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AefPage } from './AefPage'
import { type AefPmf, type AefPmfField, EMPTY_FILTERS, type TranselecAef } from '../api'
import type { FilterController } from '../lib/useFilters'
import { ROUTES, RouterProvider } from '../router'
import { makeRow } from '../test/factories'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, getAef: vi.fn(), getPmfDetail: vi.fn() }
})

const { getAef, getPmfDetail } = await import('../api')

const controller: FilterController = {
  filters: EMPTY_FILTERS,
  draftQuery: '',
  setQuery: () => {},
  setField: () => {},
  replaceFilters: () => {},
  reset: () => {},
}

const ALL_FIELDS = ['aef', 'quien_solicita', 'fecha_solicitud', 'fecha_corta', 'fecha_termino']

const BLANK: AefPmfField = {
  status: 'blank',
  value: null,
  value_kind: null,
  source_rows: [],
  variants: [],
}

function value(text: string, rows: number[], kind: AefPmfField['value_kind'] = 'text'): AefPmfField {
  return {
    status: 'value',
    value: text,
    value_kind: kind,
    source_rows: rows,
    variants: [{ value: text, source_rows: rows }],
  }
}

function pmf(overrides: Partial<AefPmf> = {}): AefPmf {
  return {
    pmf: 'MP001',
    total_rows: 3,
    rows_with_any_tracking: 1,
    rows_with_aef: 1,
    source_row_numbers: [2, 3, 4],
    has_conflict: false,
    chronology_flags: [],
    fields: {
      aef: value('Presentado', [2]),
      quien_solicita: value('Persona A', [2]),
      fecha_solicitud: value('2026-07-03', [2], 'date'),
      fecha_corta: value('2026-07-09', [2], 'date'),
      fecha_termino: value('2026-09-01', [2], 'date'),
    },
    ...overrides,
  }
}

function aef(overrides: Partial<TranselecAef> = {}): TranselecAef {
  return {
    basis: 'pmf_from_source_rows',
    source_fields: ALL_FIELDS,
    row_count: 5,
    pmf_count: 3,
    rows_with_any_tracking: 2,
    rows_with_aef: 2,
    rows_with_quien_solicita: 1,
    rows_with_fecha_solicitud: 2,
    rows_with_fecha_corta: 2,
    rows_with_fecha_termino: 2,
    rows_with_chronology_warning: 1,
    pmf_with_tracking: 2,
    pmf_with_aef: 2,
    pmf_with_conflict: 0,
    pmf_conflicts_by_field: {},
    pmf_with_chronology_warning: 1,
    por_aef: [
      { label: 'Presentado', count: 1 },
      { label: 'Solicitado, se puede cortar', count: 1 },
    ],
    por_solicitante: [
      { label: 'Persona A', count: 1 },
      { label: null, count: 1 },
    ],
    pmf_por_aef: [
      { label: 'Presentado', count: 1 },
      { label: 'Solicitado, se puede cortar', count: 1 },
    ],
    pmf_por_solicitante: [
      { label: 'Persona A', count: 1 },
      { label: null, count: 1 },
    ],
    pmfs: [
      pmf(),
      pmf({
        pmf: 'MP002',
        total_rows: 1,
        source_row_numbers: [5],
        chronology_flags: ['cronologia_corta_antes_de_solicitud'],
        fields: {
          aef: value('Solicitado, se puede cortar', [5]),
          quien_solicita: BLANK,
          fecha_solicitud: value('2026-08-20', [5], 'date'),
          fecha_corta: value('2026-08-19', [5], 'date'),
          fecha_termino: value('2026-09-01', [5], 'date'),
        },
      }),
    ],
    rows: [
      makeRow({
        source_row_number: 2,
        pmf: 'MP001',
        aef: 'Presentado',
        quien_solicita: 'Persona A',
        fecha_solicitud: '2026-07-03',
        fecha_corta: '2026-07-09',
        fecha_termino: '2026-09-01',
      }),
      makeRow({
        source_row_number: 5,
        pmf: 'MP002',
        aef: 'Solicitado, se puede cortar',
        fecha_solicitud: '2026-08-20',
        fecha_corta: '2026-08-19',
        fecha_termino: '2026-09-01',
        chronology_flags: ['cronologia_corta_antes_de_solicitud'],
      }),
    ],
    ...overrides,
  }
}

function renderPage(sourceFields: string[] | null = ALL_FIELDS) {
  render(
    <RouterProvider initialPath={ROUTES.aef}>
      <AefPage filterController={controller} sourceFields={sourceFields} />
    </RouterProvider>,
  )
}

describe('AefPage', () => {
  beforeEach(() => {
    vi.mocked(getAef).mockReset()
    vi.mocked(getPmfDetail).mockReset()
  })

  it('shows each PMF value with the row it came from, and keeps row detail', async () => {
    vi.mocked(getAef).mockResolvedValue({ ok: true, data: aef() })
    renderPage()

    await waitFor(() => expect(screen.getByTestId('aef-kpis')).toBeInTheDocument())
    expect(screen.getByTestId('kpi-aef-pmf')).toHaveTextContent('2 de 3')
    expect(screen.getByText('Valores por PMF, con su fila de origen')).toBeInTheDocument()

    const mp001 = screen.getByTestId('aef-pmf-MP001')
    expect(mp001).toHaveTextContent('Presentado')
    expect(mp001).toHaveTextContent('fila 2')
    expect(mp001).toHaveTextContent('01-09-2026')

    const mp002 = screen.getByTestId('aef-pmf-MP002')
    expect(mp002).toHaveTextContent('Sin solicitante')
    expect(mp002).toHaveTextContent('Fecha corta anterior a la solicitud')

    // Row-level detail is still there, unchanged.
    const row = screen.getByTestId('aef-row-5')
    expect(row).toHaveTextContent('Sin solicitante')
    expect(row).toHaveTextContent('19-08-2026')
    expect(within(screen.getByTestId('aef-by-requester')).getByText('Sin solicitante')).toBeTruthy()
    expect(screen.queryByText('Valores distintos dentro de un PMF')).not.toBeInTheDocument()
  })

  it('flags a PMF whose rows disagree and never picks a value', async () => {
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: aef({
        pmf_with_conflict: 1,
        pmf_conflicts_by_field: { aef: 1 },
        pmfs: [
          pmf({
            has_conflict: true,
            fields: {
              ...pmf().fields,
              aef: {
                status: 'conflict',
                value: null,
                value_kind: null,
                source_rows: [2, 4],
                variants: [
                  { value: 'Presentado', source_rows: [2] },
                  { value: 'Solicitado, se puede cortar', source_rows: [4] },
                ],
              },
            },
          }),
        ],
      }),
    })
    renderPage()

    await waitFor(() =>
      expect(screen.getByText('Valores distintos dentro de un PMF')).toBeInTheDocument(),
    )
    const mp001 = screen.getByTestId('aef-pmf-MP001')
    expect(mp001).toHaveTextContent('Conflicto entre filas')
    expect(mp001).toHaveTextContent('Valores distintos')
    expect(mp001).toHaveTextContent('Presentadofila 2')
    expect(mp001).toHaveTextContent('Solicitado, se puede cortarfila 4')
    expect(screen.getByTestId('kpi-aef-conflicts')).toHaveTextContent('1')
  })

  it('shows unresolved text from a date column as written', async () => {
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: aef({
        pmfs: [
          pmf({
            fields: { ...pmf().fields, fecha_termino: value('-', [2], 'raw_text') },
          }),
        ],
      }),
    })
    renderPage()

    const mp001 = await screen.findByTestId('aef-pmf-MP001')
    expect(mp001).toHaveTextContent('- Texto sin fecha')
  })

  it('says the version has no AEF columns instead of reporting zero AEF rows', async () => {
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: aef({ source_fields: [], rows: [], pmfs: [], rows_with_aef: 0, rows_with_any_tracking: 0 }),
    })
    renderPage([])

    await waitFor(() =>
      expect(screen.getByText('Esta versión no incluye columnas AEF')).toBeInTheDocument(),
    )
    expect(screen.queryByTestId('aef-kpis')).not.toBeInTheDocument()
  })

  it('opens the row drawer, which points to the PMF row that holds the value', async () => {
    vi.mocked(getAef).mockResolvedValue({ ok: true, data: aef() })
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: 'MP002',
        row_count: 2,
        basis_estado_resumido: 'estado_resumido_first_row',
        estado_resumido: 'Aprobado',
        rows: [
          makeRow({ source_row_number: 5, pmf: 'MP002', aef: 'Solicitado, se puede cortar' }),
          makeRow({ source_row_number: 6, pmf: 'MP002', aef: null }),
        ],
      },
    })
    renderPage()

    await waitFor(() => expect(screen.getByTestId('aef-row-5')).toBeInTheDocument())
    await userEvent.click(screen.getByTestId('aef-row-5'))

    const drawer = await screen.findByTestId('drawer-aef')
    expect(drawer).toHaveTextContent('Fechas a revisar en la planilla')
    expect(drawer).toHaveTextContent('Quién solicitaSin registro en esta fila')
    await waitFor(() =>
      expect(screen.getByTestId('drawer-aef-coverage')).toHaveTextContent(
        '1 de 2 filas de MP002 tienen registro AEF.',
      ),
    )
  })
})
