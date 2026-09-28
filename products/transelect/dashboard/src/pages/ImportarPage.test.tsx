import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ImportarPage } from './ImportarPage'
import { ROUTES, RouterProvider } from '../router'
import type { LayoutReport, ValidateAndProjectResult } from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    uploadWorkbook: vi.fn(),
    listRecentUploads: vi.fn(),
    validateAndProject: vi.fn(),
    publishImport: vi.fn(),
  }
})

const { listRecentUploads, publishImport, uploadWorkbook, validateAndProject } = await import(
  '../api'
)

const uploadOk = {
  ok: true as const,
  data: {
    source_snapshot_id: 195,
    sha256: '82ba5eaed0b1a110b5966b301ca4a0bcbd3588ad5b8db7ba50d911b320af1851',
    byte_size: 5710,
    validation_evidence: { sheet_names: ['Resumen'], resumen_row_count: 7, contract_error: null },
    job_id: 83,
  },
}

const runsOk = {
  ok: true as const,
  data: [
    {
      ingestion_run_id: 41,
      source_snapshot_id: 195,
      filename: 'resumen.xlsx',
      sha256: '82ba',
      requested_by_app_user_id: 3,
      created_at: '2026-09-02T21:08:00+00:00',
      import_id: null,
      is_active: false,
    },
  ],
}

function validated(overrides: Partial<ValidateAndProjectResult> = {}) {
  return {
    ok: true as const,
    data: {
      status: 'validated' as const,
      import_id: 83,
      source_snapshot_id: 195,
      ingestion_run_id: 41,
      schema_contract_version: 'transelec-resumen-v1',
      parser_version: 'transelec_ingestion.xlsx_contract@1',
      business_rows: 7,
      distinct_pmf: 6,
      distinct_provisional_predio_ids: 1,
      surface_total: 32.5,
      validated_at: '2026-09-02T21:09:40+00:00',
      is_active: false,
      warning_count: 0,
      mapping_report: null,
      ...overrides,
    },
  }
}

function renderPage(onChanged = vi.fn()) {
  render(
    <RouterProvider initialPath={ROUTES.importar}>
      <ImportarPage onActiveVersionChanged={onChanged} />
    </RouterProvider>,
  )
  return onChanged
}

