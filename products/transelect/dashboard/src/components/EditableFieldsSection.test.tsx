import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TranselecOverride } from '../api'
import { EditableFieldsSection } from './EditableFieldsSection'
import { WebEditsContext } from '../lib/webEditsState'
import { makeRow } from '../test/factories'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, saveOverride: vi.fn(), discardOverride: vi.fn() }
})

const { saveOverride, discardOverride } = await import('../api')

const base = {
  activeImportId: 7,
  sourceFields: null,
  overrides: [],
  suggestions: { estado_resumido: ['Aprobado', 'En tramite'] },
  onReload: vi.fn(),
}

const applied: TranselecOverride = {
  id: 31,
  field: 'estado',
  field_label: 'Estado vigente',
  status: 'aplicada',
  pmf: 'MP001',
  rol: '101',
  numero_predio: '1',
  numero_area_corta: 'A1',
  source_row_number: 2,
  web_value: 'Aprobado',
  planilla_value_at_edit: 'En tramite',
  created_by_display_name: 'Ana Operadora',
  created_at: '2026-10-03T15:00:00Z',
} as unknown as TranselecOverride

describe('EditableFieldsSection', () => {
  beforeEach(() => {
    vi.mocked(saveOverride).mockReset()
    vi.mocked(discardOverride).mockReset()
    base.onReload.mockReset()
  })

  it('saves a new value with the value the editor saw', async () => {
    const onSaved = vi.fn()
    const row = makeRow({ source_row_number: 2, estado_resumido: 'En tramite' })
    vi.mocked(saveOverride).mockResolvedValue({
      ok: true,
      data: {
        override_id: 31,
        changed: true,
        row: { ...row, estado_resumido: 'Aprobado', web_fields: ['estado_resumido'] },
      },
    })
    render(<EditableFieldsSection {...base} row={row} canEdit onSaved={onSaved} />)

    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado resumido' }))
    const input = screen.getByLabelText('Nuevo valor de Estado resumido')
    await userEvent.clear(input)
    await userEvent.type(input, 'Aprobado')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))

    expect(saveOverride).toHaveBeenCalledWith({
      importId: 7,
      sourceRowNumber: 2,
      field: 'estado_resumido',
      value: 'Aprobado',
      expectedValue: 'En tramite',
    })
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ estado_resumido: 'Aprobado' }))
    expect(await screen.findByTestId('editables-status')).toHaveTextContent('Se guardó')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Editar Estado resumido' })).toHaveFocus(),
    )
  })

  it('explains a concurrent change and offers a reload', async () => {
    vi.mocked(saveOverride).mockResolvedValue({
      ok: false,
      status: 409,
      error: 'x',
      payload: { detail: 'x', code: 'value_changed' },
    })
    render(<EditableFieldsSection {...base} row={makeRow()} canEdit onSaved={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Otra persona cambió este valor')
    expect(screen.getByRole('button', { name: 'Recargar' })).toBeInTheDocument()
  })

  it('shows chips but no edit controls to a viewer', () => {
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow({ web_fields: ['estado'] })}
        canEdit={false}
        onSaved={vi.fn()}
      />,
    )
    expect(screen.getAllByTestId('web-chip')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument()
  })

  it('hides Editar for a field the published planilla has no column for', () => {
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow()}
        canEdit
        sourceFields={['estado', 'estado_resumido']}
        onSaved={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Editar Estado vigente' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Editar N.º ingreso 2' })).not.toBeInTheDocument()
  })

  it('uses a date input for date fields and a datalist for suggestible ones', async () => {
    render(<EditableFieldsSection {...base} row={makeRow()} canEdit onSaved={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Editar Fecha ingreso' }))
    expect(screen.getByLabelText('Nuevo valor de Fecha ingreso')).toHaveAttribute('type', 'date')
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado resumido' }))
    const input = screen.getByLabelText('Nuevo valor de Estado resumido')
    expect(input).toHaveAttribute('list', 'suggest-estado_resumido')
    expect(document.querySelectorAll('#suggest-estado_resumido option')).toHaveLength(2)
  })

  it('shows who edited a value as visible text, not only a tooltip', () => {
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow({ source_row_number: 2, web_fields: ['estado'] })}
        overrides={[applied]}
        overridesStatus="ready"
        canEdit={false}
        onSaved={vi.fn()}
      />,
    )
    expect(screen.getByTestId('editable-estado')).toHaveTextContent(
      'Editado en la web por Ana Operadora · 03-10-2026 · en la planilla: En tramite',
    )
  })

  it('says when the provenance is loading or failed', () => {
    const row = makeRow({ web_fields: ['estado'] })
    const { rerender } = render(
      <EditableFieldsSection {...base} row={row} overridesStatus="loading" canEdit={false} onSaved={vi.fn()} />,
    )
    expect(screen.getByText(/Cargando quién editó/)).toBeInTheDocument()
    rerender(
      <EditableFieldsSection {...base} row={row} overridesStatus="error" canEdit={false} onSaved={vi.fn()} />,
    )
    expect(screen.getByText(/No se pudo cargar quién editó/)).toBeInTheDocument()
  })

  it('Escape cancels the editor without reaching the drawer', async () => {
    const outside = vi.fn()
    document.addEventListener('keydown', outside)
    render(<EditableFieldsSection {...base} row={makeRow()} canEdit onSaved={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByLabelText('Nuevo valor de Estado vigente')).not.toBeInTheDocument()
    expect(outside).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Editar Estado vigente' })).toHaveFocus(),
    )
    document.removeEventListener('keydown', outside)
  })

  it('asks before going back to the planilla value', async () => {
    vi.mocked(discardOverride).mockResolvedValue({ ok: true, data: undefined })
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow({ source_row_number: 2, web_fields: ['estado'] })}
        overrides={[applied]}
        overridesStatus="ready"
        canEdit
        onSaved={vi.fn()}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Volver al valor de la planilla de Estado vigente' }))
    expect(discardOverride).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toHaveTextContent('En tramite')
    await userEvent.click(screen.getByTestId('confirm-accept'))
    expect(discardOverride).toHaveBeenCalledWith(31)
    await waitFor(() => expect(base.onReload).toHaveBeenCalled())
  })

  it('shows unparsed date text and still sends null as the value it saw', async () => {
    const row = makeRow({
      source_row_number: 2,
      fecha_ingreso: null,
      source_text_dates: {
        fecha_ingreso: { raw: 'por confirmar', resolution: 'unrecognized', parsed: null },
      },
    })
    vi.mocked(saveOverride).mockResolvedValue({
      ok: true,
      data: { override_id: 5, changed: true, row: { ...row, fecha_ingreso: '2026-05-06' } },
    })
    render(<EditableFieldsSection {...base} row={row} canEdit onSaved={vi.fn()} />)
    expect(screen.getByTestId('editable-fecha_ingreso')).toHaveTextContent('por confirmar')
    await userEvent.click(screen.getByRole('button', { name: 'Editar Fecha ingreso' }))
    expect(screen.getByTestId('text-date-fecha_ingreso')).toHaveTextContent(
      'La planilla tiene texto: «por confirmar»',
    )
    expect(screen.getByLabelText('Nuevo valor de Fecha ingreso')).toHaveAccessibleDescription(
      /La planilla tiene texto/,
    )
    await userEvent.type(screen.getByLabelText('Nuevo valor de Fecha ingreso'), '2026-05-06')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(saveOverride).toHaveBeenCalledWith(
      expect.objectContaining({ field: 'fecha_ingreso', value: '2026-05-06', expectedValue: null }),
    )
  })

  it('checks the save against the value the editor opened with, even if the row changes', async () => {
    vi.mocked(saveOverride).mockResolvedValue({ ok: false, status: 409, error: 'x', payload: { detail: 'x', code: 'value_changed' } })
    const first = makeRow({ source_row_number: 2, estado: 'En tramite' })
    const { rerender } = render(
      <EditableFieldsSection {...base} row={first} canEdit onSaved={vi.fn()} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
    rerender(
      <EditableFieldsSection
        {...base}
        row={{ ...first, estado: 'Aprobado por otra persona' }}
        canEdit
        onSaved={vi.fn()}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(saveOverride).toHaveBeenCalledWith(
      expect.objectContaining({ field: 'estado', expectedValue: 'En tramite' }),
    )
  })

  it('says when a field was left empty', async () => {
    const row = makeRow({ source_row_number: 2, estado: 'En tramite' })
    vi.mocked(saveOverride).mockResolvedValue({
      ok: true,
      data: { override_id: 5, changed: true, row: { ...row, estado: null } },
    })
    render(<EditableFieldsSection {...base} row={row} canEdit onSaved={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
    await userEvent.clear(screen.getByLabelText('Nuevo valor de Estado vigente'))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByTestId('editables-status')).toHaveTextContent('Estado vigente se dejó vacío.')
  })

  it('tells the page to refresh the row after a revert and after Recargar', async () => {
    vi.mocked(discardOverride).mockResolvedValue({ ok: true, data: undefined })
    const onRowEdited = vi.fn()
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow({ source_row_number: 2, web_fields: ['estado'] })}
        overrides={[applied]}
        overridesStatus="ready"
        canEdit
        onSaved={vi.fn()}
        onRowEdited={onRowEdited}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Volver al valor de la planilla de Estado vigente' }))
    await userEvent.click(screen.getByTestId('confirm-accept'))
    await waitFor(() => expect(onRowEdited).toHaveBeenCalledTimes(1))
  })

  describe('Recargar after a conflict', () => {
    const conflict = (code: string) =>
      vi.mocked(saveOverride).mockResolvedValue({
        ok: false,
        status: 409,
        error: 'x',
        payload: { detail: 'x', code },
      })

    it('shows the alert beside the edited field, then closes the editor and re-captures the value', async () => {
      conflict('value_changed')
      const onRowEdited = vi.fn()
      const props = { ...base, canEdit: true, onSaved: vi.fn(), onRowEdited }
      const { rerender } = render(
        <EditableFieldsSection {...props} row={makeRow({ source_row_number: 2, estado: 'En tramite' })} />,
      )
      await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
      await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))

      const alert = await screen.findByRole('alert')
      expect(screen.getByTestId('editable-estado')).toContainElement(alert)

      await userEvent.click(screen.getByRole('button', { name: 'Recargar' }))
      expect(base.onReload).toHaveBeenCalledTimes(1)
      expect(onRowEdited).toHaveBeenCalledTimes(1)
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Nuevo valor de Estado vigente')).not.toBeInTheDocument()

      // The drawer refetched: the row now carries the other person's value.
      rerender(
        <EditableFieldsSection {...props} row={makeRow({ source_row_number: 2, estado: 'Aprobado' })} />,
      )
      vi.mocked(saveOverride).mockResolvedValue({
        ok: true,
        data: { override_id: 5, changed: true, row: makeRow({ estado: 'Desistido' }) },
      })
      await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
      await userEvent.clear(screen.getByLabelText('Nuevo valor de Estado vigente'))
      await userEvent.type(screen.getByLabelText('Nuevo valor de Estado vigente'), 'Desistido')
      await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
      expect(saveOverride).toHaveBeenLastCalledWith(
        expect.objectContaining({ field: 'estado', expectedValue: 'Aprobado' }),
      )
    })

    it('offers a full page reload when the active version changed', async () => {
      conflict('version_changed')
      const reload = vi.fn()
      const original = window.location
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: { ...original, reload },
      })
      try {
        render(
          <EditableFieldsSection {...base} row={makeRow({ source_row_number: 2 })} canEdit onSaved={vi.fn()} />,
        )
        await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
        await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
        await userEvent.click(await screen.findByRole('button', { name: 'Recargar la página' }))
        expect(reload).toHaveBeenCalledTimes(1)
        expect(base.onReload).not.toHaveBeenCalled()
      } finally {
        Object.defineProperty(window, 'location', { configurable: true, value: original })
      }
    })
  })
})

