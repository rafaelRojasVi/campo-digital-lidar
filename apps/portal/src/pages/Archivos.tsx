import { useEffect, useRef, useState } from 'react'
import { Link } from '../router/Router'
import { getCampoEnvironment } from '../runtime/environment'
import {
  DEV_IDENTITIES,
  devLogin,
  getAuditLog,
  getMe,
  listJobs,
  logout as apiLogout,
  retryJob,
  uploadFile,
  type AuditEventView,
  type JobView,
  type Me,
  type ProductKey,
  type Role,
} from '../lib/platformApi'

const PRODUCT_LABELS: Record<ProductKey, string> = {
  lidar: 'LiDAR / Cubicación',
  forestry: 'Gestión Predial Forestal',
  transelect: 'Transelec',
}

const PRODUCT_KEYS = Object.keys(PRODUCT_LABELS) as ProductKey[]

function roleFor(me: Me, productKey: string): Role | null {
  return me.product_grants.find((grant) => grant.product_key === productKey)?.role ?? null
}

function canUpload(role: Role | null): boolean {
  return role === 'admin' || role === 'operator'
}

function canRetry(role: Role | null): boolean {
  return role === 'admin' || role === 'operator'
}

export function Archivos() {
  const [me, setMe] = useState<Me | null>(null)
  const [loadingMe, setLoadingMe] = useState(true)
  const [selectedProduct, setSelectedProduct] = useState<ProductKey>('forestry')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  const [jobs, setJobs] = useState<JobView[]>([])
  const [auditEvents, setAuditEvents] = useState<AuditEventView[]>([])
  const pollHandle = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    getMe().then((result) => {
      if (!cancelled) {
        setMe(result.ok ? result.data : null)
        setLoadingMe(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!me) {
      return
    }

    const refreshJobs = () => {
      listJobs().then((result) => {
        if (result.ok) {
          setJobs(result.data)
        }
      })
    }

    refreshJobs()
    pollHandle.current = window.setInterval(refreshJobs, 2000)
    return () => {
      if (pollHandle.current !== null) {
        window.clearInterval(pollHandle.current)
      }
    }
  }, [me])

  const isAdmin = me?.product_grants.some((grant) => grant.role === 'admin') ?? false

  useEffect(() => {
    if (!me || !isAdmin) {
      return
    }
    getAuditLog().then((result) => {
      if (result.ok) {
        setAuditEvents(result.data)
      }
    })
  }, [me, isAdmin, jobs])

  const visibleAuditEvents = isAdmin ? auditEvents : []

  async function handleLogin(identityKey: string) {
    const result = await devLogin(identityKey)
    if (result.ok) {
      setMe(result.data)
    }
  }

  async function handleLogout() {
    await apiLogout()
    setMe(null)
    setJobs([])
    setAuditEvents([])
    setSelectedFile(null)
    setUploadMessage(null)
    setSelectedProduct('forestry')
  }

  async function handleUpload() {
    if (!selectedFile) {
      return
    }
    setUploadMessage('Subiendo…')
    const result = await uploadFile(selectedProduct, selectedFile)
    if (result.ok) {
      setUploadMessage(
        `Recibido: SHA-256 ${result.data.sha256.slice(0, 12)}… ` +
          `(${result.data.byte_size} bytes). Job #${result.data.job_id} en cola.`,
      )
    } else {
      setUploadMessage(`Error: ${result.error}`)
    }
  }

  async function handleRetry(jobId: number) {
    await retryJob(jobId)
  }

  if (loadingMe) {
    return <p>Cargando…</p>
  }

  if (!me) {
    const environment = getCampoEnvironment()
    return (
      <div className="ingesta">
        <p>
          <Link to="/">← Campo Digital</Link>
        </p>
        <h1>Archivos</h1>
        {environment === 'staging' ? (
          <p className="ingesta__note">
            El inicio de sesión de plataforma aún no está disponible en este entorno (queda
            pendiente la integración con Entra ID).
          </p>
        ) : (
          <>
            <p className="ingesta__note">
              Autenticación local de desarrollo — no representa un mecanismo de producción.
            </p>
            <div className="ingesta__login" role="group" aria-label="Elegir identidad local">
              {DEV_IDENTITIES.map((identityKey) => (
                <button key={identityKey} type="button" onClick={() => handleLogin(identityKey)}>
                  {identityKey}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    )
  }

  const uploadRole = roleFor(me, selectedProduct)

  return (
    <div className="ingesta">
      <p>
        <Link to="/">← Campo Digital</Link>
      </p>
      <h1>Archivos</h1>
      <p className="ingesta__note">
        Autenticación local de desarrollo — no representa un mecanismo de producción.
      </p>

      <div className="ingesta__session">
        <span>
          {me.display_name} ({me.identity_key})
        </span>
        <button type="button" onClick={handleLogout}>
          Salir
        </button>
      </div>

      <section>
        <h2>Subir archivo</h2>
        <label>
          Producto{' '}
          <select
            value={selectedProduct}
            onChange={(event) => setSelectedProduct(event.target.value as ProductKey)}
          >
            {PRODUCT_KEYS.map((key) => (
              <option key={key} value={key}>
                {PRODUCT_LABELS[key]} ({roleFor(me, key) ?? 'sin acceso'})
              </option>
            ))}
          </select>
        </label>
        <input
          type="file"
          aria-label="Archivo a subir"
          onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
          disabled={!canUpload(uploadRole)}
        />
        <button
          type="button"
          onClick={handleUpload}
          disabled={!canUpload(uploadRole) || !selectedFile}
        >
          Subir
        </button>
        {!canUpload(uploadRole) && (
          <p className="ingesta__denied">Tu rol no permite subir archivos para este producto.</p>
        )}
        {uploadMessage && <p className="ingesta__upload-message">{uploadMessage}</p>}
      </section>

      <section>
        <h2>Trabajos</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Producto</th>
              <th>Estado</th>
              <th>Intentos</th>
              <th>Creado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => {
              const jobRole = roleFor(me, job.product_key)
              return (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{job.product_key}</td>
                  <td>{job.status}</td>
                  <td>{job.attempt_count}</td>
                  <td>{job.created_at}</td>
                  <td>
                    {job.status === 'failed' && canRetry(jobRole) && (
                      <button type="button" onClick={() => handleRetry(job.id)}>
                        Reintentar
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      {isAdmin && (
        <section>
          <h2>Auditoría</h2>
          <table>
            <thead>
              <tr>
                <th>Cuándo</th>
                <th>Evento</th>
                <th>Producto</th>
                <th>Sujeto</th>
              </tr>
            </thead>
            <tbody>
              {visibleAuditEvents.map((event) => (
                <tr key={event.id}>
                  <td>{event.occurred_at}</td>
                  <td>{event.event_type}</td>
                  <td>{event.product_key ?? '—'}</td>
                  <td>{event.subject_kind ? `${event.subject_kind}#${event.subject_id}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}