async function selectAndSubmit() {
  const file = new File(['workbook'], 'resumen.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  await userEvent.upload(screen.getByLabelText('Planilla maestra (.xlsx)'), file)
  await userEvent.click(screen.getByTestId('upload-submit'))
}

describe('ImportarPage (TR-FUNC-040, redesigned)', () => {
  beforeEach(() => {
    vi.mocked(uploadWorkbook).mockReset()
    vi.mocked(listRecentUploads).mockReset()
    vi.mocked(validateAndProject).mockReset()
    vi.mocked(publishImport).mockReset()
  })

  it('shows the three pipeline steps and does not publish as a side effect of validating', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(validated())

    renderPage()
    await selectAndSubmit()

    await waitFor(() => expect(screen.getByTestId('validation-result')).toBeInTheDocument())
    expect(screen.getByText('Planilla validada')).toBeInTheDocument()
    expect(screen.getByText(/Todavía no está publicada/)).toBeInTheDocument()
    expect(publishImport).not.toHaveBeenCalled()
  })

  it('resolves the ingestion run id from the upload’s snapshot id before validating', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(validated())

    renderPage()
    await selectAndSubmit()

    await waitFor(() => expect(validateAndProject).toHaveBeenCalledWith(41))
  })

  it('requires an explicit confirmation before publishing, and can be cancelled', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(validated())

    renderPage()
    await selectAndSubmit()
    await waitFor(() => expect(screen.getByTestId('publish-open')).toBeInTheDocument())

    await userEvent.click(screen.getByTestId('publish-open'))
    expect(screen.getByRole('dialog')).toHaveTextContent('la importación #83 sea la versión activa')

    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(publishImport).not.toHaveBeenCalled()
  })

  it('publishes after confirmation and reports which version it replaced', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(validated())
    vi.mocked(publishImport).mockResolvedValue({
      ok: true,
      data: {
        status: 'published',
        event_type: 'publish',
        import_id: 83,
        previous_import_id: 12,
        publish_event_id: 29,
        occurred_at: '2026-09-02T21:10:00+00:00',
        active_import_id: 83,
      },
    })

    const onChanged = renderPage()
    await selectAndSubmit()
    await waitFor(() => expect(screen.getByTestId('publish-open')).toBeInTheDocument())
    await userEvent.click(screen.getByTestId('publish-open'))
    await userEvent.click(screen.getByTestId('confirm-accept'))

    await waitFor(() => expect(screen.getByTestId('publish-result')).toBeInTheDocument())
    expect(publishImport).toHaveBeenCalledWith(83, { acknowledgeWarnings: false })
    expect(screen.getByText(/Reemplaza a la versión #12/)).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it('shows the invalid-upload state with the API’s generic Spanish copy and no technical detail', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue({
      ok: false,
      status: 422,
      error: 'La planilla no cumple el contrato de origen esperado. Contacte a soporte.',
    })

    renderPage()
    await selectAndSubmit()

    await waitFor(() => expect(screen.getByTestId('import-failure')).toBeInTheDocument())
    expect(screen.getByText('Planilla no válida')).toBeInTheDocument()
    expect(
      screen.getByText('La planilla no cumple el contrato de origen esperado. Contacte a soporte.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/La versión publicada actualmente no ha cambiado/)).toBeInTheDocument()
    expect(screen.queryByTestId('validation-result')).not.toBeInTheDocument()
  })

  it('shows the import-failed state and states the active version is unchanged', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue({
      ok: false,
      status: 500,
      error: 'No se pudo verificar la importación. La versión activa no cambió.',
    })

    renderPage()
    await selectAndSubmit()

    await waitFor(() => expect(screen.getByTestId('import-failure')).toBeInTheDocument())
    expect(screen.getByText('La importación no se completó')).toBeInTheDocument()
    expect(screen.getByText(/La versión activa no cambió/)).toBeInTheDocument()
  })

  it('shows the unavailable-source state when the stored object is gone', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue({
      ok: false,
      status: 409,
      error: 'El archivo cargado ya no está disponible. Vuelva a cargarlo.',
    })

    renderPage()
    await selectAndSubmit()

    await waitFor(() => expect(screen.getByText('Archivo no disponible')).toBeInTheDocument())
  })

  it('reports a duplicate upload that is not yet active and still offers to publish it', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(validated({ status: 'already_imported' }))

    renderPage()
    await selectAndSubmit()

    await waitFor(() =>
      expect(screen.getByText('Esta planilla ya había sido importada')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('publish-open')).toBeEnabled()
  })

  it('reports a duplicate upload that is already current and offers no action', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(
      validated({ status: 'already_current', is_active: true }),
    )

    renderPage()
    await selectAndSubmit()

    await waitFor(() =>
      expect(screen.getByText('Esta planilla ya es la versión vigente')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('publish-open')).toBeDisabled()
  })

  it('surfaces an upload rejection without ever reaching the validation step', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue({
      ok: false,
      status: 413,
      error: 'Request Entity Too Large',
    })

    renderPage()
    await selectAndSubmit()

    await waitFor(() => expect(screen.getByText('Archivo demasiado grande')).toBeInTheDocument())
    expect(validateAndProject).not.toHaveBeenCalled()
  })

  it('surfaces a failed publish without claiming the version changed', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(validated())
    vi.mocked(publishImport).mockResolvedValue({
      ok: false,
      status: 500,
      error: 'No se pudo publicar la versión. La versión activa no cambió.',
    })

    const onChanged = renderPage()
    await selectAndSubmit()
    await waitFor(() => expect(screen.getByTestId('publish-open')).toBeInTheDocument())
    await userEvent.click(screen.getByTestId('publish-open'))
    await userEvent.click(screen.getByTestId('confirm-accept'))

    await waitFor(() => expect(screen.getByTestId('import-failure')).toBeInTheDocument())
    expect(screen.queryByTestId('publish-result')).not.toBeInTheDocument()
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('surfaces the inspection contract observation as evidence, not as a rejection', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue({
      ...uploadOk,
      data: {
        ...uploadOk.data,
        validation_evidence: {
          sheet_names: ['Resumen'],
          resumen_row_count: 7,
          contract_error: 'Resumen schema mismatch at column 3',
        },
      },
    })
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(validated())

    renderPage()
    await selectAndSubmit()

    await waitFor(() =>
      expect(screen.getByText('Observación de la inspección inicial')).toBeInTheDocument(),
    )
    // The technical detail stays in the audit log, never on screen.
    expect(screen.queryByText(/schema mismatch/)).not.toBeInTheDocument()
  })

  it('shows what was matched and requires acknowledging warnings before publishing', async () => {
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue(
      validated({ warning_count: 1, mapping_report: reviewReport() }),
    )

    renderPage()
    await selectAndSubmit()
    await waitFor(() => expect(screen.getByTestId('layout-review')).toBeInTheDocument())

    expect(screen.getByTestId('layout-warnings')).toHaveTextContent(
      'Fila 315: «Fecha corta» es anterior a «Fecha solicitud».',
    )
    expect(screen.getByTestId('layout-warnings')).toHaveTextContent('Columnas C, D · Fila 315')
    expect(screen.getByTestId('layout-mapped')).toHaveTextContent('carpeta_normalizada')
    expect(screen.getByTestId('layout-ignored')).toHaveTextContent('AK–BB')

    expect(screen.getByTestId('publish-open')).toBeDisabled()
    await userEvent.click(screen.getByTestId('warnings-ack'))
    expect(screen.getByTestId('publish-open')).toBeEnabled()
    await userEvent.click(screen.getByTestId('publish-open'))
    expect(screen.getByRole('dialog')).toHaveTextContent('1 advertencia revisada')
    expect(publishImport).not.toHaveBeenCalled()

    vi.mocked(publishImport).mockResolvedValue({
      ok: false,
      status: 500,
      error: 'x',
    })
    await userEvent.click(screen.getByRole('button', { name: 'Publicar la importación #83' }))
    expect(publishImport).toHaveBeenCalledWith(83, { acknowledgeWarnings: true })
  })

  it('shows every blocking issue with its references when the workbook is refused', async () => {
    const refused = reviewReport({
      business_rows: 0,
      issues: [
        {
          code: 'carpeta_ambigua',
          severity: 'error',
          message: 'La columna L se llama «Carpeta», pero su posición no permite distinguir…',
          field: null,
          columns: ['L'],
          rows: [],
          row_count: 0,
        },
        {
          code: 'encabezado_duplicado_conflictivo',
          severity: 'error',
          message: 'El campo «Estado» aparece en varias columnas con valores distintos.',
          field: 'estado',
          columns: ['M', 'AJ'],
          rows: [3, 4],
          row_count: 60,
        },
      ],
    })
    vi.mocked(uploadWorkbook).mockResolvedValue(uploadOk)
    vi.mocked(listRecentUploads).mockResolvedValue(runsOk)
    vi.mocked(validateAndProject).mockResolvedValue({
      ok: false,
      status: 422,
      error: 'La planilla necesita revisión antes de importarse.',
      payload: { detail: 'La planilla necesita revisión antes de importarse.', report: refused },
    })

    renderPage()
    await selectAndSubmit()
    await waitFor(() => expect(screen.getByTestId('import-failure')).toBeInTheDocument())

    const errors = screen.getByTestId('layout-errors')
    expect(errors).toHaveTextContent('Columna L')
    expect(errors).toHaveTextContent('Columnas M, AJ · Filas 3, 4 y 58 más')
    expect(screen.queryByTestId('publish-open')).not.toBeInTheDocument()
  })
})

