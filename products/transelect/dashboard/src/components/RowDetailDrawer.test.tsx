import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RowDetailDrawer } from './RowDetailDrawer'
import { makeRow } from '../test/factories'
import type { AefPmf, AefPmfField, TranselecAef } from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, getPmfDetail: vi.fn(), getAef: vi.fn() }
})

const { getPmfDetail, getAef } = await import('../api')

const tracked = makeRow({ source_row_number: 2, pmf: 'BN001', aef: 'Presentado' })
const untracked = makeRow({ source_row_number: 3, pmf: 'BN001' })
const blank: AefPmfField = {
  status: 'blank', value: null, value_kind: null, source_rows: [], variants: [],
}
const pmfTracking: AefPmf = {
  pmf: 'BN001',
  total_rows: 2,
  rows_with_any_tracking: 1,
  rows_with_aef: 1,
  source_row_numbers: [2, 3],
  has_conflict: false,
  chronology_flags: [],
  fields: {
    aef: {
      status: 'value',
      value: 'Presentado',
      value_kind: 'text',
      source_rows: [2],
      variants: [],
    },
    quien_solicita: blank,
    fecha_solicitud: blank,
    fecha_corta: blank,
    fecha_termino: blank,
  },
}

describe('RowDetailDrawer — AEF section', () => {
  beforeEach(() => {
    vi.mocked(getPmfDetail).mockReset()
    vi.mocked(getAef).mockReset()
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: { pmfs: [pmfTracking] } as unknown as TranselecAef,
    })
    vi.mocked(getPmfDetail).mockResolvedValue({
      ok: true,
      data: {
        pmf: 'BN001',
        row_count: 2,
        basis_estado_resumido: 'estado_resumido_first_row',
        estado_resumido: 'Aprobado',
        rows: [tracked, untracked],
      },
    })
  })

  it('shows a blank row as blank and points to the PMF row that holds the value', async () => {
    render(
      <RowDetailDrawer row={untracked} onClose={() => {}} sourceFields={['aef', 'pmf']} />,
    )

    expect(screen.getByTestId('drawer-aef')).toHaveTextContent('AEF de esta fila de origen')
    expect(screen.getByTestId('drawer-aef')).toHaveTextContent('AEFSin registro en esta fila')
    await waitFor(() =>
      expect(screen.getByTestId('drawer-pmf-aef-rows')).toHaveTextContent(
        'Todos los valores de este PMF vienen de la fila 2 de la hoja «Resumen».',
      ),
    )
    expect(screen.getByTestId('drawer-pmf-aef')).toHaveTextContent('AEFPresentado')
    expect(screen.getByTestId('drawer-pmf-aef')).not.toHaveTextContent('· fila')
    await waitFor(() =>
      expect(screen.getByTestId('drawer-aef-coverage')).toHaveTextContent(
        '1 de 2 filas de BN001 tienen registro AEF. El seguimiento de este PMF está en la fila 2; esta fila no lo repite y se muestra vacía, como en la planilla.',
      ),
    )
  })

  it('names each value\'s source row when the PMF\'s values come from different rows', async () => {
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: {
        pmfs: [{
          ...pmfTracking,
          fields: {
            ...pmfTracking.fields,
            quien_solicita: {
              status: 'value',
              value: 'Persona Sintética',
              value_kind: 'text',
              source_rows: [3],
              variants: [],
            },
          },
        }],
      } as unknown as TranselecAef,
    })
    render(<RowDetailDrawer row={untracked} onClose={() => {}} sourceFields={['aef', 'pmf']} />)
    await waitFor(() =>
      expect(screen.getByTestId('drawer-pmf-aef')).toHaveTextContent('AEFPresentadofila 2'),
    )
    expect(screen.getByTestId('drawer-pmf-aef')).toHaveTextContent('Persona Sintéticafila 3')
    expect(screen.queryByTestId('drawer-pmf-aef-rows')).not.toBeInTheDocument()
  })

  it('says the published workbook has no AEF columns rather than implying blanks', () => {
    render(<RowDetailDrawer row={untracked} onClose={() => {}} sourceFields={['pmf']} />)

    expect(screen.getByTestId('drawer-aef')).toHaveTextContent(
      'La planilla publicada no incluye las columnas de seguimiento AEF',
    )
    expect(screen.queryByText('Sin registro en esta fila')).not.toBeInTheDocument()
    expect(screen.queryByTestId('drawer-pmf-aef')).not.toBeInTheDocument()
    expect(getAef).not.toHaveBeenCalled()
  })

  it('does not choose between conflicting PMF AEF values', async () => {
    vi.mocked(getAef).mockResolvedValue({
      ok: true,
      data: {
        pmfs: [{
          ...pmfTracking,
          has_conflict: true,
          fields: {
            ...pmfTracking.fields,
            aef: {
              status: 'conflict',
              value: null,
              value_kind: null,
              source_rows: [],
              variants: [
                { value: 'Presentado', source_rows: [2] },
                { value: 'Solicitado', source_rows: [3] },
              ],
            },
          },
        }],
      } as unknown as TranselecAef,
    })
    render(<RowDetailDrawer row={untracked} onClose={() => {}} sourceFields={['aef', 'pmf']} />)
    await waitFor(() =>
      expect(screen.getByTestId('drawer-pmf-aef')).toHaveTextContent(
        'Valores distintos; requiere revisión',
      ),
    )
    expect(screen.getByTestId('drawer-pmf-aef')).toHaveTextContent('Presentado · fila 2')
    expect(screen.getByTestId('drawer-pmf-aef')).toHaveTextContent('Solicitado · fila 3')
    expect(screen.getByTestId('drawer-aef')).toHaveTextContent('Sin registro en esta fila')
  })

  it('shows the raw text of a date cell, and marks unresolved text as not a date', () => {
    const row = makeRow({
      source_row_number: 4,
      pmf: 'BN001',
      fecha_ingreso: '2024-11-13',
      fecha_90_dias: null,
      source_text_dates: {
        fecha_ingreso: {
          raw: '13 de noviembre de 2024',
          resolution: 'parsed_spanish_long',
          parsed: '2024-11-13',
        },
        fecha_90_dias: {
          raw: '28-04-2025 28-09-26',
          resolution: 'multiple_dates',
          parsed: null,
        },
      },
    })
    render(<RowDetailDrawer row={row} onClose={() => {}} sourceFields={['aef', 'pmf']} />)

    expect(
      screen.getByText('Fecha escrita en texto: «13 de noviembre de 2024»'),
    ).toBeInTheDocument()
    expect(screen.getByText('13-11-2024', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('28-04-2025 28-09-26')).toBeInTheDocument()
    expect(screen.getByText('Varias fechas en la celda')).toBeInTheDocument()
  })
})
