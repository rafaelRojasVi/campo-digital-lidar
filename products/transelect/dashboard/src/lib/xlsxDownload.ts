/**
 * «Descargar planilla con ediciones (.xlsx)», shared by Ediciones web and the
 * header log's footer. The file is fetched first, so a failure can be shown
 * instead of a dead download.
 */
import { useCallback, useState } from 'react'
import { downloadOverridesXlsx } from '../api'
import { classifyFailure } from './apiState'

export const DOWNLOAD_LABEL = 'Descargar planilla con ediciones (.xlsx)'
export const DOWNLOAD_BUSY = 'Preparando la planilla…'
const DOWNLOAD_SERVER_ERROR =
  'La plataforma no pudo preparar la planilla. Intente de nuevo; si se repite, contacte a soporte.'

/** 403 and a bare 5xx get fixed Spanish copy; 404/409/422 keep the server's own detail. */
function downloadErrorCopy(result: { status: number; error: string; payload?: unknown }): string {
  if (result.status === 403) return classifyFailure(result).message
  if (result.status >= 500 && result.payload === undefined) return DOWNLOAD_SERVER_ERROR
  return result.error
}

export function useXlsxDownload() {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const download = useCallback(async () => {
    // Callers use aria-disabled, not disabled, so the button keeps focus while busy.
    if (downloading) return
    setDownloading(true)
    setError(null)
    const result = await downloadOverridesXlsx()
    setDownloading(false)
    if (!result.ok) {
      setError(downloadErrorCopy(result))
      return
    }
    const url = URL.createObjectURL(result.data.blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = result.data.filename
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    // Safari can abort the save if the URL is revoked in the same tick.
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }, [downloading])

  return { downloading, error, download }
}