function reviewReport(overrides: Partial<LayoutReport> = {}): LayoutReport {
  return {
    parser_version: 'transelec_ingestion.resumen_layout@2',
    sheet_name: 'Resumen',
    header_row: 1,
    business_rows: 7,
    columns: [
      { column: 'A', header: 'AEF', status: 'mapped', field: 'aef', note: null },
      {
        column: 'AH',
        header: 'Carpeta',
        status: 'mapped',
        field: 'carpeta_normalizada',
        note: '«Carpeta» junto a «Tramite»/«Sector»: carpeta normalizada.',
      },
      { column: 'AJ', header: null, status: 'separator', field: null, note: 'Columna vacía.' },
    ],
    fields: [
      { field: 'aef', header: 'AEF', tier: 'optional', column: 'A', filled_rows: 2 },
      {
        field: 'carpeta_normalizada',
        header: 'Carpeta',
        tier: 'expected',
        column: 'AH',
        filled_rows: 7,
      },
    ],
    auxiliary_regions: [
      { first_column: 'AK', last_column: 'BB', column_count: 18, reason: 'Región auxiliar.' },
    ],
    issues: [
      {
        code: 'cronologia_corta_antes_de_solicitud',
        severity: 'warning',
        message:
          'Fila 315: «Fecha corta» es anterior a «Fecha solicitud». Se conservan las fechas tal como vienen; revise la planilla.',
        field: 'fecha_corta',
        columns: ['C', 'D'],
        rows: [315],
        row_count: 1,
      },
    ],
    counts: { error: 0, warning: 1, info: 0 },
    ...overrides,
  }
}