describe('EditableFieldsSection — the shared edits log', () => {
  const refresh = vi.fn()
  const withLog = (node: React.ReactNode) => (
    <WebEditsContext.Provider value={{ history: null, status: 'ready', refresh, openLog: vi.fn() }}>
      {node}
    </WebEditsContext.Provider>
  )

  beforeEach(() => {
    refresh.mockReset()
    vi.mocked(saveOverride).mockReset()
    vi.mocked(discardOverride).mockReset()
  })

  async function saveEstadoResumido(changed: boolean) {
    const row = makeRow({ source_row_number: 2, estado_resumido: 'En tramite' })
    vi.mocked(saveOverride).mockResolvedValue({
      ok: true,
      data: { override_id: changed ? 31 : null, changed, row },
    })
    render(withLog(<EditableFieldsSection {...base} row={row} canEdit onSaved={vi.fn()} />))
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado resumido' }))
    await userEvent.clear(screen.getByLabelText('Nuevo valor de Estado resumido'))
    await userEvent.type(screen.getByLabelText('Nuevo valor de Estado resumido'), 'Aprobado')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText(/Se guardó|no hubo cambios/)
  }

  it('refreshes the log after a save that changed something', async () => {
    await saveEstadoResumido(true)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('does not refresh it after a save that changed nothing', async () => {
    await saveEstadoResumido(false)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('refreshes the log after a revert', async () => {
    vi.mocked(discardOverride).mockResolvedValue({ ok: true, data: undefined })
    render(
      withLog(
        <EditableFieldsSection
          {...base}
          row={makeRow({ source_row_number: 2, web_fields: ['estado'] })}
          overrides={[applied]}
          canEdit
          onSaved={vi.fn()}
        />,
      ),
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Volver al valor de la planilla de Estado vigente' }),
    )
    await userEvent.click(screen.getByTestId('confirm-accept'))
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1))
  })
})

describe('EditableFieldsSection — unsaved changes', () => {
  it('reports an open editor holding a change, a save in flight, and neither', async () => {
    let finish!: (value: unknown) => void
    vi.mocked(saveOverride).mockReturnValue(
      new Promise((done) => {
        finish = done
      }) as never,
    )
    const onEditStateChange = vi.fn()
    const row = makeRow({ estado: 'En evaluacion' })
    render(
      <EditableFieldsSection
        {...base}
        row={row}
        canEdit
        onSaved={vi.fn()}
        onEditStateChange={onEditStateChange}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
    expect(onEditStateChange).toHaveBeenLastCalledWith('idle')
    await userEvent.type(screen.getByLabelText('Nuevo valor de Estado vigente'), ' x')
    expect(onEditStateChange).toHaveBeenLastCalledWith('unsaved')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(onEditStateChange).toHaveBeenLastCalledWith('saving')
    await act(async () =>
      finish({ ok: true, data: { override_id: 1, changed: true, row } }),
    )
    expect(onEditStateChange).toHaveBeenLastCalledWith('idle')
  })

  it('reports an unsaved change as gone after Cancelar', async () => {
    const onEditStateChange = vi.fn()
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow({ estado: 'En evaluacion' })}
        canEdit
        onSaved={vi.fn()}
        onEditStateChange={onEditStateChange}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Editar Estado vigente' }))
    await userEvent.type(screen.getByLabelText('Nuevo valor de Estado vigente'), ' x')
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(onEditStateChange).toHaveBeenLastCalledWith('idle')
  })
})

describe('EditableFieldsSection — a field the planilla has no column for', () => {
  it('says the column is missing instead of «Sin dato»', () => {
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow({ numero_ingreso_2: null, fecha_ingreso_2: null })}
        canEdit
        sourceFields={['estado', 'estado_resumido', 'tipo_rechazo', 'numero_ingreso', 'fecha_ingreso']}
        onSaved={vi.fn()}
      />,
    )
    for (const field of ['numero_ingreso_2', 'fecha_ingreso_2']) {
      const row = screen.getByTestId(`editable-${field}`)
      expect(row).toHaveTextContent('La planilla publicada no tiene esta columna.')
      expect(row).not.toHaveTextContent('Sin dato')
    }
    // A field the planilla has, but empty, still reads «Sin dato».
    expect(screen.getByTestId('editable-tipo_rechazo')).toHaveTextContent('Sin dato')
  })

  it('still shows a web value for it, with its chip', () => {
    render(
      <EditableFieldsSection
        {...base}
        row={makeRow({ numero_ingreso_2: 'ING-9', web_fields: ['numero_ingreso_2'] })}
        canEdit={false}
        sourceFields={['estado']}
        onSaved={vi.fn()}
      />,
    )
    const row = screen.getByTestId('editable-numero_ingreso_2')
    expect(row).toHaveTextContent('ING-9')
    expect(row).not.toHaveTextContent('no tiene esta columna')
  })
})
