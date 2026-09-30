/**
 * «Cargar versión»: one shapefile ZIP in, one version pending review out.
 *
 * Uploading never changes the map. The server validates the archive and the
 * layer, keeps the original ZIP, and answers with the new version's number;
 * the next step is its review page, where «Publicar» lives.
 */
import { useRef, useState } from 'react'
import { canUpload, mutationMessage, uploadShapefileZip } from '../api.ts'
import { Notice, PageShell } from '../components/PageShell.tsx'
import { formatBytes } from '../lib/versions.ts'
import { ROUTES, navigate, reviewPath } from '../router.ts'
import type { ForestryRole } from '../types.ts'

const MAX_BYTES = 50 * 1024 * 1024

export function ImportarPage({ role }: { role: ForestryRole | null }) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const choose = (chosen: File | undefined) => {
    setError(null)
    if (chosen === undefined) return
    if (!chosen.name.toLowerCase().endsWith('.zip')) {
      setFile(null)
      setError('Elija un archivo .zip con la capa completa.')
      return
    }
    if (chosen.size > MAX_BYTES) {
      setFile(null)
      setError('El archivo supera el máximo de 50 MiB.')
      return
    }
    setFile(chosen)
  }

  const submit = async () => {
    if (file === null) return
    setBusy(true)
    setError(null)
    try {
      const result = await uploadShapefileZip(file)
      navigate(`${reviewPath(result.shapefile_snapshot_id)}&cargada=${result.status}`)
    } catch (caught) {
      setError(mutationMessage(caught, 'No se pudo cargar el archivo. La versión publicada no cambió.'))
      setBusy(false)
    }
  }

  if (!canUpload(role)) {
    return (
      <PageShell active={ROUTES.importar} role={role}>
        <Notice tone="info" title="Su cuenta sólo puede ver Rodales">
          Para cargar una versión se necesita un acceso de operador o administrador de Rodales.
        </Notice>
      </PageShell>
    )
  }

  return (
    <PageShell active={ROUTES.importar} role={role}>
      <h2 className="page__title">Cargar una nueva versión</h2>
      <p className="page__lead">
        Cargue la capa de rodales como un archivo <code>.zip</code> con sus archivos{' '}
        <code>.shp</code>, <code>.shx</code>, <code>.dbf</code>, <code>.prj</code> y{' '}
        <code>.cpg</code>. La versión queda <b>pendiente de revisión</b>: el mapa que ven los demás
        usuarios no cambia hasta que usted la revise y seleccione «Publicar».
      </p>

      <div
        className={`dropzone${dragging ? ' dropzone--active' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          choose(event.dataTransfer.files?.[0])
        }}
      >
        <p className="dropzone__text">Arrastre el archivo .zip aquí, o elíjalo desde su equipo.</p>
        <input
          ref={inputRef}
          id="rodales-zip"
          className="dropzone__input"
          type="file"
          accept=".zip,application/zip"
          onChange={(event) => choose(event.target.files?.[0])}
        />
        <label className="button button--ghost" htmlFor="rodales-zip">
          Elegir archivo
        </label>
        {file !== null ? (
          <p className="dropzone__file">
            <b>{file.name}</b> · {formatBytes(file.size)}
          </p>
        ) : (
          <p className="dropzone__hint">Tamaño máximo: 50 MiB.</p>
        )}
      </div>

      {error !== null ? (
        <Notice tone="error" title="No se cargó la versión">
          <p>{error}</p>
          <p>La versión publicada no cambió.</p>
        </Notice>
      ) : null}

      <div className="page__actions">
        <button
          type="button"
          className="button"
          disabled={file === null || busy}
          onClick={() => void submit()}
        >
          {busy ? 'Validando la capa…' : 'Cargar para revisión'}
        </button>
        {busy ? (
          <span className="page__busy" role="status">
            Se revisan el ZIP, el sistema de coordenadas y cada polígono. Puede tardar unos
            segundos.
          </span>
        ) : null}
      </div>
    </PageShell>
  )
}
