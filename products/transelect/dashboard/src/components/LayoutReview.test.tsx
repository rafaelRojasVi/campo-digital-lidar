import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LayoutReview } from './LayoutReview'
import type { LayoutIssue, LayoutReport } from '../api'

function report(issues: LayoutIssue[]): LayoutReport {
  return {
    parser_version: 'transelec_ingestion.resumen_layout@2',
    sheet_name: 'Resumen',
    header_row: 1,
    business_rows: 729,
    columns: [],
    fields: [],
    auxiliary_regions: [],
    issues,
    counts: { error: 0, warning: issues.length, info: 0 },
  }
}

const rows = Array.from({ length: 58 }, (_, index) => index + 10)

describe('LayoutReview', () => {
  it('lists every affected row of a long text-date issue behind a toggle', () => {
    render(
      <LayoutReview
        report={report([
          {
            code: 'fecha_texto_multiple',
            severity: 'warning',
            message: '«Fecha de ingreso» tiene 58 celdas con más de una fecha en el mismo texto.',
            field: 'fecha_ingreso',
            columns: ['Y'],
            rows,
            row_count: 58,
          },
          {
            code: 'aef_conflicto_pmf',
            severity: 'warning',
            message: '«AEF»: 1 PMF tienen valores distintos en sus filas.',
            field: 'aef',
            columns: ['A'],
            rows: [2, 4],
            row_count: 2,
          },
        ])}
      />,
    )

    const toggle = screen.getByTestId('issue-rows')
    expect(toggle).toHaveTextContent('58 filas — ver todas')
    expect(toggle).toHaveTextContent(rows.join(', '))
    const warnings = screen.getByTestId('layout-warnings')
    expect(within(warnings).getByText('Columna A · Filas 2, 4')).toBeInTheDocument()
  })
})
