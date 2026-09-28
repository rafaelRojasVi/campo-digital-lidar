import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReportPanel } from './ReportPanel'
import { makeReport } from '../test/factories'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('ReportPanel (TR-FUNC-034/035/036)', () => {
  it('renders the server-generated report text verbatim, preserving its line breaks', () => {
    const report = makeReport()
    render(<ReportPanel report={report} />)

    const node = screen.getByTestId('report-text')
    expect(node.textContent).toBe(report.text)
    expect(node.tagName).toBe('PRE')
  })

  it('never renders the report as HTML', () => {
    render(
      <ReportPanel report={makeReport({ text: 'Corte <b>de</b> información\n<script>x()</script>' })} />,
    )
    const node = screen.getByTestId('report-text')
    expect(node.querySelector('b')).toBeNull()
    expect(node.querySelector('script')).toBeNull()
    expect(node.textContent).toContain('<b>de</b>')
  })

  it('copies the report text to the clipboard and confirms it', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })

    const report = makeReport()
    render(<ReportPanel report={report} />)
    await userEvent.click(screen.getByTestId('copy-report'))

    expect(writeText).toHaveBeenCalledWith(report.text)
    await waitFor(() =>
      expect(screen.getByText('Reporte copiado al portapapeles.')).toBeInTheDocument(),
    )
  })

  it('tells the reader what to do when the browser refuses clipboard access', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })

    render(<ReportPanel report={makeReport()} />)
    await userEvent.click(screen.getByTestId('copy-report'))

    await waitFor(() =>
      expect(screen.getByText(/cópielo manualmente/)).toBeInTheDocument(),
    )
  })

  it('downloads the report as a text/plain attachment with a fixed filename', async () => {
    const createObjectURL = vi.fn().mockReturnValue('blob:report')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    render(<ReportPanel report={makeReport()} />)
    await userEvent.click(screen.getByTestId('download-report'))

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect((createObjectURL.mock.calls[0][0] as Blob).type).toBe('text/plain;charset=utf-8')
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:report')
  })

  it('states that the cut-off date comes from the active version, and names both rules', () => {
    render(<ReportPanel report={makeReport()} />)
    expect(screen.getByText(/Corte de información tomado de la versión activa/)).toBeInTheDocument()
    expect(screen.getByText('estado_resumido_first_row')).toBeInTheDocument()
    expect(screen.getByText('pending_priority_legacy')).toBeInTheDocument()
  })
})
